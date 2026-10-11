# PDF-to-EPUB: Multi-Format Ebook & Web Novel Suite

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![EPUB3 Compliant](https://img.shields.io/badge/EPUB-3.0-green.svg)](https://www.w3.org/publishing/epub3/)
[![W3C MathML](https://img.shields.io/badge/MathML-Native-purple.svg)](https://www.w3.org/Math/)
[![Antigravity Skill](https://img.shields.io/badge/Antigravity-Skill%20Ready-blueviolet.svg)](#installing-to-different-llms--agents)
[![Claude Skill](https://img.shields.io/badge/Claude%20Code-Compatible-orange.svg)](#installing-to-different-llms--agents)

A universal, high-fidelity document conversion engine and autonomous agent skill. Converts **Web Novels, Word documents (DOCX), LaTeX (TeX), PowerPoint presentations (PPTX/PPT), HTML/Web articles, and complex PDFs** into clean, publication-grade **EPUB3** ebooks and **Markdown**.

> 📖 **Full Command & Tool Documentation**: For complete command-line arguments, exhaustive format details, and the step-by-step LLM crawler manual, see **[USAGE.md](USAGE.md)**.

---

## Key Features

- **Web Novel Crawler & Sanitizer**: No-LLM DOM text-to-link density scoring, multi-tier ad stripping, polite delays, and resumable chapter caching.
- **DevTools Browser Exporter**: Generates a self-contained JavaScript snippet to run in any browser console (F12) to bypass Cloudflare Turnstile, CAPTCHAs, or login paywalls and download a `.zip`.
- **Direct Word to EPUB (Zero PDF)**: Converts DOCX/ODT directly to EPUB3 without intermediate PDF rendering, stripping system font bloat and matching Google Docs formatting.
- **Native W3C MathML Equations**: Converts LaTeX math into native `<math>` tags for responsive e-reader typography.
- **Document Layout Analysis (DLA)**: Clusters presentation slides into coherent textbook chapters using a heading stack state machine while purging margin headers and footers.
- **Adaptive Visual Grid Probing**: Probes complex PDFs using 3x3, 3x2, and 2x2 collage grids, dispatching parallel subagents for multi-page documents.
- **Self-Contained EPUB3 Compiler**: Packager generates compliant manifests (`package.opf`, `nav.xhtml`, `toc.ncx`) and dark-mode-ready styles using Python's standard library.

---

## Supported Input Formats

| Format | Extension / Scheme | Engine | Output Formats | Reference |
|---|---|---|---|---|
| **Web Novels** | `http://`, `https://` | `novel_crawler.py` | EPUB3, HTML | [Guide](USAGE.md#web-novel-crawler-novel_crawlerpy--crawl2epub) |
| **Word Documents** | `.docx`, `.odt`, `.rtf` | `docx_to_epub.py` | EPUB3, PDF | [Guide](USAGE.md#word-documents-docx_to_epubpy--docx2epub) |
| **LaTeX / TeX** | `.tex` | `tex_to_epub.py` | EPUB3 (MathML) | [Guide](USAGE.md#latex--tex-documents-tex_to_epubpy--tex2epub) |
| **PowerPoint** | `.pptx`, `.ppt` | `pptx_parser.py` | EPUB3, Markdown | [Guide](USAGE.md#powerpoint-presentations-pptx_parserpy--pptx) |
| **HTML / Articles** | `.html`, `.xhtml`, URL | `html_to_epub.py` | EPUB3 | [Guide](USAGE.md#html--online-articles-html_to_epubpy--html2epub) |
| **Complex PDFs** | `.pdf` | `collage_maker.py` + Agents | EPUB3, Markdown | [Guide](USAGE.md#complex-pdfs--vision-probing-collage_makerpy) |
| **Console ZIPs** | `.zip` | `novel_crawler.py import-zip` | EPUB3 | [Guide](USAGE.md#devtools-browser-exporter-bypass-cloudflare--paywalls) |

---

## Installing to Different LLMs & Agents

The repository follows the canonical 3-level progressive disclosure skill architecture (`SKILL.md`, `scripts/`, `references/`, `assets/`) and can be installed into any AI environment:

### 1. Google Antigravity (AGY)
Install as a global skill available across all conversations:
```bash
# Clone and install into Antigravity global skill registry
git clone https://github.com/tasmirz/pdf-to-epub.git
mkdir -p ~/.gemini/config/skills/pdf-to-epub
cp pdf-to-epub/SKILL.md ~/.gemini/config/skills/pdf-to-epub/
cp -r pdf-to-epub/scripts pdf-to-epub/references pdf-to-epub/assets ~/.gemini/config/skills/pdf-to-epub/
chmod +x ~/.gemini/config/skills/pdf-to-epub/scripts/*.py
```
*Antigravity automatically discovers the skill via the YAML frontmatter in `SKILL.md`.*

---

### 2. Claude Code / Claude Desktop
Install for use with Anthropic's Claude Code CLI or Desktop:
```bash
# Claude Code global skills directory:
mkdir -p ~/.claude/skills/pdf-to-epub
cp pdf-to-epub/SKILL.md ~/.claude/skills/pdf-to-epub/
cp -r pdf-to-epub/scripts pdf-to-epub/references pdf-to-epub/assets ~/.claude/skills/pdf-to-epub/
chmod +x ~/.claude/skills/pdf-to-epub/scripts/*.py
```
Or link in a specific project's `.claude/skills/` directory:
```bash
mkdir -p .claude/skills
ln -s /path/to/pdf-to-epub .claude/skills/pdf-to-epub
```

---

### 3. Cursor / Windsurf / Roo-Code / Copilot
For IDE-based autonomous coding agents, add this pointer to your `.cursorrules`, `.windsurfrules`, or system prompt:

```markdown
<!-- pdf-to-epub skill instruction -->
When asked to convert PDFs, Word documents (.docx), LaTeX (.tex), presentations (.pptx),
HTML web pages, or Web Novels into EPUB3 or Markdown, follow the protocol in:
/path/to/pdf-to-epub/SKILL.md and USAGE.md
Use the unified CLI: pdf-to-epub convert <input> -o <output.epub>
```

---

### 4. Local CLI / Standalone Shell (Linux & macOS)
Install system-wide for everyday terminal use:
```bash
git clone https://github.com/tasmirz/pdf-to-epub.git
cd pdf-to-epub
chmod +x install.sh && ./install.sh
```

**System Dependencies (Optional depending on formats):**
```bash
# Ubuntu / Debian:
sudo apt-get install -y poppler-utils tesseract-ocr libreoffice-core texlive-extra-utils tex4ebook

# Arch Linux:
sudo pacman -S --needed poppler tesseract libreoffice-fresh texlive-bin

# macOS:
brew install poppler tesseract libreoffice
```

---

## Quickstart

```bash
# Universal auto-detect conversion
pdf-to-epub convert document.docx -o book.epub
pdf-to-epub convert paper.tex     -o paper.epub
pdf-to-epub convert article.html  -o article.epub
pdf-to-epub convert slides.pptx   -o presentation.epub

# Web Novel Crawl
pdf-to-epub crawl2epub https://novel-site.com/book/toc --pilot 5 -o novel.epub

# DevTools Console script (bypasses Cloudflare / Paywalls)
pdf-to-epub novel-console-script https://site.com/novel/ch1
# (Paste in browser F12 Console, download ZIP, then package:)
pdf-to-epub convert downloaded_chapters.zip -o novel.epub
```

👉 **See [USAGE.md](USAGE.md) for complete options and advanced configurations.**

---

## Repository Structure

```text
pdf-to-epub/
├── SKILL.md                          # Progressive disclosure specification (<500 lines)
├── README.md                         # Clean feature overview & multi-LLM setup
├── USAGE.md                          # Exhaustive tool reference & LLM crawler manual
├── LICENSE                           # Open source MIT License
├── requirements.txt                  # Minimal Python dependencies
├── install.sh                        # Universal 1-command installer
├── scripts/                          # Executable deterministic code
│   ├── cli.py                        # Unified CLI router (pdf-to-epub)
│   ├── novel_crawler.py              # Web novel crawler, ad sanitizer & console script
│   ├── docx_to_epub.py               # Direct DOCX to EPUB3 (Zero PDF)
│   ├── docx_to_pdf.py                # Direct DOCX to vector PDF
│   ├── tex_to_epub.py                # Direct LaTeX to EPUB3 (Native MathML)
│   ├── html_to_epub.py               # HTML / Web article to EPUB3
│   ├── pptx_parser.py                # PowerPoint to EPUB3 & Markdown with DLA
│   ├── collage_maker.py              # Visual grid collage (3x3, 2x2, 1x1) & cropper
│   ├── epub_packager.py              # Standalone EPUB3 compiler
│   ├── dla_analyzer.py               # Document layout analysis & shape classification
│   ├── build_textbook_edition.py     # Pedagogical textbook restructurer
│   ├── verify_fidelity.py            # Sentence alignment coverage verifier
│   └── compare_with_gold.py          # Benchmark tester against reference gold standards
├── references/                       # Deep domain documentation loaded on-demand
│   ├── crawler_rules.md              # Algorithmic DOM density scoring & anti-bot rules
│   ├── mathml_standards.md           # W3C MathML namespace, OPF properties & LaTeX rules
│   └── dla_architecture.md           # Visual collage probing, heading stack & margin purging
├── assets/                           # Bundled styling, templates, and starter configs
│   ├── styles/
│   │   ├── epub_default.css          # Dark-mode-ready EPUB3 stylesheet
│   │   └── mathml.css                # Mathematical formula styling
│   └── site_recipes/
│       └── template_recipe.json      # Starter site recipe for web novel domains
└── tests/                            # Automated test suite and sample fixtures
```

---

## License

Released under the [MIT License](LICENSE).
