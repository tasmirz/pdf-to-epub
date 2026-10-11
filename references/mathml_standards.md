# W3C MathML Standards & Math Preservation Guide

This reference details the MathML integration and math formatting standards used across the `pdf-to-epub` pipeline.

---

## 1. EPUB3 MathML Specification

EPUB 3.0+ natively supports mathematical markup using the W3C MathML (Mathematical Markup Language) Recommendation.

### Mandatory XHTML Requirements
1. **XML Namespace Declaration**:
   Any XHTML document containing math elements must declare the MathML namespace:
   ```xml
   <html xmlns="http://www.w3.org/1999/xhtml"
         xmlns:epub="http://www.idpf.org/2007/ops"
         xmlns:m="http://www.w3.org/1998/Math/MathML"
         xml:lang="en">
   ```
2. **Package Manifest Property**:
   In `package.opf`, any chapter item that contains `<math>` elements must declare the `mathml` property:
   ```xml
   <item id="chapter_001"
         href="chapter_001.xhtml"
         media-type="application/xhtml+xml"
         properties="mathml" />
   ```

---

## 2. Inline vs Display Math Elements

- **Inline Equations**: Wrapped in `<math display="inline">` or `<math>` within paragraph context.
  ```html
  <p>The energy is given by <math xmlns="http://www.w3.org/1998/Math/MathML"><mi>E</mi><mo>=</mo><mi>m</mi><msup><mi>c</mi><mn>2</mn></msup></math>.</p>
  ```
- **Display Block Equations**: Wrapped in `<math display="block">` inside a centered block container.
  ```html
  <div class="display-equation">
    <math xmlns="http://www.w3.org/1998/Math/MathML" display="block">
      <mrow>
        <mi>f</mi><mo stretchy="false">(</mo><mi>x</mi><mo stretchy="false">)</mo>
        <mo>=</mo>
        <msubsup><mo>&#x222B;</mo><mrow><mo>-</mo><mi>&#x221E;</mi></mrow><mi>&#x221E;</mi></msubsup>
        <msup><mi>e</mi><mrow><mo>-</mo><msup><mi>t</mi><mn>2</mn></msup></mrow></msup>
        <mi>d</mi><mi>t</mi>
      </mrow>
    </math>
  </div>
  ```

---

## 3. Toolchain & Conversion Pipelines

### TeX to EPUB3 (`tex_to_epub.py`)
1. Calls `tex4ebook` with standard `mathml` and `epub3` switches:
   ```bash
   tex4ebook -f epub3 -c tex4ebook.cfg input.tex "mathml,mathjax"
   ```
2. Automatically generates `<math>` tags from LaTeX expressions (`\frac`, `\sum`, `\int`, `\matrix`).
3. Vector PDF diagrams (`.pdf`, `.eps`) are transcoded to high-resolution PNGs via `pdftoppm -png -r 300`.

### LaTeX-in-Markdown (`epub_packager.py`)
1. When parsing Markdown files containing `$...$` or `$$...$$` blocks, the packager uses `latex2mathml` to convert the LaTeX string directly into standard MathML XML trees.
2. If conversion fails on obscure macros, the packager preserves the raw formula as a clean text fallback rather than dropping content.

---

## 4. Visual Fallback Rules
Only route to visual image cropping (`collage_maker.py crop`) when:
- The equation includes complex 2D spatial diagrams (Feynman diagrams, commutative diagrams with diagonal arrows).
- The equation is embedded inside a rasterized diagram or flowchart.
- The handwritten formula is ambiguous and OCR confidence is below $70\%$.
