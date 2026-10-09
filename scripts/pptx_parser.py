#!/usr/bin/env python3
"""
pdf-to-epub: pptx_parser.py
High-fidelity PowerPoint (PPTX / PPT) to Markdown & EPUB3 extraction engine.
Supports slide hierarchies, bullet points, tables, embedded pictures,
vector diagrams, OLE equations, speaker notes, and OCR for image-based slides.
"""

import argparse
import io
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

# Try importing pytesseract for OCR
try:
    import pytesseract
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

# Try importing PyMuPDF for PDF rendering/fallback
try:
    import fitz
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
    Useful for rendering full-slide visual layouts, OLE objects, and complex diagrams.
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
    """Clean special bullet characters (Wingdings, Private Use Area chars like \\uf06c)."""
    # Common bullet icons in PowerPoint fonts:
    text = re.sub(r"^[\uf06c\uf0a7\uf0d8\u2022\u25cf\u25cb\u25aa\u25ab\u25ba\u2192\-\*]\s*", "", text)
    return text.strip()


def run_ocr_on_image(image_bytes: bytes, lang: str = "eng") -> str:
    """Run OCR on image bytes using pytesseract if available."""
    if not HAS_OCR:
        return ""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        # Preprocess if tiny
        w, h = img.size
        if w < 300 or h < 300:
            img = img.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
        text = pytesseract.image_to_string(img, lang=lang)
        cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        return cleaned
    except Exception:
        return ""


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
        # Pad if ragged
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
    ocr: bool = True,
    ocr_lang: str = "eng",
    render_complex_slides: bool = True
) -> Dict[str, Any]:
    """
    Parse a PowerPoint file into rich Markdown, extracted figures, and metadata.
    Returns:
    {
        "title": str,
        "markdown": str,
        "figures": List[str],
        "events": List[Dict],
        "slide_count": int,
        "ocr_performed": int
    }
    """
    actual_pptx, cleanup_dir = ensure_pptx(pptx_path)
    prs = pptx.Presentation(actual_pptx)
    slide_count = len(prs.slides)

    fig_out = Path(figures_dir).resolve() if figures_dir else (Path(pptx_path).parent / "figures")
    fig_out.mkdir(parents=True, exist_ok=True)

    extracted_figures = []
    events = []
    md_sections = []
    ocr_count = 0

    # Determine document title
    doc_title = Path(pptx_path).stem
    first_slide_title = ""
    if prs.slides:
        s0 = prs.slides[0]
        if s0.shapes.title and s0.shapes.title.text.strip():
            first_slide_title = s0.shapes.title.text.strip().replace("\n", " ")

    if first_slide_title:
        doc_title = first_slide_title

    # Convert to PDF in background if complex slides/OLE objects exist or for slide crops
    pdf_backup_path = None
    pdf_doc = None
    try:
        pdf_backup_path = convert_presentation_to_pdf(actual_pptx)
        if HAS_PYMUPDF and pdf_backup_path:
            pdf_doc = fitz.open(pdf_backup_path)
    except Exception:
        pdf_backup_path = None
        pdf_doc = None

    # Process each slide sequentially
    for s_idx, slide in enumerate(prs.slides, 1):
        slide_title = ""
        slide_text_blocks = []
        slide_images = []
        slide_tables = []
        has_ole = False

        # 1. Detect Slide Title
        if slide.shapes.title and slide.shapes.title.text.strip():
            slide_title = slide.shapes.title.text.strip().replace("\n", " ")

        # 2. Extract Shapes
        for shape in extract_shapes_recursive(slide.shapes):
            # Check if this is the title shape
            if shape == slide.shapes.title:
                continue

            # Skip header / footer / slide number placeholders
            if shape.is_placeholder:
                try:
                    ph_type = shape.placeholder_format.type
                    if ph_type in (PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.HEADER, PP_PLACEHOLDER.SLIDE_NUMBER, PP_PLACEHOLDER.DATE):
                        continue
                except Exception:
                    pass

            # Embedded OLE objects (e.g. equations, charts)
            if shape.shape_type == MSO_SHAPE_TYPE.EMBEDDED_OLE_OBJECT:
                has_ole = True

            # Table
            if shape.has_table:
                tbl_md = table_to_markdown(shape.table)
                if tbl_md.strip():
                    slide_tables.append(tbl_md)
                continue

            # Picture
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                try:
                    blob = shape.image.blob
                    ext = shape.image.ext.lower()
                    if ext not in ["png", "jpg", "jpeg", "svg", "webp", "gif"]:
                        # Convert to PNG using Pillow
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
                    slide_images.append((img_name, blob))
                except Exception:
                    pass
                continue

            # Text frame
            if shape.has_text_frame:
                txt_f = shape.text_frame
                tf_paragraphs = []
                for p in txt_f.paragraphs:
                    p_text = clean_bullet_symbol(p.text)
                    if not p_text:
                        continue
                    # Ignore pure slide numbers or repeated footer text
                    if re.match(r"^\d{1,3}$", p_text) and len(p_text) <= 3:
                        continue

                    # If no slide title was found yet, use first prominent text
                    if not slide_title and p.level == 0 and len(p_text) < 80:
                        slide_title = p_text
                        continue

                    # Markdown bullet formatting based on level
                    indent = "  " * p.level
                    # Bold runs if styled
                    styled_text = ""
                    for run in p.runs:
                        t = run.text
                        if run.font.bold and t.strip():
                            styled_text += f"**{t}**"
                        elif run.font.italic and t.strip():
                            styled_text += f"*{t}*"
                        else:
                            styled_text += t
                    if not styled_text.strip():
                        styled_text = p_text
                    styled_text = clean_bullet_symbol(styled_text)

                    if p.level > 0 or len(txt_f.paragraphs) > 1:
                        tf_paragraphs.append(f"{indent}- {styled_text}")
                    else:
                        tf_paragraphs.append(styled_text)

                if tf_paragraphs:
                    slide_text_blocks.append("\n".join(tf_paragraphs))

        # Check speaker notes
        speaker_notes = ""
        try:
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes_raw = slide.notes_slide.notes_text_frame.text.strip()
                if notes_raw and not notes_raw.startswith("Slide "):
                    speaker_notes = notes_raw
        except Exception:
            pass

        # If slide title still empty, synthesize one
        if not slide_title:
            slide_title = f"Slide {s_idx}"

        slide_heading = f"# Slide {s_idx}: {slide_title}"
        events.append({"type": "heading", "level": 1, "title": f"Slide {s_idx}: {slide_title}", "page": s_idx})

        section_lines = [slide_heading, ""]

        # If the slide had OLE objects or if text is sparse, check PDF fallback text
        pdf_fallback_text = ""
        if pdf_doc and s_idx <= len(pdf_doc):
            try:
                p_page = pdf_doc[s_idx - 1]
                p_text = p_page.get_text()
                # If OLE objects exist, pdf_text often captures equations missed by python-pptx!
                if has_ole and p_text:
                    pdf_fallback_text = p_text.strip()
            except Exception:
                pass

        # Text blocks
        if slide_text_blocks:
            for b in slide_text_blocks:
                section_lines.append(b)
                section_lines.append("")

        # Tables
        for tbl in slide_tables:
            section_lines.append(tbl)
            section_lines.append("")

        # Images & OCR
        total_native_text_len = sum(len(b) for b in slide_text_blocks)
        for img_name, img_bytes in slide_images:
            section_lines.append(f"![Illustration for Slide {s_idx}](figures/{img_name})")
            section_lines.append("")

            # If slide has minimal native text or warning said SOME ARE IMAGES, run OCR!
            if ocr and HAS_OCR:
                ocr_text = run_ocr_on_image(img_bytes, lang=ocr_lang)
                if ocr_text and len(ocr_text) > 15:
                    ocr_count += 1
                    # Avoid duplicate if OCR matches native text
                    if ocr_text.lower() not in " ".join(slide_text_blocks).lower():
                        section_lines.append(f"**Extracted Text from Slide Image:**\n")
                        # Format as quote block
                        for oline in ocr_text.splitlines():
                            section_lines.append(f"> {oline}")
                        section_lines.append("")

        # If slide had NO native text and NO extracted images, but PDF fallback has a page:
        if total_native_text_len == 0 and not slide_images and pdf_doc and s_idx <= len(pdf_doc):
            try:
                p_page = pdf_doc[s_idx - 1]
                pix = p_page.get_pixmap(dpi=150)
                img_name = f"fig_s{s_idx:02d}_rendered.png"
                img_path = fig_out / img_name
                pix.save(str(img_path))
                extracted_figures.append(img_name)
                section_lines.append(f"![Slide {s_idx} Full View](figures/{img_name})")
                section_lines.append("")
                if ocr and HAS_OCR:
                    ocr_text = run_ocr_on_image(img_path.read_bytes(), lang=ocr_lang)
                    if ocr_text:
                        ocr_count += 1
                        section_lines.append(f"**Extracted Text:**\n")
                        for oline in ocr_text.splitlines():
                            section_lines.append(f"> {oline}")
                        section_lines.append("")
            except Exception:
                pass

        # If PDF has extra text (like OLE equations) not present in native text, append it
        if pdf_fallback_text and has_ole:
            clean_pdf_lines = [l.strip() for l in pdf_fallback_text.splitlines() if l.strip()]
            new_lines = [l for l in clean_pdf_lines if l.lower() not in " ".join(slide_text_blocks).lower()]
            if new_lines and len(new_lines) > 2:
                section_lines.append("**Supplementary Content & Formulas:**\n")
                for nl in new_lines:
                    section_lines.append(f"- {nl}")
                section_lines.append("")

        # Speaker Notes
        if speaker_notes:
            section_lines.append(f"> **Notes:** {speaker_notes}\n")

        md_sections.append("\n".join(section_lines).strip() + "\n")

    if pdf_doc:
        pdf_doc.close()
    if cleanup_dir:
        shutil.rmtree(cleanup_dir, ignore_errors=True)

    # Append events metadata block
    import json
    events_json = json.dumps(events, indent=2)
    final_md = "\n\n".join(md_sections) + f"\n\n```events\n{events_json}\n```\n"

    return {
        "title": doc_title,
        "markdown": final_md,
        "figures": extracted_figures,
        "events": events,
        "slide_count": slide_count,
        "ocr_performed": ocr_count
    }


def pptx_to_epub(
    pptx_path: str,
    output_epub: str,
    figures_dir: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = "Course Instructor",
    lang: str = "en",
    ocr: bool = True
) -> str:
    """
    Direct end-to-end PowerPoint to EPUB3 converter.
    """
    from epub_packager import build_epub3

    p = Path(pptx_path).resolve()
    fig_dir = Path(figures_dir).resolve() if figures_dir else (p.parent / f"{p.stem}_figures")
    fig_dir.mkdir(parents=True, exist_ok=True)

    result = parse_presentation(str(p), figures_dir=str(fig_dir), ocr=ocr)

    book_title = title or result["title"]
    md_temp = fig_dir / f"{p.stem}.md"
    md_temp.write_text(result["markdown"], encoding="utf-8")

    build_epub3(
        markdown_path=str(md_temp),
        output_epub=output_epub,
        figures_dir=str(fig_dir),
        title=book_title,
        author=author or "Course Instructor",
        lang=lang,
        split_mode="h1"
    )

    return output_epub


def main():
    parser = argparse.ArgumentParser(description="PowerPoint (PPTX / PPT) to Markdown & EPUB3 Converter")
    parser.add_argument("presentation", help="Path to input presentation (.pptx or .ppt)")
    parser.add_argument("-o", "--output", required=True, help="Output file (.md or .epub)")
    parser.add_argument("--figures", help="Directory to save extracted figure assets")
    parser.add_argument("--title", help="Custom book/document title")
    parser.add_argument("--author", default="Course Instructor", help="Author name")
    parser.add_argument("--lang", default="en", help="Language code")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR for image slides")

    args = parser.parse_args()
    out_path = Path(args.output).resolve()

    if out_path.suffix.lower() == ".epub":
        pptx_to_epub(
            pptx_path=args.presentation,
            output_epub=str(out_path),
            figures_dir=args.figures,
            title=args.title,
            author=args.author,
            lang=args.lang,
            ocr=not args.no_ocr
        )
        print(f"[OK] Successfully converted presentation to EPUB3: {out_path}")
    else:
        fig_dir = args.figures or str(out_path.parent / "figures")
        res = parse_presentation(args.presentation, figures_dir=fig_dir, ocr=not args.no_ocr)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(res["markdown"], encoding="utf-8")
        print(f"[OK] Extracted Markdown: {out_path} ({res['slide_count']} slides, {len(res['figures'])} figures, {res['ocr_performed']} OCR operations)")


if __name__ == "__main__":
    main()
