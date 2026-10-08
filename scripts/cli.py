#!/usr/bin/env python3
"""
pdf-to-epub: Unified Command-Line Interface
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

def run_collage(args):
    from collage_maker import main as cm_main
    sys.argv = ["collage_maker.py"] + args
    cm_main()

def run_packager(args):
    from epub_packager import main as ep_main
    sys.argv = ["epub_packager.py"] + args
    ep_main()

def run_probe(pdf_path: str, output_dir: str = "/tmp/pdf_probe"):
    from collage_maker import get_pdf_page_count, create_collage
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    count = get_pdf_page_count(pdf_path)
    print(f"=== Document Information ===")
    print(f"File: {pdf_path}")
    print(f"Total Pages: {count}")
    print(f"\nGenerating adaptive collage probes into: {out}")

    # Generate 3x3 probe
    end_3x3 = min(count, 9)
    p3 = out / "probe_3x3.png"
    create_collage(pdf_path, 1, end_3x3, "3x3", str(p3), dpi=120)

    # Generate 2x2 probe
    end_2x2 = min(count, 4)
    p2 = out / "probe_2x2.png"
    create_collage(pdf_path, 1, end_2x2, "2x2", str(p2), dpi=140)

    # Generate 1x1 probe
    p1 = out / "probe_1x1.png"
    create_collage(pdf_path, 1, 1, "1x1", str(p1), dpi=180)

    print("\n[OK] Probes created successfully:")
    print(f"  - 3x3 (Pages 1-{end_3x3}): {p3}")
    print(f"  - 2x2 (Pages 1-{end_2x2}): {p2}")
    print(f"  - 1x1 (Page 1 high-res): {p1}")

def run_install_skill():
    dest = Path.home() / ".gemini" / "config" / "skills" / "pdf-to-epub"
    dest.mkdir(parents=True, exist_ok=True)
    scripts_dest = dest / "scripts"
    scripts_dest.mkdir(parents=True, exist_ok=True)

    skill_src = HERE.parent / "SKILL.md"
    if skill_src.exists():
        shutil.copy2(skill_src, dest / "SKILL.md")
        print(f"Installed SKILL.md -> {dest / 'SKILL.md'}")

    for script in HERE.glob("*.py"):
        shutil.copy2(script, scripts_dest / script.name)
        (scripts_dest / script.name).chmod(0o755)
        print(f"Installed script -> {scripts_dest / script.name}")

    print(f"\n[OK] pdf-to-epub skill successfully installed to {dest}")

def main():
    parser = argparse.ArgumentParser(
        prog="pdf-to-epub",
        description="Vision-First Adaptive PDF to EPUB3 & Markdown Conversion Suite"
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # probe
    p_probe = subparsers.add_parser("probe", help="Generate adaptive 3x3, 2x2, 1x1 resolution probes")
    p_probe.add_argument("pdf", help="Path to input PDF")
    p_probe.add_argument("-o", "--output-dir", default="/tmp/pdf_probe", help="Output directory for probe images")

    # count
    p_count = subparsers.add_parser("count", help="Count pages in PDF")
    p_count.add_argument("pdf", help="Path to input PDF")

    # collage
    p_col = subparsers.add_parser("collage", help="Generate page grid collage")
    p_col.add_argument("pdf", help="Path to input PDF")
    p_col.add_argument("-s", "--start", type=int, default=1, help="Start page")
    p_col.add_argument("-e", "--end", type=int, default=9, help="End page")
    p_col.add_argument("-g", "--grid", choices=["3x3", "2x2", "1x1"], default="3x3")
    p_col.add_argument("-o", "--output", required=True, help="Output image file (.png)")
    p_col.add_argument("--dpi", type=int, default=120, help="Rendering DPI")

    # crop
    p_crop = subparsers.add_parser("crop", help="Crop bounding box region from page")
    p_crop.add_argument("pdf", help="Path to input PDF")
    p_crop.add_argument("-p", "--page", type=int, required=True, help="Page number (1-indexed)")
    p_crop.add_argument("-c", "--coords", required=True, help="Bounding box 'ymin,xmin,ymax,xmax' (0-1000 or 0.0-1.0)")
    p_crop.add_argument("-o", "--output", required=True, help="Output image file (.png)")
    p_crop.add_argument("--dpi", type=int, default=300, help="Rendering DPI")

    # package
    p_pkg = subparsers.add_parser("package", help="Compile Markdown and figures into EPUB3")
    p_pkg.add_argument("markdown", help="Path to Markdown document")
    p_pkg.add_argument("-o", "--output", required=True, help="Output .epub file")
    p_pkg.add_argument("--figures", help="Directory of figure image assets")
    p_pkg.add_argument("--title", default="Converted Document", help="Document title")
    p_pkg.add_argument("--author", default="Unknown Author", help="Author name")
    p_pkg.add_argument("--lang", default="en", help="Language code")

    # install-skill
    subparsers.add_parser("install-skill", help="Install/link into Antigravity global skills directory")

    args = parser.parse_args()

    if args.subcommand == "probe":
        run_probe(args.pdf, args.output_dir)
    elif args.subcommand == "count":
        from collage_maker import get_pdf_page_count
        print(get_pdf_page_count(args.pdf))
    elif args.subcommand == "collage":
        from collage_maker import create_collage
        create_collage(args.pdf, args.start, args.end, args.grid, args.output, dpi=args.dpi)
    elif args.subcommand == "crop":
        from collage_maker import crop_region
        crop_region(args.pdf, args.page, args.coords, args.output, dpi=args.dpi)
    elif args.subcommand == "package":
        from epub_packager import build_epub3
        build_epub3(args.markdown, args.output, figures_dir=args.figures, title=args.title, author=args.author, lang=args.lang)
    elif args.subcommand == "install-skill":
        run_install_skill()

if __name__ == "__main__":
    main()
