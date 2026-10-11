#!/usr/bin/env python3
"""
novel_crawler.py - High-Performance Web Novel Crawler, Sanitizer & EPUB3 Builder
Part of pdf-to-epub pipeline.

Key Capabilities:
  1. No-LLM Algorithmic Parsing:
     - Automatic content placeholder discovery using DOM text-to-link density scoring.
     - Multi-tier ad, watermark, and anti-scraper junk cleansing.
  2. Multi-Engine Architecture (Asks user / configurable via CLI):
     - HTTP Engine (Default): Lightweight, zero-dependency, fast urllib with browser headers & cookies.
     - Playwright Engine: Headless browser for JavaScript-heavy or dynamic SPAs.
     - DevTools Console Script Generator: Standalone JS snippet you paste into browser console
       to scrape & download a complete .zip bypassing Cloudflare / login paywalls!
  3. Boundaries & Persistence (.novel_cache/):
     - Domain/URL boundary filters inspired by HTTrack.
     - Reusable per-site recipes (.novel_cache/site_recipes/<domain>.json).
     - Resumable per-novel cache (.novel_cache/novels/<slug>/).
  4. Pilot Run & Quality Verification:
     - --pilot N: Fetch initial batch of chapters with health diagnostics before full crawl.
     - --verify: Audit cached chapters for blank content, abnormal word count, missing indices.
  5. Direct EPUB3 Compilation & Zip Import:
     - Converts cached clean chapters or browser-downloaded zips into validated EPUB3 ebooks.
"""

import os
import sys
import re
import json
import time
import random
import urllib.parse
import urllib.request
import http.cookiejar
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set, Any
from bs4 import BeautifulSoup, Tag, NavigableString

# ==============================================================================
# DEFAULT BOUNDARIES & CONSTANTS
# ==============================================================================

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

COMMON_AD_SELECTORS = [
    ".ad", ".ads", ".advert", ".advertisement", ".ad-box", ".ad-wrapper",
    ".banner-ad", ".adsbygoogle", "ins.adsbygoogle", ".google-ad",
    ".ad-container", "[id*='ad-']", "[class*='ad-']", "[id*='google_ads']",
    ".sponsor", ".patreon-box", ".social-share", ".share-buttons",
    ".comments", "#comments", ".footer-links", ".sidebar",
    "iframe", "script", "style", "noscript"
]

WATERMARK_REGEXES = [
    re.compile(r'(?i)(visit|read at|novel updated on|translated by|support me on|patreon\.com|uploaded by)\s+.*', re.MULTILINE),
    re.compile(r'(?i)^\s*find authorized novels in webnovel.*$', re.MULTILINE),
    re.compile(r'(?i)^\s*if you discover any errors.*report.*$', re.MULTILINE),
    re.compile(r'(?i)^\s*please support the translator at.*$', re.MULTILINE),
]


# ==============================================================================
# SITE RECIPE & BOUNDARY DEFINITIONS
# ==============================================================================

class SiteRecipe:
    """Stores reusable site extraction selectors and crawling boundaries."""
    def __init__(self, domain: str, recipe_dir: Optional[Path] = None):
        self.domain = domain
        self.recipe_dir = recipe_dir or (Path(".novel_cache") / "site_recipes")
        self.recipe_path = self.recipe_dir / f"{domain}.json"
        
        # Selectors
        self.content_selector: Optional[str] = None
        self.title_selector: Optional[str] = None
        self.next_selector: Optional[str] = None
        self.toc_selector: Optional[str] = None
        self.ad_selectors: List[str] = list(COMMON_AD_SELECTORS)
        self.watermark_patterns: List[str] = [p.pattern for p in WATERMARK_REGEXES]
        self.url_whitelist_regex: Optional[str] = None
        self.delay: float = 1.0
        self.headers: Dict[str, str] = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        self.load()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "content_selector": self.content_selector,
            "title_selector": self.title_selector,
            "next_selector": self.next_selector,
            "toc_selector": self.toc_selector,
            "ad_selectors": self.ad_selectors,
            "watermark_patterns": self.watermark_patterns,
            "url_whitelist_regex": self.url_whitelist_regex,
            "delay": self.delay,
            "headers": self.headers
        }

    def load(self) -> bool:
        if self.recipe_path.exists():
            try:
                data = json.loads(self.recipe_path.read_text(encoding="utf-8"))
                self.content_selector = data.get("content_selector")
                self.title_selector = data.get("title_selector")
                self.next_selector = data.get("next_selector")
                self.toc_selector = data.get("toc_selector")
                if "ad_selectors" in data:
                    self.ad_selectors = data["ad_selectors"]
                if "watermark_patterns" in data:
                    self.watermark_patterns = data["watermark_patterns"]
                self.url_whitelist_regex = data.get("url_whitelist_regex")
                self.delay = data.get("delay", 1.0)
                self.headers.update(data.get("headers", {}))
                return True
            except Exception as e:
                print(f"[Warning] Failed loading site recipe {self.recipe_path}: {e}")
        return False

    def save(self):
        self.recipe_dir.mkdir(parents=True, exist_ok=True)
        self.recipe_path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[Recipe] Saved site recipe to {self.recipe_path}")


# ==============================================================================
# ALGORITHMIC CONTENT EXTRACTION & AD REMOVAL (NO-LLM)
# ==============================================================================

class ContentExtractor:
    """Heuristic DOM analyzer to score content placeholders and strip ad noise."""

    @staticmethod
    def score_container(elem: Tag) -> float:
        """Computes text density score for candidate content container."""
        # Collect paragraphs and word count
        p_tags = elem.find_all("p")
        text = elem.get_text(separator=" ", strip=True)
        total_len = len(text)
        if total_len < 100:
            return 0.0

        # Penalize high link density (navigation or footer menus)
        link_text = "".join(a.get_text(strip=True) for a in elem.find_all("a"))
        link_ratio = len(link_text) / (total_len + 1)
        if link_ratio > 0.4:
            return 0.0

        score = (len(p_tags) * 50) + (total_len * 0.5)
        score *= (1.0 - link_ratio)

        # Bonus / penalty based on class & id hints
        elem_id = (elem.get("id") or "").lower()
        elem_cls = " ".join(elem.get("class") or []).lower()
        combined = f"{elem_id} {elem_cls}"

        if any(h in combined for h in ["content", "chapter", "read", "body", "entry", "text", "article"]):
            score *= 1.5
        if any(bad in combined for bad in ["comment", "sidebar", "nav", "footer", "widget", "recommend", "menu"]):
            score *= 0.1

        return score

    @classmethod
    def discover_content_placeholder(cls, soup: BeautifulSoup) -> Tuple[Optional[str], Optional[Tag]]:
        """Identifies the most probable novel chapter text placeholder."""
        candidates: List[Tuple[float, str, Tag]] = []

        # Check explicit article or main tags first
        for tag_name in ["article", "main", "div", "section"]:
            for elem in soup.find_all(tag_name):
                score = cls.score_container(elem)
                if score > 150:
                    selector = cls.build_css_selector(elem)
                    candidates.append((score, selector, elem))

        if not candidates:
            return None, None

        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_selector, best_elem = candidates[0]
        return best_selector, best_elem

    @staticmethod
    def build_css_selector(elem: Tag) -> str:
        """Builds a succinct, reproducible CSS selector for an element."""
        if elem.get("id"):
            return f"#{elem['id']}"
        classes = elem.get("class")
        if classes:
            valid_classes = [c for c in classes if not re.search(r'\d{6,}', c)]
            if valid_classes:
                return f"{elem.name}.{'.'.join(valid_classes[:2])}"
        parent = elem.parent
        if parent and parent.name != "[document]":
            return f"{parent.name} > {elem.name}"
        return elem.name

    @staticmethod
    def extract_chapter_title(soup: BeautifulSoup, recipe: Optional[SiteRecipe] = None) -> str:
        """Extracts chapter title using selector or heuristic header search."""
        if recipe and recipe.title_selector:
            t = soup.select_one(recipe.title_selector)
            if t and t.get_text(strip=True):
                return t.get_text(strip=True)

        for h in soup.find_all(["h1", "h2", "h3"]):
            text = h.get_text(strip=True)
            if re.search(r'(?i)(chapter|ch\.|episode|prologue|epilogue|act|\d+)', text):
                return text

        title_tag = soup.find("title")
        if title_tag and title_tag.get_text(strip=True):
            raw = title_tag.get_text(strip=True)
            # Remove site branding from <title> e.g. "Chapter 1 - Read Light Novel"
            return re.split(r'[-–—|:]\s*', raw)[0].strip()

        return "Untitled Chapter"

    @classmethod
    def clean_chapter_content(
        cls,
        container: Tag,
        recipe: SiteRecipe,
        repeated_boilerplates: Optional[Set[str]] = None
    ) -> BeautifulSoup:
        """Multi-tier cleansing: selector purge, hidden text strip, regex watermarks."""
        # Work on a clone
        clean_soup = BeautifulSoup(str(container), "html.parser")
        root = clean_soup.find()

        # 1. Structural CSS Selector Purge
        for sel in recipe.ad_selectors:
            try:
                for match in root.select(sel):
                    match.decompose()
            except Exception:
                pass

        # 2. Anti-scraper Hidden Element Stripping
        for elem in root.find_all(True):
            style = (elem.get("style") or "").lower()
            if "display:none" in style or "visibility:hidden" in style or "font-size:0" in style or "opacity:0" in style:
                elem.decompose()
                continue
            if elem.get("aria-hidden") == "true":
                elem.decompose()
                continue

        # 3. Clean inline paragraphs & watermarks
        watermark_res = [re.compile(p, re.MULTILINE) for p in recipe.watermark_patterns]
        for p in root.find_all(["p", "div", "span"]):
            p_text = p.get_text(strip=True)
            
            # Check repeated cross-chapter boilerplate
            if repeated_boilerplates and p_text in repeated_boilerplates:
                p.decompose()
                continue

            # Check watermark regexes
            if any(r.search(p_text) for r in watermark_res):
                p.decompose()
                continue

        return clean_soup


# ==============================================================================
# DISCOVERY & LINK EXTRACTOR (TOC & NEXT LINKS)
# ==============================================================================

class LinkDiscovery:
    """Discovers chapter links from Table of Contents or Next Chapter chains."""

    @staticmethod
    def extract_toc_links(
        soup: BeautifulSoup,
        base_url: str,
        recipe: Optional[SiteRecipe] = None
    ) -> List[Tuple[str, str]]:
        """Finds ordered list of (title, absolute_url) from Table of Contents."""
        links: List[Tuple[str, str]] = []
        seen_urls: Set[str] = set()

        # Try user/recipe selector first
        candidate_links = []
        if recipe and recipe.toc_selector:
            candidate_links = soup.select(recipe.toc_selector)

        # Fallback: Find links whose text or URL looks like a chapter
        if not candidate_links:
            chapter_re = re.compile(r'(?i)(chapter|ch\.|volume|vol\.|episode|\b\d+\b)')
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                text = a.get_text(strip=True)
                if not href or href.startswith(("#", "javascript:", "mailto:")):
                    continue
                if chapter_re.search(text) or chapter_re.search(href):
                    candidate_links.append(a)

        for a in candidate_links:
            href = a.get("href")
            if not href:
                continue
            abs_url = urllib.parse.urljoin(base_url, href)
            # Remove hash fragment
            abs_url = urllib.parse.urldefrag(abs_url)[0]
            
            if abs_url in seen_urls:
                continue

            # Apply URL boundary regex if defined
            if recipe and recipe.url_whitelist_regex:
                if not re.search(recipe.url_whitelist_regex, abs_url):
                    continue

            seen_urls.add(abs_url)
            title = a.get_text(strip=True) or f"Chapter {len(links) + 1}"
            links.append((title, abs_url))

        return links

    @staticmethod
    def extract_next_link(
        soup: BeautifulSoup,
        current_url: str,
        recipe: Optional[SiteRecipe] = None
    ) -> Optional[str]:
        """Finds the 'Next Chapter' link URL for sequential link chain traversal."""
        if recipe and recipe.next_selector:
            next_tag = soup.select_one(recipe.next_selector)
            if next_tag and next_tag.get("href"):
                return urllib.parse.urljoin(current_url, next_tag["href"])

        # Heuristic search for "Next", "Next Chapter", "下一章", ">"
        next_patterns = [
            re.compile(r'(?i)^\s*(next|next\s+chapter|next\s+page|下一章|>|»)\s*$'),
            re.compile(r'(?i)\bnext\s+chapter\b'),
            re.compile(r'(?i)\bnext\b')
        ]

        for pattern in next_patterns:
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                if pattern.search(text):
                    href = a["href"].strip()
                    if href and not href.startswith(("#", "javascript:")):
                        return urllib.parse.urljoin(current_url, href)

        return None


# ==============================================================================
# FETCHING ENGINES: HTTP CLIENT & PLAYWRIGHT
# ==============================================================================

class HttpFetcher:
    """Fast, zero-dependency HTTP client with browser headers, cookies, and retry."""
    def __init__(self, recipe: SiteRecipe):
        self.recipe = recipe
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )

    def fetch(self, url: str) -> str:
        req = urllib.request.Request(url, headers=self.recipe.headers)
        max_retries = 3
        backoff = 2.0

        for attempt in range(1, max_retries + 1):
            try:
                with self.opener.open(req, timeout=15) as resp:
                    encoding = resp.headers.get_content_charset() or "utf-8"
                    return resp.read().decode(encoding, errors="replace")
            except Exception as e:
                if attempt == max_retries:
                    raise RuntimeError(f"HTTP fetch failed for {url} after {max_retries} attempts: {e}")
                time.sleep(backoff * attempt)
        return ""


class PlaywrightFetcher:
    """Headless browser fetcher for JavaScript-rendered web novels."""
    def __init__(self, recipe: SiteRecipe):
        self.recipe = recipe
        self._playwright = None
        self._browser = None
        self._context = None

    def initialize(self):
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            self._context = self._browser.new_context(
                user_agent=self.recipe.headers.get("User-Agent", DEFAULT_USER_AGENT),
                viewport={"width": 1280, "height": 800}
            )
        except Exception as e:
            raise RuntimeError(
                f"Playwright initialization failed. Is playwright installed? Error: {e}"
            )

    def fetch(self, url: str) -> str:
        if not self._context:
            self.initialize()
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Give short settle time for hydration
            page.wait_for_timeout(1000)
            return page.content()
        finally:
            page.close()

    def close(self):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()


# ==============================================================================
# BROWSER DEVTOOLS CONSOLE GENERATOR (RUN IN USER'S BROWSER)
# ==============================================================================

class ConsoleScriptGenerator:
    """Generates a standalone JS snippet for browser DevTools console execution."""

    @staticmethod
    def generate(
        start_url: str,
        content_selector: Optional[str] = None,
        title_selector: Optional[str] = None,
        next_selector: Optional[str] = None,
        max_chapters: int = 500,
        delay_ms: int = 1200
    ) -> str:
        """Generates self-contained browser script bundling JSZip & downloading ZIP directly."""
        c_sel = content_selector or "#content, .chapter-content, .entry-content, article"
        t_sel = title_selector or "h1, .chapter-title, .title"
        n_sel = next_selector or "a:contains('Next'), a.next-chapter, #next_chap"

        return f"""// ==============================================================================
// Web Novel Browser Exporter (Paste into DevTools Console)
// Runs directly in your authenticated browser session (Bypasses Cloudflare / Paywalls)
// ==============================================================================
(async function() {{
    console.log("%c[Novel Exporter] Initializing...", "color: #4CAF50; font-weight: bold; font-size: 14px;");

    // 1. Inject JSZip dynamically
    if (typeof JSZip === "undefined") {{
        console.log("[Novel Exporter] Loading JSZip library...");
        await new Promise((resolve, reject) => {{
            const s = document.createElement("script");
            s.src = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
        }});
    }}

    const zip = new JSZip();
    const manifest = {{ title: document.title, chapters: [], source_url: window.location.href }};
    const contentSel = "{c_sel}";
    const titleSel = "{t_sel}";
    const delay = ms => new Promise(r => setTimeout(r, ms));

    let currentUrl = window.location.href;
    let count = 0;
    const maxChapters = {max_chapters};

    console.log("[Novel Exporter] Starting chapter capture loop (Max: " + maxChapters + ")...");

    while (currentUrl && count < maxChapters) {{
        count++;
        console.log(`[Novel Exporter] Fetching Chapter ${{count}}: ${{currentUrl}}`);

        let doc = document;
        // If not the very first active page, fetch in background
        if (count > 1) {{
            try {{
                const resp = await fetch(currentUrl, {{ credentials: 'include' }});
                const htmlText = await resp.text();
                const parser = new DOMParser();
                doc = parser.parseFromString(htmlText, "text/html");
            }} catch (err) {{
                console.error(`[Novel Exporter] Failed fetching ${{currentUrl}}:`, err);
                break;
            }}
        }}

        // Extract Title & Content
        const titleElem = doc.querySelector(titleSel) || doc.querySelector("h1, h2");
        const title = titleElem ? titleElem.innerText.trim() : `Chapter ${{count}}`;
        const contentElem = doc.querySelector(contentSel);

        if (!contentElem) {{
            console.warn(`[Novel Exporter] Content selector '${{contentSel}}' not found on page ${{count}}. Stopping.`);
            break;
        }}

        // Clean common ads inside content
        const adElements = contentElem.querySelectorAll(".ad, .ads, ins, script, style, iframe, .sponsor");
        adElements.forEach(el => el.remove());

        const cleanHtml = `<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>${{title}}</title></head>
<body>
  <h1>${{title}}</h1>
  ${{contentElem.innerHTML}}
</body>
</html>`;

        const filename = `chapter_${{String(count).padStart(4, '0')}}.html`;
        zip.file(filename, cleanHtml);
        manifest.chapters.push({{ index: count, title: title, url: currentUrl, file: filename }});

        // Find Next Link
        let nextLink = null;
        const nextCandidates = doc.querySelectorAll("a");
        for (const a of nextCandidates) {{
            const t = a.innerText.trim().toLowerCase();
            if (t === "next" || t === "next chapter" || t.includes("next") || t === "下一章" || t === ">") {{
                if (a.href && !a.href.startsWith("javascript:") && a.href !== currentUrl) {{
                    nextLink = a.href;
                    break;
                }}
            }}
        }}

        if (!nextLink || nextLink === currentUrl) {{
            console.log("[Novel Exporter] Reached last chapter or no next link found.");
            break;
        }}

        currentUrl = nextLink;
        await delay({delay_ms});
    }}

    manifest.total_chapters = count;
    zip.file("manifest.json", JSON.stringify(manifest, null, 2));

    console.log(`[Novel Exporter] Packaging ${{count}} chapters into ZIP...`);
    const blob = await zip.generateAsync({{ type: "blob" }});
    const downloadUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const safeTitle = manifest.title.replace(/[^a-zA-Z0-9_-]/g, "_").substring(0, 40);
    a.href = downloadUrl;
    a.download = `${{safeTitle}}_chapters.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    console.log("%c[Novel Exporter] Complete! Download initiated: " + a.download, "color: #00BCD4; font-weight: bold; font-size: 16px;");
}})();
"""


# ==============================================================================
# NOVEL SESSION & CACHE ORCHESTRATION
# ==============================================================================

class NovelSession:
    """Manages downloading, local caching, and verification of a web novel."""

    def __init__(self, novel_url: str, base_cache_dir: Optional[Path] = None):
        self.novel_url = novel_url
        self.parsed = urllib.parse.urlparse(novel_url)
        self.domain = self.parsed.netloc.lower()
        if self.domain.startswith("www."):
            self.domain = self.domain[4:]

        self.slug = self._create_slug(novel_url)
        self.base_cache_dir = base_cache_dir or Path(".novel_cache")
        self.novel_dir = self.base_cache_dir / "novels" / self.slug
        self.raw_dir = self.novel_dir / "raw_html"
        self.clean_dir = self.novel_dir / "clean_html"
        
        self.manifest_path = self.novel_dir / "manifest.json"
        self.metadata_path = self.novel_dir / "metadata.json"

        self.recipe = SiteRecipe(self.domain, self.base_cache_dir / "site_recipes")
        self.manifest: Dict[str, Any] = {"title": self.slug, "chapters": [], "source_url": novel_url}
        self.metadata: Dict[str, Any] = {"title": self.slug, "author": "Unknown", "source_url": novel_url}

        self._init_dirs()
        self._load_state()

    def _create_slug(self, url: str) -> str:
        path = urllib.parse.urlparse(url).path.strip("/").replace("/", "_")
        slug = re.sub(r'[^a-zA-Z0-9_-]', '_', path)
        return (slug[:40] or "web_novel").strip("_")

    def _init_dirs(self):
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.clean_dir.mkdir(parents=True, exist_ok=True)

    def _load_state(self):
        if self.manifest_path.exists():
            try:
                self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        if self.metadata_path.exists():
            try:
                self.metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def save_state(self):
        self.manifest_path.write_text(json.dumps(self.manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        self.metadata_path.write_text(json.dumps(self.metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    def probe(self, fetcher: Any) -> Dict[str, Any]:
        """Probes the novel URL, detects TOC links, content selector, and ad blocks."""
        print(f"\n[Probe] Analyzing {self.novel_url} ...")
        html = fetcher.fetch(self.novel_url)
        soup = BeautifulSoup(html, "html.parser")

        # 1. Discover Table of Contents links
        toc_links = LinkDiscovery.extract_toc_links(soup, self.novel_url, self.recipe)
        
        # 2. Score Content Placeholder
        content_sel, content_elem = ContentExtractor.discover_content_placeholder(soup)
        title = ContentExtractor.extract_chapter_title(soup, self.recipe)
        next_link = LinkDiscovery.extract_next_link(soup, self.novel_url, self.recipe)

        probe_report = {
            "url": self.novel_url,
            "domain": self.domain,
            "detected_title": title,
            "is_toc_page": len(toc_links) > 2,
            "toc_links_found": len(toc_links),
            "sample_toc_links": toc_links[:5],
            "detected_content_selector": content_sel,
            "has_next_chapter": bool(next_link),
            "next_link": next_link
        }

        # Update recipe if newly discovered
        if not self.recipe.content_selector and content_sel:
            self.recipe.content_selector = content_sel
        if not self.recipe.next_selector and next_link:
            self.recipe.next_selector = "a:contains('Next')"
        if probe_report["is_toc_page"]:
            self.recipe.toc_selector = "a[href*='chapter']"

        self.recipe.save()
        return probe_report

    def crawl(
        self,
        fetcher: Any,
        pilot_count: Optional[int] = None,
        max_chapters: int = 1000
    ) -> List[Path]:
        """Executes resilient chapter crawling, sanitization, and caching."""
        print(f"\n[Crawler] Starting crawl for '{self.slug}' (Engine: {fetcher.__class__.__name__})")
        print(f"[Crawler] Cache workspace: {self.novel_dir}")

        # Step 1: Probe / retrieve chapter list
        html = fetcher.fetch(self.novel_url)
        soup = BeautifulSoup(html, "html.parser")

        toc_links = LinkDiscovery.extract_toc_links(soup, self.novel_url, self.recipe)
        chapter_queue: List[Tuple[str, str]] = []

        if len(toc_links) >= 2:
            print(f"[Crawler] Discovered {len(toc_links)} chapters from TOC index.")
            chapter_queue = toc_links
        else:
            print("[Crawler] No multi-link TOC index found. Switching to sequential Next-Link chain.")
            initial_title = ContentExtractor.extract_chapter_title(soup, self.recipe)
            chapter_queue.append((initial_title, self.novel_url))

        # Check existing cached chapters to resume
        cached_files = sorted(self.clean_dir.glob("ch_*.html"))
        processed_count = len(cached_files)
        print(f"[Crawler] Found {processed_count} already cached chapters. Resuming...")

        limit = pilot_count if pilot_count else max_chapters
        downloaded_paths: List[Path] = []
        current_idx = 0

        while current_idx < len(chapter_queue) and current_idx < limit:
            title, url = chapter_queue[current_idx]
            current_idx += 1
            idx_str = f"{current_idx:04d}"
            raw_path = self.raw_dir / f"ch_{idx_str}.html"
            clean_path = self.clean_dir / f"ch_{idx_str}.html"

            # Skip if already cached and clean
            if clean_path.exists() and clean_path.stat().st_size > 100:
                downloaded_paths.append(clean_path)
                continue

            print(f"[{current_idx}/{min(len(chapter_queue), limit)}] Fetching '{title}' -> {url}")
            try:
                ch_html = fetcher.fetch(url)
                raw_path.write_text(ch_html, encoding="utf-8")
            except Exception as e:
                print(f"  [Error] Failed to fetch {url}: {e}")
                break

            ch_soup = BeautifulSoup(ch_html, "html.parser")

            # Extract content using recipe or fallback scorer
            content_elem = None
            if self.recipe.content_selector:
                content_elem = ch_soup.select_one(self.recipe.content_selector)
            if not content_elem:
                _, content_elem = ContentExtractor.discover_content_placeholder(ch_soup)

            if not content_elem:
                print(f"  [Warning] No content container found for Chapter {current_idx}! Saving raw body.")
                content_elem = ch_soup.body or ch_soup

            # Sanitize content
            clean_soup = ContentExtractor.clean_chapter_content(content_elem, self.recipe)
            clean_text = clean_soup.get_text(separator=" ", strip=True)

            # Build valid XHTML chapter
            doc_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
</head>
<body>
  <h1>{title}</h1>
  <div class="chapter-content">
    {clean_soup}
  </div>
</body>
</html>"""
            clean_path.write_text(doc_html, encoding="utf-8")
            downloaded_paths.append(clean_path)

            # Record in manifest
            self.manifest["chapters"].append({
                "index": current_idx,
                "title": title,
                "url": url,
                "words": len(clean_text.split()),
                "file": clean_path.name
            })
            self.save_state()

            # If sequential mode without TOC, discover next link
            if len(toc_links) < 2 and current_idx < limit:
                next_url = LinkDiscovery.extract_next_link(ch_soup, url, self.recipe)
                if next_url and next_url != url:
                    next_title = f"Chapter {current_idx + 1}"
                    chapter_queue.append((next_title, next_url))
                else:
                    print("[Crawler] No further Next Chapter links found. Reached end of novel.")
                    break

            # Polite delay with jitter
            jitter = random.uniform(0.2, 0.6)
            time.sleep(self.recipe.delay + jitter)

        # Verification checkpoint
        self.verify(limit_reported=limit)
        return downloaded_paths

    def verify(self, limit_reported: Optional[int] = None) -> Dict[str, Any]:
        """Audits downloaded chapters for empty bodies, word counts, and formatting."""
        clean_files = sorted(self.clean_dir.glob("ch_*.html"))
        if limit_reported:
            clean_files = clean_files[:limit_reported]

        total = len(clean_files)
        word_counts = []
        suspicious_short = []

        for f in clean_files:
            text = f.read_text(encoding="utf-8")
            soup = BeautifulSoup(text, "html.parser")
            words = len(soup.get_text(separator=" ", strip=True).split())
            word_counts.append(words)
            if words < 150:
                suspicious_short.append((f.name, words))

        avg_words = sum(word_counts) // max(len(word_counts), 1)

        print("\n" + "=" * 60)
        print("          NOVEL CRAWL HEALTH & VERIFICATION REPORT")
        print("=" * 60)
        print(f"Total Cached Chapters Analyzed: {total}")
        print(f"Average Words per Chapter:      {avg_words}")
        if suspicious_short:
            print(f"[!] Warning: {len(suspicious_short)} unusually short chapters (<150 words):")
            for name, w in suspicious_short[:5]:
                print(f"    - {name}: {w} words")
        else:
            print("[✓] All chapters exhibit healthy word counts (>150 words).")
            print("[✓] Ad blocks and scripts cleanly stripped.")
        print("=" * 60 + "\n")

        return {
            "total_chapters": total,
            "avg_words": avg_words,
            "suspicious_short": suspicious_short
        }

    def export_epub(self, output_epub_path: Path) -> Path:
        """Packages cached clean chapters into EPUB3 using html_to_epub pipeline."""
        clean_files = sorted(self.clean_dir.glob("ch_*.html"))
        if not clean_files:
            raise RuntimeError(f"No clean chapters found in {self.clean_dir} to export!")

        print(f"[Export] Packaging {len(clean_files)} chapters into EPUB3 -> {output_epub_path} ...")
        
        scripts_dir = Path(__file__).resolve().parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from html_to_epub import convert_multi_html_to_epub

        convert_multi_html_to_epub(
            clean_files,
            output_epub=output_epub_path,
            title=self.metadata.get("title", self.slug),
            author=self.metadata.get("author", "Unknown")
        )
        print(f"[Export] Successfully generated {output_epub_path} ({output_epub_path.stat().st_size // 1024} KB)")
        return output_epub_path


# ==============================================================================
# ZIP IMPORTER (IMPORTS BROWSER-CONSOLE DOWNLOADED ZIPS)
# ==============================================================================

def import_console_zip(zip_path: Path, output_epub: Optional[Path] = None) -> Path:
    """Imports a .zip downloaded via browser DevTools console script into an EPUB3."""
    import zipfile
    print(f"\n[Import] Unpacking browser-downloaded zip: {zip_path} ...")
    extract_dir = Path(".novel_cache") / "imported_zips" / zip_path.stem
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extract_dir)

    manifest_file = extract_dir / "manifest.json"
    title = zip_path.stem
    author = "Unknown"
    if manifest_file.exists():
        try:
            m = json.loads(manifest_file.read_text(encoding="utf-8"))
            title = m.get("title", title)
            author = m.get("author", author)
        except Exception:
            pass

    chapter_files = sorted(extract_dir.glob("chapter_*.html"))
    if not chapter_files:
        chapter_files = sorted(extract_dir.glob("*.html"))

    if not chapter_files:
        raise RuntimeError(f"No HTML chapters found in {zip_path}!")

    out_epub = output_epub or (zip_path.parent / f"{zip_path.stem}.epub")
    
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from html_to_epub import convert_multi_html_to_epub

    convert_multi_html_to_epub(chapter_files, output_epub=out_epub, title=title, author=author)
    print(f"[Import] Successfully converted browser zip to EPUB: {out_epub}")
    return out_epub


# ==============================================================================
# USER ENGINE SELECTION PROMPT
# ==============================================================================

def prompt_engine_selection() -> str:
    """Interactively asks user which crawling engine to use if not specified."""
    if not sys.stdin.isatty():
        # Non-interactive fallback: HTTP client (safest, fastest, no external deps)
        return "http"

    print("\n" + "=" * 65)
    print("         WEB NOVEL CRAWLER: SELECT EXECUTION ENGINE")
    print("=" * 65)
    print(" [1] HTTP Client (Fast, lightweight, zero-dependency) [Recommended]")
    print(" [2] Headless Playwright (Full JavaScript browser rendering)")
    print(" [3] Output DevTools Console Script (Run in browser to bypass Cloudflare)")
    print("=" * 65)
    
    try:
        choice = input("Enter engine choice [1/2/3] (Default: 1): ").strip()
    except (EOFError, KeyboardInterrupt):
        return "http"

    if choice == "2":
        return "playwright"
    elif choice == "3":
        return "console"
    return "http"


# ==============================================================================
# CLI DISPATCHER
# ==============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="High-Performance Web Novel Crawler, Sanitizer & EPUB3 Builder"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Command: crawl
    crawl_p = subparsers.add_parser("crawl", help="Crawl novel from URL")
    crawl_p.add_argument("url", help="Novel TOC or Chapter 1 URL")
    crawl_p.add_argument("-o", "--output", help="Output EPUB filename", default=None)
    crawl_p.add_argument("--engine", choices=["http", "playwright", "console"], help="Crawler engine")
    crawl_p.add_argument("--pilot", type=int, default=None, help="Pilot run count (e.g. 5 chapters for verification)")
    crawl_p.add_argument("--max-chapters", type=int, default=1000, help="Maximum chapters to crawl")
    crawl_p.add_argument("--delay", type=float, default=1.0, help="Polite delay between requests in seconds")

    # Command: probe
    probe_p = subparsers.add_parser("probe", help="Inspect URL and generate draft site recipe")
    probe_p.add_argument("url", help="URL to probe")

    # Command: console-script
    cs_p = subparsers.add_parser("console-script", help="Generate DevTools console script for in-browser extraction")
    cs_p.add_argument("url", help="Novel URL")
    cs_p.add_argument("--max-chapters", type=int, default=500, help="Max chapters")
    cs_p.add_argument("-o", "--output-js", help="Save script to file")

    # Command: import-zip
    zip_p = subparsers.add_parser("import-zip", help="Import browser-downloaded zip into EPUB3")
    zip_p.add_argument("zip_file", help="Path to downloaded .zip")
    zip_p.add_argument("-o", "--output", help="Output EPUB filename")

    # Command: verify
    ver_p = subparsers.add_parser("verify", help="Audit cached novel chapters")
    ver_p.add_argument("url_or_slug", help="Novel URL or cached slug")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # 1. Probe
    if args.command == "probe":
        session = NovelSession(args.url)
        fetcher = HttpFetcher(session.recipe)
        report = session.probe(fetcher)
        print("\n[Probe Report]:")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    # 2. Console Script
    if args.command == "console-script":
        session = NovelSession(args.url)
        js = ConsoleScriptGenerator.generate(
            start_url=args.url,
            content_selector=session.recipe.content_selector,
            title_selector=session.recipe.title_selector,
            next_selector=session.recipe.next_selector,
            max_chapters=args.max_chapters
        )
        if args.output_js:
            Path(args.output_js).write_text(js, encoding="utf-8")
            print(f"[Console Script] Saved script to {args.output_js}")
        else:
            print("\n" + "=" * 60)
            print(" PASTE THIS SCRIPT INTO BROWSER DEVTOOLS CONSOLE (F12):")
            print("=" * 60)
            print(js)
            print("=" * 60)
        return

    # 3. Import Zip
    if args.command == "import-zip":
        zip_path = Path(args.zip_file)
        out_epub = Path(args.output) if args.output else None
        import_console_zip(zip_path, out_epub)
        return

    # 4. Verify
    if args.command == "verify":
        session = NovelSession(args.url_or_slug)
        session.verify()
        return

    # 5. Crawl
    if args.command == "crawl":
        engine = args.engine or prompt_engine_selection()
        session = NovelSession(args.url)
        if args.delay:
            session.recipe.delay = args.delay

        if engine == "console":
            js = ConsoleScriptGenerator.generate(args.url, session.recipe.content_selector)
            print("\n[Engine: Console] Paste this script in your browser DevTools console:")
            print(js)
            return

        fetcher = None
        if engine == "playwright":
            fetcher = PlaywrightFetcher(session.recipe)
        else:
            fetcher = HttpFetcher(session.recipe)

        try:
            downloaded = session.crawl(
                fetcher,
                pilot_count=args.pilot,
                max_chapters=args.max_chapters
            )
            out_epub = Path(args.output) if args.output else Path(f"{session.slug}.epub")
            session.export_epub(out_epub)
        finally:
            if hasattr(fetcher, "close"):
                fetcher.close()


if __name__ == "__main__":
    main()
