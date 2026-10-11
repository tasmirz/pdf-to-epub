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
for cd in [
    HERE,
    Path.home() / ".gemini/config/skills/presentation-to-epub/scripts",
    Path.home() / ".gemini/config/skills/pdf-to-epub/scripts",
    Path("/home/user/Projects/pdf-to-epub/scripts")
]:
    if cd.exists() and str(cd) not in sys.path:
        sys.path.insert(0, str(cd))

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

    # docx2pdf
    p_d2p = subparsers.add_parser("docx2pdf", help="Directly convert DOCX / Word documents to PDF")
    p_d2p.add_argument("inputs", nargs="+", help="Input .docx file(s), folder, or glob pattern")
    p_d2p.add_argument("-o", "--output", help="Exact output PDF file (for single document input)")
    p_d2p.add_argument("-d", "--outdir", help="Output directory for generated PDFs")
    p_d2p.add_argument("--preview", action="store_true", help="Generate page 1 PNG preview thumbnail")
    # docx2epub (Direct DOCX -> EPUB, No PDF in between)
    p_d2e = subparsers.add_parser("docx2epub", help="Directly convert DOCX / Word documents to EPUB3 (No PDF)")
    p_d2e.add_argument("inputs", nargs="+", help="Input .docx file(s), folder, or glob pattern")
    p_d2e.add_argument("-o", "--output", help="Exact output EPUB file (for single document input)")
    p_d2e.add_argument("-d", "--outdir", help="Output directory for generated EPUBs")
    p_d2e.add_argument("--flow", choices=["single", "split"], default="single", help="EPUB XHTML flow architecture (default: single, matching Google Docs)")
    p_d2e.add_argument("--keep-fonts", action="store_true", help="Do not strip embedded system fonts")
    p_d2e.add_argument("--engine", choices=["auto", "office", "semantic"], default="auto", help="Conversion engine")
    p_d2e.add_argument("--title", help="Document title metadata")
    p_d2e.add_argument("--author", help="Author name metadata")

    # tex2epub (Direct TeX / LaTeX -> EPUB3 with Native MathML)
    p_t2e = subparsers.add_parser("tex2epub", help="Directly convert TeX / LaTeX documents (.tex) to EPUB3 (Native MathML)")
    p_t2e.add_argument("inputs", nargs="+", help="Input .tex file(s), folder, or glob pattern")
    p_t2e.add_argument("-o", "--output", help="Exact output EPUB file (for single document input)")
    p_t2e.add_argument("-d", "--outdir", help="Output directory for generated EPUBs")
    p_t2e.add_argument("--flow", choices=["split", "single"], default="split", help="EPUB XHTML flow architecture (default: split)")
    p_t2e.add_argument("--no-mathml", action="store_true", help="Disable W3C MathML equations")
    p_t2e.add_argument("--engine", choices=["auto", "tex4ebook", "make4ht"], default="auto", help="Conversion engine")
    p_t2e.add_argument("--title", help="Document title metadata")
    p_t2e.add_argument("--author", help="Author name metadata")

    # html2epub (Direct HTML / XHTML / Web Page -> EPUB3 with Native MathML & Asset Bundling)
    p_h2e = subparsers.add_parser("html2epub", help="Directly convert HTML / XHTML documents or URLs to EPUB3")
    p_h2e.add_argument("inputs", nargs="+", help="Input HTML file(s), folder, glob, or URL(s)")
    p_h2e.add_argument("-o", "--output", help="Exact output EPUB file")
    p_h2e.add_argument("-d", "--outdir", help="Output directory for generated EPUBs")
    p_h2e.add_argument("--flow", choices=["single", "split", "auto"], default="single", help="EPUB XHTML flow architecture (default: single)")
    p_h2e.add_argument("--clean-article", action="store_true", help="Clean ads, scripts, navigation chrome for article readability")
    p_h2e.add_argument("--title", help="Document title metadata")
    p_h2e.add_argument("--author", help="Author name metadata")
    p_h2e.add_argument("--lang", default="en", help="Language code (default: en)")

    # convert (universal)
    p_conv = subparsers.add_parser("convert", help="Universal converter for HTML, DOCX, PDF, PPTX, PPT, and TeX/LaTeX to EPUB3 or PDF")
    p_conv.add_argument("input", help="Path to input document (.html, .docx, .pdf, .pptx, .ppt, or .tex) or URL")
    p_conv.add_argument("-o", "--output", required=True, help="Output .epub or .pdf file")
    p_conv.add_argument("--flow", choices=["single", "split"], default="single", help="EPUB flow architecture for DOCX/TeX/HTML conversion")
    p_conv.add_argument("--clean-article", action="store_true", help="Clean ads, scripts, navigation chrome for HTML article readability")
    p_conv.add_argument("--title", help="Document title")
    p_conv.add_argument("--author", default="Unknown Author", help="Author name")
    p_conv.add_argument("--lang", default="en", help="Language code")
    p_conv.add_argument("--figures", help="Directory of figure image assets")
    p_conv.add_argument("--no-heading-stack", action="store_true", help="Disable heading stack")
    p_conv.add_argument("--no-filter-repetitive", action="store_true", help="Disable repetitive footer filtering")

    # crawl2epub (Web Novel Crawler & Sanitizer to EPUB3)
    p_c2e = subparsers.add_parser("crawl2epub", help="Crawl, sanitize, and convert a web novel into EPUB3")
    p_c2e.add_argument("url", help="Novel TOC or Chapter 1 URL")
    p_c2e.add_argument("-o", "--output", help="Output EPUB filename")
    p_c2e.add_argument("--engine", choices=["http", "playwright", "console"], help="Crawler engine (http=Fast/lightweight, playwright=JS browser, console=DevTools script)")
    p_c2e.add_argument("--pilot", type=int, default=None, help="Pilot run count (e.g. 5 chapters for verification)")
    p_c2e.add_argument("--max-chapters", type=int, default=1000, help="Maximum chapters to crawl")
    p_c2e.add_argument("--delay", type=float, default=1.0, help="Polite delay between requests (default: 1.0s)")

    # novel-probe
    p_nprobe = subparsers.add_parser("novel-probe", help="Inspect novel URL and generate draft site recipe")
    p_nprobe.add_argument("url", help="Novel URL to inspect")

    # novel-console-script
    p_ncs = subparsers.add_parser("novel-console-script", help="Generate DevTools console script for in-browser extraction")
    p_ncs.add_argument("url", help="Novel URL")
    p_ncs.add_argument("--max-chapters", type=int, default=500, help="Max chapters")
    p_ncs.add_argument("-o", "--output-js", help="Save script to file")

    # novel-import-zip
    p_nzip = subparsers.add_parser("novel-import-zip", help="Import browser-downloaded novel zip into EPUB3")
    p_nzip.add_argument("zip_file", help="Path to downloaded novel .zip")
    p_nzip.add_argument("-o", "--output", help="Output EPUB filename")

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
    elif args.subcommand == "docx2pdf":
        from docx_to_pdf import convert_docx_to_pdf, SUPPORTED_EXTENSIONS
        import glob
        expanded = []
        for item in args.inputs:
            p = Path(item)
            if p.is_dir():
                for ext in SUPPORTED_EXTENSIONS:
                    expanded.extend(list(p.glob(f"*{ext}")))
            elif any(c in item for c in ["*", "?", "["]):
                expanded.extend([Path(m) for m in glob.glob(item)])
            else:
                expanded.append(p)
        if not expanded:
            print("[ERROR] No input document files found.", file=sys.stderr)
            sys.exit(1)
        verify = not args.no_verify
        success_cnt = 0
        for doc_file in expanded:
            out_pdf = args.output if (len(expanded) == 1 and args.output) else None
            res = convert_docx_to_pdf(doc_file, output_pdf=out_pdf, outdir=args.outdir, verify=verify, preview=args.preview)
            if res["success"]:
                success_cnt += 1
                pages_str = f" ({res['page_count']} pages)" if res["page_count"] else ""
                print(f"[OK] {doc_file.name} -> {res['output_path']}{pages_str} [{res['elapsed_sec']}s]")
                if res.get("preview_path"):
                    print(f"     Preview: {res['preview_path']}")
            else:
                print(f"[FAIL] {doc_file.name}: {res['error']}", file=sys.stderr)
        if success_cnt == 0:
            sys.exit(1)
    elif args.subcommand == "docx2epub":
        from docx_to_epub import convert_docx_to_epub, SUPPORTED_DOCX_EXTENSIONS
        import glob
        expanded = []
        for item in args.inputs:
            p = Path(item)
            if p.is_dir():
                for ext in SUPPORTED_DOCX_EXTENSIONS:
                    expanded.extend(list(p.glob(f"*{ext}")))
            elif any(c in item for c in ["*", "?", "["]):
                expanded.extend([Path(m) for m in glob.glob(item)])
            else:
                expanded.append(p)
        if not expanded:
            print("[ERROR] No input document files found.", file=sys.stderr)
            sys.exit(1)
        strip_fonts = not args.keep_fonts
        success_cnt = 0
        for doc_file in expanded:
            out_epub = args.output if (len(expanded) == 1 and args.output) else None
            res = convert_docx_to_epub(
                doc_file,
                output_epub=out_epub,
                outdir=args.outdir,
                strip_fonts=strip_fonts,
                flow_mode=getattr(args, "flow", "single"),
                title=args.title,
                author=args.author,
                engine=args.engine
            )
            if res["success"]:
                success_cnt += 1
                size_kb = res["file_size"] / 1024
                print(f"[OK] {doc_file.name} -> {res['output_path']} [{size_kb:.1f} KB, {res['elapsed_sec']}s, engine={res['engine']}]")
            else:
                print(f"[FAIL] {doc_file.name}: {res['error']}", file=sys.stderr)
        if success_cnt == 0:
            sys.exit(1)
    elif args.subcommand == "tex2epub":
        from tex_to_epub import convert_tex_to_epub, SUPPORTED_TEX_EXTENSIONS
        import glob
        expanded = []
        for item in args.inputs:
            p = Path(item)
            if p.is_dir():
                for ext in SUPPORTED_TEX_EXTENSIONS:
                    expanded.extend(list(p.glob(f"*{ext}")))
            elif any(c in item for c in ["*", "?", "["]):
                expanded.extend([Path(m) for m in glob.glob(item)])
            else:
                expanded.append(p)
        if not expanded:
            print("[ERROR] No input .tex files found.", file=sys.stderr)
            sys.exit(1)
        mathml = not getattr(args, "no_mathml", False)
        success_cnt = 0
        for tex_file in expanded:
            out_epub = args.output if (len(expanded) == 1 and args.output) else None
            res = convert_tex_to_epub(
                tex_file,
                output_epub=out_epub,
                outdir=args.outdir,
                mathml=mathml,
                flow_mode=getattr(args, "flow", "split"),
                title=args.title,
                author=args.author,
                engine=args.engine
            )
            if res["success"]:
                success_cnt += 1
                size_kb = res["file_size"] / 1024
                print(f"[OK] {tex_file.name} -> {res['output_path']} [{size_kb:.1f} KB, {res['elapsed_sec']}s, engine={res['engine']}]")
            else:
                print(f"[FAIL] {tex_file.name}: {res['error']}", file=sys.stderr)
        if success_cnt == 0:
            sys.exit(1)
    elif args.subcommand == "html2epub":
        from html_to_epub import convert_html_to_epub, convert_multi_html_to_epub, SUPPORTED_HTML_EXTENSIONS
        import glob
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

        # Merge multiple files into one book if -o is specified
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
        for item in expanded:
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
                print(f"[OK] {name} -> {res['output_path']} [{size_kb:.1f} KB, {res['elapsed_sec']}s]")
            else:
                name = item if isinstance(item, str) else item.name
                print(f"[FAIL] {name}: {res['error']}", file=sys.stderr)
        if success_cnt == 0:
            sys.exit(1)
    elif args.subcommand == "convert":
        in_str = str(args.input)
        is_url = in_str.startswith("http://") or in_str.startswith("https://")
        in_p = Path(in_str).resolve() if not is_url else Path(in_str)
        out_p = Path(args.output).resolve()
        use_stack = not getattr(args, "no_heading_stack", False)
        filter_rep = not getattr(args, "no_filter_repetitive", False)
        clean_art = getattr(args, "clean_article", False)

        if is_url or (not is_url and in_p.suffix.lower() in [".html", ".htm", ".xhtml", ".shtml", ".mhtml"]):
            # Direct HTML / Web page to EPUB3
            from html_to_epub import convert_html_to_epub
            res = convert_html_to_epub(
                in_str if is_url else in_p,
                output_epub=out_p,
                flow_mode=getattr(args, "flow", "single"),
                clean_article=clean_art,
                title=args.title,
                author=args.author,
                lang=args.lang
            )
            if res["success"]:
                size_kb = res["file_size"] / 1024
                target_name = in_str if is_url else in_p.name
                print(f"[OK] Converted {target_name} directly to EPUB3 (native MathML & assets): {out_p} [{size_kb:.1f} KB, {res['elapsed_sec']}s]")
            else:
                print(f"[ERROR] Direct HTML to EPUB failed: {res['error']}", file=sys.stderr)
                sys.exit(1)
        elif in_p.suffix.lower() in [".tex", ".ltx"]:
            # Direct TeX / LaTeX to EPUB3 (Native MathML)
            from tex_to_epub import convert_tex_to_epub
            res = convert_tex_to_epub(
                str(in_p),
                output_epub=str(out_p),
                flow_mode=getattr(args, "flow", "split"),
                title=args.title,
                author=args.author
            )
            if res["success"]:
                size_kb = res["file_size"] / 1024
                print(f"[OK] Converted {in_p.name} directly to EPUB3 (native MathML): {out_p} [{size_kb:.1f} KB, {res['elapsed_sec']}s, engine={res['engine']}]")
            else:
                print(f"[ERROR] Direct TeX to EPUB failed: {res['error']}", file=sys.stderr)
                sys.exit(1)
        elif in_p.suffix.lower() in [".docx", ".doc", ".dotx", ".odt", ".rtf"]:
            if out_p.suffix.lower() == ".pdf":
                from docx_to_pdf import convert_docx_to_pdf
                res = convert_docx_to_pdf(str(in_p), output_pdf=str(out_p))
                if res["success"]:
                    print(f"[OK] Converted {in_p.name} to PDF: {out_p} ({res['page_count']} pages)")
                else:
                    print(f"[ERROR] DOCX conversion failed: {res['error']}", file=sys.stderr)
                    sys.exit(1)
            else:
                # Direct DOCX to EPUB (No intermediate PDF!)
                from docx_to_epub import convert_docx_to_epub
                res = convert_docx_to_epub(
                    str(in_p),
                    output_epub=str(out_p),
                    flow_mode=getattr(args, "flow", "single"),
                    title=args.title,
                    author=args.author
                )
                if res["success"]:
                    size_kb = res["file_size"] / 1024
                    print(f"[OK] Converted {in_p.name} directly to EPUB (no PDF): {out_p} [{size_kb:.1f} KB, {res['elapsed_sec']}s]")
                else:
                    print(f"[ERROR] Direct DOCX to EPUB failed: {res['error']}", file=sys.stderr)
                    sys.exit(1)
        elif in_p.suffix.lower() in [".pptx", ".ppt"]:
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
        elif in_p.suffix.lower() == ".zip":
            from novel_crawler import import_console_zip
            import_console_zip(in_p, output_epub=out_p)
            print(f"[OK] Converted novel zip archive to EPUB: {out_p}")
        elif in_p.suffix.lower() == ".md":
            from epub_packager import build_epub3
            build_epub3(str(in_p), str(out_p), figures_dir=args.figures, title=args.title or in_p.stem, author=args.author, lang=args.lang)
            print(f"[OK] Packaged {in_p.name} to EPUB: {out_p}")
        else:
            print(f"[NOTE] For PDF conversion, use subagents or convert to Markdown first then package.")
    elif args.subcommand == "crawl2epub":
        from novel_crawler import NovelSession, HttpFetcher, PlaywrightFetcher, prompt_engine_selection
        engine = args.engine or prompt_engine_selection()
        session = NovelSession(args.url)
        if args.delay:
            session.recipe.delay = args.delay

        if engine == "console":
            from novel_crawler import ConsoleScriptGenerator
            js = ConsoleScriptGenerator.generate(args.url, session.recipe.content_selector)
            print("\n[Engine: Console] Paste this script in your browser DevTools console:")
            print(js)
            sys.exit(0)

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
            print(f"[OK] Novel crawled and packaged to EPUB: {out_epub}")
        finally:
            if hasattr(fetcher, "close"):
                fetcher.close()
    elif args.subcommand == "novel-probe":
        from novel_crawler import NovelSession, HttpFetcher
        import json
        session = NovelSession(args.url)
        fetcher = HttpFetcher(session.recipe)
        report = session.probe(fetcher)
        print("\n[Probe Report]:")
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.subcommand == "novel-console-script":
        from novel_crawler import NovelSession, ConsoleScriptGenerator
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
    elif args.subcommand == "novel-import-zip":
        from novel_crawler import import_console_zip
        zip_path = Path(args.zip_file)
        out_epub = Path(args.output) if args.output else None
        import_console_zip(zip_path, out_epub)
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
