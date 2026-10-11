# Document Layout Analysis (DLA) & Adaptive Visual Probing

This reference explains the Document Layout Analysis (DLA) architecture, visual collage probing protocols, and slide-to-chapter clustering used in `pdf-to-epub`.

---

## 1. Adaptive Visual Grid Probing

When an autonomous agent processes a PDF document, it should not blindly render every page at 300 DPI (which bloats token limits and model latency). Instead, it uses **adaptive collage probing**:

| Grid Mode | Layout | Target Aspect Ratio | Typical Use Case | Recommended DPI |
|---|---|---|---|---|
| **3x3** | 3 cols $\times$ 3 rows | $1:1$ square (9 pages) | Academic papers, dense books, novels | 120 DPI |
| **3x2** | 3 cols $\times$ 2 rows | $48:18$ ($8:3$) widescreen | 16:9 lecture slides, pitch decks | 130–140 DPI |
| **2x2** | 2 cols $\times$ 2 rows | $4:3$ standard | Two-column journals, conference papers | 140–160 DPI |
| **1x1** | Single page | Original aspect ratio | High-resolution diagram extraction | 200–300 DPI |

### 3x2 Grid for Lecture Slides
Because lecture slides use large text fonts (20–36pt) and 16:9 horizontal orientation:
- Arranging 6 slides in a 3-across by 2-down grid achieves complete legibility of subscripts, superscripts, and matrix entries at 130 DPI.
- Reduces subagent turns and vision token consumption by **33%** compared to 2x2.

---

## 2. Shape Classification & Repetitive Purging (`pptx_parser.py`)

Presentations often contain repetitive noise that degrades reading flow:

1. **Margin Purge (Top 15% & Bottom 15%)**:
   - Headers: Course title, university name, semester code.
   - Footers: Slide numbers, copyright notices, professor email.
   - Any shape positioned in margin coordinates with identical or predictable text across $\ge 3$ slides is purged.
2. **Shape Classification**:
   - **Text Containers**: Converted to semantic Markdown (`#`, `##`, `###`, `- bullet`).
   - **Table Shapes**: Extracted cell-by-cell into GitHub-Flavored Markdown tables.
   - **Images & Diagrams**: Exported to standalone PNG assets and linked via `![caption](figures/fig_*.png)`.
   - **Equation Objects**: Extracted from OMML (`officeMath`) into LaTeX MathML.

---

## 3. Heading Stack State Machine (Slide Topic Grouping)

Raw slide decks frequently split a single topic across 5 continuation slides with the same title (*"Transformer Attention (Cont.)"*).

Generating an EPUB chapter for every single slide creates a broken reading experience with tiny, disjointed pages.

### The Heading Stack Solution
`pptx_parser.py` maintains a persistent heading stack state machine:
- **Major Topic (H1)**: Initiates a new top-level EPUB chapter.
- **Subtopic (H2)**: Adds a major section within the current chapter.
- **Continuation Slide**: If slide $N$ shares the title or is labeled *(Cont.)*, *(Part 2)*, or continues bullet hierarchy, its body is appended directly to the current section without triggering a page break.
