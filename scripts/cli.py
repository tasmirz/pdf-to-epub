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
    p_col.add_argument("-g", "--grid", choices=["3x3", "3x2", "2x3", "2x2", "1x1"], default="3x3", help="Grid configuration (3x2 is optimal for widescreen 16:9 slides)")
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

    # verify
    p_ver = subparsers.add_parser("verify", help="Run line-by-line fidelity and quality verification on EPUB against source PDF")
    p_ver.add_argument("--pdf", required=True, help="Path to source PDF")
    p_ver.add_argument("--epub", required=True, help="Path to generated EPUB")
    p_ver.add_argument("--threshold", type=float, default=95.0, help="Required sentence coverage percentage (default: 95.0)")
    p_ver.add_argument("--verbose", action="store_true", help="Print detailed unmatched sentences and debug info")
    p_ver.add_argument("--json", help="Save output report as JSON file")

    # pptx
    p_pptx = subparsers.add_parser("pptx", help="Convert PPTX/PPT presentation to EPUB3 or Markdown with DLA")
    p_pptx.add_argument("presentation", help="Path to input .pptx or .ppt presentation")
    p_pptx.add_argument("-o", "--output", required=True, help="Output .epub or .md file")
    p_pptx.add_argument("--figures", help="Directory to save extracted figure assets")
    p_pptx.add_argument("--title", help="Custom document title")
    p_pptx.add_argument("--author", default="Course Instructor", help="Author name")
    p_pptx.add_argument("--lang", default="en", help="Language code")
    p_pptx.add_argument("--no-heading-stack", action="store_true", help="Disable heading stack (split every slide)")
    p_pptx.add_argument("--no-filter-repetitive", action="store_true", help="Disable repetitive footer/header filtering")
    p_pptx.add_argument("--manifest", help="Optional path to output DLA manifest JSON")
    p_pptx.add_argument("--transcriptions", help="Optional JSON file mapping slide numbers to LaTeX transcriptions")

    # convert (universal)
    p_conv = subparsers.add_parser("convert", help="Universal converter for PDF, PPTX, and PPT to EPUB3")
    p_conv.add_argument("input", help="Path to input document (.pdf, .pptx, or .ppt)")
    p_conv.add_argument("-o", "--output", required=True, help="Output .epub file")
    p_conv.add_argument("--title", help="Document title")
    p_conv.add_argument("--author", default="Unknown Author", help="Author name")
    p_conv.add_argument("--lang", default="en", help="Language code")
    p_conv.add_argument("--figures", help="Directory of figure image assets")
    p_conv.add_argument("--no-heading-stack", action="store_true", help="Disable heading stack")
    p_conv.add_argument("--no-filter-repetitive", action="store_true", help="Disable repetitive footer filtering")

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
    elif args.subcommand == "pptx":
        from pptx_parser import pptx_to_epub, parse_presentation
        out_p = Path(args.output).resolve()
        use_stack = not getattr(args, "no_heading_stack", False)
        filter_rep = not getattr(args, "no_filter_repetitive", False)
        transcriptions_dict = None
        if getattr(args, "transcriptions", None) and Path(args.transcriptions).exists():
            import json
            raw_t = json.loads(Path(args.transcriptions).read_text(encoding="utf-8"))
            transcriptions_dict = {int(k): v for k, v in raw_t.items()}

        if out_p.suffix.lower() == ".epub":
            pptx_to_epub(
                args.presentation,
                str(out_p),
                figures_dir=args.figures,
                title=args.title,
                author=args.author,
                lang=args.lang,
                transcriptions=transcriptions_dict,
                use_heading_stack=use_stack,
                filter_repetitive=filter_rep
            )
            print(f"[OK] Converted presentation to EPUB: {out_p}")
        else:
            res = parse_presentation(
                args.presentation,
                figures_dir=args.figures,
                transcriptions=transcriptions_dict,
                use_heading_stack=use_stack,
                filter_repetitive=filter_rep
            )
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(res["markdown"], encoding="utf-8")
            if getattr(args, "manifest", None):
                import json
                Path(args.manifest).write_text(json.dumps(res["dla_manifest"], indent=2), encoding="utf-8")
            print(f"[OK] Extracted presentation to Markdown: {out_p}")
    elif args.subcommand == "convert":
        in_p = Path(args.input).resolve()
        out_p = Path(args.output).resolve()
        use_stack = not getattr(args, "no_heading_stack", False)
        filter_rep = not getattr(args, "no_filter_repetitive", False)
        if in_p.suffix.lower() in [".pptx", ".ppt"]:
            from pptx_parser import pptx_to_epub
            pptx_to_epub(
                str(in_p),
                str(out_p),
                figures_dir=args.figures,
                title=args.title,
                author=args.author,
                lang=args.lang,
                use_heading_stack=use_stack,
                filter_repetitive=filter_rep
            )
            print(f"[OK] Converted {in_p.name} to EPUB: {out_p}")
        elif in_p.suffix.lower() == ".md":
            from epub_packager import build_epub3
            build_epub3(str(in_p), str(out_p), figures_dir=args.figures, title=args.title or in_p.stem, author=args.author, lang=args.lang)
            print(f"[OK] Packaged {in_p.name} to EPUB: {out_p}")
        else:
            print(f"[NOTE] For PDF conversion, use subagents or convert to Markdown first then package.")
    elif args.subcommand == "verify":
        from verify_fidelity import run_verification, print_cli_report
        report = run_verification(args.pdf, args.epub, threshold=args.threshold, verbose=args.verbose)
        if args.json:
            import json
            Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print_cli_report(report, verbose=args.verbose)
        sys.exit(0 if report["overall_pass"] else 1)
    elif args.subcommand == "install-skill":
        run_install_skill()


if __name__ == "__main__":
    main()
