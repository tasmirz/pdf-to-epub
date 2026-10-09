#!/usr/bin/env python3
"""
pdf-to-epub: collage_maker.py
Adaptive PDF page grid collage generator and high-resolution bounding-box cropper.
Works universally using PyMuPDF (fitz) or system pdftoppm + Pillow.
"""

import argparse
import math
import os
import subprocess
import sys
import tempfile
import hashlib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def resolve_document_pdf(doc_path: str) -> str:
    """
    If input is PPTX or PPT, automatically convert to cached PDF via LibreOffice.
    Returns the path to a readable PDF.
    """
    p = Path(doc_path).resolve()
    if p.suffix.lower() in [".pptx", ".ppt"]:
        cache_dir = Path("/tmp/pdf_cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        stat = p.stat()
        file_hash = hashlib.md5(f"{p}:{stat.st_mtime}".encode()).hexdigest()[:12]
        cached_pdf = cache_dir / f"{p.stem}_{file_hash}.pdf"
        if not cached_pdf.exists():
            cmd = ["soffice", "--headless", "--convert-to", "pdf", str(p), "--outdir", str(cache_dir)]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            out_pdf = cache_dir / f"{p.stem}.pdf"
            if out_pdf.exists():
                out_pdf.rename(cached_pdf)
        if cached_pdf.exists():
            return str(cached_pdf)
    return str(p)


def get_pdf_page_count(pdf_path: str) -> int:
    """Detect total pages/slides in PDF or PPTX/PPT."""
    p = Path(pdf_path)
    if p.suffix.lower() == ".pptx":
        try:
            import pptx
            prs = pptx.Presentation(str(p))
            return len(prs.slides)
        except Exception:
            pass

    resolved_path = resolve_document_pdf(pdf_path)
    try:
        import fitz
        doc = fitz.open(resolved_path)
        count = len(doc)
        doc.close()
        return count
    except Exception:
        pass

    try:
        res = subprocess.run(["pdfinfo", resolved_path], capture_output=True, text=True, check=True)
        for line in res.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":")[1].strip())
    except Exception:
        pass

    try:
        import pypdf
        reader = pypdf.PdfReader(resolved_path)
        return len(reader.pages)
    except Exception:
        pass

    # Fallback using pdftoppm probe
    try:
        res = subprocess.run(["pdftoppm", "-png", "-f", "1", "-l", "1", resolved_path, "/dev/null"], capture_output=True, text=True)
        return 50
    except Exception:
        return 1


def render_page_image(pdf_path: str, page_num: int, dpi: int = 150) -> Image.Image:
    """Render a single 1-indexed PDF/PPTX page as a PIL Image."""
    pdf_path = resolve_document_pdf(pdf_path)
    # Method 1: PyMuPDF if available
    try:
        import fitz
        doc = fitz.open(pdf_path)
        page = doc.load_page(page_num - 1)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()
        return img
    except Exception:
        pass

    # Method 2: pdftoppm (standard on Linux/Poppler)
    with tempfile.TemporaryDirectory() as tmpdir:
        prefix = os.path.join(tmpdir, "page")
        cmd = [
            "pdftoppm",
            "-png",
            "-r", str(dpi),
            "-f", str(page_num),
            "-l", str(page_num),
            pdf_path,
            prefix
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        generated = sorted(Path(tmpdir).glob("page-*.png"))
        if not generated:
            raise RuntimeError(f"pdftoppm failed to render page {page_num}")
        img = Image.open(generated[0]).convert("RGB")
        return img.copy()


def draw_label(img: Image.Image, text: str) -> Image.Image:
    """Overlay a clear banner at the top of a page image with page index."""
    draw = ImageDraw.Draw(img)
    w, h = img.size
    banner_h = max(24, int(h * 0.035))
    draw.rectangle([(0, 0), (w, banner_h)], fill=(30, 41, 59))
    draw.rectangle([(0, 0), (w, h)], outline=(148, 163, 184), width=2)

    # Text
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    draw.text((10, max(2, int(banner_h * 0.15))), text, fill=(255, 255, 255), font=font)
    return img


def create_collage(pdf_path: str, start_page: int, end_page: int, grid_mode: str, output_path: str, dpi: int = 120):
    """
    Generate an NxN collage grid for the specified range.
    grid_mode: '3x3', '2x2', or '1x1'
    """
    grid_map = {
        "1x1": (1, 1),
        "2x2": (2, 2),
        "3x3": (3, 3)
    }
    cols, rows = grid_map.get(grid_mode, (3, 3))
    max_pages = cols * rows

    actual_end = min(end_page, start_page + max_pages - 1)
    page_numbers = list(range(start_page, actual_end + 1))

    if not page_numbers:
        raise ValueError(f"Invalid page range: {start_page} to {end_page}")

    page_images = []
    for p in page_numbers:
        img = render_page_image(pdf_path, p, dpi=dpi)
        img = draw_label(img, f"Page {p} [Range {start_page}-{actual_end}]")
        page_images.append((p, img))

    # Standardize cell size based on first page aspect ratio
    ref_w, ref_h = page_images[0][1].size
    cell_w, cell_h = ref_w, ref_h

    canvas_w = cell_w * cols
    canvas_h = cell_h * rows
    collage = Image.new("RGB", (canvas_w, canvas_h), color=(241, 245, 249))

    for idx, (p, img) in enumerate(page_images):
        c = idx % cols
        r = idx // cols
        resized = img.resize((cell_w, cell_h), Image.Resampling.LANCZOS)
        collage.paste(resized, (c * cell_w, r * cell_h))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    collage.save(str(out), "PNG", optimize=True)
    print(f"[OK] Collage ({grid_mode}) saved to {out} (Pages {page_numbers[0]}-{page_numbers[-1]}, size: {canvas_w}x{canvas_h})")


def crop_region(pdf_path: str, page_num: int, coords: str, output_path: str, dpi: int = 300):
    """
    Crop a bounding box from a high-resolution page.
    coords: "ymin,xmin,ymax,xmax" in normalized 0-1000 range or 0.0-1.0 float range.
    """
    parts = [float(x.strip()) for x in coords.split(",")]
    if len(parts) != 4:
        raise ValueError("coords must be formatted as 'ymin,xmin,ymax,xmax'")

    ymin, xmin, ymax, xmax = parts
    # Normalize if in 0-1000 coordinate space
    if any(val > 1.0 for val in parts):
        ymin /= 1000.0
        xmin /= 1000.0
        ymax /= 1000.0
        xmax /= 1000.0

    img = render_page_image(pdf_path, page_num, dpi=dpi)
    w, h = img.size

    left = int(max(0, xmin * w))
    top = int(max(0, ymin * h))
    right = int(min(w, xmax * w))
    bottom = int(min(h, ymax * h))

    if right <= left or bottom <= top:
        raise ValueError(f"Invalid crop box: left={left}, top={top}, right={right}, bottom={bottom}")

    cropped = img.crop((left, top, right, bottom))
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(str(out), "PNG", optimize=True)
    print(f"[OK] Cropped box [{ymin:.3f},{xmin:.3f},{ymax:.3f},{xmax:.3f}] from page {page_num} saved to {out} ({cropped.size[0]}x{cropped.size[1]}px)")


def main():
    parser = argparse.ArgumentParser(description="PDF Collage Maker & Region Cropper")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # Subcommand: count
    count_p = subparsers.add_parser("count", help="Get total page count of PDF")
    count_p.add_argument("pdf", help="Path to PDF file")

    # Subcommand: collage
    col_p = subparsers.add_parser("collage", help="Create a grid collage of pages")
    col_p.add_argument("pdf", help="Path to PDF file")
    col_p.add_argument("--start", "-s", type=int, default=1, help="Start page (1-indexed)")
    col_p.add_argument("--end", "-e", type=int, default=9, help="End page (inclusive)")
    col_p.add_argument("--grid", "-g", choices=["3x3", "2x2", "1x1"], default="3x3", help="Grid configuration")
    col_p.add_argument("--output", "-o", required=True, help="Output image file path (.png)")
    col_p.add_argument("--dpi", type=int, default=120, help="Rendering DPI (default: 120)")

    # Subcommand: crop
    crop_p = subparsers.add_parser("crop", help="Crop a bounding box region from a page")
    crop_p.add_argument("pdf", help="Path to PDF file")
    crop_p.add_argument("--page", "-p", type=int, required=True, help="Page number (1-indexed)")
    crop_p.add_argument("--coords", "-c", required=True, help="Normalized bbox ymin,xmin,ymax,xmax (0-1000 or 0.0-1.0)")
    crop_p.add_argument("--output", "-o", required=True, help="Output image path (.png)")
    crop_p.add_argument("--dpi", type=int, default=300, help="Rendering DPI (default: 300 for crisp figures)")

    args = parser.parse_args()

    if args.cmd == "count":
        cnt = get_pdf_page_count(args.pdf)
        print(cnt)
    elif args.cmd == "collage":
        create_collage(args.pdf, args.start, args.end, args.grid, args.output, dpi=args.dpi)
    elif args.cmd == "crop":
        crop_region(args.pdf, args.page, args.coords, args.output, dpi=args.dpi)


if __name__ == "__main__":
    main()
