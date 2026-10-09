#!/usr/bin/env python3
"""
Fidelity and Quality Verifier for PDF-to-EPUB Conversion.

Performs:
1. Structural EPUB validation (mimetype, package.opf, nav.xhtml, XML well-formedness).
2. Artifact & syntax linting (escaped HTML, raw markdown leaks, math squishing, broken images).
3. Line-by-line and sentence-by-sentence text coverage alignment against source PDF.
4. List and reference numbering validation.

Usage:
    python scripts/verify_fidelity.py --pdf sample.pdf --epub output.epub [--verbose]
"""

import argparse
import difflib
import html
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple, Any


def extract_pdf_sentences(pdf_path: str) -> Tuple[List[str], str]:
    """Extract clean sentences and full text from PDF."""
    raw_text = ""
    # Try pdftotext first (poppler) for clean layout extraction
    try:
        proc = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        raw_text = proc.stdout.decode("utf-8", errors="replace")
    except Exception:
        # Fallback to pypdf
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        raw_text = "\n".join(p.extract_text() for p in reader.pages)

    # Clean lines: remove running conference headers, page numbers, copyright notices
    cleaned_lines = []
    for line in raw_text.splitlines():
        s = line.strip()
        if not s:
            continue
        # Skip typical running headers and solitary page numbers
        if re.search(r"Proceedings of the Sixth International AAAI Conference", s, re.I):
            continue
        if re.search(r"IEEE.*International Conference", s, re.I):
            continue
        if "Authorized licensed use limited to" in s or "Restrictions apply" in s:
            continue
        if re.search(r"©\s*\d{4}\s*IEEE", s) or "978-1-" in s:
            continue
        if re.match(r"^\d{1,5}$", s):
            continue
        if "Copyright ©" in s or "All rights reserved" in s:
            continue
        cleaned_lines.append(s)

    full_text = " ".join(cleaned_lines)
    # De-hyphenate across line wraps
    full_text = re.sub(r"(\w+)-\s+(\w+)", r"\1\2", full_text)
    full_text = re.sub(r"\s+", " ", full_text).strip()

    # Split into sentences
    sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", full_text)
        if len(s.strip()) > 15
    ]
    return sentences, full_text


def extract_pptx_sentences(pptx_path: str) -> Tuple[List[str], str]:
    """Extract clean sentences and text from PowerPoint file."""
    import pptx
    from pptx.enum.shapes import PP_PLACEHOLDER
    p = Path(pptx_path).resolve()
    prs = pptx.Presentation(str(p))
    lines = []
    sentences = []
    for s in prs.slides:
        for shp in s.shapes:
            if shp.is_placeholder:
                try:
                    if shp.placeholder_format.type in (PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.HEADER, PP_PLACEHOLDER.SLIDE_NUMBER, PP_PLACEHOLDER.DATE):
                        continue
                except Exception:
                    pass
            if shp.has_text_frame:
                for p_elem in shp.text_frame.paragraphs:
                    t = p_elem.text.strip()
                    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", t).strip()
                    if not t or len(t) < 15 or re.match(r"^\d{1,3}$", t):
                        continue
                    if re.search(r"prof\.\s*dr\.|cse,\s*kuet|department of|all rights reserved", t, re.I):
                        continue
                    lines.append(t)
                    # For sentence coverage, split on punctuation per paragraph
                    for sent in re.split(r"(?<=[.!?])\s+", t):
                        s_clean = sent.strip()
                        if len(s_clean) > 15 and not re.match(r"^\d+$", s_clean):
                            # Skip pure broken equation glyph fragments in text
                            if not re.search(r"[\uF000-\uF8FF√=×\*\^]", s_clean):
                                sentences.append(s_clean)
    full_text = " ".join(lines)
    full_text = re.sub(r"\s+", " ", full_text).strip()
    return sentences, full_text


def extract_source_sentences(source_path: str) -> Tuple[List[str], str]:
    """Extract sentences from PDF, PPTX, or PPT source file."""
    p = Path(source_path)
    if p.suffix.lower() in [".pptx", ".ppt"]:
        return extract_pptx_sentences(str(p))
    return extract_pdf_sentences(str(p))


def extract_epub_content(epub_path: str) -> Dict[str, Any]:
    """Extract all text, XHTML files, images, and math from an EPUB3 archive."""
    res = {
        "text_by_file": {},
        "full_text": "",
        "xhtml_files": {},
        "images": [],
        "math_count": 0,
        "ol_count": 0,
        "li_count": 0,
        "manifest_items": [],
        "errors": []
    }

    if not Path(epub_path).exists():
        res["errors"].append(f"EPUB file not found: {epub_path}")
        return res

    try:
        with zipfile.ZipFile(str(epub_path), "r") as z:
            namelist = z.namelist()

            # Check mimetype
            if "mimetype" not in namelist:
                res["errors"].append("Missing 'mimetype' file in EPUB root.")
            else:
                mime_content = z.read("mimetype").decode("utf-8").strip()
                if mime_content != "application/epub+zip":
                    res["errors"].append(f"Invalid mimetype content: {mime_content}")

            # Check container.xml
            if "META-INF/container.xml" not in namelist:
                res["errors"].append("Missing 'META-INF/container.xml'.")

            # Collect image assets
            for name in namelist:
                if re.search(r"\.(png|jpg|jpeg|svg|webp)$", name, re.I):
                    data = z.read(name)
                    res["images"].append((name, len(data)))

            # Read package.opf to find spine documents
            opf_path = next((n for n in namelist if n.endswith(".opf")), None)
            spine_files = []
            if opf_path:
                try:
                    opf_tree = ET.fromstring(z.read(opf_path))
                    manifest = {
                        item.get("id"): item.get("href")
                        for item in opf_tree.iter("{http://www.idpf.org/2007/opf}item")
                    }
                    res["manifest_items"] = list(manifest.values())
                    for itemref in opf_tree.iter("{http://www.idpf.org/2007/opf}itemref"):
                        idref = itemref.get("idref")
                        if idref in manifest:
                            opf_dir = str(Path(opf_path).parent)
                            href = manifest[idref]
                            full_target = f"{opf_dir}/{href}" if opf_dir != "." else href
                            spine_files.append(full_target)
                except Exception as e:
                    res["errors"].append(f"Error parsing package.opf: {e}")

            # If spine not detected via OPF, fallback to all .xhtml files
            if not spine_files:
                spine_files = [n for n in namelist if n.endswith(".xhtml") and not n.endswith("nav.xhtml")]

            full_texts = []
            for sf in spine_files:
                if sf not in namelist:
                    res["errors"].append(f"Spine file {sf} missing from ZIP.")
                    continue
                raw_bytes = z.read(sf)
                # Check XML well-formedness
                try:
                    root = ET.fromstring(raw_bytes)
                except Exception as e:
                    res["errors"].append(f"XHTML XML parse error in {sf}: {e}")
                    continue

                xhtml_str = raw_bytes.decode("utf-8", errors="replace")
                res["xhtml_files"][sf] = xhtml_str
                res["math_count"] += xhtml_str.count("<math")
                res["ol_count"] += xhtml_str.count("<ol")
                res["li_count"] += xhtml_str.count("<li")

                # Extract text
                doc_text = "".join(root.itertext())
                res["text_by_file"][sf] = doc_text
                full_texts.append(doc_text)

            res["full_text"] = " ".join(full_texts)
            res["full_text"] = re.sub(r"(\w+)-\s+(\w+)", r"\1\2", res["full_text"])
            res["full_text"] = re.sub(r"\s+", " ", res["full_text"]).strip()

    except Exception as e:
        res["errors"].append(f"Failed to open EPUB as zip: {e}")

    return res


def lint_epub_markup(epub_data: Dict[str, Any]) -> List[str]:
    """Check for common conversion artifacts and syntax bugs."""
    issues = []

    for fname, xhtml in epub_data.get("xhtml_files", {}).items():
        # 1. Escaped HTML tags that should have been native elements
        escaped_tags = re.findall(r"&lt;/?(?:div|span|code|p|table|tr|td|th|br|strong|em)[^&]*&gt;", xhtml, re.I)
        if escaped_tags:
            issues.append(f"[{fname}] Escaped HTML tags detected (rendered as visible code): {escaped_tags[:3]}")

        # 2. Raw Markdown heading leaks (### Heading)
        raw_heads = re.findall(r"(?:^|\n)<p>#{1,6}\s+[^<]+</p>", xhtml)
        if raw_heads:
            issues.append(f"[{fname}] Raw Markdown header syntax leaked into text: {raw_heads[:2]}")

        # 3. Raw LaTeX math syntax leaks (\[ or \( or $$)
        raw_latex = re.findall(r"(?:\\\[|\\\(|\$\$)", xhtml)
        if raw_latex:
            issues.append(f"[{fname}] Unrendered LaTeX math delimiters found: {raw_latex[:3]}")

        # 4. Words jammed together due to currency $ math false positives
        squished_words = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+){3,}\b", xhtml)
        # Filter out common camelCase or legitimate identifiers
        filtered_squished = [w for w in squished_words if not w.startswith(("MathML", "JavaScript", "PubMed", "RotationToAxisAngle"))]
        if filtered_squished:
            issues.append(f"[{fname}] Possible squished text detected (e.g. from math regex): {filtered_squished[:3]}")

        # 5. Multiple disconnected <ol> blocks in references
        # If there are many <ol> but each contains only 1 <li>, that indicates the repeating "1. 1. 1." bug
        ol_matches = re.findall(r"<ol[^>]*>(.*?)</ol>", xhtml, re.DOTALL)
        single_item_ols = sum(1 for m in ol_matches if m.count("<li") == 1)
        if len(ol_matches) > 5 and single_item_ols / len(ol_matches) > 0.8:
            issues.append(f"[{fname}] Disconnected ordered lists detected ({single_item_ols}/{len(ol_matches)} single-item <ol>s; causes repeated '1. 1. 1.' bug).")

        # 6. Broken image references
        img_srcs = re.findall(r'<img[^>]+src="([^"]+)"', xhtml)
        existing_imgs = {name.split("/")[-1] for name, sz in epub_data.get("images", [])}
        for src in img_srcs:
            basename = src.split("/")[-1]
            if basename not in existing_imgs:
                issues.append(f"[{fname}] Image source '{src}' missing from EPUB assets.")

    return issues


def normalize_for_alignment(text: str) -> str:
    """Normalize typography and whitespace for fair sentence comparison."""
    t = text.lower()
    t = re.sub(r"[\u2018\u2019\u0027\u0060\u00b4]", "'", t)
    t = re.sub(r"[\u201c\u201d\u0022]", '"', t)
    t = re.sub(r"[\u2013\u2014\u2212]", "-", t)
    t = re.sub(r"-\s+", "", t)
    t = re.sub(r"[√]", "sqrt", t)
    t = re.sub(r"\s+", " ", t)
    # Kerning artifacts e.g. "pr ivacy" -> "privacy"
    t = re.sub(r"\bpr ivacy\b", "privacy", t)
    t = re.sub(r"\bpop ulation\b", "population", t)
    t = re.sub(r"\bcon cerns?\b", "concern", t)
    return t


def align_sentences(pdf_sentences: List[str], epub_text: str) -> Tuple[int, List[str], float]:
    """Check how many PDF sentences match in the EPUB text with robust normalization."""
    if not pdf_sentences:
        return 0, [], 100.0

    epub_norm = normalize_for_alignment(epub_text)
    epub_sents_norm = [
        normalize_for_alignment(s)
        for s in re.split(r"(?<=[.!?])\s+", epub_text)
        if len(s.strip()) > 15
    ]

    matched = 0
    missing = []

    for s in pdf_sentences:
        s_norm = normalize_for_alignment(s.strip())
        if len(s_norm) < 15:
            continue

        # Check 1: Prefix match (first 30 characters)
        if s_norm[:30] in epub_norm:
            matched += 1
            continue

        # Check 2: Suffix match (last 30 characters)
        if s_norm[-30:] in epub_norm:
            matched += 1
            continue

        # Check 3: Middle match (40 chars)
        mid_idx = max(0, len(s_norm) // 2 - 20)
        if s_norm[mid_idx:mid_idx + 40] in epub_norm:
            matched += 1
            continue

        # Check 4: Fuzzy sequence matcher against EPUB sentences
        close = difflib.get_close_matches(s_norm, epub_sents_norm, n=1, cutoff=0.70)
        if close:
            matched += 1
        else:
            missing.append(s.strip())

    total_valid = len([s for s in pdf_sentences if len(s.strip()) >= 15])
    coverage_pct = (matched / total_valid) * 100.0 if total_valid > 0 else 100.0
    return matched, missing, coverage_pct



def run_verification(source_path: str, epub_path: str, threshold: float = 95.0, verbose: bool = False) -> Dict[str, Any]:
    """Execute end-to-end fidelity check and return summary report."""
    report = {
        "source_path": str(source_path),
        "pdf_path": str(source_path),
        "epub_path": str(epub_path),
        "checks": {},
        "overall_pass": True,
        "coverage_pct": 0.0,
        "issues": []
    }

    # 1. Extract content
    source_sentences, source_full = extract_source_sentences(source_path)
    epub_data = extract_epub_content(epub_path)

    # 2. Container & XML Checks
    container_errors = epub_data.get("errors", [])
    report["checks"]["container_structure"] = {
        "pass": len(container_errors) == 0,
        "errors": container_errors
    }
    if container_errors:
        report["issues"].extend(container_errors)
        report["overall_pass"] = False

    # 3. Markup Linting
    markup_issues = lint_epub_markup(epub_data)
    report["checks"]["markup_linting"] = {
        "pass": len(markup_issues) == 0,
        "issues": markup_issues
    }
    if markup_issues:
        report["issues"].extend(markup_issues)
        report["overall_pass"] = False

    # 4. MathML check
    math_count = epub_data.get("math_count", 0)
    report["checks"]["mathml"] = {
        "math_elements_count": math_count,
        "has_mathml": math_count > 0
    }

    # 5. Images check
    images = epub_data.get("images", [])
    report["checks"]["images"] = {
        "image_count": len(images),
        "images": [{"name": n, "size_bytes": s} for n, s in images]
    }

    # 6. Sentence Alignment Coverage
    matched, missing, coverage = align_sentences(source_sentences, epub_data.get("full_text", ""))
    report["coverage_pct"] = round(coverage, 2)
    report["checks"]["sentence_alignment"] = {
        "source_sentences_total": len(source_sentences),
        "pdf_sentences_total": len(source_sentences),
        "matched_count": matched,
        "missing_count": len(missing),
        "coverage_pct": round(coverage, 2),
        "pass": coverage >= threshold,
        "missing_sample": missing[:5] if missing else []
    }

    if coverage < threshold:
        report["overall_pass"] = False
        report["issues"].append(
            f"Sentence coverage ({coverage:.1f}%) is below required threshold ({threshold:.1f}%)."
        )

    return report


def print_cli_report(report: Dict[str, Any], verbose: bool = False):
    """Print clean formatted terminal output."""
    print("=" * 72)
    print("      DOCUMENT-TO-EPUB FIDELITY & QUALITY VERIFICATION REPORT")
    print("=" * 72)
    print(f" Source Doc : {report.get('source_path', report.get('pdf_path'))}")
    print(f" Target EPUB: {report['epub_path']}")
    print("-" * 72)

    checks = report.get("checks", {})

    # Container check
    c_check = checks.get("container_structure", {})
    c_status = "[PASS]" if c_check.get("pass") else "[FAIL]"
    print(f"{c_status:8} EPUB Container & XML Well-Formedness")
    if not c_check.get("pass"):
        for err in c_check.get("errors", []):
            print(f"         ! {err}")

    # Markup Linting
    m_check = checks.get("markup_linting", {})
    m_status = "[PASS]" if m_check.get("pass") else "[FAIL]"
    print(f"{m_status:8} Markup Artifacts & Syntax Linting")
    if not m_check.get("pass"):
        for iss in m_check.get("issues", []):
            print(f"         ! {iss}")

    # MathML
    math_info = checks.get("mathml", {})
    print(f"[INFO]   Native MathML Elements: {math_info.get('math_elements_count', 0)}")

    # Images
    img_info = checks.get("images", {})
    print(f"[INFO]   Embedded Figures / Images: {img_info.get('image_count', 0)}")

    # Sentence Alignment
    align = checks.get("sentence_alignment", {})
    a_status = "[PASS]" if align.get("pass") else "[FAIL]"
    cov = align.get("coverage_pct", 0.0)
    tot = align.get("source_sentences_total", align.get("pdf_sentences_total", 0))
    mat = align.get("matched_count", 0)
    print(f"{a_status:8} Line-by-Line / Sentence Coverage: {mat}/{tot} ({cov:.1f}%)")

    missing = align.get("missing_sample", [])
    if missing and (not align.get("pass") or verbose):
        print("\n  Sample Unmatched Segments:")
        for idx, m in enumerate(missing[:5], 1):
            print(f"    {idx}. {m[:100]}...")

    print("-" * 72)
    overall_status = "SUCCESS" if report["overall_pass"] else "FAILURE"
    print(f" OVERALL VERDICT: {overall_status} (Coverage: {cov:.1f}%)")
    print("=" * 72)


def main():
    parser = argparse.ArgumentParser(description="Verify Document-to-EPUB Fidelity")
    parser.add_argument("--source", "--pdf", dest="source", required=True, help="Path to original PDF or PPTX/PPT file")
    parser.add_argument("--epub", required=True, help="Path to generated EPUB file")
    parser.add_argument("--threshold", type=float, default=95.0, help="Required sentence coverage percentage (default: 95.0)")
    parser.add_argument("--verbose", action="store_true", help="Print detailed unmatched sentences and debug info")
    parser.add_argument("--json", help="Save output report as JSON file")

    args = parser.parse_args()
    report = run_verification(args.source, args.epub, threshold=args.threshold, verbose=args.verbose)

    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Saved JSON report to {args.json}")

    print_cli_report(report, verbose=args.verbose)

    sys.exit(0 if report["overall_pass"] else 1)


if __name__ == "__main__":
    main()
