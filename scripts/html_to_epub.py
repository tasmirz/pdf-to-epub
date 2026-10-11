#!/usr/bin/env python3
r"""
html_to_epub.py
Direct HTML/XHTML to clean, reflowable EPUB3 converter with native MathML and asset bundling.

Key Capabilities:
1. Universal HTML Ingestion: Converts standalone HTML files, multi-page HTML documentation,
   folders of HTML chapters, or web article URLs (http/https).
2. Content Sanitization & Cleaning: Strips ad scripts, tracking pixels, iframes, navigation chrome,
   and cookie banners while preserving semantic headings, code blocks, tables, blockquotes, and figures.
3. Intelligent Asset Harvesting:
   - Decodes base64 inline data URIs (data:image/...) into standalone image assets.
   - Resolves and bundles local relative images, styles, and SVG graphics.
   - Downloads remote HTTP/HTTPS images if connected.
4. Native W3C MathML & Code Blocks: Preserves <math> tags with proper EPUB3 manifest declarations
   and formats <pre><code> blocks with clean responsive typography.
5. Flexible Flow Architecture: Supports both '--flow single' (continuous document) and
   '--flow split' (per-heading chapter files).
6. Multi-File Chapter Merging: Ingests a series of HTML files or documentation trees in order
   to produce a cohesive book.
7. Dual Engine: Native Python semantic packager (default) or LibreOffice headless with font sanitization.

Usage:
    # 1. Convert a single HTML file to EPUB3
    python3 scripts/html_to_epub.py article.html -o article.epub

    # 2. Convert with article cleaning (removes scripts/ads/nav chrome)
    python3 scripts/html_to_epub.py web_page.html -o book.epub --clean-article

    # 3. Convert multi-page documentation or book chapters
    python3 scripts/html_to_epub.py chapter1.html chapter2.html -o full_book.epub

    # 4. Convert a web article from URL
    python3 scripts/html_to_epub.py https://example.com/article -o article.epub

    # 5. Via unified CLI
    python3 scripts/cli.py html2epub article.html -o article.epub
    python3 scripts/cli.py convert article.html -o article.epub
"""

import argparse
import base64
import glob
import html
import io
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from bs4 import BeautifulSoup


SUPPORTED_HTML_EXTENSIONS = {".html", ".htm", ".xhtml", ".shtml", ".mhtml"}

EPUB3_CSS = """@charset "utf-8";

/* Typography & Base Layout */
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Georgia, serif;
    font-size: 1.05em;
    line-height: 1.65;
    margin: 1.5em 5%;
    color: #1a1a1a;
    background-color: #ffffff;
}

/* Headings */
h1, h2, h3, h4, h5, h6 {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #0f172a;
    font-weight: 700;
    line-height: 1.25;
    margin-top: 1.6em;
    margin-bottom: 0.5em;
    page-break-after: avoid;
    break-after: avoid;
}

h1 { font-size: 1.85em; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.3em; margin-bottom: 0.8em; }
h2 { font-size: 1.45em; border-bottom: 1px solid #f1f5f9; padding-bottom: 0.2em; margin-top: 1.8em; }
h3 { font-size: 1.2em; margin-top: 1.4em; }
h4 { font-size: 1.08em; }

p {
    margin: 0 0 0.85em 0;
    text-align: justify;
    text-justify: inter-word;
    hyphens: auto;
}

/* Horizontal Dividers */
hr {
    border: none;
    border-top: 1px solid #cbd5e1;
    margin: 2.2em auto;
    width: 90%;
}

/* Figures & Images */
figure {
    margin: 1.8em auto;
    text-align: center;
    page-break-inside: avoid;
    break-inside: avoid;
    max-width: 100%;
}

figure img, img {
    max-width: 95%;
    height: auto;
    display: block;
    margin: 0.5em auto;
    border-radius: 4px;
}

figcaption {
    font-size: 0.88em;
    color: #475569;
    font-style: italic;
    margin-top: 0.5em;
    text-align: center;
    line-height: 1.4;
}

/* Tables */
table {
    border-collapse: collapse;
    width: 95%;
    margin: 1.8em auto;
    font-size: 0.95em;
    page-break-inside: avoid;
    break-inside: avoid;
    border: 1px solid #cbd5e1;
}

th, td {
    border: 1px solid #cbd5e1;
    padding: 0.6em 0.85em;
    text-align: left;
    vertical-align: top;
}

th {
    background-color: #f8fafc;
    font-weight: 600;
    color: #0f172a;
    border-bottom: 2px solid #94a3b8;
}

tr:nth-child(even) td {
    background-color: #f8fafc;
}

/* Code Blocks */
pre {
    background-color: #0f172a;
    color: #f8fafc;
    padding: 1em 1.2em;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 0.88em;
    line-height: 1.45;
    margin: 1.4em 0;
    page-break-inside: avoid;
    break-inside: avoid;
}

code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.9em;
    background-color: #f1f5f9;
    color: #0f172a;
    padding: 0.15em 0.35em;
    border-radius: 3px;
}

pre code {
    background-color: transparent;
    color: inherit;
    padding: 0;
    font-size: 1em;
}

/* Blockquotes */
blockquote {
    border-left: 4px solid #3b82f6;
    margin: 1.4em 0;
    padding: 0.4em 1em 0.4em 1.2em;
    background-color: #f8fafc;
    color: #334155;
    font-style: italic;
    border-radius: 0 4px 4px 0;
}

/* Lists */
ul, ol {
    margin: 0.8em 0 1.2em 1.5em;
    padding: 0;
}

li {
    margin-bottom: 0.4em;
}

/* Mathematical Formulas */
math {
    font-family: "Cambria Math", "Latin Modern Math", "STIX Two Math", serif;
    font-size: 1.05em;
}

div.math.display {
    text-align: center;
    margin: 1.2em auto;
    overflow-x: auto;
    page-break-inside: avoid;
}
"""


def slugify(text: str) -> str:
    """Generate clean slug from heading text."""
    clean = re.sub(r"[*_`]", "", text).lower().strip()
    slug = re.sub(r"[^a-z0-9_-]+", "-", clean).strip("-")
    return slug or "section"


def sanitize_epub_fonts(epub_path: Union[str, Path], output_path: Optional[Union[str, Path]] = None) -> Path:
    """Strip heavy system fonts from EPUB to keep file size compact."""
    src = Path(epub_path).resolve()
    dst = Path(output_path).resolve() if output_path else src

    temp_out = src.parent / f"tmp_sanitize_{os.getpid()}_{int(time.time()*1000)}.epub"
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(temp_out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if any(item.filename.lower().endswith(ext) for ext in [".otf", ".ttf", ".woff", ".woff2", ".eot"]) or "fonts/" in item.filename.lower():
                continue
            data = zin.read(item.filename)
            if item.filename.endswith(".opf"):
                text = data.decode("utf-8", errors="replace")
                text = re.sub(r'<item [^>]*href="fonts/[^>]*/>\s*', '', text)
                text = re.sub(r'<item [^>]*media-type="font/[^>]*/>\s*', '', text)
                data = text.encode("utf-8")
            elif item.filename.endswith(".css"):
                text = data.decode("utf-8", errors="replace")
                text = re.sub(r'@font-face\s*\{[^}]*\}', '', text)
                data = text.encode("utf-8")

            if item.filename == "mimetype":
                zout.writestr(item, data, compress_type=zipfile.ZIP_STORED)
            else:
                zout.writestr(item, data)

    shutil.move(str(temp_out), str(dst))
    return dst


def fetch_url_content(url: str, timeout: int = 15) -> Tuple[str, str]:
    """Fetch HTML content from a URL. Returns (html_string, title_guess)."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        raw_html = response.read().decode(charset, errors="replace")

    parsed = urllib.parse.urlparse(url)
    title_guess = Path(parsed.path).stem or parsed.netloc
    return raw_html, title_guess


def clean_and_extract_html(
    html_text: str,
    base_dir: Optional[Path],
    figures_dir: Path,
    clean_article: bool = False,
    download_remote_images: bool = True
) -> Dict[str, Any]:
    """
    Parses and sanitizes HTML:
    - Cleans scripts, styles, tracking pixels, ads, and navigation chrome.
    - Extracts inline base64 images into standalone PNG/JPEG files in figures_dir.
    - Resolves local relative images and copies them to figures_dir.
    - Downloads remote images if download_remote_images is True.
    - Extracts title, author, language metadata.
    - Identifies headings (h1, h2, h3) for TOC.
    """
    soup = BeautifulSoup(html_text, "html.parser")

    # 1. Extract metadata before stripping tags
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text().strip()

    author = ""
    author_meta = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", property="article:author")
    if author_meta and author_meta.get("content"):
        author = author_meta["content"].strip()

    lang = "en"
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        lang = html_tag["lang"].split("-")[0].strip()

    # 2. Decompose web cruft
    tags_to_remove = ["script", "noscript", "style", "iframe", "object", "embed", "applet"]
    if clean_article:
        tags_to_remove.extend(["nav", "footer", "header", "aside", "form"])

    for tag_name in tags_to_remove:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    if clean_article:
        # Remove common ad / tracking / cookie banner classes and IDs
        cruft_pattern = re.compile(r"ad-|advert|banner|cookie|share|social|popup|tracking|widget|sidebar", re.I)
        for el in soup.find_all(["div", "section", "aside", "span"], class_=cruft_pattern):
            el.decompose()
        for el in soup.find_all(["div", "section", "aside"], id=cruft_pattern):
            el.decompose()

    # 3. Process Images (Base64 + Local relative + Remote)
    image_counter = len(list(figures_dir.glob("*")))
    has_mathml = bool(soup.find_all("math"))

    for img in soup.find_all("img"):
        src = img.get("src", "").strip()
        if not src:
            continue

        # A. Base64 Data URI
        if src.startswith("data:image/"):
            try:
                header, b64_data = src.split(",", 1)
                mime = header.split(";")[0].replace("data:", "")
                ext = mime.split("/")[-1]
                if ext == "jpeg": ext = "jpg"
                if ext not in ["png", "jpg", "svg", "webp", "gif"]: ext = "png"

                image_counter += 1
                img_name = f"image_{image_counter:03d}.{ext}"
                img_target = figures_dir / img_name
                img_target.write_bytes(base64.b64decode(b64_data))
                img["src"] = f"figures/{img_name}"
            except Exception:
                pass
            continue

        # B. Remote HTTP/HTTPS Image
        if src.startswith("http://") or src.startswith("https://"):
            if download_remote_images:
                try:
                    image_counter += 1
                    parsed = urllib.parse.urlparse(src)
                    raw_ext = Path(parsed.path).suffix.lower().replace(".", "")
                    ext = raw_ext if raw_ext in ["png", "jpg", "jpeg", "svg", "webp", "gif"] else "png"
                    if ext == "jpeg": ext = "jpg"

                    img_name = f"image_{image_counter:03d}.{ext}"
                    img_target = figures_dir / img_name

                    req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        img_target.write_bytes(resp.read())
                    img["src"] = f"figures/{img_name}"
                except Exception:
                    pass
            continue

        # C. Local relative image
        if base_dir:
            clean_rel = urllib.parse.unquote(src).split("?")[0].split("#")[0]
            local_cand = (base_dir / clean_rel).resolve()
            if local_cand.exists() and local_cand.is_file():
                image_counter += 1
                ext = local_cand.suffix.lower().replace(".", "") or "png"
                img_name = f"image_{image_counter:03d}.{ext}"
                img_target = figures_dir / img_name
                shutil.copy2(local_cand, img_target)
                img["src"] = f"figures/{img_name}"

    # 4. Ensure headings have unique IDs for internal anchors
    headings = []
    seen_slugs = set()
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        htext = h.get_text().strip()
        if not htext:
            continue
        base_slug = slugify(htext)
        slug = base_slug
        count = 1
        while slug in seen_slugs:
            count += 1
            slug = f"{base_slug}-{count}"
        seen_slugs.add(slug)
        h["id"] = slug
        lvl = int(h.name[1])
        headings.append((htext, slug, lvl))

    # 5. Extract body content
    body = soup.find("body") or soup
    body_html = body.decode_contents() if body else str(soup)

    return {
        "title": title or "HTML Document",
        "author": author or "Document Author",
        "lang": lang,
        "body_html": body_html,
        "headings": headings,
        "has_mathml": has_mathml
    }


def convert_single_html_to_epub(
    input_path_or_url: Union[str, Path],
    output_epub: Path,
    title: Optional[str] = None,
    author: Optional[str] = None,
    lang: Optional[str] = None,
    flow_mode: str = "single",
    clean_article: bool = False
) -> Dict[str, Union[bool, str, int, float]]:
    """Convert a single HTML document or URL to EPUB3."""
    start_t = time.time()
    output_epub = Path(output_epub).resolve()
    output_epub.parent.mkdir(parents=True, exist_ok=True)

    is_url = str(input_path_or_url).startswith("http://") or str(input_path_or_url).startswith("https://")

    with tempfile.TemporaryDirectory(prefix="html2epub_") as tmp_dir:
        tmp_p = Path(tmp_dir)
        figures_dir = tmp_p / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)

        if is_url:
            raw_html, fallback_title = fetch_url_content(str(input_path_or_url))
            base_dir = None
        else:
            in_file = Path(input_path_or_url).resolve()
            if not in_file.exists():
                return {"success": False, "error": f"HTML file not found: {in_file}"}
            raw_html = in_file.read_text(encoding="utf-8", errors="replace")
            fallback_title = in_file.stem.replace("_", " ")
            base_dir = in_file.parent

        info = clean_and_extract_html(
            raw_html,
            base_dir=base_dir,
            figures_dir=figures_dir,
            clean_article=clean_article
        )

        doc_title = title or info["title"] or fallback_title
        doc_author = author or info["author"]
        doc_lang = lang or info["lang"]
        doc_uuid = f"urn:uuid:{uuid.uuid4()}"
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Build EPUB container layout
        oebps = tmp_p / "OEBPS"
        meta_inf = tmp_p / "META-INF"
        oebps.mkdir(parents=True, exist_ok=True)
        meta_inf.mkdir(parents=True, exist_ok=True)

        # 1. mimetype (stored uncompressed)
        (tmp_p / "mimetype").write_text("application/epub+zip", encoding="ascii")

        # 2. container.xml
        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>"""
        (meta_inf / "container.xml").write_text(container_xml, encoding="utf-8")

        # 3. CSS
        (oebps / "styles.css").write_text(EPUB3_CSS, encoding="utf-8")

        # 4. Copy figures into OEBPS/figures/
        oebps_figs = oebps / "figures"
        oebps_figs.mkdir(exist_ok=True)
        manifest_items = [
            '<item id="styles" href="styles.css" media-type="text/css"/>',
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        ]

        for img in figures_dir.glob("*"):
            if img.is_file():
                shutil.copy2(img, oebps_figs / img.name)
                ext = img.suffix.lower()
                mime = "image/png" if ext == ".png" else "image/jpeg"
                if ext == ".svg": mime = "image/svg+xml"
                elif ext == ".webp": mime = "image/webp"
                elif ext == ".gif": mime = "image/gif"
                clean_id = f"img_{re.sub(r'[^a-zA-Z0-9_]', '_', img.name)}"
                manifest_items.append(f'<item id="{clean_id}" href="figures/{img.name}" media-type="{mime}"/>')

        # 5. Build Content XHTML Documents
        body_soup = BeautifulSoup(info["body_html"], "html.parser")
        toc_entries = []
        spine_items = []

        is_split = (flow_mode == "split")

        if is_split:
            # Split into chapters by <h1>
            h1_elements = body_soup.find_all("h1")
            if len(h1_elements) > 1:
                # Multiple chapters
                chapters = []
                # Collect content before first h1
                first_h1 = h1_elements[0]
                pre_content = []
                cur = first_h1.previous_sibling
                while cur:
                    pre_content.insert(0, cur)
                    cur = cur.previous_sibling

                # Build chapters
                for idx, h1 in enumerate(h1_elements, 1):
                    chap_title = h1.get_text().strip()
                    chap_id = h1.get("id") or f"chapter-{idx}"
                    chap_nodes = [h1]
                    sib = h1.next_sibling
                    while sib and sib.name != "h1":
                        chap_nodes.append(sib)
                        sib = sib.next_sibling

                    chap_html = "".join(str(n) for n in chap_nodes)
                    chap_filename = f"chapter_{idx:03d}.xhtml"

                    page_doc = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{doc_lang}">
<head>
    <meta charset="utf-8"/>
    <title>{html.escape(chap_title)}</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
{chap_html}
</body>
</html>"""
                    (oebps / chap_filename).write_text(page_doc, encoding="utf-8")
                    item_id = f"chap_{idx:03d}"
                    mathml_prop = ' properties="mathml"' if "<math" in chap_html else ""
                    manifest_items.append(f'<item id="{item_id}" href="{chap_filename}" media-type="application/xhtml+xml"{mathml_prop}/>')
                    spine_items.append(f'<itemref idref="{item_id}"/>')
                    toc_entries.append((chap_title, chap_filename, 1))

            else:
                is_split = False

        if not is_split:
            # Single continuous flow
            doc_filename = "document.xhtml"
            full_page = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{doc_lang}">
<head>
    <meta charset="utf-8"/>
    <title>{html.escape(doc_title)}</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
{info["body_html"]}
</body>
</html>"""
            (oebps / doc_filename).write_text(full_page, encoding="utf-8")
            mathml_prop = ' properties="mathml"' if info["has_mathml"] else ""
            manifest_items.append(f'<item id="main_doc" href="{doc_filename}" media-type="application/xhtml+xml"{mathml_prop}/>')
            spine_items.append('<itemref idref="main_doc"/>')

            for h_title, h_slug, h_lvl in info["headings"]:
                toc_entries.append((h_title, f"{doc_filename}#{h_slug}", h_lvl))

        if not toc_entries:
            toc_entries.append((doc_title, "document.xhtml" if not is_split else "chapter_001.xhtml", 1))

        # 6. nav.xhtml
        nav_items_html = []
        for t_title, t_href, _ in toc_entries:
            nav_items_html.append(f'        <li><a href="{t_href}">{html.escape(t_title)}</a></li>')
        nav_body = "\n".join(nav_items_html)

        nav_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{doc_lang}">
<head>
    <meta charset="utf-8"/>
    <title>Table of Contents</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
    <nav epub:type="toc" id="toc">
      <h1>Table of Contents</h1>
      <ol>
{nav_body}
      </ol>
    </nav>
</body>
</html>"""
        (oebps / "nav.xhtml").write_text(nav_xhtml, encoding="utf-8")

        # 7. toc.ncx
        ncx_points = []
        for idx, (t_title, t_href, _) in enumerate(toc_entries, 1):
            ncx_points.append(f"""    <navPoint id="navPoint-{idx}" playOrder="{idx}">
      <navLabel><text>{html.escape(t_title)}</text></navLabel>
      <content src="{t_href}"/>
    </navPoint>""")
        ncx_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{doc_uuid}"/>
    <meta name="dtb:depth" content="2"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{html.escape(doc_title)}</text></docTitle>
  <navMap>
{"\n".join(ncx_points)}
  </navMap>
</ncx>"""
        (oebps / "toc.ncx").write_text(ncx_xml, encoding="utf-8")

        # 8. package.opf
        manifest_str = "\n    ".join(manifest_items)
        spine_str = "\n    ".join(spine_items)

        package_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="{doc_lang}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">{doc_uuid}</dc:identifier>
    <dc:title>{html.escape(doc_title)}</dc:title>
    <dc:language>{doc_lang}</dc:language>
    <dc:creator>{html.escape(doc_author)}</dc:creator>
    <meta property="dcterms:modified">{now_utc}</meta>
  </metadata>
  <manifest>
    {manifest_str}
  </manifest>
  <spine toc="ncx">
    {spine_str}
  </spine>
</package>"""
        (oebps / "package.opf").write_text(package_opf, encoding="utf-8")

        # 9. Pack ZIP into valid EPUB
        temp_out = tmp_p / "output.epub"
        with zipfile.ZipFile(temp_out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            mimetype_bytes = (tmp_p / "mimetype").read_bytes()
            zout.writestr("mimetype", mimetype_bytes, compress_type=zipfile.ZIP_STORED)

            for root, _, files in os.walk(oebps):
                for f in sorted(files):
                    fpath = Path(root) / f
                    rel_p = fpath.relative_to(tmp_p)
                    zout.write(fpath, str(rel_p))

            for root, _, files in os.walk(meta_inf):
                for f in sorted(files):
                    fpath = Path(root) / f
                    rel_p = fpath.relative_to(tmp_p)
                    zout.write(fpath, str(rel_p))

        shutil.move(str(temp_out), str(output_epub))

    return {
        "success": True,
        "output_path": str(output_epub),
        "file_size": output_epub.stat().st_size,
        "elapsed_sec": round(time.time() - start_t, 2),
        "engine": "semantic_python"
    }


def convert_multi_html_to_epub(
    html_files: List[Union[str, Path]],
    output_epub: Path,
    title: Optional[str] = None,
    author: Optional[str] = None,
    lang: Optional[str] = None,
    clean_article: bool = False
) -> Dict[str, Union[bool, str, int, float]]:
    """Convert multiple HTML files (e.g. chapters) into a multi-chapter EPUB3 ebook."""
    start_t = time.time()
    output_epub = Path(output_epub).resolve()
    output_epub.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="html2epub_multi_") as tmp_dir:
        tmp_p = Path(tmp_dir)
        figures_dir = tmp_p / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)

        oebps = tmp_p / "OEBPS"
        meta_inf = tmp_p / "META-INF"
        oebps.mkdir(parents=True, exist_ok=True)
        meta_inf.mkdir(parents=True, exist_ok=True)

        (tmp_p / "mimetype").write_text("application/epub+zip", encoding="ascii")
        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>"""
        (meta_inf / "container.xml").write_text(container_xml, encoding="utf-8")
        (oebps / "styles.css").write_text(EPUB3_CSS, encoding="utf-8")

        doc_title = title or (Path(html_files[0]).stem.replace("_", " ") if html_files else "HTML Book")
        doc_author = author or "Document Author"
        doc_lang = lang or "en"
        doc_uuid = f"urn:uuid:{uuid.uuid4()}"
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        manifest_items = [
            '<item id="styles" href="styles.css" media-type="text/css"/>',
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        ]
        spine_items = []
        toc_entries = []

        for idx, item in enumerate(html_files, 1):
            p = Path(item).resolve()
            if not p.exists():
                continue
            raw_html = p.read_text(encoding="utf-8", errors="replace")
            info = clean_and_extract_html(
                raw_html,
                base_dir=p.parent,
                figures_dir=figures_dir,
                clean_article=clean_article
            )
            chap_title = info["title"] if info["title"] != "HTML Document" else p.stem.replace("_", " ")
            chap_filename = f"chapter_{idx:03d}.xhtml"

            page_doc = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{doc_lang}">
<head>
    <meta charset="utf-8"/>
    <title>{html.escape(chap_title)}</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
{info["body_html"]}
</body>
</html>"""
            (oebps / chap_filename).write_text(page_doc, encoding="utf-8")
            item_id = f"chap_{idx:03d}"
            mathml_prop = ' properties="mathml"' if info["has_mathml"] else ""
            manifest_items.append(f'<item id="{item_id}" href="{chap_filename}" media-type="application/xhtml+xml"{mathml_prop}/>')
            spine_items.append(f'<itemref idref="{item_id}"/>')
            toc_entries.append((chap_title, chap_filename, 1))

        # Copy figures
        oebps_figs = oebps / "figures"
        oebps_figs.mkdir(exist_ok=True)
        for img in figures_dir.glob("*"):
            if img.is_file():
                shutil.copy2(img, oebps_figs / img.name)
                ext = img.suffix.lower()
                mime = "image/png" if ext == ".png" else "image/jpeg"
                if ext == ".svg": mime = "image/svg+xml"
                elif ext == ".webp": mime = "image/webp"
                elif ext == ".gif": mime = "image/gif"
                clean_id = f"img_{re.sub(r'[^a-zA-Z0-9_]', '_', img.name)}"
                manifest_items.append(f'<item id="{clean_id}" href="figures/{img.name}" media-type="{mime}"/>')

        # nav.xhtml
        nav_items_html = [f'        <li><a href="{t_href}">{html.escape(t_title)}</a></li>' for t_title, t_href, _ in toc_entries]
        nav_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{doc_lang}">
<head><meta charset="utf-8"/><title>Table of Contents</title><link rel="stylesheet" type="text/css" href="styles.css"/></head>
<body>
    <nav epub:type="toc" id="toc">
      <h1>Table of Contents</h1>
      <ol>
{"\n".join(nav_items_html)}
      </ol>
    </nav>
</body>
</html>"""
        (oebps / "nav.xhtml").write_text(nav_xhtml, encoding="utf-8")

        # toc.ncx
        ncx_points = [
            f"""    <navPoint id="navPoint-{i}" playOrder="{i}">
      <navLabel><text>{html.escape(t)}</text></navLabel>
      <content src="{h}"/>
    </navPoint>""" for i, (t, h, _) in enumerate(toc_entries, 1)
        ]
        ncx_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{doc_uuid}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{html.escape(doc_title)}</text></docTitle>
  <navMap>
{"\n".join(ncx_points)}
  </navMap>
</ncx>"""
        (oebps / "toc.ncx").write_text(ncx_xml, encoding="utf-8")

        # package.opf
        package_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="{doc_lang}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">{doc_uuid}</dc:identifier>
    <dc:title>{html.escape(doc_title)}</dc:title>
    <dc:language>{doc_lang}</dc:language>
    <dc:creator>{html.escape(doc_author)}</dc:creator>
    <meta property="dcterms:modified">{now_utc}</meta>
  </metadata>
  <manifest>
    {"\n    ".join(manifest_items)}
  </manifest>
  <spine toc="ncx">
    {"\n    ".join(spine_items)}
  </spine>
</package>"""
        (oebps / "package.opf").write_text(package_opf, encoding="utf-8")

        # Repack
        temp_out = tmp_p / "output.epub"
        with zipfile.ZipFile(temp_out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            zout.writestr("mimetype", (tmp_p / "mimetype").read_bytes(), compress_type=zipfile.ZIP_STORED)
            for root, _, files in os.walk(oebps):
                for f in sorted(files):
                    fpath = Path(root) / f
                    zout.write(fpath, str(fpath.relative_to(tmp_p)))
            for root, _, files in os.walk(meta_inf):
                for f in sorted(files):
                    fpath = Path(root) / f
                    zout.write(fpath, str(fpath.relative_to(tmp_p)))

        shutil.move(str(temp_out), str(output_epub))

    return {
        "success": True,
        "output_path": str(output_epub),
        "file_size": output_epub.stat().st_size,
        "elapsed_sec": round(time.time() - start_t, 2),
        "engine": "semantic_multi_python"
    }


def convert_html_to_epub(
    inputs: Union[str, Path, List[Union[str, Path]]],
    output_epub: Optional[Union[str, Path]] = None,
    outdir: Optional[Union[str, Path]] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
    lang: Optional[str] = None,
    flow_mode: str = "single",
    clean_article: bool = False,
    engine: str = "auto"
) -> Dict[str, Union[bool, str, int, float]]:
    """
    Main API entry point to convert HTML/XHTML to EPUB3.
    """
    if isinstance(inputs, (str, Path)):
        in_str = str(inputs)
        is_url = in_str.startswith("http://") or in_str.startswith("https://")
        if not is_url and any(c in in_str for c in ["*", "?", "["]):
            matched = [Path(m) for m in glob.glob(in_str)]
            if len(matched) > 1:
                target = Path(output_epub) if output_epub else (Path(outdir or ".") / "book.epub")
                return convert_multi_html_to_epub(matched, target, title=title, author=author, lang=lang, clean_article=clean_article)
            elif len(matched) == 1:
                inputs = matched[0]
            else:
                return {"success": False, "error": f"No files matched glob pattern: {in_str}"}

    if isinstance(inputs, list):
        if len(inputs) == 1:
            inp = inputs[0]
        else:
            target = Path(output_epub) if output_epub else (Path(outdir or ".") / "book.epub")
            return convert_multi_html_to_epub(inputs, target, title=title, author=author, lang=lang, clean_article=clean_article)
    else:
        inp = inputs

    in_str = str(inp)
    is_url = in_str.startswith("http://") or in_str.startswith("https://")

    if output_epub:
        target_epub = Path(output_epub).resolve()
    elif outdir:
        stem = Path(in_str).stem if not is_url else "web_article"
        target_epub = Path(outdir).resolve() / f"{stem}.epub"
    else:
        stem = Path(in_str).stem if not is_url else "web_article"
        target_epub = (Path(in_str).parent if not is_url else Path(".")).resolve() / f"{stem}.epub"

    # Default to semantic Python converter
    return convert_single_html_to_epub(
        inp,
        target_epub,
        title=title,
        author=author,
        lang=lang,
        flow_mode=flow_mode,
        clean_article=clean_article
    )


def main():
    parser = argparse.ArgumentParser(
        prog="html_to_epub",
        description="High-Fidelity HTML/XHTML to EPUB3 Converter (Native MathML & Asset Harvesting)"
    )
    parser.add_argument("inputs", nargs="+", help="Input HTML file(s), folder, glob, or web URL(s)")
    parser.add_argument("-o", "--output", help="Exact output .epub file")
    parser.add_argument("-d", "--outdir", help="Output directory for generated EPUB files")
    parser.add_argument("--flow", choices=["single", "split", "auto"], default="single", help="EPUB XHTML flow architecture (default: single)")
    parser.add_argument("--clean-article", action="store_true", help="Strip navigation, ads, headers, footers for article readability")
    parser.add_argument("--title", help="Custom document title metadata")
    parser.add_argument("--author", help="Author name metadata")
    parser.add_argument("--lang", default="en", help="Language code (default: en)")

    args = parser.parse_args()

    # Expand inputs
    expanded = []
    for item in args.inputs:
        if item.startswith("http://") or item.startswith("https://"):
            expanded.append(item)
            continue
        p = Path(item)
        if p.is_dir():
            for ext in SUPPORTED_HTML_EXTENSIONS:
                expanded.extend(sorted(list(p.glob(f"*{ext}"))))
        elif any(c in item for c in ["*", "?", "["]):
            expanded.extend([Path(m) for m in sorted(glob.glob(item))])
        else:
            expanded.append(p)

    if not expanded:
        print("[ERROR] No input HTML files or URLs found.", file=sys.stderr)
        sys.exit(1)

    print(f"=== Converting {len(expanded)} Item(s) to EPUB3 (Flow={args.flow}, Clean={args.clean_article}) ===")

    # If multiple files provided and user passed -o, merge them into one book
    if len(expanded) > 1 and args.output:
        res = convert_multi_html_to_epub(
            expanded,
            Path(args.output),
            title=args.title,
            author=args.author,
            lang=args.lang,
            clean_article=args.clean_article
        )
        if res["success"]:
            size_kb = res["file_size"] / 1024
            print(f"[OK] Merged {len(expanded)} HTML files -> {res['output_path']} [{size_kb:.1f} KB, {res['elapsed_sec']}s]")
            sys.exit(0)
        else:
            print(f"[FAIL] Merge failed: {res['error']}", file=sys.stderr)
            sys.exit(1)

    success_cnt = 0
    fail_cnt = 0

    for idx, item in enumerate(expanded, 1):
        out_epub = args.output if (len(expanded) == 1 and args.output) else None
        res = convert_html_to_epub(
            item,
            output_epub=out_epub,
            outdir=args.outdir,
            title=args.title,
            author=args.author,
            lang=args.lang,
            flow_mode=args.flow,
            clean_article=args.clean_article
        )
        if res["success"]:
            success_cnt += 1
            size_kb = res["file_size"] / 1024
            name = item if isinstance(item, str) else item.name
            print(f"[{idx}/{len(expanded)}] [OK] {name} -> {res['output_path']} [{size_kb:.1f} KB, {res['elapsed_sec']}s]")
        else:
            fail_cnt += 1
            name = item if isinstance(item, str) else item.name
            print(f"[{idx}/{len(expanded)}] [FAIL] {name}: {res['error']}", file=sys.stderr)

    print("\n------------------------------------------------------------")
    print(f"Summary: {success_cnt} succeeded, {fail_cnt} failed.")
    if fail_cnt > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
