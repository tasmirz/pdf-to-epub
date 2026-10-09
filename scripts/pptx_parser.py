#!/usr/bin/env python3
"""
pdf-to-epub: pptx_parser.py
High-fidelity PowerPoint (PPTX / PPT) to Markdown & EPUB3 conversion engine.

Features:
- DLA (Document Layout Analysis) for intelligent region classification.
- Repetitive header & footer detection and filtering (purges redundant instructor
  names, slide counters, dates, and course titles).
- Heading Stack state machine: groups continuation slides under cohesive topics
  (H1 -> H2 -> H3) to prevent artificial 1-slide page breaks.
- Vision routing: differentiates between visual diagrams (kept as-is) and
  mathematical equations/text graphics.
- High-resolution equation cropping: replaces broken equation glyphs (• []) with
  crisp vector/raster formulas or LaTeX MathML.
- No pytesseract dependency: relies on DLA layout heuristics and Multimodal Vision.
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import pptx
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER
from PIL import Image

# Import DLA Engine
try:
    from dla_analyzer import (
        RepetitivePatternDetector,
        HeadingStack,
        DLAClassifier,
        ElementType,
        ActionType,
        EQUATION_GLYPH_REGEX
    )
except ImportError:
    # If run standalone from other path
    from scripts.dla_analyzer import (
        RepetitivePatternDetector,
        HeadingStack,
        DLAClassifier,
        ElementType,
        ActionType,
        EQUATION_GLYPH_REGEX
    )

# Try importing PyMuPDF for high-res slide rendering and equation cropping
try:
    import fitz  # pymupdf
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


def ensure_pptx(file_path: str) -> Tuple[str, Optional[str]]:
    """
    Ensure input is a PPTX file. If legacy .ppt is provided,
    convert it to .pptx using LibreOffice headless.
    Returns (pptx_path, cleanup_dir_or_none).
    """
    p = Path(file_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Presentation file not found: {p}")

    if p.suffix.lower() == ".ppt":
        tmpdir = tempfile.mkdtemp(prefix="ppt_convert_")
        cmd = [
            "soffice", "--headless", "--convert-to", "pptx",
            str(p), "--outdir", tmpdir
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise RuntimeError(f"LibreOffice failed to convert .ppt to .pptx: {res.stderr}")

        converted = list(Path(tmpdir).glob("*.pptx"))
        if not converted:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise RuntimeError(f"Converted .pptx not found in {tmpdir}")
        return str(converted[0]), tmpdir

    return str(p), None


def convert_presentation_to_pdf(presentation_path: str, output_pdf_dir: Optional[str] = None) -> str:
    """
    Convert presentation (PPT/PPTX) to PDF using LibreOffice headless.
    Used for rendering high-res slide figures, OLE equations, and visual layout probes.
    """
    out_dir = output_pdf_dir or tempfile.mkdtemp(prefix="pptx_pdf_")
    cmd = [
        "soffice", "--headless", "--convert-to", "pdf",
        str(presentation_path), "--outdir", out_dir
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"LibreOffice failed to convert presentation to PDF: {res.stderr}")

    base_name = Path(presentation_path).stem
    expected = Path(out_dir) / f"{base_name}.pdf"
    if not expected.exists():
        candidates = list(Path(out_dir).glob("*.pdf"))
        if candidates:
            return str(candidates[0])
        raise RuntimeError(f"Converted PDF not found in {out_dir}")
    return str(expected)


def clean_bullet_symbol(text: str) -> str:
    """Clean special bullet characters (Wingdings, Private Use Area chars)."""
    text = re.sub(r"^[\uf06c\uf0a7\uf0d8\u2022\u25cf\u25cb\u25aa\u25ab\u25ba\u2192\-\*]\s*", "", text)
    return text.strip()


def extract_shapes_recursive(shapes):
    """Recursively yield all shapes, including those nested in GROUP shapes."""
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for sub in extract_shapes_recursive(shape.shapes):
                yield sub
        else:
            yield shape


def table_to_markdown(table) -> str:
    """Convert a PowerPoint table shape to a clean Markdown table."""
    rows = []
    max_cols = max(len(row.cells) for row in table.rows) if table.rows else 0
    if max_cols == 0:
        return ""

    for row in table.rows:
        row_vals = []
        for cell in row.cells:
            cell_txt = " ".join(cell.text.split()).replace("|", "\\|")
            row_vals.append(cell_txt)
        while len(row_vals) < max_cols:
            row_vals.append("")
        rows.append(row_vals)

    if not rows:
        return ""

    header = rows[0]
    separator = ["---"] * max_cols
    body = rows[1:]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |"
    ]
    for r in body:
        lines.append("| " + " | ".join(r) + " |")

    return "\n" + "\n".join(lines) + "\n"


def parse_presentation(
    pptx_path: str,
    figures_dir: Optional[str] = None,
    transcriptions: Optional[Dict[int, str]] = None,
    use_heading_stack: bool = True,
    filter_repetitive: bool = True
) -> Dict[str, Any]:
    """
    Parse a PowerPoint presentation with Document Layout Analysis (DLA).

    Args:
        pptx_path: Path to presentation.
        figures_dir: Output directory for figures.
        transcriptions: Optional dict mapping slide_idx -> LaTeX/Markdown transcribed by Vision model.
        use_heading_stack: If True, merges consecutive slides under semantic H1/H2 chapters.
        filter_repetitive: If True, purges recurring footers, headers, and slide numbers.

    Returns:
        Dict with keys: 'title', 'markdown', 'figures', 'events', 'slide_count', 'dla_manifest'.
    """
    actual_pptx, cleanup_dir = ensure_pptx(pptx_path)
    prs = pptx.Presentation(actual_pptx)
    slide_count = len(prs.slides)
    slide_height = float(prs.slide_height) if prs.slide_height else 5400000.0

    fig_out = Path(figures_dir).resolve() if figures_dir else (Path(pptx_path).parent / "figures")
    fig_out.mkdir(parents=True, exist_ok=True)

    extracted_figures = []
    events = []
    md_sections = []
    dla_manifest = []

    # 1. Pass 1: Repetitive Header & Footer Detection
    pattern_detector = RepetitivePatternDetector()
    if filter_repetitive:
        slides_text_pos = []
        for slide in prs.slides:
            slide_items = []
            for shape in extract_shapes_recursive(slide.shapes):
                if shape.has_text_frame:
                    t_str = shape.text_frame.text.strip()
                    if t_str:
                        top_r = float(shape.top) / slide_height if shape.top is not None else 0.5
                        bot_r = float(shape.top + shape.height) / slide_height if (shape.top is not None and shape.height is not None) else 0.5
                        slide_items.append({
                            "text": t_str,
                            "top_ratio": top_r,
                            "bottom_ratio": bot_r
                        })
            slides_text_pos.append(slide_items)
        pattern_detector.scan_presentation_candidates(slides_text_pos)

    # 2. Document Title
    doc_title = Path(pptx_path).stem
    if prs.slides:
        s0 = prs.slides[0]
        if s0.shapes.title and s0.shapes.title.text.strip():
            doc_title = s0.shapes.title.text.strip().replace("\n", " ")
    doc_title = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", doc_title).strip()

    # 3. PDF Fallback for High-Res Equation Crops & Renderings
    pdf_backup_path = None
    pdf_doc = None
    try:
        pdf_backup_path = convert_presentation_to_pdf(actual_pptx)
        if HAS_PYMUPDF and pdf_backup_path:
            pdf_doc = fitz.open(pdf_backup_path)
    except Exception:
        pdf_backup_path = None
        pdf_doc = None

    # 4. Heading Stack Initialization
    heading_stack = HeadingStack()

    # 5. Pass 2: Slide Extraction & DLA Processing
    for s_idx, slide in enumerate(prs.slides, 1):
        slide_title = ""
        slide_text_blocks = []
        slide_images = []
        slide_tables = []
        has_ole = False

        # Detect Title
        if slide.shapes.title and slide.shapes.title.text.strip():
            slide_title = slide.shapes.title.text.strip().replace("\n", " ")
            slide_title = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", slide_title).strip()

        # Extract Shapes
        for shape in extract_shapes_recursive(slide.shapes):
            if shape == slide.shapes.title:
                continue

            # Standard Placeholder Filtering
            if shape.is_placeholder:
                try:
                    ph_type = shape.placeholder_format.type
                    if ph_type in (PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.HEADER, PP_PLACEHOLDER.SLIDE_NUMBER, PP_PLACEHOLDER.DATE):
                        continue
                except Exception:
                    pass

            top_r = float(shape.top) / slide_height if shape.top is not None else 0.5
            bot_r = float(shape.top + shape.height) / slide_height if (shape.top is not None and shape.height is not None) else 0.5

            # OLE Equation Objects
            if shape.shape_type == MSO_SHAPE_TYPE.EMBEDDED_OLE_OBJECT:
                has_ole = True

            # Table Shape
            if shape.has_table:
                tbl_md = table_to_markdown(shape.table)
                if tbl_md.strip():
                    slide_tables.append(tbl_md)
                continue

            # Picture Shape
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                try:
                    blob = shape.image.blob
                    ext = shape.image.ext.lower()
                    if ext not in ["png", "jpg", "jpeg", "svg", "webp", "gif"]:
                        try:
                            im = Image.open(io.BytesIO(blob))
                            buf = io.BytesIO()
                            im.save(buf, format="PNG")
                            blob = buf.getvalue()
                            ext = "png"
                        except Exception:
                            ext = "png"
                    img_name = f"fig_s{s_idx:02d}_{len(slide_images)+1:02d}.{ext}"
                    img_path = fig_out / img_name
                    img_path.write_bytes(blob)
                    extracted_figures.append(img_name)
                    slide_images.append((img_name, blob, shape.width, shape.height))
                except Exception:
                    pass
                continue

            # Text Frame
            if shape.has_text_frame:
                txt_f = shape.text_frame
                tf_paragraphs = []
                for p in txt_f.paragraphs:
                    p_text = clean_bullet_symbol(p.text)
                    if not p_text:
                        continue

                    # Filter repetitive headers/footers
                    if filter_repetitive and pattern_detector.is_repetitive(p_text, top_r, bot_r):
                        continue

                    # If no slide title was found yet, use first prominent text
                    if not slide_title and p.level == 0 and len(p_text) < 80:
                        slide_title = p_text
                        continue

                    # Markdown bullet formatting
                    indent = "  " * p.level
                    cleaned_p = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", p_text).strip()

                    # Bold / italic run preservation
                    styled_text = cleaned_p
                    non_empty_runs = [r for r in p.runs if r.text.strip()]
                    if non_empty_runs and all(r.font.bold for r in non_empty_runs):
                        styled_text = f"**{cleaned_p}**"
                    elif non_empty_runs and all(r.font.italic for r in non_empty_runs):
                        styled_text = f"*{cleaned_p}*"

                    # Check for broken equation glyphs in native text
                    if EQUATION_GLYPH_REGEX.search(cleaned_p):
                        has_ole = True
                        continue

                    if p.level > 0 or len(txt_f.paragraphs) > 1:
                        tf_paragraphs.append(f"{indent}- {styled_text}")
                    else:
                        tf_paragraphs.append(styled_text)

                if tf_paragraphs:
                    slide_text_blocks.append("\n".join(tf_paragraphs))

        # Speaker notes
        speaker_notes = ""
        try:
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes_raw = slide.notes_slide.notes_text_frame.text.strip()
                if notes_raw and not notes_raw.startswith("Slide "):
                    speaker_notes = notes_raw
        except Exception:
            pass

        if not slide_title:
            slide_title = f"Topic {s_idx}"

        # 6. Apply Heading Stack State Machine
        if use_heading_stack:
            heading_info = heading_stack.process_slide(slide_title, s_idx)
            heading_md = heading_info["heading_markdown"]
            if heading_info["is_new_h1"]:
                events.append({
                    "type": "heading",
                    "level": 1,
                    "title": heading_info["h1_title"],
                    "page": s_idx
                })
        else:
            heading_md = f"# Slide {s_idx}: {slide_title}"
            events.append({
                "type": "heading",
                "level": 1,
                "title": f"Slide {s_idx}: {slide_title}",
                "page": s_idx
            })

        section_lines = []
        if heading_md.strip():
            section_lines.append(heading_md)
            section_lines.append("")

        # Anchor for navigation and traceability
        section_lines.append(f'<span id="slide-{s_idx}" class="slide-ref"></span>')
        section_lines.append("")

        # Native text blocks
        for b in slide_text_blocks:
            section_lines.append(b)
            section_lines.append("")

        # Tables
        for tbl in slide_tables:
            section_lines.append(tbl)
            section_lines.append("")

        # DLA Image & Vision Classification
        total_text_len = sum(len(b) for b in slide_text_blocks)
        for img_name, img_bytes, w, h in slide_images:
            elem_type, action = DLAClassifier.inspect_image(
                image_bytes=img_bytes,
                slide_text_len=total_text_len,
                has_ole_on_slide=has_ole,
                image_width=w or 0,
                image_height=h or 0
            )

            dla_manifest.append({
                "slide": s_idx,
                "image": img_name,
                "type": elem_type.value,
                "action": action.value
            })

            # Check if vision transcription is available for this slide
            if transcriptions and s_idx in transcriptions:
                # Transcribed LaTeX/Markdown replaces or accompanies figure
                section_lines.append(f"![Illustration](figures/{img_name})")
                section_lines.append("")
                section_lines.append(transcriptions[s_idx])
                section_lines.append("")
            else:
                # Embed diagram as-is
                section_lines.append(f"![Illustration for Slide {s_idx}](figures/{img_name})")
                section_lines.append("")

        # Handle Equations / Complex Slides with OLE objects
        if has_ole:
            dla_manifest.append({
                "slide": s_idx,
                "type": "equation_block",
                "action": "transcribe_latex"
            })
            if transcriptions and s_idx in transcriptions:
                section_lines.append(transcriptions[s_idx])
                section_lines.append("")
            elif pdf_doc and s_idx <= len(pdf_doc):
                # High-res visual crop fallback: crop equation from rendered slide
                try:
                    p_page = pdf_doc[s_idx - 1]
                    pix = p_page.get_pixmap(dpi=200)
                    crop_name = f"eq_s{s_idx:02d}.png"
                    crop_path = fig_out / crop_name
                    pix.save(str(crop_path))
                    extracted_figures.append(crop_name)
                    section_lines.append(f"![Mathematical Formula](figures/{crop_name})")
                    section_lines.append("")
                except Exception:
                    pass

        # If slide was completely empty (scanned slide or pure graphic)
        if total_text_len == 0 and not slide_images and pdf_doc and s_idx <= len(pdf_doc):
            try:
                p_page = pdf_doc[s_idx - 1]
                pix = p_page.get_pixmap(dpi=150)
                img_name = f"fig_s{s_idx:02d}_rendered.png"
                img_path = fig_out / img_name
                pix.save(str(img_path))
                extracted_figures.append(img_name)
                section_lines.append(f"![Slide {s_idx} Full View](figures/{img_name})")
                section_lines.append("")
                dla_manifest.append({
                    "slide": s_idx,
                    "image": img_name,
                    "type": "transcribe_candidate",
                    "action": "transcribe_vision"
                })
            except Exception:
                pass

        # Speaker notes
        if speaker_notes:
            section_lines.append(f"> **Notes:** {speaker_notes}\n")

        md_sections.append("\n".join(section_lines).strip() + "\n")

    if pdf_doc:
        pdf_doc.close()
    if cleanup_dir:
        shutil.rmtree(cleanup_dir, ignore_errors=True)

    events_json = json.dumps(events, indent=2)
    final_md = "\n\n".join(md_sections) + f"\n\n```events\n{events_json}\n```\n"

    return {
        "title": doc_title,
        "markdown": final_md,
        "figures": extracted_figures,
        "events": events,
        "slide_count": slide_count,
        "dla_manifest": dla_manifest
    }


def pptx_to_epub(
    pptx_path: str,
    output_epub: str,
    figures_dir: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = "Course Instructor",
    lang: str = "en",
    transcriptions: Optional[Dict[int, str]] = None,
    use_heading_stack: bool = True,
    filter_repetitive: bool = True
) -> str:
    """
    Directly converts PowerPoint presentation to EPUB3 using DLA and Heading Stack.
    """
    from epub_packager import build_epub3

    res = parse_presentation(
        pptx_path=pptx_path,
        figures_dir=figures_dir,
        transcriptions=transcriptions,
        use_heading_stack=use_heading_stack,
        filter_repetitive=filter_repetitive
    )

    doc_title = title or res["title"]
    fig_dir = figures_dir or (Path(pptx_path).parent / "figures")

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(res["markdown"])
        temp_md = f.name

    try:
        out_path = Path(output_epub).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        build_epub3(
            markdown_path=temp_md,
            output_epub=str(out_path),
            figures_dir=str(fig_dir),
            title=doc_title,
            author=author,
            lang=lang
        )
        return str(out_path)
    finally:
        if os.path.exists(temp_md):
            os.remove(temp_md)


def main():
    parser = argparse.ArgumentParser(description="PowerPoint to Markdown/EPUB3 Converter with DLA")
    parser.add_argument("presentation", help="Path to input presentation (.pptx or .ppt)")
    parser.add_argument("-o", "--output", required=True, help="Output file (.epub or .md)")
    parser.add_argument("--figures", help="Directory to save extracted figure assets")
    parser.add_argument("--title", help="Custom document title")
    parser.add_argument("--author", default="Course Instructor", help="Author name")
    parser.add_argument("--lang", default="en", help="Language code")
    parser.add_argument("--no-heading-stack", action="store_true", help="Disable heading stack (split every slide)")
    parser.add_argument("--no-filter-repetitive", action="store_true", help="Disable repetitive footer/header filtering")
    parser.add_argument("--manifest", help="Optional path to output DLA manifest JSON")

    args = parser.parse_args()
    out_p = Path(args.output).resolve()

    if out_p.suffix.lower() == ".epub":
        pptx_to_epub(
            pptx_path=args.presentation,
            output_epub=str(out_p),
            figures_dir=args.figures,
            title=args.title,
            author=args.author,
            lang=args.lang,
            use_heading_stack=not args.no_heading_stack,
            filter_repetitive=not args.no_filter_repetitive
        )
        print(f"[OK] Converted {args.presentation} -> EPUB: {out_p}")
    else:
        res = parse_presentation(
            pptx_path=args.presentation,
            figures_dir=args.figures,
            use_heading_stack=not args.no_heading_stack,
            filter_repetitive=not args.no_filter_repetitive
        )
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(res["markdown"], encoding="utf-8")
        if args.manifest:
            Path(args.manifest).write_text(json.dumps(res["dla_manifest"], indent=2), encoding="utf-8")
        print(f"[OK] Extracted {args.presentation} -> Markdown: {out_p}")


if __name__ == "__main__":
    main()
