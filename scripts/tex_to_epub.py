#!/usr/bin/env python3
r"""
tex_to_epub.py
Direct LaTeX / TeX (.tex) to EPUB3 converter with native W3C MathML equations.

Key Capabilities:
1. Native W3C MathML: Compiles equations ($...$, $$...$$, \begin{equation}, etc.) directly into standard MathML.
2. Sandboxed Compilation: Keeps working directories completely clean; all auxiliary files (.aux, .log, .idv) are sandboxed in temp dirs.
3. PDF Figure Auto-Transcoding: Automatically converts vector PDF figures (\includegraphics{...pdf}) into high-res PNG for EPUB compliance.
4. Auto-Preamble Injection: Converts raw TeX snippets or notes lacking \documentclass by injecting a robust math/graphics preamble.
5. Flexible Flow Architecture: Supports both '--flow single' (single-flow document) and '--flow split' (per-section files).
6. Dual Engine: Powered by native 'tex4ebook' (TeX Live standard) with fallback to 'make4ht' + 'epub_packager'.

Usage:
    # 1. Direct conversion to EPUB3 with MathML
    python3 scripts/tex_to_epub.py document.tex -o document.epub

    # 2. Single continuous flow layout
    python3 scripts/tex_to_epub.py document.tex -o document.epub --flow single

    # 3. Batch conversion
    python3 scripts/tex_to_epub.py tex_folder/ --outdir output_epubs/

    # 4. Via unified CLI
    python3 scripts/cli.py tex2epub document.tex -o document.epub
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Union
from bs4 import BeautifulSoup


SUPPORTED_TEX_EXTENSIONS = {".tex", ".ltx"}


def find_tex_binary(name: str = "tex4ebook") -> Optional[str]:
    """Find tex4ebook or make4ht binary on PATH."""
    p = shutil.which(name)
    if p:
        return p
    return None


def sanitize_epub_fonts(epub_path: Union[str, Path], output_path: Optional[Union[str, Path]] = None) -> Path:
    """Strip any embedded system fonts from EPUB to keep file size compact."""
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


def prepare_tex_source(
    tex_path: Path,
    work_dir: Path,
    title: Optional[str] = None,
    author: Optional[str] = None
) -> Path:
    """
    Preprocess TeX source:
    - Injects preamble if missing.
    - Copies referenced local figures and converts PDF graphics to PNG.
    - Copies .bib bibliography files if present.
    """
    content = tex_path.read_text(encoding="utf-8", errors="replace")
    has_documentclass = bool(re.search(r"\\documentclass(\[[^\]]*\])?\{[^}]+\}", content))

    src_dir = tex_path.parent

    # 1. Handle referenced PDF images and strip restrictive scale options
    def replace_graphics(match):
        opt = match.group(1) or ""
        img_arg = match.group(2)
        candidates = [img_arg]
        if not img_arg.lower().endswith((".png", ".jpg", ".jpeg", ".svg", ".pdf")):
            candidates.append(f"{img_arg}.pdf")
            candidates.append(f"{img_arg}.png")

        final_arg = img_arg
        for cand in candidates:
            cand_p = (src_dir / cand).resolve()
            if cand_p.exists() and cand_p.suffix.lower() == ".pdf":
                # Convert PDF to PNG
                base_name = cand_p.stem
                out_png_name = f"{base_name}_converted.png"
                out_png_path = work_dir / out_png_name
                if shutil.which("pdftoppm"):
                    try:
                        subprocess.run(
                            ["pdftoppm", "-png", "-r", "200", "-singlefile", str(cand_p), str(work_dir / f"{base_name}_converted")],
                            check=True,
                            capture_output=True
                        )
                        final_arg = out_png_name
                        break
                    except Exception:
                        pass

        # Clean restrictive scale options that cause TeX4ht to emit 20px thumbnails
        if opt:
            cleaned_opt = re.sub(r"scale\s*=\s*[\d\.]+\s*,?", "", opt)
            cleaned_opt = re.sub(r",\s*\]", "]", cleaned_opt)
            cleaned_opt = re.sub(r"\[\s*,", "[", cleaned_opt)
            if cleaned_opt in ["[]", ""]:
                cleaned_opt = ""
            return f"\\includegraphics{cleaned_opt}{{{final_arg}}}"
        return f"\\includegraphics{{{final_arg}}}"

    content = re.sub(r"\\includegraphics(\[[^\]]*\])?\{([^}]+)\}", replace_graphics, content)

    # 2. Inject TeX4ht graphics override so LaTeX avoids loading dvips.def graphics driver.
    # The default driver corrupts TeX4ht's internal MathML font mapping tables, causing <mi>/<mo>/<mn> to be dropped.
    hcode_img_override = (
        "\n\\makeatletter\n"
        "\\AtBeginDocument{%\n"
        "  \\providecommand\\HCode[1]{}%\n"
        "  \\providecommand{\\includegraphics}[2][]{}%\n"
        "  \\renewcommand{\\includegraphics}[2][]{%\n"
        "    \\HCode{<img src=\"#2\" alt=\"PIC\" />}%\n"
        "  }%\n"
        "}\n"
        "\\makeatother\n"
    )

    if has_documentclass:
        doc_idx = content.find(r"\begin{document}")
        if doc_idx != -1:
            content = content[:doc_idx] + hcode_img_override + content[doc_idx:]
        else:
            content = hcode_img_override + content
    else:
        doc_title = title or tex_path.stem.replace("_", " ")
        doc_author = author or "Author"
        preamble = (
            "\\documentclass[11pt]{article}\n"
            "\\usepackage[utf8]{inputenc}\n"
            "\\usepackage{amsmath,amssymb,amsfonts,amsthm}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{booktabs}\n"
            "\\usepackage{hyperref}\n"
            f"\\title{{{doc_title}}}\n"
            f"\\author{{{doc_author}}}\n"
            + hcode_img_override +
            "\\begin{document}\n"
            "\\maketitle\n\n"
        )
        postamble = "\n\n\\end{document}\n"
        content = preamble + content + postamble

    # 3. Copy all local assets (images, styles, bib, bbl) into work_dir
    for item in src_dir.iterdir():
        if item.is_file() and item.suffix.lower() in [
            ".png", ".jpg", ".jpeg", ".gif", ".svg", ".bib", ".sty", ".cls", ".bst", ".bbl", ".bcf", ".xml", ".eps"
        ]:
            dest = work_dir / item.name
            if not dest.exists():
                shutil.copy2(item, dest)

    out_tex = work_dir / tex_path.name

    # Ensure target stem .bbl exists so LaTeX resolves citations on first pass without [?]
    target_bbl = work_dir / f"{out_tex.stem}.bbl"
    if not target_bbl.exists():
        main_bbl = src_dir / "main.bbl"
        bbl_files = list(src_dir.glob("*.bbl"))
        if main_bbl.exists():
            shutil.copy2(main_bbl, target_bbl)
        elif bbl_files:
            shutil.copy2(bbl_files[0], target_bbl)


    out_tex = work_dir / tex_path.name
    out_tex.write_text(content, encoding="utf-8")
    return out_tex


def merge_epub_to_single_flow(
    epub_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None
) -> Path:
    """
    Merges multiple split section XHTML files in a tex4ebook EPUB into a single
    continuous XHTML document.
    """
    src = Path(epub_path).resolve()
    dst = Path(output_path).resolve() if output_path else src

    temp_dir = tempfile.mkdtemp(prefix="tex_single_flow_")
    try:
        with zipfile.ZipFile(src, "r") as zin:
            zin.extractall(temp_dir)

        oebps_dir = Path(temp_dir) / "OEBPS"
        if not oebps_dir.exists():
            oebps_dir = Path(temp_dir)

        xhtml_files = sorted([
            f for f in oebps_dir.glob("*.xhtml")
            if not f.name.startswith("generic_toc") and not f.name.startswith("toc")
        ])

        if len(xhtml_files) <= 1:
            return dst

        # Identify main file and sections
        main_file = None
        section_files = []
        for xf in xhtml_files:
            if "se" not in xf.stem and main_file is None:
                main_file = xf
            else:
                section_files.append(xf)

        if not main_file:
            main_file = xhtml_files[0]
            section_files = xhtml_files[1:]

        with open(main_file, "r", encoding="utf-8") as fp:
            base_soup = BeautifulSoup(fp.read(), "html.parser")

        for sf in section_files:
            with open(sf, "r", encoding="utf-8") as fp:
                s = BeautifulSoup(fp.read(), "html.parser")
            sec_name = sf.stem
            sec_div = base_soup.new_tag("div", attrs={"class": f"tex-section {sec_name}", "id": sec_name})
            for child in list(s.body.children):
                sec_div.append(child)
            base_soup.body.append(sec_div)
            sf.unlink()

        with open(main_file, "w", encoding="utf-8") as fp:
            fp.write(str(base_soup))

        # Update content.opf
        opf_candidates = list(Path(temp_dir).glob("**/*.opf"))
        if opf_candidates:
            opf_p = opf_candidates[0]
            opf_text = opf_p.read_text(encoding="utf-8")
            for sf in section_files:
                opf_text = re.sub(rf'<item [^>]*href="{re.escape(sf.name)}"[^>]*/>\s*', '', opf_text)
                opf_text = re.sub(rf'<itemref [^>]*idref="{re.escape(sf.stem)}"[^>]*/>\s*', '', opf_text)
            opf_p.write_text(opf_text, encoding="utf-8")

        # Update toc / ncx
        for nav_p in list(Path(temp_dir).glob("**/*toc*.xhtml")) + list(Path(temp_dir).glob("**/*.ncx")):
            nav_text = nav_p.read_text(encoding="utf-8")
            for sf in section_files:
                nav_text = nav_text.replace(sf.name, f"{main_file.name}#{sf.stem}")
            nav_p.write_text(nav_text, encoding="utf-8")

        # Repack
        repack_epub(Path(temp_dir), dst)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return dst


def repack_epub(source_dir: Path, output_epub: Path) -> Path:
    """Repack a directory into an EPUB3 zip archive, ensuring mimetype is stored first uncompressed."""
    temp_out = output_epub.parent / f"tmp_repack_{os.getpid()}_{int(time.time()*1000)}.epub"
    with zipfile.ZipFile(temp_out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        mimetype_p = source_dir / "mimetype"
        if mimetype_p.exists():
            zout.writestr("mimetype", mimetype_p.read_bytes(), compress_type=zipfile.ZIP_STORED)

        for root, dirs, files in os.walk(source_dir):
            dirs.sort()
            for fname in sorted(files):
                full_p = Path(root) / fname
                rel_p = full_p.relative_to(source_dir)
                if str(rel_p) == "mimetype":
                    continue
                zout.write(full_p, str(rel_p))

    shutil.move(str(temp_out), str(output_epub))
    return output_epub


def postprocess_epub_xhtml(
    epub_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    assets_dir: Optional[Union[str, Path, List[Union[str, Path]]]] = None
) -> Path:
    """
    Post-processes the generated EPUB:
    1. Injects xmlns="http://www.w3.org/1998/Math/MathML" into all <math> tags.
    2. Injects xmlns:m="http://www.w3.org/1998/Math/MathML" into <html> tags.
    3. Strips hardcoded height/width attributes from <img> tags and enforces responsive CSS.
    4. Bundles referenced figures/images into OEBPS and declares them in content.opf manifest.
    5. Cleans ugly footnote underscore dividers (_{8,}) and dingbat artifacts into clean <hr class="footnote-rule"/>.
    6. Injects publication-grade responsive CSS and MathML styles.
    7. Ensures properties="mathml" is declared in content.opf.
    """
    src = Path(epub_path).resolve()
    dst = Path(output_path).resolve() if output_path else src

    temp_dir = tempfile.mkdtemp(prefix="tex_postprocess_")
    try:
        with zipfile.ZipFile(src, "r") as zin:
            zin.extractall(temp_dir)

        root_p = Path(temp_dir)
        oebps_dir = root_p / "OEBPS"
        if not oebps_dir.exists():
            oebps_dir = root_p

        # 1. Enrich existing CSS files with publication rules
        css_rules = (
            "\n\n/* === PDF-to-EPUB Publication Enhancements === */\n"
            "body {\n"
            "    font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Georgia, serif;\n"
            "    line-height: 1.65;\n"
            "    color: #1a1a1a;\n"
            "}\n"
            "img {\n"
            "    max-width: 100% !important;\n"
            "    height: auto !important;\n"
            "    display: block !important;\n"
            "    margin: 1.2em auto !important;\n"
            "}\n"
            "figure {\n"
            "    max-width: 100% !important;\n"
            "    margin: 1.5em auto !important;\n"
            "    text-align: center;\n"
            "}\n"
            "figcaption, .caption {\n"
            "    font-size: 0.9em;\n"
            "    color: #555555;\n"
            "    margin-top: 0.5em;\n"
            "    text-align: center;\n"
            "    font-style: italic;\n"
            "}\n"
            "hr.footnote-rule {\n"
            "    border: none !important;\n"
            "    border-top: 1px solid #d0d0d0 !important;\n"
            "    width: 35% !important;\n"
            "    margin: 2em 0 1em 0 !important;\n"
            "}\n"
            "math {\n"
            "    font-family: \"STIX Two Math\", \"Cambria Math\", \"Latin Modern Math\", serif;\n"
            "    font-style: normal;\n"
            "}\n"
            "math[display=\"block\"], .display-equation, table.equation {\n"
            "    display: block !important;\n"
            "    margin: 1.2em auto !important;\n"
            "    text-align: center !important;\n"
            "    overflow-x: auto !important;\n"
            "    overflow-y: hidden !important;\n"
            "    max-width: 100% !important;\n"
            "    padding: 0.5em 0;\n"
            "}\n"
            "math[display=\"inline\"] {\n"
            "    display: inline !important;\n"
            "    vertical-align: baseline !important;\n"
            "}\n"
            "table.equation td {\n"
            "    border: none !important;\n"
            "    padding: 0.2em 0.5em !important;\n"
            "}\n"
            "td.eq-no {\n"
            "    text-align: right !important;\n"
            "    font-weight: normal;\n"
            "}\n"
            "a {\n"
            "    color: #0366d6;\n"
            "    text-decoration: none;\n"
            "}\n"
            "a:hover {\n"
            "    text-decoration: underline;\n"
            "}\n"
        )

        css_files = list(root_p.glob("**/*.css"))
        for cf in css_files:
            cf_text = cf.read_text(encoding="utf-8", errors="replace")
            # Remove any broken mrow inline-block
            cf_text = re.sub(r'mrow\s*\{\s*display:\s*inline-block;\s*\}', '', cf_text)
            cf.write_text(cf_text + css_rules, encoding="utf-8")

        # 2. Process all XHTML files
        xhtml_files = list(root_p.glob("**/*.xhtml")) + list(root_p.glob("**/*.html"))
        has_math = False
        for xf in xhtml_files:
            text = xf.read_text(encoding="utf-8", errors="replace")

            # A. Ensure MathML namespaces
            if "<math" in text:
                has_math = True
                # Inject xmlns:m into <html> if not present
                text = re.sub(r'<html(?![^>]*\bxmlns:m\b)', r'<html xmlns:m="http://www.w3.org/1998/Math/MathML"', text)
                # Inject xmlns into all <math> tags if not present
                text = re.sub(r'<math(?![^>]*\bxmlns\b)', r'<math xmlns="http://www.w3.org/1998/Math/MathML"', text)

            # B. Clean <img> tags: remove dummy width/height and add responsive styling
            def clean_img(m):
                tag = m.group(0)
                tag = re.sub(r'\s+width=[\'"][^\'"]*[\'"]', '', tag)
                tag = re.sub(r'\s+height=[\'"][^\'"]*[\'"]', '', tag)
                if 'style="' in tag:
                    tag = tag.replace('style="', 'style="max-width: 100%; height: auto; display: block; margin: 1.2em auto; ')
                elif "style='" in tag:
                    tag = tag.replace("style='", "style='max-width: 100%; height: auto; display: block; margin: 1.2em auto; ")
                else:
                    tag = re.sub(r'<img\s+', '<img style="max-width: 100%; height: auto; display: block; margin: 1.2em auto;" ', tag)
                return tag

            text = re.sub(r'<img[^>]*>', clean_img, text)

            # C. Clean template noise: replace underscore lines and dingbat artifacts
            text = re.sub(r'<p[^>]*>\s*_{8,}.*?</p>', '<hr class="footnote-rule"/>', text, flags=re.DOTALL)
            text = re.sub(r'(\s*_{8,}\s*)+', '<hr class="footnote-rule"/>', text)
            text = re.sub(r'<span class=[\'"]pzdr[^\'"]*[\'"]>\s*✦\s*</span>', '', text)
            text = re.sub(r'<p[^>]*>\s*</p>', '', text)

            xf.write_text(text, encoding="utf-8")

        # 3. Bundle referenced images into OEBPS and update content.opf
        opf_files = list(root_p.glob("**/*.opf"))
        opf_p = opf_files[0] if opf_files else None

        if opf_p:
            opf_text = opf_p.read_text(encoding="utf-8", errors="replace")
            candidate_dirs = []
            if assets_dir:
                if isinstance(assets_dir, (list, tuple)):
                    for ad in assets_dir:
                        if ad:
                            candidate_dirs.append(Path(ad))
                else:
                    candidate_dirs.append(Path(assets_dir))
            candidate_dirs.append(src.parent)

            for xf in xhtml_files:
                text = xf.read_text(encoding="utf-8", errors="replace")
                img_srcs = re.findall(r'<img[^>]+src=[\'"]([^\'"]+)[\'"]', text)
                for src_name in img_srcs:
                    if src_name.startswith(("http://", "https://", "data:")):
                        continue
                    target_img = oebps_dir / src_name
                    if not target_img.exists():
                        for cd in candidate_dirs:
                            src_candidate = cd / src_name
                            if src_candidate.exists():
                                target_img.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(src_candidate, target_img)
                                break
                    if target_img.exists() and f'href="{src_name}"' not in opf_text and f"href='{src_name}'" not in opf_text:
                        lower_src = src_name.lower()
                        if lower_src.endswith(".png"):
                            mime = "image/png"
                        elif lower_src.endswith((".jpg", ".jpeg")):
                            mime = "image/jpeg"
                        elif lower_src.endswith(".gif"):
                            mime = "image/gif"
                        elif lower_src.endswith(".svg"):
                            mime = "image/svg+xml"
                        elif lower_src.endswith(".webp"):
                            mime = "image/webp"
                        else:
                            mime = "application/octet-stream"
                        item_id = f"img_{re.sub(r'[^a-zA-Z0-9_]', '_', src_name)}"
                        item_tag = f'<item href="{src_name}" id="{item_id}" media-type="{mime}"/>'
                        if "<manifest>" in opf_text:
                            opf_text = opf_text.replace("<manifest>", f"<manifest>\n{item_tag}")
                        elif "<manifest " in opf_text:
                            opf_text = re.sub(r'(<manifest[^>]*>)', rf'\1\n{item_tag}', opf_text)

            # Update MathML property if math is present
            if has_math:
                for xf in xhtml_files:
                    pattern = rf'(<item [^>]*href=[\'"]{re.escape(xf.name)}[\'"][^>]*)>'
                    def add_mathml_prop(m):
                        tag = m.group(1)
                        if "properties=" not in tag:
                            return f'{tag} properties="mathml">'
                        elif "mathml" not in tag:
                            return re.sub(r'properties=[\'"]([^\'"]*)[\'"]', r'properties="\1 mathml"', tag) + '>'
                        return m.group(0)
                    opf_text = re.sub(pattern, add_mathml_prop, opf_text)

            opf_p.write_text(opf_text, encoding="utf-8")

        # 4. Repack EPUB
        repack_epub(root_p, dst)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return dst


def convert_via_tex4ebook(
    tex_path: Path,
    output_epub: Path,
    mathml: bool = True,
    flow_mode: str = "split",
    timeout: int = 180
) -> Dict[str, Union[bool, str, int, float]]:
    """Convert LaTeX directly to EPUB3 using tex4ebook."""
    start_t = time.time()
    t4e_bin = find_tex_binary("tex4ebook")
    if not t4e_bin:
        return {"success": False, "error": "tex4ebook binary not found on PATH."}

    output_epub.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="tex_src_") as src_tmp, \
         tempfile.TemporaryDirectory(prefix="tex_build_") as build_tmp, \
         tempfile.TemporaryDirectory(prefix="tex_out_") as out_tmp:

        src_tmp_dir = Path(src_tmp)
        build_tmp_dir = Path(build_tmp)
        out_tmp_dir = Path(out_tmp)

        prepared_tex = prepare_tex_source(tex_path, src_tmp_dir)

        cmd = [
            t4e_bin,
            "-f", "epub3",
            "-s",  # shell escape
            "-B", str(build_tmp_dir),
            "-d", str(out_tmp_dir),
            prepared_tex.name
        ]
        if mathml:
            cmd.append("mathml")

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(src_tmp_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"tex4ebook timed out after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": f"Failed to run tex4ebook: {e}"}

        # Look for produced .epub in output dir
        produced = list(out_tmp_dir.glob("*.epub"))
        if not produced:
            # Fallback check in src_tmp_dir
            produced = list(src_tmp_dir.glob("*.epub"))

        if not produced:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            out = proc.stdout.decode("utf-8", errors="replace").strip()
            # Extract LaTeX error from log if present
            log_files = list(build_tmp_dir.glob("*.log")) + list(src_tmp_dir.glob("*.log"))
            log_snip = ""
            if log_files:
                log_txt = log_files[0].read_text(encoding="utf-8", errors="replace")
                err_lines = [l for l in log_txt.splitlines() if l.startswith("!") or "Error:" in l]
                if err_lines:
                    log_snip = " | " + "; ".join(err_lines[:3])

            return {"success": False, "error": f"No EPUB produced by tex4ebook: {err or out[:200]}{log_snip}"}

        shutil.move(str(produced[0]), str(output_epub))

        # Strip any heavy font declarations
        try:
            sanitize_epub_fonts(output_epub)
        except Exception:
            pass

        # Merge sections into single flow if requested
        if flow_mode == "single":
            try:
                merge_epub_to_single_flow(output_epub)
            except Exception:
                pass

        # Post-process EPUB for MathML namespaces, responsive images, and clean typography
        try:
            postprocess_epub_xhtml(output_epub, assets_dir=[src_tmp_dir, tex_path.parent])
        except Exception:
            pass

    return {
        "success": True,
        "output_path": str(output_epub),
        "file_size": output_epub.stat().st_size,
        "elapsed_sec": round(time.time() - start_t, 2),
        "engine": "tex4ebook"
    }


def convert_via_make4ht(
    tex_path: Path,
    output_epub: Path,
    title: Optional[str] = None,
    author: Optional[str] = None,
    timeout: int = 180
) -> Dict[str, Union[bool, str, int, float]]:
    """Fallback: Convert LaTeX to XHTML via make4ht and bundle using epub_packager."""
    start_t = time.time()
    m4h_bin = find_tex_binary("make4ht")
    if not m4h_bin:
        return {"success": False, "error": "make4ht binary not found."}

    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    try:
        from epub_packager import build_epub3
    except ImportError:
        return {"success": False, "error": "epub_packager module not found."}

    with tempfile.TemporaryDirectory(prefix="tex_make4ht_") as tmp_dir:
        tmp_p = Path(tmp_dir)
        prepared_tex = prepare_tex_source(tex_path, tmp_p, title=title, author=author)

        cmd = [m4h_bin, "-u", "-f", "xhtml", prepared_tex.name, "mathml"]
        try:
            proc = subprocess.run(cmd, cwd=str(tmp_p), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        except Exception as e:
            return {"success": False, "error": f"make4ht execution failed: {e}"}

        html_files = sorted(list(tmp_p.glob("*.html")) + list(tmp_p.glob("*.xhtml")))
        if not html_files:
            return {"success": False, "error": "make4ht produced no XHTML/HTML output."}

        main_html = html_files[0]
        html_content = main_html.read_text(encoding="utf-8")

        # Convert to Markdown/HTML wrapper for epub_packager
        md_file = tmp_p / "document.md"
        md_file.write_text(html_content, encoding="utf-8")

        figs_dir = tmp_p / "figures"
        figs_dir.mkdir(exist_ok=True)
        for img in tmp_p.glob("*.png"):
            if img.name != main_html.name:
                shutil.copy2(img, figs_dir / img.name)

        doc_title = title or tex_path.stem.replace("_", " ")
        build_epub3(
            markdown_path=str(md_file),
            output_epub=str(output_epub),
            figures_dir=str(figs_dir) if any(figs_dir.iterdir()) else None,
            title=doc_title,
            author=author or "TeX Document Author",
            split_mode="single"
        )

        try:
            postprocess_epub_xhtml(output_epub, assets_dir=[figs_dir, tmp_p, tex_path.parent])
        except Exception:
            pass


    return {
        "success": True,
        "output_path": str(output_epub),
        "file_size": output_epub.stat().st_size,
        "elapsed_sec": round(time.time() - start_t, 2),
        "engine": "make4ht+packager"
    }


def convert_tex_to_epub(
    input_path: Union[str, Path],
    output_epub: Optional[Union[str, Path]] = None,
    outdir: Optional[Union[str, Path]] = None,
    mathml: bool = True,
    flow_mode: str = "split",
    title: Optional[str] = None,
    author: Optional[str] = None,
    engine: str = "auto"
) -> Dict[str, Union[bool, str, int, float]]:
    """
    Directly convert a LaTeX (.tex) document to EPUB3.

    Args:
        input_path: Path to .tex or .ltx file
        output_epub: Target .epub file path
        outdir: Target directory
        mathml: Whether to enable native W3C MathML equations (default: True)
        flow_mode: 'split' (per-section files) or 'single' (continuous XHTML)
        title: Document title metadata
        author: Author name metadata
        engine: 'auto', 'tex4ebook', or 'make4ht'
    """
    inp = Path(input_path).resolve()
    if not inp.exists():
        return {"success": False, "error": f"Input TeX file not found: {inp}"}

    if inp.suffix.lower() not in SUPPORTED_TEX_EXTENSIONS:
        return {"success": False, "error": f"Unsupported extension {inp.suffix}. Supported: {sorted(SUPPORTED_TEX_EXTENSIONS)}"}

    if output_epub:
        target_epub = Path(output_epub).resolve()
    elif outdir:
        target_epub = Path(outdir).resolve() / f"{inp.stem}.epub"
    else:
        target_epub = inp.with_suffix(".epub")

    if engine == "make4ht":
        return convert_via_make4ht(inp, target_epub, title=title, author=author)

    if find_tex_binary("tex4ebook") and engine in ["auto", "tex4ebook"]:
        res = convert_via_tex4ebook(inp, target_epub, mathml=mathml, flow_mode=flow_mode)
        if res["success"]:
            return res
        if engine == "tex4ebook":
            return res

    # Fallback to make4ht
    if find_tex_binary("make4ht"):
        return convert_via_make4ht(inp, target_epub, title=title, author=author)

    return {"success": False, "error": "Neither tex4ebook nor make4ht are available on this system."}


def batch_convert_tex_to_epub(
    inputs: List[Union[str, Path]],
    outdir: Optional[Union[str, Path]] = None,
    mathml: bool = True,
    flow_mode: str = "split",
    engine: str = "auto"
) -> List[Dict[str, Union[bool, str, int, float]]]:
    """Convert multiple TeX files to EPUB3."""
    results = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            for ext in SUPPORTED_TEX_EXTENSIONS:
                for doc in p.glob(f"*{ext}"):
                    results.append(convert_tex_to_epub(doc, outdir=outdir, mathml=mathml, flow_mode=flow_mode, engine=engine))
        elif any(c in str(item) for c in ["*", "?", "["]):
            for match in glob.glob(str(item)):
                results.append(convert_tex_to_epub(match, outdir=outdir, mathml=mathml, flow_mode=flow_mode, engine=engine))
        else:
            results.append(convert_tex_to_epub(p, outdir=outdir, mathml=mathml, flow_mode=flow_mode, engine=engine))
    return results


def main():
    parser = argparse.ArgumentParser(
        prog="tex_to_epub",
        description="Direct High-Fidelity LaTeX (.tex) to EPUB3 Converter with Native MathML"
    )
    parser.add_argument("inputs", nargs="+", help="Input .tex file(s), folder, or glob pattern")
    parser.add_argument("-o", "--output", help="Exact output .epub file (only valid for single input)")
    parser.add_argument("-d", "--outdir", help="Output directory for generated EPUB files")
    parser.add_argument("--flow", choices=["split", "single"], default="split", help="EPUB XHTML flow architecture (default: split)")
    parser.add_argument("--no-mathml", action="store_true", help="Disable W3C MathML output")
    parser.add_argument("--engine", choices=["auto", "tex4ebook", "make4ht"], default="auto", help="Conversion engine")
    parser.add_argument("--title", help="Custom document title metadata")
    parser.add_argument("--author", help="Author name metadata")

    args = parser.parse_args()

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

    if len(expanded) > 1 and args.output:
        print("[ERROR] -o/--output can only be specified when converting a single document.", file=sys.stderr)
        sys.exit(1)

    mathml = not args.no_mathml
    success_cnt = 0
    fail_cnt = 0

    print(f"=== Converting {len(expanded)} TeX Document(s) to EPUB3 (MathML={mathml}, Flow={args.flow}) ===")
    for idx, tex_file in enumerate(expanded, 1):
        out_epub = args.output if (len(expanded) == 1 and args.output) else None
        res = convert_tex_to_epub(
            tex_file,
            output_epub=out_epub,
            outdir=args.outdir,
            mathml=mathml,
            flow_mode=args.flow,
            title=args.title,
            author=args.author,
            engine=args.engine
        )
        if res["success"]:
            success_cnt += 1
            size_kb = res["file_size"] / 1024
            print(f"[{idx}/{len(expanded)}] [OK] {tex_file.name} -> {res['output_path']} [{size_kb:.1f} KB, {res['elapsed_sec']}s, engine={res['engine']}]")
        else:
            fail_cnt += 1
            print(f"[{idx}/{len(expanded)}] [FAIL] {tex_file.name}: {res['error']}", file=sys.stderr)

    print("\n------------------------------------------------------------")
    print(f"Summary: {success_cnt} succeeded, {fail_cnt} failed.")
    if fail_cnt > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
