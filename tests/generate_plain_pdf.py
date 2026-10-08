#!/usr/bin/env python3
"""
Generate a realistic plain single-column PDF sample for testing.
"""

from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_plain_pdf(output_path: str):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=24,
        leading=28,
        spaceAfter=14,
        textColor=colors.HexColor('#0f172a')
    )
    h2_style = ParagraphStyle(
        'DocH2',
        parent=styles['Heading2'],
        fontSize=16,
        leading=20,
        spaceBefore=14,
        spaceAfter=8,
        textColor=colors.HexColor('#1e293b')
    )
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontSize=11,
        leading=16,
        spaceAfter=10,
        textColor=colors.HexColor('#334155')
    )
    quote_style = ParagraphStyle(
        'DocQuote',
        parent=styles['Italic'],
        fontSize=10.5,
        leading=15,
        leftIndent=24,
        rightIndent=24,
        spaceBefore=8,
        spaceAfter=10,
        textColor=colors.HexColor('#475569')
    )

    story = []

    # Title & Chapter 1
    story.append(Paragraph("A Journey Through Modern Computing", title_style))
    story.append(Paragraph("Chapter 1: The Architecture of Thought", h2_style))
    story.append(Paragraph(
        "In the early days of automated computation, the challenge was primarily electrical and mechanical. "
        "Engineers wrestled with relays, vacuum tubes, and mercury delay lines. The conceptual leap from calculation "
        "to general-purpose reasoning took decades to crystallize into modern architectures.",
        body_style
    ))
    story.append(Paragraph(
        "As computational systems grew in sophistication, the representation of structured knowledge became paramount. "
        "Documents were no longer static ink pressed upon cellulose, but dynamic streams of symbols requiring parsing, "
        "layout analysis, and semantic interpretation.",
        body_style
    ))
    story.append(Paragraph(
        "\"The computer is incredibly fast, accurate, and stupid. Man is incredibly slow, inaccurate, and brilliant. "
        "The marriage of the two is a force beyond calculation.\" — Leo Cherne",
        quote_style
    ))
    story.append(Paragraph(
        "Modern reflowable document formats like EPUB3 represent the culmination of this evolution, decoupling "
        "semantic typography from rigid visual coordinate systems.",
        body_style
    ))

    story.append(PageBreak())

    # Chapter 2
    story.append(Paragraph("Chapter 2: The Art of Typography", h2_style))
    story.append(Paragraph(
        "Typography in electronic publishing balances aesthetics with adaptability. Unlike fixed print sheets, "
        "an electronic reading device may be a six-inch e-ink screen, an eight-inch tablet, or a desktop workstation. "
        "The font size, margins, and line heights must dynamically recalculate without human intervention.",
        body_style
    ))
    story.append(Paragraph(
        "Key principles for reflowable digital texts include:",
        body_style
    ))
    story.append(Paragraph("• Proportional vertical margins to maintain optical balance.", body_style))
    story.append(Paragraph("• High-contrast typography optimized for varied ambient lighting.", body_style))
    story.append(Paragraph("• Dynamic hyphens that expand and collapse cleanly across line wraps.", body_style))
    story.append(Paragraph(
        "When converting from fixed-canvas representations, the primary objective is recovering this inherent "
        "semantic structure without visual clutter.",
        body_style
    ))

    doc.build(story)
    print(f"Generated plain sample PDF: {output_path}")

if __name__ == "__main__":
    out_file = Path(__file__).resolve().parent / "samples" / "plain_book_sample.pdf"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    generate_plain_pdf(str(out_file))
