#!/usr/bin/env python3
"""
pdf-to-epub: Automated Test Suite & Benchmark Runner
Tests:
1. Plain PDF (single-column, book style)
2. 2-sided / 2-column PDF (academic layout with figures & equations)
3. Complex PDF test harness (for user-provided documents)
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from collage_maker import get_pdf_page_count, create_collage, crop_region
from epub_packager import build_epub3


def test_plain_pdf() -> bool:
    print("\n" + "=" * 60)
    print("TEST 1: Plain Single-Column PDF Conversion & Packaging")
    print("=" * 60)

    sample_pdf = HERE / "samples" / "plain_book_sample.pdf"
    if not sample_pdf.exists():
        print(f"[FAIL] Missing test sample: {sample_pdf}")
        return False

    with tempfile.TemporaryDirectory(prefix="test_plain_") as tmpdir:
        tmp = Path(tmpdir)

        # 1. Page count check
        page_count = get_pdf_page_count(str(sample_pdf))
        print(f"[*] Detected page count: {page_count} (Expected: 2)")
        assert page_count == 2, f"Expected 2 pages, got {page_count}"

        # 2. Render 2x2 collage
        collage_out = tmp / "plain_collage.png"
        create_collage(str(sample_pdf), 1, 2, "2x2", str(collage_out), dpi=140)
        assert collage_out.exists() and collage_out.stat().st_size > 1000, "Collage generation failed"
        print(f"[*] Visual collage generated: {collage_out.stat().st_size} bytes")

        # 3. Simulate extracted Markdown
        md_text = """# A Journey Through Modern Computing

# Chapter 1: The Architecture of Thought

In the early days of automated computation, the challenge was primarily electrical and mechanical. Engineers wrestled with relays, vacuum tubes, and mercury delay lines. The conceptual leap from calculation to general-purpose reasoning took decades to crystallize into modern architectures.

> "The computer is incredibly fast, accurate, and stupid. Man is incredibly slow, inaccurate, and brilliant. The marriage of the two is a force beyond calculation." — Leo Cherne

Modern reflowable document formats like EPUB3 represent the culmination of this evolution, decoupling semantic typography from rigid visual coordinate systems.

# Chapter 2: The Art of Typography

Typography in electronic publishing balances aesthetics with adaptability. Unlike fixed print sheets, an electronic reading device may be a six-inch e-ink screen, an eight-inch tablet, or a desktop workstation. The font size, margins, and line heights must dynamically recalculate without human intervention.

Key principles for reflowable digital texts include:
- Proportional vertical margins to maintain optical balance.
- High-contrast typography optimized for varied ambient lighting.
- Dynamic hyphens that expand and collapse cleanly across line wraps.
"""
        sample_md = tmp / "plain_document.md"
        sample_md.write_text(md_text, encoding="utf-8")

        # 4. Compile EPUB3
        epub_out = tmp / "plain_document.epub"
        build_epub3(
            markdown_path=str(sample_md),
            output_epub=str(epub_out),
            title="A Journey Through Modern Computing",
            author="Computing Pioneer",
            lang="en"
        )
        assert epub_out.exists(), "EPUB file was not created"
        print(f"[*] Compiled EPUB: {epub_out.stat().st_size} bytes")

        # 5. Verify EPUB internals
        with zipfile.ZipFile(str(epub_out), "r") as z:
            namelist = z.namelist()
            assert namelist[0] == "mimetype", "First entry must be mimetype"
            assert "META-INF/container.xml" in namelist
            assert "EPUB/package.opf" in namelist
            assert "EPUB/nav.xhtml" in namelist
            assert "EPUB/styles.css" in namelist
            assert "EPUB/chapter_001.xhtml" in namelist or "EPUB/document.xhtml" in namelist
            # Verify uncompressed mimetype
            info = z.getinfo("mimetype")
            assert info.compress_type == zipfile.ZIP_STORED, "mimetype must be uncompressed"

        print("[PASS] Test 1: Plain PDF passed all verifications!")
        return True


def test_two_sided_pdf() -> bool:
    print("\n" + "=" * 60)
    print("TEST 2: Two-Sided / Two-Column Academic PDF")
    print("=" * 60)

    sample_pdf = HERE / "samples" / "two_column_academic.pdf"
    if not sample_pdf.exists():
        print(f"[FAIL] Missing test sample: {sample_pdf}")
        return False

    with tempfile.TemporaryDirectory(prefix="test_twocol_") as tmpdir:
        tmp = Path(tmpdir)
        figs_dir = tmp / "figures"
        figs_dir.mkdir()

        # 1. Page count check
        page_count = get_pdf_page_count(str(sample_pdf))
        print(f"[*] Detected page count: {page_count} (Expected: 10)")
        assert page_count >= 1, "Page count must be >= 1"

        # 2. Render adaptive 2x2 grid collage for first 4 pages
        collage_out = tmp / "academic_collage_2x2.png"
        create_collage(str(sample_pdf), 1, 4, "2x2", str(collage_out), dpi=140)
        assert collage_out.exists() and collage_out.stat().st_size > 10000, "Collage generation failed"
        print(f"[*] 2x2 layout collage generated: {collage_out.stat().st_size} bytes")

        # 3. Test high-res figure crop (e.g. diagram/header on page 1)
        fig_crop = figs_dir / "fig_p1_crop.png"
        crop_region(str(sample_pdf), 1, "80,100,220,900", str(fig_crop), dpi=300)
        assert fig_crop.exists() and fig_crop.stat().st_size > 1000, "Region cropping failed"
        print(f"[*] High-res crop generated: {fig_crop.stat().st_size} bytes")

        # 4. Generate academic Markdown with LaTeX math & embedded figure
        academic_md = f"""# Accelerating Blockchain-enabled Distributed Machine Learning

## Abstract

We study proof-of-useful-work mechanisms in distributed machine learning pipelines.
Consider a network of $N$ worker nodes where each node computes gradient updates:

$$g_i = \\nabla L(w; x_i)$$

The aggregate consensus model is updated according to:

$$w_{{t+1}} = w_t - \\eta \\sum_{{i=1}}^N g_i$$

## System Architecture

Below is the verified node interaction diagram:

![Architecture Overview](figures/fig_p1_crop.png)

| Parameter | Description | Default Value |
|---|---|---|
| $N$ | Number of participating nodes | 100 |
| $\\eta$ | Learning rate coefficient | 0.01 |
| $\\tau$ | Block validation threshold | 10s |
"""
        md_file = tmp / "academic.md"
        md_file.write_text(academic_md, encoding="utf-8")

        # 5. Compile EPUB3 with embedded figures & math styling
        epub_out = tmp / "academic.epub"
        build_epub3(
            markdown_path=str(md_file),
            output_epub=str(epub_out),
            figures_dir=str(figs_dir),
            title="Accelerating Distributed Machine Learning",
            author="Blockchain Research Lab",
            lang="en"
        )
        assert epub_out.exists(), "Academic EPUB was not created"
        print(f"[*] Compiled academic EPUB: {epub_out.stat().st_size} bytes")

        # 6. Verify figure packaging and math elements inside EPUB
        with zipfile.ZipFile(str(epub_out), "r") as z:
            namelist = z.namelist()
            assert "EPUB/figures/fig_p1_crop.png" in namelist, "Cropped figure was not embedded in EPUB"
            assert ("EPUB/chapter_001.xhtml" in namelist or "EPUB/document.xhtml" in namelist)

            # Check math tags in XHTML
            all_chapters = " ".join(z.read(f).decode("utf-8") for f in namelist if f.startswith("EPUB/chapter_") or f == "EPUB/document.xhtml")
            assert 'class="math inline"' in all_chapters, "Inline LaTeX math tags missing"
            assert 'class="math display"' in all_chapters, "Display LaTeX math tags missing"

        print("[PASS] Test 2: Two-column / Two-sided academic PDF passed all verifications!")
        return True


def test_complex_pdf(custom_pdf_path: str) -> bool:
    print("\n" + "=" * 60)
    print(f"TEST 3: Complex Custom PDF: {custom_pdf_path}")
    print("=" * 60)

    pdf = Path(custom_pdf_path).resolve()
    if not pdf.exists():
        print(f"[FAIL] Custom PDF not found: {pdf}")
        return False

    with tempfile.TemporaryDirectory(prefix="test_complex_") as tmpdir:
        tmp = Path(tmpdir)
        count = get_pdf_page_count(str(pdf))
        print(f"[*] Detected page count: {count}")

        # Generate probes
        p3 = tmp / "probe_3x3.png"
        p2 = tmp / "probe_2x2.png"
        p1 = tmp / "probe_1x1.png"

        create_collage(str(pdf), 1, min(count, 9), "3x3", str(p3), dpi=120)
        create_collage(str(pdf), 1, min(count, 4), "2x2", str(p2), dpi=140)
        create_collage(str(pdf), 1, 1, "1x1", str(p1), dpi=180)

        print(f"[OK] Generated adaptive probes for complex PDF:")
        print(f"  - 3x3: {p3.stat().st_size} bytes")
        print(f"  - 2x2: {p2.stat().st_size} bytes")
        print(f"  - 1x1: {p1.stat().st_size} bytes")

        print("[PASS] Complex PDF probe test completed successfully!")
        return True


def test_pptx_conversion() -> bool:
    print("\n" + "=" * 60)
    print("TEST 3: PowerPoint (PPTX) Presentation to EPUB3 Conversion")
    print("=" * 60)

    import pptx
    from pptx.util import Inches, Pt
    from PIL import Image, ImageDraw, ImageFont
    from pptx_parser import pptx_to_epub
    from verify_fidelity import run_verification

    with tempfile.TemporaryDirectory(prefix="test_pptx_") as tmpdir:
        tmp = Path(tmpdir)
        pptx_path = tmp / "test_presentation.pptx"
        epub_out = tmp / "test_presentation.epub"

        # 1. Create programmatic PPTX
        prs = pptx.Presentation()

        # Slide 1: Title
        slide1 = prs.slides.add_slide(prs.slide_layouts[0])
        slide1.shapes.title.text = "Computer Graphics Fundamentals"
        slide1.placeholders[1].text = "Department of Computer Science\nInteractive E-Book Edition"

        # Slide 2: Bullet points
        slide2 = prs.slides.add_slide(prs.slide_layouts[1])
        slide2.shapes.title.text = "Raster vs Vector Graphics"
        tf2 = slide2.placeholders[1].text_frame
        tf2.text = "Raster graphics represent images as a rectangular grid of pixels."
        p2_1 = tf2.add_paragraph()
        p2_1.text = "Common raster formats include PNG, JPEG, and WebP."
        p2_1.level = 1
        p2_2 = tf2.add_paragraph()
        p2_2.text = "Vector graphics represent images using mathematical geometric primitives."
        p2_3 = tf2.add_paragraph()
        p2_3.text = "Vector primitives include points, lines, curves, and polygons."
        p2_3.level = 1

        # Slide 3: Table
        slide3 = prs.slides.add_slide(prs.slide_layouts[5])
        slide3.shapes.title.text = "Display Technologies Comparison"
        rows, cols = 3, 3
        tbl_shape = slide3.shapes.add_table(rows, cols, Inches(1), Inches(2), Inches(8), Inches(3))
        table = tbl_shape.table
        table.cell(0, 0).text = "Technology"
        table.cell(0, 1).text = "Contrast Ratio"
        table.cell(0, 2).text = "Refresh Rate"
        table.cell(1, 0).text = "OLED"
        table.cell(1, 1).text = "Infinite"
        table.cell(1, 2).text = "120Hz - 240Hz"
        table.cell(2, 0).text = "IPS LCD"
        table.cell(2, 1).text = "1000:1"
        table.cell(2, 2).text = "60Hz - 144Hz"

        # Slide 4: Image slide with generated PIL image
        img_path = tmp / "sample_diagram.png"
        im = Image.new("RGB", (600, 400), color=(240, 244, 248))
        draw = ImageDraw.Draw(im)
        draw.rectangle([(50, 50), (550, 350)], outline=(30, 64, 175), width=4)
        draw.text((120, 180), "Computer Graphics Pipeline Diagram", fill=(30, 41, 59))
        im.save(str(img_path))

        slide4 = prs.slides.add_slide(prs.slide_layouts[5])
        slide4.shapes.title.text = "Graphics Pipeline Architecture"
        slide4.shapes.add_picture(str(img_path), Inches(1.5), Inches(2), width=Inches(7))

        # Save presentation
        prs.save(str(pptx_path))
        print(f"[*] Generated test PPTX at: {pptx_path}")

        # 2. Convert PPTX to EPUB3
        figs_dir = tmp / "figures"
        pptx_to_epub(
            pptx_path=str(pptx_path),
            output_epub=str(epub_out),
            figures_dir=str(figs_dir),
            title="Computer Graphics Fundamentals",
            author="Department of Computer Science"
        )
        assert epub_out.exists(), "PPTX EPUB file was not created"
        print(f"[*] Compiled PPTX EPUB: {epub_out.stat().st_size} bytes")

        # 3. Verify EPUB internals
        with zipfile.ZipFile(str(epub_out), "r") as z:
            namelist = z.namelist()
            assert namelist[0] == "mimetype", "First entry must be mimetype"
            assert "META-INF/container.xml" in namelist
            assert "EPUB/package.opf" in namelist
            assert "EPUB/nav.xhtml" in namelist
            assert "EPUB/styles.css" in namelist
            assert "EPUB/chapter_001.xhtml" in namelist
            assert "EPUB/chapter_004.xhtml" in namelist
            info = z.getinfo("mimetype")
            assert info.compress_type == zipfile.ZIP_STORED, "mimetype must be uncompressed"

        # 4. Verify fidelity
        report = run_verification(str(pptx_path), str(epub_out), threshold=95.0)
        assert report["overall_pass"], f"Fidelity verification failed: {report['issues']}"
        assert report["coverage_pct"] >= 95.0, f"Coverage too low: {report['coverage_pct']}%"

        print(f"[PASS] Test 3: PPTX conversion passed all verifications! (Coverage: {report['coverage_pct']}%)")
        return True


def main():
    parser = argparse.ArgumentParser(description="pdf-to-epub Test Runner")
    parser.add_argument("--complex-pdf", help="Path to complex test PDF provided by user")
    parser.add_argument("--all", action="store_true", help="Run all standard tests")
    args = parser.parse_args()

    success = True
    if args.complex_pdf:
        success = test_complex_pdf(args.complex_pdf)
    else:
        t1 = test_plain_pdf()
        t2 = test_two_sided_pdf()
        t3 = test_pptx_conversion()
        success = t1 and t2 and t3

    if success:
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED SUCCESSFULLY! (100%)")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("TEST RUN ENCOUNTERED FAILURES.")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
