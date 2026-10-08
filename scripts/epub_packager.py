#!/usr/bin/env python3
"""
pdf-to-epub: epub_packager.py
Self-contained EPUB3 compiler with native W3C MathML and intelligent single/multi-flow layout.
"""

import argparse
import datetime
import html
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple


EPUB_CSS = """
@charset "utf-8";

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

p {
    margin: 0 0 0.85em 0;
    text-align: justify;
    text-justify: inter-word;
    hyphens: auto;
}

/* Horizontal Divider */
hr {
    border: none;
    border-top: 1px solid #cbd5e1;
    margin: 2.2em auto;
    width: 90%;
}

/* Metadata & Author Header */
.author-block {
    margin-bottom: 2em;
    color: #334155;
    font-size: 0.98em;
    line-height: 1.5;
}

/* Figures & Images */
figure {
    margin: 1.8em auto;
    text-align: center;
    page-break-inside: avoid;
    break-inside: avoid;
    max-width: 100%;
}

figure img {
    max-width: 95%;
    height: auto;
    display: block;
    margin: 0 auto;
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

/* Mathematical Formulas (W3C MathML & EPUB3 Standard) */
math {
    font-family: "Cambria Math", "Latin Modern Math", "STIX Two Math", KaTeX_Math, serif;
    font-size: 1.05em;
    direction: ltr;
}

math[display="block"] {
    display: block;
    margin: 1.2em auto;
    text-align: center;
}

.math.display {
    margin: 1.2em 0;
    text-align: center;
    overflow-x: auto;
    padding: 0.4em 0;
}

.math.inline {
    display: inline;
    padding: 0 0.1em;
}

/* Tables */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 1.4em 0;
    font-size: 0.9em;
    overflow-x: auto;
    display: block;
}

th, td {
    border: 1px solid #cbd5e1;
    padding: 0.5em 0.75em;
    text-align: left;
}

th {
    background-color: #f1f5f9;
    font-weight: 600;
}

tr:nth-child(even) td {
    background-color: #f8fafc;
}

/* Code Blocks */
pre {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 0.8em 1em;
    overflow-x: auto;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
    font-size: 0.85em;
    line-height: 1.45;
}

code {
    font-family: "SFMono-Regular", Consolas, monospace;
    font-size: 0.88em;
    background-color: #f1f5f9;
    padding: 0.15em 0.3em;
    border-radius: 3px;
}

pre code {
    background: none;
    padding: 0;
}

/* Blockquotes */
blockquote {
    border-left: 3.5px solid #3b82f6;
    margin: 1.2em 0;
    padding: 0.5em 1.2em;
    color: #334155;
    background-color: #f8fafc;
    font-style: italic;
    border-radius: 0 4px 4px 0;
}

blockquote p {
    margin: 0.4em 0;
}

/* Lists */
ul, ol {
    margin: 0.8em 0 1.2em 1.5em;
    padding: 0;
}

li {
    margin-bottom: 0.4em;
}

/* Footnotes & Citations */
.footnote-ref {
    font-size: 0.75em;
    vertical-align: super;
    text-decoration: none;
    font-weight: bold;
    color: #2563eb;
}

.footnote-content {
    font-size: 0.85em;
    color: #64748b;
    border-top: 1px solid #e2e8f0;
    margin-top: 2em;
    padding-top: 0.8em;
}
"""


def latex_to_mathml(latex_str: str, display: str = "inline") -> str:
    """Convert LaTeX string to W3C MathML XML."""
    raw_tex = latex_str.strip()
    try:
        import latex2mathml.converter
        mml = latex2mathml.converter.convert(raw_tex, display=display)
        if display == "block":
            return f'<div class="math display">{mml}</div>'
        else:
            return f'<span class="math inline">{mml}</span>'
    except Exception:
        safe_tex = html.escape(raw_tex)
        if display == "block":
            return f'<div class="math display" role="math">\\[{safe_tex}\\]</div>'
        return f'<span class="math inline" role="math">\\({safe_tex}\\)</span>'


def slugify(text: str) -> str:
    """Generate a clean URL/anchor slug from a heading text."""
    clean = re.sub(r"[*_`]", "", text).lower().strip()
    slug = re.sub(r"[^a-z0-9_-]+", "-", clean).strip("-")
    return slug or "section"


def markdown_to_xhtml(md_text: str) -> str:
    """
    Robust lightweight Markdown-to-XHTML converter.
    Handles: Headers with IDs, paragraphs, hr dividers, images, tables, lists, code blocks, blockquotes, MathML math.
    """
    lines = md_text.splitlines()
    xhtml_out = []
    in_code_block = False
    code_block_lines = []
    in_table = False
    table_rows = []
    in_ul = False
    in_ol = False
    in_blockquote = False
    blockquote_lines = []
    p_buffer = []

    def flush_p():
        nonlocal p_buffer
        if p_buffer:
            text = " ".join(p_buffer).strip()
            if text:
                xhtml_out.append(f"<p>{format_inlines(text)}</p>")
            p_buffer = []

    def flush_list():
        nonlocal in_ul, in_ol
        if in_ul:
            xhtml_out.append("</ul>")
            in_ul = False
        if in_ol:
            xhtml_out.append("</ol>")
            in_ol = False

    def flush_blockquote():
        nonlocal in_blockquote, blockquote_lines
        if in_blockquote:
            content = " ".join(blockquote_lines)
            xhtml_out.append(f"<blockquote><p>{format_inlines(content)}</p></blockquote>")
            in_blockquote = False
            blockquote_lines = []

    def flush_table():
        nonlocal in_table, table_rows
        if in_table and table_rows:
            xhtml_out.append("<table>")
            header = table_rows[0]
            xhtml_out.append("<thead><tr>")
            for cell in header:
                xhtml_out.append(f"<th>{format_inlines(cell)}</th>")
            xhtml_out.append("</tr></thead>")
            if len(table_rows) > 1:
                xhtml_out.append("<tbody>")
                for row in table_rows[1:]:
                    xhtml_out.append("<tr>")
                    for cell in row:
                        xhtml_out.append(f"<td>{format_inlines(cell)}</td>")
                    xhtml_out.append("</tr>")
                xhtml_out.append("</tbody>")
            xhtml_out.append("</table>")
            in_table = False
            table_rows = []

    def format_inlines(text: str) -> str:
        # 1. Protect and convert math first to MathML
        math_tokens = {}

        def save_display_math(match):
            key = f"__MATH_DISP_{len(math_tokens)}__"
            math_tokens[key] = latex_to_mathml(match.group(1), display="block")
            return key

        def save_inline_math(match):
            key = f"__MATH_INL_{len(math_tokens)}__"
            math_tokens[key] = latex_to_mathml(match.group(1), display="inline")
            return key

        # Inline math: must not be followed by digits (currency like $10, $100) or spaces
        text = re.sub(r"(?<![\\\$])\$(?!\s|\d)(.+?)(?<!\s)\$(?!\d)", save_inline_math, text)

        # 2. Escape XML entities on non-math text
        text = html.escape(text, quote=False)

        # 3. Images: ![alt](src)
        def replace_img(match):
            alt, src = match.group(1), match.group(2)
            caption_html = f"<figcaption>{alt}</figcaption>" if alt.strip() else ""
            return f'<figure><img src="{src}" alt="{alt}"/>{caption_html}</figure>'
        text = re.sub(r"!\[(.*?)\]\((.*?)\)", replace_img, text)

        # 4. Links: [text](href)
        text = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', text)

        # 5. Bold & Italic
        text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)

        # 6. Inline Code: `code`
        text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text)

        # 7. Restore MathML
        for key, mml in math_tokens.items():
            text = text.replace(key, mml)

        return text

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()

        # Code block fence ```
        if stripped.startswith("```"):
            flush_p()
            flush_list()
            flush_blockquote()
            flush_table()
            if in_code_block:
                joined = html.escape("\n".join(code_block_lines))
                xhtml_out.append(f"<pre><code>{joined}</code></pre>")
                code_block_lines = []
                in_code_block = False
            else:
                in_code_block = True
            idx += 1
            continue

        if in_code_block:
            code_block_lines.append(line)
            idx += 1
            continue

        # Display Math block $$
        if stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 2:
            flush_p()
            flush_list()
            flush_blockquote()
            flush_table()
            math_content = stripped[2:-2].strip()
            xhtml_out.append(latex_to_mathml(math_content, display="block"))
            idx += 1
            continue

        # Horizontal Rule --- or *** or ___
        if re.match(r"^(\*{3,}|-{3,}|_{3,})$", stripped):
            flush_p()
            flush_list()
            flush_blockquote()
            flush_table()
            xhtml_out.append("<hr/>")
            idx += 1
            continue

        # Standalone Image / Figure block ![alt](src)
        m_img = re.match(r"^!\[(.*?)\]\((.*?)\)$", stripped)
        if m_img:
            flush_p()
            flush_list()
            flush_blockquote()
            flush_table()
            alt, src = m_img.group(1), m_img.group(2)
            caption_html = f"<figcaption>{format_inlines(alt)}</figcaption>" if alt.strip() else ""
            xhtml_out.append(f'<figure><img src="{src}" alt="{html.escape(alt, quote=True)}"/>{caption_html}</figure>')
            idx += 1
            continue

        # Blockquote >
        if stripped.startswith(">"):
            flush_p()
            flush_list()
            flush_table()
            in_blockquote = True
            blockquote_lines.append(stripped[1:].strip())
            idx += 1
            continue
        elif in_blockquote:
            flush_blockquote()

        # Table rows | ... |
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_p()
            flush_list()
            if re.match(r"^\|(\s*:?-+:?\s*\|)+$", stripped):
                idx += 1
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if not in_table:
                in_table = True
                table_rows = [cells]
            else:
                table_rows.append(cells)
            idx += 1
            continue
        elif in_table:
            flush_table()

        # Raw HTML block handling (e.g. <div class="...">, </div>, <br/>, etc.)
        if re.match(r"^</?(?:div|section|aside|header|footer|span|table|tr|td|th|strong|em|code|br)[^>]*>", stripped, re.IGNORECASE):
            flush_p()
            flush_list()
            flush_blockquote()
            flush_table()
            xhtml_out.append(stripped)
            idx += 1
            continue

        # Headings # .. ######
        m_head = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m_head:
            flush_p()
            flush_list()
            flush_blockquote()
            flush_table()
            level = len(m_head.group(1))
            raw_title = m_head.group(2).strip()
            title = format_inlines(raw_title)
            slug = slugify(raw_title)
            xhtml_out.append(f'<h{level} id="{slug}">{title}</h{level}>')
            idx += 1
            continue

        # Unordered list - or *
        m_ul = re.match(r"^[-*]\s+(.*)$", stripped)
        if m_ul:
            flush_p()
            if not in_ul:
                flush_list()
                xhtml_out.append("<ul>")
                in_ul = True
            item_text = format_inlines(m_ul.group(1))
            xhtml_out.append(f"<li>{item_text}</li>")
            idx += 1
            continue

        # Ordered list 1.
        m_ol = re.match(r"^\d+\.\s+(.*)$", stripped)
        if m_ol:
            flush_p()
            if not in_ol:
                flush_list()
                xhtml_out.append("<ol>")
                in_ol = True
            item_text = format_inlines(m_ol.group(1))
            xhtml_out.append(f"<li>{item_text}</li>")
            idx += 1
            continue

        # Blank line = paragraph break
        if not stripped:
            flush_p()
            if in_ol or in_ul:
                next_non_empty = None
                for lookahead in lines[idx + 1:]:
                    ls = lookahead.strip()
                    if ls:
                        next_non_empty = ls
                        break
                if in_ol and next_non_empty and re.match(r"^\d+\.\s+", next_non_empty):
                    idx += 1
                    continue
                elif in_ul and next_non_empty and re.match(r"^[-*]\s+", next_non_empty):
                    idx += 1
                    continue
                else:
                    flush_list()
            idx += 1
            continue

        # Regular text
        p_buffer.append(stripped)
        idx += 1

    # End of document flushes
    flush_p()
    flush_list()
    flush_blockquote()
    flush_table()

    return "\n".join(xhtml_out)


def extract_headings(md_text: str) -> List[Tuple[str, str, int]]:
    """Extract (title, slug, level) for all headings."""
    headings = []
    for line in md_text.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)$", line.strip())
        if m:
            lvl = len(m.group(1))
            raw_title = m.group(2).strip()
            clean_title = re.sub(r"[*_`]", "", raw_title).strip()
            slug = slugify(clean_title)
            headings.append((clean_title, slug, lvl))
    return headings


def split_into_chapters_by_h1(md_text: str) -> List[Tuple[str, str, int]]:
    """Split a Markdown document into chapters by top-level # headings."""
    lines = md_text.splitlines()
    chapters = []
    current_title = "Introduction"
    current_level = 1
    current_lines = []

    for line in lines:
        m = re.match(r"^(#)\s+(.*)$", line.strip())
        if m:
            if current_lines:
                chapters.append((current_title, "\n".join(current_lines), current_level))
                current_lines = []
            current_title = m.group(2).strip()
            current_lines.append(line)
        else:
            current_lines.append(line)

    if current_lines:
        chapters.append((current_title, "\n".join(current_lines), current_level))

    if not chapters:
        chapters.append(("Main Content", md_text, 1))

    return chapters


def build_epub3(
    markdown_path: str,
    output_epub: str,
    figures_dir: Optional[str] = None,
    title: str = "Converted Document",
    author: str = "Unknown Author",
    lang: str = "en",
    split_mode: str = "auto"
):
    """
    Compile Markdown file into a validated, beautiful EPUB3 container.
    split_mode:
      - 'auto': single-flow if document has <= 1 H1 (academic papers, articles); multi-chapter if > 1 H1.
      - 'single': force single continuous reading flow with anchor navigation (NO blank pages).
      - 'h1': force split on every top-level # heading.
    """
    md_file = Path(markdown_path).resolve()
    if not md_file.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_file}")

    md_content = md_file.read_text(encoding="utf-8")
    h1_headings = re.findall(r"^#\s+", md_content, re.MULTILINE)

    is_single_flow = (split_mode == "single") or (split_mode == "auto" and len(h1_headings) <= 1)

    doc_uuid = f"urn:uuid:{uuid.uuid4()}"
    modified_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with tempfile.TemporaryDirectory(prefix="epub_build_") as tmpdir:
        build_dir = Path(tmpdir)
        oebps = build_dir / "EPUB"
        meta_inf = build_dir / "META-INF"
        images_dir = oebps / "figures"

        oebps.mkdir(parents=True, exist_ok=True)
        meta_inf.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)

        # 1. mimetype (MUST be first, uncompressed)
        mimetype_path = build_dir / "mimetype"
        mimetype_path.write_bytes(b"application/epub+zip")

        # 2. META-INF/container.xml
        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
        (meta_inf / "container.xml").write_text(container_xml, encoding="utf-8")

        # 3. EPUB/styles.css
        (oebps / "styles.css").write_text(EPUB_CSS, encoding="utf-8")

        # 4. Copy figure assets
        asset_manifest = []
        source_figs = Path(figures_dir).resolve() if figures_dir else (md_file.parent / "figures")
        if source_figs.exists() and source_figs.is_dir():
            for img_file in source_figs.glob("*.*"):
                if img_file.suffix.lower() in [".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"]:
                    dest = images_dir / img_file.name
                    shutil.copy2(img_file, dest)
                    mime = "image/png" if img_file.suffix.lower() == ".png" else "image/jpeg"
                    if img_file.suffix.lower() == ".svg":
                        mime = "image/svg+xml"
                    asset_manifest.append((img_file.name, f"figures/{img_file.name}", mime))

        # 5. Build Content XHTML Documents
        chapter_manifest = []
        toc_entries = []

        if is_single_flow:
            # Single continuous reflowable document (Papers, articles, short reports)
            filename = "document.xhtml"
            doc_xhtml = markdown_to_xhtml(md_content)
            doc_xhtml = re.sub(r'src="(?:[\./]*figures/|/tmp/[^/]+/figures/)?([^"]+)"', r'src="figures/\1"', doc_xhtml)

            full_page = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}">
<head>
    <meta charset="utf-8"/>
    <title>{html.escape(title)}</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
{doc_xhtml}
</body>
</html>"""
            (oebps / filename).write_text(full_page, encoding="utf-8")
            chapter_manifest.append(("main_doc", filename))

            # Build TOC with internal anchor jumps (#slug)
            all_headings = extract_headings(md_content)
            for h_title, h_slug, h_lvl in all_headings:
                toc_entries.append((h_title, f"{filename}#{h_slug}", h_lvl))

        else:
            # Multi-chapter split (Books with multiple H1 sections)
            chapters_raw = split_into_chapters_by_h1(md_content)
            for idx, (chap_title, chap_md, chap_lvl) in enumerate(chapters_raw, 1):
                filename = f"chapter_{idx:03d}.xhtml"
                chap_xhtml = markdown_to_xhtml(chap_md)
                page_title = html.escape(chap_title)

                chap_xhtml = re.sub(r'src="(?:[\./]*figures/|/tmp/[^/]+/figures/)?([^"]+)"', r'src="figures/\1"', chap_xhtml)

                full_page = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}">
<head>
    <meta charset="utf-8"/>
    <title>{page_title}</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
{chap_xhtml}
</body>
</html>"""
                (oebps / filename).write_text(full_page, encoding="utf-8")
                chapter_manifest.append((f"chap_{idx}", filename))
                toc_entries.append((chap_title, filename, chap_lvl))

        # 6. Build EPUB3 Navigation Document: nav.xhtml
        nav_items_html = []
        for title_str, target_href, lvl in toc_entries:
            safe_title = html.escape(title_str)
            nav_items_html.append(f'        <li><a href="{target_href}">{safe_title}</a></li>')
        nav_body = "\n".join(nav_items_html)

        nav_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}">
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

        # 7. Build EPUB2 toc.ncx for legacy ereader fallback
        ncx_points = []
        for idx, (title_str, target_href, lvl) in enumerate(toc_entries, 1):
            safe_title = html.escape(title_str)
            ncx_points.append(f"""    <navPoint id="navPoint-{idx}" playOrder="{idx}">
      <navLabel><text>{safe_title}</text></navLabel>
      <content src="{target_href}"/>
    </navPoint>""")
        ncx_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{doc_uuid}"/>
    <meta name="dtb:depth" content="2"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{html.escape(title)}</text></docTitle>
  <navMap>
{'\n'.join(ncx_points)}
  </navMap>
</ncx>"""
        (oebps / "toc.ncx").write_text(ncx_xml, encoding="utf-8")

        # 8. Build package.opf
        manifest_entries = [
            '<item id="style" href="styles.css" media-type="text/css"/>',
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        ]
        for cid, cfname in chapter_manifest:
            chap_file = oebps / cfname
            prop_mathml = ' properties="mathml"' if (chap_file.exists() and "<math" in chap_file.read_text(encoding="utf-8")) else ""
            manifest_entries.append(f'<item id="{cid}" href="{cfname}" media-type="application/xhtml+xml"{prop_mathml}/>')

        for idx, (iname, ipath, imime) in enumerate(asset_manifest, 1):
            manifest_entries.append(f'<item id="img_{idx}" href="{ipath}" media-type="{imime}"/>')

        spine_entries = ['<itemref idref="' + cid + '"/>' for cid, _ in chapter_manifest]

        package_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id" xml:lang="{lang}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">{doc_uuid}</dc:identifier>
    <dc:title>{html.escape(title)}</dc:title>
    <dc:creator>{html.escape(author)}</dc:creator>
    <dc:language>{lang}</dc:language>
    <meta property="dcterms:modified">{modified_iso}</meta>
  </metadata>
  <manifest>
{chr(10).join("    " + e for e in manifest_entries)}
  </manifest>
  <spine toc="ncx">
{chr(10).join("    " + e for e in spine_entries)}
  </spine>
</package>"""
        (oebps / "package.opf").write_text(package_opf, encoding="utf-8")

        # 9. Pack into final EPUB zip file (mimetype first and uncompressed)
        out_file = Path(output_epub).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(str(out_file), "w") as z:
            z.write(str(mimetype_path), "mimetype", compress_type=zipfile.ZIP_STORED)
            for root, dirs, files in os.walk(str(build_dir)):
                for f in files:
                    full_p = Path(root) / f
                    rel_p = full_p.relative_to(build_dir)
                    if str(rel_p) == "mimetype":
                        continue
                    z.write(str(full_p), str(rel_p), compress_type=zipfile.ZIP_DEFLATED)

        flow_type = "single-flow continuous" if is_single_flow else f"{len(chapter_manifest)} chapters"
        print(f"[OK] Successfully built EPUB3 ({flow_type}): {out_file} ({len(toc_entries)} TOC entries, {len(asset_manifest)} figures)")


def main():
    parser = argparse.ArgumentParser(description="Standalone EPUB3 Compiler from Markdown")
    parser.add_argument("markdown", help="Path to input Markdown file")
    parser.add_argument("-o", "--output", required=True, help="Output .epub file path")
    parser.add_argument("--figures", help="Directory containing figure image assets")
    parser.add_argument("--title", default="Converted Document", help="Book title")
    parser.add_argument("--author", default="Unknown Author", help="Book author")
    parser.add_argument("--lang", default="en", help="Language code (default: en)")
    parser.add_argument("--split-mode", choices=["auto", "single", "h1"], default="auto", help="Chapter splitting strategy")

    args = parser.parse_args()
    build_epub3(
        markdown_path=args.markdown,
        output_epub=args.output,
        figures_dir=args.figures,
        title=args.title,
        author=args.author,
        lang=args.lang,
        split_mode=args.split_mode
    )


if __name__ == "__main__":
    main()
