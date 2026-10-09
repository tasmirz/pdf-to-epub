#!/usr/bin/env python3
"""
pdf-to-epub: dla_analyzer.py
Document Layout Analysis (DLA) & Semantic Structure Engine.

Capabilities:
1. Repetitive Header & Footer Detection:
   Identifies and purges repeating instructor names, institutions, slide numbers,
   and course titles across presentations and PDFs.
2. Heading Stack State Machine:
   Tracks topic hierarchies (H1 -> H2 -> H3) to seamlessly merge consecutive
   continuation slides into rich, cohesive chapters instead of 1-slide page breaks.
3. Shape & Region Classifier (DLA):
   Classifies content into TEXT_BLOCK, TABLE, DIAGRAM_IMAGE, EQUATION_BLOCK,
   and TRANSCRIBE_CANDIDATE.
4. Vision Routing:
   Decides when to keep images as-is vs when to route equations / text-dense
   graphics to Multimodal LLM Vision for LaTeX / MathML transcription.
   No pytesseract dependency.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any


class ElementType(Enum):
    TITLE = "title"
    HEADER = "header"
    FOOTER = "footer"
    TEXT_BLOCK = "text_block"
    TABLE = "table"
    DIAGRAM_IMAGE = "diagram_image"
    EQUATION_BLOCK = "equation_block"
    TRANSCRIBE_CANDIDATE = "transcribe_candidate"
    SPEAKER_NOTE = "speaker_note"


class ActionType(Enum):
    KEEP_AS_IS = "keep_as_is"
    EMBED_FIGURE = "embed_figure"
    TRANSCRIBE_LATEX = "transcribe_latex"
    TRANSCRIBE_VISION = "transcribe_vision"
    FILTER_OUT = "filter_out"


@dataclass
class DLAElement:
    element_type: ElementType
    action: ActionType
    content: Any  # string, markdown, image bytes, etc.
    bbox: Optional[Tuple[float, float, float, float]] = None  # (left, top, width, height)
    metadata: Dict[str, Any] = field(default_factory=dict)


# Known mathematical symbol font glyphs commonly extracted when Equation Editor formulas break
EQUATION_GLYPH_REGEX = re.compile(r"[\uF000-\uF8FF]")


class RepetitivePatternDetector:
    """
    Two-pass detector that discovers repeating headers, footers,
    slide counters, and institutional watermarks across slides.
    """

    def __init__(self, occurrence_threshold: float = 0.15, min_slides: int = 3):
        self.occurrence_threshold = occurrence_threshold
        self.min_slides = min_slides
        self.blacklist_exact: Set[str] = set()
        self.blacklist_patterns: List[re.Pattern] = [
            re.compile(r"^\d{1,4}$"),                           # Raw slide numbers (e.g. "12")
            re.compile(r"^(?:slide|page)\s*\d+(?:\s*(?:of|/)\s*\d+)?$", re.I), # "Slide 12", "Page 1 of 50"
            re.compile(r"^\d{1,4}\s*/\s*\d{1,4}$"),            # "12 / 108"
            re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$"),   # Dates "10/09/2026"
        ]

    def normalize(self, text: str) -> str:
        t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def scan_presentation_candidates(self, slides_text_and_positions: List[List[Dict[str, Any]]]):
        """
        Pass 1: Gather frequency of text in margin regions (top 15% and bottom 15%).
        slides_text_and_positions: list per slide of [{ 'text': ..., 'top_ratio': float, 'bottom_ratio': float }]
        """
        total_slides = len(slides_text_and_positions)
        if total_slides < 2:
            return

        text_counts: Dict[str, int] = {}
        for slide_items in slides_text_and_positions:
            seen_on_this_slide = set()
            for item in slide_items:
                raw = item.get("text", "")
                norm = self.normalize(raw)
                if not norm:
                    continue
                top_ratio = item.get("top_ratio", 0.5)
                bottom_ratio = item.get("bottom_ratio", 0.5)

                # Prioritize margin text (header: top < 0.15, footer: bottom > 0.85)
                is_margin = (top_ratio <= 0.18 or bottom_ratio >= 0.82)
                if is_margin and len(norm) <= 120:
                    if norm not in seen_on_this_slide:
                        text_counts[norm] = text_counts.get(norm, 0) + 1
                        seen_on_this_slide.add(norm)

        # Threshold check
        required_count = max(self.min_slides, int(total_slides * self.occurrence_threshold))
        for norm_text, count in text_counts.items():
            if count >= required_count:
                self.blacklist_exact.add(norm_text.lower())

    def is_repetitive(self, text: str, top_ratio: float = 0.5, bottom_ratio: float = 0.5) -> bool:
        norm = self.normalize(text)
        if not norm:
            return True

        norm_lower = norm.lower()

        # Check exact repetitive margin text
        if norm_lower in self.blacklist_exact:
            return True

        # Check common header/footer patterns
        for pattern in self.blacklist_patterns:
            if pattern.match(norm):
                return True

        # Check known university / instructor footer patterns in margin
        if bottom_ratio >= 0.82 or top_ratio <= 0.18:
            if re.search(r"prof\.\s*dr\.|department of|cse,\s*kuet|university|all rights reserved", norm_lower):
                return True

        return False


class HeadingStack:
    """
    Heading Stack State Machine.
    Prevents artificial 1-slide page breaks by recognizing when consecutive
    slides belong to the same topic hierarchy (H1 -> H2 -> H3).
    """

    def __init__(self):
        self.current_h1: Optional[str] = None
        self.current_h2: Optional[str] = None
        self.current_h3: Optional[str] = None
        self.slide_index_in_topic: int = 0

    def clean_title(self, raw_title: str) -> str:
        """Strip slide prefixes, continuation markers, and formatting artifacts."""
        t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", raw_title)
        t = re.sub(r"^Slide\s*\d+\s*:\s*", "", t, flags=re.I)
        t = re.sub(r"^Lecture\s*\d+\s*:\s*", "", t, flags=re.I)
        t = re.sub(r"\s*\((?:cont(?:inued)?\.?|part\s*\d+)\)$", "", t, flags=re.I)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def extract_hierarchy(self, slide_title: str) -> Tuple[str, Optional[str]]:
        """
        Decomposes slide title into (Major Topic, Sub Topic).
        Uses thematic clustering and subordinate heuristics to prevent
        artificial 1-slide page breaks and unite continuation slides into
        cohesive textbook chapters.
        """
        title = self.clean_title(slide_title)
        if not title:
            return (self.current_h1 or "Topic"), None

        # Check explicit major standalone chapters first
        major_standalone = [
            (r"problems?\s+to\s+be\s+solved|practice\s*problems?|review\s*questions?", "Practice Problems & Exercises"),
            (r"further\s*composition|finding\s*composite\s*r", "Arbitrary Axis Rotation by Decomposition")
        ]
        for pat, canonical in major_standalone:
            if re.search(pat, title, re.I):
                sub = title if title.lower() != canonical.lower() else None
                return canonical, sub

        # Subordinate patterns that should remain under active major topic
        subordinate_keywords = [
            r"^examples?", r"^problems?", r"^exercises?", r"^solutions?", r"^proof", r"^derivation",
            r"^digression", r"^comments?", r"^connections?", r"^finally", r"^solve it", r"^diy",
            r"^notes?", r"^summary", r"^more\s+", r"^so\s+how", r"^how\s+do\s+we", r"^why\s+is",
            r"^visualization", r"^transform\s+.*like", r"^finding\s+.*", r"^rotate\s+about",
            r"^translate\s+.*", r"^inverse\s+alignment"
        ]
        if self.current_h1 and any(re.search(kw, title, re.I) for kw in subordinate_keywords):
            return self.current_h1, title

        # Thematic clusters for course lecture slides
        clusters = [
            (r"quaternion", "Quaternions & 3D Rotation"),
            (r"rodrigues", "Rodrigues' Rotation Formula & Axis-Angle"),
            (r"axis\s+and\s+angle", "Rodrigues' Rotation Formula & Axis-Angle"),
            (r"mirror\s*reflection|m[nN]\s*,\s*p|other\s+transformations", "Mirror Reflection & Other Transformations"),
            (r"normal|tangent\s*vector|object\s+transformation|shear\s+and\s+scale", "Surface Normal Transformations"),
            (r"aligning\s*vector|a[vV]\s*:|alignment\s*transformation", "Vector Alignment Transformation"),
            (r"coordinate[\s-]axes\s*rotations?|order\s+of\s+rotations|rotation\s*(?:about|in|–|-)\s*(?:[xyz]-?axis|3d)", "3D Rotations about Coordinate Axes"),
            (r"general\s*3d\s*rotations?|r\s*[\u03b8\u0398\u03b8,\s\uF071]?\s*,\s*l", "General 3D Rotations (Arbitrary Axis)"),
            (r"composite\s*transformations?|relative\s*scaling", "Composite 3D Transformations"),
            (r"coordinate\s*transformations?", "Coordinate Transformations"),
            (r"plane|vector\s*equation|curve\s*&\s*line|surface\s*&\s*plane|vectors\s*in\s*3d", "3D Geometry & Vector Foundations"),
            (r"translation\s*[–-]\s*3d|scaling\s*[–-]\s*3d", "3D Translation & Scaling"),
            (r"3d\s*modelling\s*transform|3d\s*transformations|orientation", "Introduction to 3D Transformations")
        ]
        for pat, canonical in clusters:
            if re.search(pat, title, re.I):
                sub = title if title.lower() != canonical.lower() else None
                return canonical, sub

        # Fallback delimiter split
        parts = [p.strip() for p in re.split(r"[:–—]", title) if p.strip()]
        if len(parts) >= 2:
            main = self._canonicalize_topic(parts[0])
            sub = " — ".join(parts[1:])
            return main, sub

        main = self._canonicalize_topic(title)
        return main, None

    def _canonicalize_topic(self, topic: str) -> str:
        t = topic.strip()
        m = re.match(r"^(.*?)\s*(?:in|–|-)\s*3D$", t, re.I)
        if m:
            return f"3D {m.group(1).strip()}"
        m2 = re.match(r"^3D\s*-\s*(.*?)$", t, re.I)
        if m2:
            return f"3D {m2.group(1).strip()}"
        return t

    def process_slide(self, slide_title: str, slide_idx: int) -> Dict[str, Any]:
        """
        Returns heading emission directive:
        {
            "is_new_h1": bool,
            "h1_title": str,
            "h2_title": Optional[str],
            "h3_title": Optional[str],
            "heading_markdown": str,
            "slide_anchor": str
        }
        """
        major, sub = self.extract_hierarchy(slide_title)
        is_same_h1 = (self.current_h1 and major.lower() == self.current_h1.lower())

        if not is_same_h1:
            # Topic Shift: Push new H1, reset H2/H3
            self.current_h1 = major
            self.current_h2 = sub
            self.current_h3 = None
            self.slide_index_in_topic = 1

            md_lines = [f"# {major}"]
            if sub and sub.lower() != major.lower():
                md_lines.append(f"\n## {sub}")

            return {
                "is_new_h1": True,
                "h1_title": major,
                "h2_title": sub,
                "h3_title": None,
                "heading_markdown": "\n".join(md_lines),
                "slide_anchor": f"slide-{slide_idx}"
            }
        else:
            # Continuation within the same major topic!
            self.slide_index_in_topic += 1

            if sub:
                norm_sub = re.sub(r"[^a-z0-9]", "", sub.lower())
                norm_curr = re.sub(r"[^a-z0-9]", "", (self.current_h2 or "").lower())
                if norm_sub and norm_sub != norm_curr:
                    self.current_h2 = sub
                    return {
                        "is_new_h1": False,
                        "h1_title": self.current_h1,
                        "h2_title": sub,
                        "h3_title": None,
                        "heading_markdown": f"## {sub}",
                        "slide_anchor": f"slide-{slide_idx}"
                    }

            # Direct slide continuation without subtopic shift
            return {
                "is_new_h1": False,
                "h1_title": self.current_h1,
                "h2_title": self.current_h2,
                "h3_title": None,
                "heading_markdown": "",  # No duplicate heading emitted!
                "slide_anchor": f"slide-{slide_idx}"
            }


class DLAClassifier:
    """
    Decides element classification and routing between:
    - Direct Text & Table
    - Standalone Diagram Figure
    - Multimodal Vision Transcription (LaTeX equations / dense graphics)
    """

    @staticmethod
    def inspect_text(text: str) -> Tuple[ElementType, ActionType]:
        if not text.strip():
            return ElementType.TEXT_BLOCK, ActionType.FILTER_OUT

        # Check for equation glyphs or broken bracket characters
        if EQUATION_GLYPH_REGEX.search(text):
            return ElementType.EQUATION_BLOCK, ActionType.TRANSCRIBE_LATEX

        return ElementType.TEXT_BLOCK, ActionType.KEEP_AS_IS

    @staticmethod
    def inspect_image(
        image_bytes: bytes,
        slide_text_len: int,
        has_ole_on_slide: bool,
        image_width: int = 0,
        image_height: int = 0
    ) -> Tuple[ElementType, ActionType]:
        """
        DLA decision:
        - If slide has OLE equations or severe formula glyph fragmentation -> EQUATION_BLOCK
        - If slide is an empty slide containing a text/formula screenshot -> TRANSCRIBE_CANDIDATE
        - Otherwise, it's a visual illustration / diagram -> DIAGRAM_IMAGE (keep as-is!)
        """
        if has_ole_on_slide:
            return ElementType.EQUATION_BLOCK, ActionType.TRANSCRIBE_LATEX

        # If slide has zero native text but a large graphic, it's likely a scanned slide or text graphic
        if slide_text_len < 30 and (image_width >= 400 or image_height >= 300):
            return ElementType.TRANSCRIBE_CANDIDATE, ActionType.TRANSCRIBE_VISION

        # Standard figure / diagram / photo: Keep as-is!
        return ElementType.DIAGRAM_IMAGE, ActionType.EMBED_FIGURE
