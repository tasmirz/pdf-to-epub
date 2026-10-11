# Web Novel Crawler & Sanitizer Reference Guide

This reference documents the deterministic crawling algorithms, boundary controls, site recipe schemas, and DevTools console extraction scripts used by `novel_crawler.py`.

---

## 1. Algorithmic Content Discovery (No-LLM)

Instead of relying on LLM tokens to locate chapter content, `novel_crawler.py` uses heuristic DOM text-to-link density scoring:

$$\text{Score}(E) = \frac{50 \cdot N_{\text{paragraphs}} + 0.5 \cdot \text{len}(\text{text})}{1 + 3 \cdot \text{len}(\text{link\_text})} \cdot C_{\text{hint}}$$

### Class / ID Weight Modifiers ($C_{\text{hint}}$)
- **Positive Hints ($\times 1.5$)**: `content`, `chapter`, `read`, `body`, `entry`, `text`, `article`
- **Negative Hints ($\times 0.1$)**: `comment`, `sidebar`, `nav`, `footer`, `widget`, `recommend`, `menu`, `related`

Nodes whose link text exceeds $40\%$ of their total text length are penalized to $0.0$ (eliminating navigation grids and link directories).

---

## 2. Site Recipe Schema (`site_recipes/<domain>.json`)

Site recipes store reusable boundaries and selectors for a specific web novel domain. When an agent probes a site, the recipe is saved and automatically applied across all novels from that domain.

```json
{
  "domain": "novelpub.com",
  "content_selector": "#chr-content",
  "title_selector": ".chr-title, h1",
  "next_selector": "#next_chap, a.btn-next",
  "toc_selector": ".chapter-list a",
  "ad_selectors": [
    ".ad",
    ".ads",
    ".advert",
    ".ad-box",
    ".ad-wrapper",
    ".banner-ad",
    ".adsbygoogle",
    "ins.adsbygoogle",
    ".sponsor",
    ".comments",
    "iframe",
    "script",
    "style"
  ],
  "watermark_patterns": [
    "(?i)(visit|read at|novel updated on|translated by|patreon)\\s+.*",
    "(?i)^\\s*find authorized novels in webnovel.*$",
    "(?i)^\\s*if you discover any errors.*report.*$"
  ],
  "url_whitelist_regex": "^https://novelpub\\.com/novel/.*",
  "delay": 1.2,
  "headers": {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9"
  }
}
```

---

## 3. Multi-Tier Sanitization Engine

Before any chapter HTML is saved into the clean cache, it passes through four sanitization filters:

1. **Structural CSS Selector Purge**:
   Elements matching `ad_selectors` are recursively removed via `.decompose()`.
2. **Hidden Anti-Scraper Tag Removal**:
   Tags with `display:none`, `visibility:hidden`, `opacity:0`, or `font-size:0` inline styles, as well as `aria-hidden="true"` decoy spans, are purged.
3. **Regex Watermark Cleanser**:
   Text nodes matching promotional patterns (*"Read latest chapter at..."*, *"Please support the author on Patreon"*) are stripped.
4. **Cross-Chapter Frequency Detection**:
   Identical short paragraphs ($<100$ characters) appearing across $\ge 80\%$ of chapters are flagged as boilerplate headers/footers and discarded.

---

## 4. DevTools Console Exporter Protocol

When automated HTTP requests or headless browsers are blocked by Cloudflare Turnstile or CAPTCHAs, use `novel-console-script`:

```bash
pdf-to-epub novel-console-script https://example.com/novel/ch1
```

### Execution Steps
1. The script dynamically injects `JSZip` from CDN into the user's browser session.
2. It fetches subsequent chapters via authenticated `window.fetch(url, { credentials: 'include' })`.
3. It cleans ad nodes in-browser using `DOMParser`.
4. It compiles `manifest.json` and XHTML files into a ZIP blob and triggers a browser download.
5. The downloaded ZIP can be converted immediately via:
   ```bash
   pdf-to-epub convert <novel>_chapters.zip -o <novel>.epub
   ```
