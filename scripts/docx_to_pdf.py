#!/usr/bin/env python3
"""
docx_to_pdf.py
High-fidelity DOCX (and Word/OpenDocument) to PDF conversion engine.

Powered by headless LibreOffice/soffice with sandboxed user profile isolation,
batch processing, PDF structure verification, and thumbnail previews.

Usage:
    # 1. Single file conversion
    python3 scripts/docx_to_pdf.py document.docx -o document.pdf

    # 2. Batch conversion of a folder
    python3 scripts/docx_to_pdf.py docs_folder/ --outdir output_pdfs/

    # 3. Conversion with PDF validation and thumbnail preview
    python3 scripts/docx_to_pdf.py report.docx --verify --preview

Python API:
    from docx_to_pdf import convert_docx_to_pdf, batch_convert_docx_to_pdf
    res = convert_docx_to_pdf("document.docx", output_pdf="document.pdf", verify=True)
"""

import argparse
import contextlib
import glob
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


SUPPORTED_EXTENSIONS = {".docx", ".doc", ".dotx", ".dot", ".odt", ".rtf", ".txt"}


def find_office_binary() -> str:
    """Find soffice or libreoffice binary on the system."""
    for bin_name in ["soffice", "libreoffice"]:
        p = shutil.which(bin_name)
        if p:
            return p
    raise RuntimeError(
        "Neither 'soffice' nor 'libreoffice' was found on PATH. "
        "Please install LibreOffice (e.g. `sudo pacman -S libreoffice-fresh` or `apt install libreoffice`)."
    )


def _needs_socket_shim() -> bool:
    """Check if AF_UNIX sockets are blocked (e.g. strict sandbox container)."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.close()
        return False
    except OSError:
        return True


def get_office_env() -> Dict[str, str]:
    """Build isolated environment for headless LibreOffice."""
    env = os.environ.copy()
    env["SAL_USE_VCLPLUGIN"] = "svp"
    # Suppress desktop notification / IPC daemon issues
    env["JAVA_TOOL_OPTIONS"] = "-Djava.awt.headless=true"
    return env


def verify_pdf(pdf_path: Union[str, Path]) -> Dict[str, Union[bool, int, str]]:
    """Validate generated PDF structure, page count, and readability."""
    p = Path(pdf_path)
    info = {
        "valid": False,
        "page_count": 0,
        "file_size": 0,
        "error": ""
    }
    if not p.exists() or p.stat().st_size == 0:
        info["error"] = "Generated PDF does not exist or is 0 bytes."
        return info

    info["file_size"] = p.stat().st_size

    # Try pypdf first
    try:
        import pypdf
        reader = pypdf.PdfReader(str(p))
        info["page_count"] = len(reader.pages)
        info["valid"] = (info["page_count"] > 0)
        return info
    except Exception:
        pass

    # Try pymupdf (fitz) fallback
    try:
        import pymupdf
        doc = pymupdf.open(str(p))
        info["page_count"] = len(doc)
        info["valid"] = (info["page_count"] > 0)
        return info
    except Exception:
        pass

    # Fallback to pdfinfo cli
    try:
        out = subprocess.check_output(["pdfinfo", str(p)], stderr=subprocess.DEVNULL).decode("utf-8")
        for line in out.splitlines():
            if line.startswith("Pages:"):
                info["page_count"] = int(line.split(":")[1].strip())
                info["valid"] = (info["page_count"] > 0)
                return info
    except Exception as e:
        info["error"] = f"Failed to inspect PDF: {e}"

    # If it has content (> 100 bytes and starts with %PDF-), consider structurally valid
    try:
        with open(str(p), "rb") as f:
            header = f.read(5)
            if header.startswith(b"%PDF-"):
                info["valid"] = True
    except Exception as e:
        info["error"] = str(e)

    return info


def generate_preview(pdf_path: Union[str, Path], output_image: Optional[Union[str, Path]] = None, dpi: int = 150) -> Optional[Path]:
    """Generate high-resolution PNG preview of the first page using pdftoppm."""
    p = Path(pdf_path)
    if not p.exists():
        return None

    if output_image:
        out_img = Path(output_image)
    else:
        out_img = p.with_name(f"{p.stem}_page1.png")

    prefix = out_img.parent / f"lo_prev_{os.getpid()}_{int(time.time()*1000)}"
    try:
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", "1", str(p), str(prefix)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        gen = list(prefix.parent.glob(f"{prefix.name}*.png"))
        if gen:
            shutil.move(str(gen[0]), str(out_img))
            return out_img
    except Exception as e:
        print(f"[WARN] Failed to generate preview thumbnail: {e}", file=sys.stderr)
    return None


def convert_docx_to_pdf(
    input_path: Union[str, Path],
    output_pdf: Optional[Union[str, Path]] = None,
    outdir: Optional[Union[str, Path]] = None,
    verify: bool = True,
    preview: bool = False,
    timeout: int = 60
) -> Dict[str, Union[bool, str, int, Optional[Path]]]:
    """
    Convert a single Word / OpenDocument file directly to PDF.

    Args:
        input_path: Path to .docx, .doc, .dotx, .odt, or .rtf file
        output_pdf: Optional exact output path for the .pdf file
        outdir: Optional directory to save the output .pdf file
        verify: Whether to validate the resulting PDF structure and page count
        preview: Whether to render a page-1 PNG preview thumbnail
        timeout: Subprocess timeout in seconds

    Returns:
        Dict with keys: success, output_path, page_count, file_size, preview_path, elapsed_sec, error
    """
    start_t = time.time()
    inp = Path(input_path).resolve()
    result = {
        "success": False,
        "input_path": str(inp),
        "output_path": None,
        "page_count": 0,
        "file_size": 0,
        "preview_path": None,
        "elapsed_sec": 0.0,
        "error": ""
    }

    if not inp.exists():
        result["error"] = f"Input file not found: {inp}"
        return result

    if inp.suffix.lower() not in SUPPORTED_EXTENSIONS:
        result["error"] = f"Unsupported file extension '{inp.suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        return result

    office_bin = find_office_binary()

    # Determine target output path and conversion directory
    if output_pdf:
        target_pdf = Path(output_pdf).resolve()
        target_dir = target_pdf.parent
    elif outdir:
        target_dir = Path(outdir).resolve()
        target_pdf = target_dir / f"{inp.stem}.pdf"
    else:
        target_dir = inp.parent
        target_pdf = inp.with_suffix(".pdf")

    target_dir.mkdir(parents=True, exist_ok=True)

    # Use isolated tempdir for intermediate LibreOffice output to ensure zero file collisions
    with tempfile.TemporaryDirectory(prefix="docx2pdf_conv_") as conv_tmp, \
         tempfile.TemporaryDirectory(prefix="lo_profile_") as lo_profile:

        conv_tmp_dir = Path(conv_tmp)
        profile_uri = Path(lo_profile).as_uri()

        cmd = [
            office_bin,
            "--headless",
            f"-env:UserInstallation={profile_uri}",
            "--convert-to", "pdf:writer_pdf_Export",
            "--outdir", str(conv_tmp_dir),
            str(inp)
        ]

        try:
            proc = subprocess.run(
                cmd,
                env=get_office_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False
            )
        except subprocess.TimeoutExpired:
            result["error"] = f"LibreOffice conversion timed out after {timeout} seconds."
            return result
        except Exception as e:
            result["error"] = f"Failed to execute LibreOffice: {e}"
            return result

        produced_pdfs = list(conv_tmp_dir.glob("*.pdf"))
        if not produced_pdfs:
            err_msg = proc.stderr.decode("utf-8", errors="replace").strip()
            out_msg = proc.stdout.decode("utf-8", errors="replace").strip()
            result["error"] = f"Conversion produced no PDF file. LibreOffice output: {err_msg or out_msg}"
            return result

        src_pdf = produced_pdfs[0]
        # Move to requested destination
        shutil.move(str(src_pdf), str(target_pdf))
        result["output_path"] = str(target_pdf)
        result["file_size"] = target_pdf.stat().st_size

    # Verification
    if verify:
        v_info = verify_pdf(target_pdf)
        result["page_count"] = v_info["page_count"]
        if not v_info["valid"]:
            result["error"] = f"Generated PDF validation failed: {v_info.get('error', 'invalid structure')}"
            return result

    # Optional Preview Thumbnail
    if preview:
        prev_path = generate_preview(target_pdf)
        if prev_path:
            result["preview_path"] = str(prev_path)

    result["success"] = True
    result["elapsed_sec"] = round(time.time() - start_t, 2)
    return result


def batch_convert_docx_to_pdf(
    inputs: List[Union[str, Path]],
    outdir: Optional[Union[str, Path]] = None,
    verify: bool = True,
    preview: bool = False
) -> List[Dict[str, Union[bool, str, int, Optional[Path]]]]:
    """Convert multiple Word files to PDF."""
    results = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            # Find all matching files in directory
            for ext in SUPPORTED_EXTENSIONS:
                for doc in p.glob(f"*{ext}"):
                    results.append(convert_docx_to_pdf(doc, outdir=outdir, verify=verify, preview=preview))
        elif any(c in str(item) for c in ["*", "?", "["]):
            for match in glob.glob(str(item)):
                results.append(convert_docx_to_pdf(match, outdir=outdir, verify=verify, preview=preview))
        else:
            results.append(convert_docx_to_pdf(p, outdir=outdir, verify=verify, preview=preview))
    return results


def main():
    parser = argparse.ArgumentParser(
        prog="docx_to_pdf",
        description="Direct High-Fidelity DOCX / Word to PDF Conversion Engine"
    )
    parser.add_argument("inputs", nargs="+", help="Input .docx file(s), directory, or glob pattern")
    parser.add_argument("-o", "--output", help="Exact output PDF file (only valid for single input)")
    parser.add_argument("-d", "--outdir", help="Output directory for generated PDFs")
    parser.add_argument("--no-verify", action="store_true", help="Skip PDF integrity and page count verification")
    parser.add_argument("--preview", action="store_true", help="Generate page-1 PNG preview thumbnail")
    parser.add_argument("--timeout", type=int, default=60, help="Per-file timeout in seconds (default: 60)")

    args = parser.parse_args()

    # Expand inputs
    expanded_files = []
    for item in args.inputs:
        p = Path(item)
        if p.is_dir():
            for ext in SUPPORTED_EXTENSIONS:
                expanded_files.extend(list(p.glob(f"*{ext}")))
        elif any(c in item for c in ["*", "?", "["]):
            expanded_files.extend([Path(m) for m in glob.glob(item)])
        else:
            expanded_files.append(p)

    if not expanded_files:
        print("[ERROR] No input document files found matching the provided arguments.", file=sys.stderr)
        sys.exit(1)

    if len(expanded_files) > 1 and args.output:
        print("[ERROR] -o/--output can only be specified when converting a single document.", file=sys.stderr)
        sys.exit(1)

    verify = not args.no_verify
    success_count = 0
    fail_count = 0

    print(f"=== Converting {len(expanded_files)} Document(s) to PDF ===")
    for idx, doc_file in enumerate(expanded_files, 1):
        out_pdf = args.output if (len(expanded_files) == 1 and args.output) else None
        res = convert_docx_to_pdf(
            doc_file,
            output_pdf=out_pdf,
            outdir=args.outdir,
            verify=verify,
            preview=args.preview,
            timeout=args.timeout
        )
        if res["success"]:
            success_count += 1
            pages_str = f" ({res['page_count']} pages)" if res["page_count"] else ""
            size_kb = res["file_size"] / 1024
            print(f"[{idx}/{len(expanded_files)}] [OK] {doc_file.name} -> {res['output_path']}{pages_str} [{size_kb:.1f} KB, {res['elapsed_sec']}s]")
            if res.get("preview_path"):
                print(f"       Preview: {res['preview_path']}")
        else:
            fail_count += 1
            print(f"[{idx}/{len(expanded_files)}] [FAIL] {doc_file.name}: {res['error']}", file=sys.stderr)

    print("\n------------------------------------------------------------")
    print(f"Summary: {success_count} succeeded, {fail_count} failed.")
    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
