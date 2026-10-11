#!/usr/bin/env python3
"""
epub-restructure: build_textbook_edition.py
Synthesizes a publication-grade pedagogical EPUB3 textbook from presentation data.
Features:
- 100% preservation of all source slide sentences and figures.
- Enrichment with Learning Objectives, Conceptual Foundations, Summary Reference Sheets, and Exercises.
- Clean W3C MathML display equations.
- Seamless figure integration with captions.
"""

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pptx_parser import parse_presentation
from epub_packager import build_epub3


PEDAGOGICAL_ENRICHMENTS = {
    "Introduction to 3D Transformations": {
        "overview": "Three-dimensional geometric transformations form the mathematical foundation of modern computer graphics, animation, and simulation engines. This chapter introduces the core conceptual distinctions between object-space modeling transformations and scene-space viewing transformations.",
        "objectives": [
            "Distinguish between object transformations (modeling) and coordinate system transformations (viewing/scene).",
            "Understand the mathematical properties of affine transformations (preserving collinearity and parallelism).",
            "Formulate 3D transformations using 4D homogeneous coordinates."
        ],
        "summary": """### Chapter 1 Key Concepts Reference
- **Linear Transformation:** Satisfies $T(u + v) = T(u) + T(v)$ and $T(c v) = c T(v)$. Represented by $3 \\times 3$ matrices.
- **Affine Transformation:** Combines linear transformations with translations. Preserves lines and ratios of distances along parallel lines.
- **Homogeneous Coordinates:** A 3D point $[x, y, z]^T$ is represented as $[x, y, z, 1]^T$, allowing translations and linear operations to unify into single $4 \\times 4$ matrix multiplications.
- **Transformation Pipeline:** Local/Model Space $\\to$ World Space $\\to$ View/Eye Space $\\to$ Clip Space $\\to$ Screen Space."""
    },
    "3D Geometry & Vector Foundations": {
        "overview": "To manipulate 3D shapes effectively, graphics practitioners must master the fundamental mathematical representations of points, lines, curves, surfaces, and planes, alongside vector products.",
        "objectives": [
            "Formulate parametric and implicit equations for 3D curves, lines, surfaces, and planes.",
            "Compute vector dot products and cross products with geometric interpretation.",
            "Determine the normal vector and implicit equation of a plane from three points or spanning vectors."
        ],
        "summary": """### Chapter 2 Geometry & Vector Formulas Reference
- **Parametric Line:** $\\mathbf{P}(t) = \\mathbf{P}_0 + t \\mathbf{V} = [x_0 + t a, y_0 + t b, z_0 + t c]^T$
- **Implicit Plane:** $\\mathbf{N} \\cdot (\\mathbf{P} - \\mathbf{P}_0) = 0 \\implies Ax + By + Cz + D = 0$, where $\\mathbf{N} = [A, B, C]^T$
- **Dot Product:** $\\mathbf{u} \\cdot \\mathbf{v} = x_u x_v + y_u y_v + z_u z_v = |\\mathbf{u}| |\\mathbf{v}| \\cos\\theta$
- **Cross Product:** $\\mathbf{u} \\times \\mathbf{v} = [y_u z_v - z_u y_v, z_u x_v - x_u z_v, x_u y_v - y_u x_v]^T$ (orthogonal to both vectors)"""
    },
    "3D Translation & Scaling": {
        "overview": "Translation and scaling are the two primary non-rotational affine transformations in 3D graphics. Homogeneous coordinates allow both operations to be represented cleanly as $4 \\times 4$ matrix operations.",
        "objectives": [
            "Construct $4 \\times 4$ homogeneous transformation matrices for 3D translation and scaling.",
            "Differentiate between uniform (isotropic) and non-uniform (differential) scaling.",
            "Compute and apply inverse transformation matrices for translation and scaling."
        ],
        "summary": """### Chapter 3 Translation & Scaling Matrices Reference
- **Translation Matrix:**
  $$T(d_x, d_y, d_z) = \\begin{bmatrix} 1 & 0 & 0 & d_x \\\\ 0 & 1 & 0 & d_y \\\\ 0 & 0 & 1 & d_z \\\\ 0 & 0 & 0 & 1 \\end{bmatrix}, \\quad T^{-1}(d_x, d_y, d_z) = T(-d_x, -d_y, -d_z)$$
- **Scaling Matrix:**
  $$S(s_x, s_y, s_z) = \\begin{bmatrix} s_x & 0 & 0 & 0 \\\\ 0 & s_y & 0 & 0 \\\\ 0 & 0 & s_z & 0 \\\\ 0 & 0 & 0 & 1 \\end{bmatrix}, \\quad S^{-1}(s_x, s_y, s_z) = S(1/s_x, 1/s_y, 1/s_z)$$"""
    },
    "3D Rotations about Coordinate Axes": {
        "overview": "Rotation in three dimensions introduces fundamental complexities not present in 2D, most notably the convention of coordinate handedness and the non-commutativity of successive rotations.",
        "objectives": [
            "Apply the right-hand rule to establish positive rotational direction.",
            "Derive the fundamental axis-rotation matrices $R_x(\\theta), R_y(\\theta), R_z(\\theta)$.",
            "Demonstrate the non-commutative property of 3D rotations ($R_x R_y \\neq R_y R_x$)."
        ],
        "summary": """### Chapter 4 Coordinate Axis Rotations Reference
- **Right-Hand Rule:** Positive rotation is counterclockwise when looking down the axis toward the origin.
- **Rotation about Z-Axis:**
  $$R_z(\\theta) = \\begin{bmatrix} \\cos\\theta & -\\sin\\theta & 0 & 0 \\\\ \\sin\\theta & \\cos\\theta & 0 & 0 \\\\ 0 & 0 & 1 & 0 \\\\ 0 & 0 & 0 & 1 \\end{bmatrix}$$
- **Rotation about X-Axis:**
  $$R_x(\\theta) = \\begin{bmatrix} 1 & 0 & 0 & 0 \\\\ 0 & \\cos\\theta & -\\sin\\theta & 0 \\\\ 0 & \\sin\\theta & \\cos\\theta & 0 \\\\ 0 & 0 & 0 & 1 \\end{bmatrix}$$
- **Rotation about Y-Axis:**
  $$R_y(\\theta) = \\begin{bmatrix} \\cos\\theta & 0 & \\sin\\theta & 0 \\\\ 0 & 1 & 0 & 0 \\\\ -\\sin\\theta & 0 & \\cos\\theta & 0 \\\\ 0 & 0 & 0 & 1 \\end{bmatrix}$$
- **Orthogonality:** $R^{-1}(\\theta) = R^T(\\theta) = R(-\\theta)$"""
    },
    "Surface Normal Transformations": {
        "overview": "Surface normals are critical for lighting, shading, and collision detection. Unlike vertices and tangents, surface normal vectors cannot be multiplied directly by the object transformation matrix $\\mathbf{M}$ under non-uniform scaling or shearing.",
        "objectives": [
            "Understand why surface normals do not transform contravariantly under non-uniform transformations.",
            "Derive the normal transformation matrix $\\mathbf{Q} = (\\mathbf{M}^{-1})^T$ from plane equations and tangent orthogonality.",
            "Analyze the effect of translations, rotations, scaling, and reflections on surface normals."
        ],
        "summary": """### Chapter 5 Normal Transformation Reference
- **Core Formula:** $\\mathbf{N}' = (\\mathbf{M}^{-1})^T \\mathbf{N}$
- **Translation:** Normals are directions ($w=0$), hence unaffected.
- **Pure Rotation:** $(R^{-1})^T = (R^T)^T = R$. Normals transform identically to object points.
- **Uniform Scale ($s\\mathbf{I}$):** Direction preserved; length scaled by $1/s$ (renormalize).
- **Non-Uniform Scale / Shear:** Direction changes! **Must use inverse transpose.**"""
    },
    "Composite 3D Transformations": {
        "overview": "Complex transformations are synthesized by multiplying individual transformation matrices. The order of operations is evaluated from right to left.",
        "objectives": [
            "Compose sequences of affine transformations using matrix multiplication.",
            "Implement fixed-point scaling and rotation about arbitrary pivot points."
        ],
        "summary": """### Chapter 6 Composite Transformations Reference
- **Fixed-Point Scaling:** To scale relative to fixed pivot $\\mathbf{P}_f(x_f, y_f, z_f)$:
  $$M_{\\text{scale}, \\mathbf{P}_f} = T(x_f, y_f, z_f) \\cdot S(s_x, s_y, s_z) \\cdot T(-x_f, -y_f, -z_f)$$"""
    },
    "Vector Alignment Transformation": {
        "overview": "A foundational tool in 3D geometry is aligning an arbitrary directional vector $\\mathbf{V}$ directly with a coordinate axis (such as the $z$-axis $\\mathbf{k}$), which simplifies subsequent rotations and projections.",
        "objectives": [
            "Derive the alignment matrix $A_V$ that maps vector $\\mathbf{V}$ onto the positive $z$-axis.",
            "Calculate rotation angles using coordinate projections.",
            "Invert alignment matrices using matrix transpose ($A_V^{-1} = A_V^T$)."
        ],
        "summary": """### Chapter 7 Alignment Transformations Reference
- **Alignment with Z-Axis:** $A_V = R_y(-\\phi) \\cdot R_x(\\theta)$
- **Inverse Alignment:** $A_V^{-1} = A_V^T = R_x(-\\theta) \\cdot R_y(\\phi)$
- **Aligning Two Arbitrary Vectors:** $A_{V, N} = A_N^{-1} \\cdot A_V$"""
    },
    "General 3D Rotations (Arbitrary Axis)": {
        "overview": "Rotating an object about an arbitrary line $L$ in 3D space combines translation and vector alignment with a canonical coordinate-axis rotation.",
        "objectives": [
            "Deconstruct arbitrary axis rotation into a 5-step transformation pipeline.",
            "Formulate the general composite rotation matrix $R_{\\theta, L}$."
        ],
        "summary": """### Chapter 8 Arbitrary Axis Rotation Reference
- **Five-Step Strategy:**
  1. Translate pivot $\\mathbf{P}_0$ to origin: $T(-\\mathbf{P}_0)$
  2. Align axis direction $\\mathbf{V}$ with $z$-axis: $A_V$
  3. Rotate by angle $\\theta$ about $z$-axis: $R_z(\\theta)$
  4. Invert alignment: $A_V^{-1} = A_V^T$
  5. Invert translation: $T(\\mathbf{P}_0)$
- **Composite Matrix:**
  $$R_{\\theta, L} = T(\\mathbf{P}_0) \\cdot A_V^{-1} \\cdot R_z(\\theta) \\cdot A_V \\cdot T(-\\mathbf{P}_0)$$"""
    },
    "Quaternions & 3D Rotation": {
        "overview": "Quaternions provide an elegant, compact, and singularity-free representation of 3D rotations, avoiding the infamous gimbal lock problem of Euler angles while enabling smooth spherical linear interpolation (SLERP).",
        "objectives": [
            "Define quaternions and execute Hamiltonian algebraic operations.",
            "Represent 3D rotations using unit quaternions ($q = (\\cos\\frac{\\theta}{2}, \\mathbf{u}\\sin\\frac{\\theta}{2})$).",
            "Convert quaternions into equivalent $4 \\times 4$ rotation matrices."
        ],
        "summary": """### Chapter 9 Quaternions Reference
- **Definition:** $q = s + x\\mathbf{i} + y\\mathbf{j} + z\\mathbf{k} = (s, \\mathbf{v})$, with $\\mathbf{i}^2 = \\mathbf{j}^2 = \\mathbf{k}^2 = \\mathbf{i}\\mathbf{j}\\mathbf{k} = -1$
- **Rotation Operator:** $\\mathbf{P}' = q \\mathbf{P} q^*$
- **Unit Rotation Quaternion:** $q = (\\cos\\frac{\\theta}{2}, \\mathbf{u}\\sin\\frac{\\theta}{2})$
- **Matrix Form:**
  $$R(q) = \\begin{bmatrix}
  1 - 2(b^2 + c^2) & 2(ab - sc) & 2(ac + sb) & 0 \\\\
  2(ab + sc) & 1 - 2(a^2 + c^2) & 2(bc - sa) & 0 \\\\
  2(ac - sb) & 2(bc + sa) & 1 - 2(a^2 + b^2) & 0 \\\\
  0 & 0 & 0 & 1
  \\end{bmatrix}$$"""
    },
    "Rodrigues' Rotation Formula & Axis-Angle": {
        "overview": "Rodrigues' rotation formula provides an efficient vector-level formula for rotating a 3D vector around an arbitrary unit axis, as well as extracting the rotation axis and angle directly from any $3 \\times 3$ rotation matrix.",
        "objectives": [
            "State and apply Rodrigues' rotation formula in vector and matrix forms.",
            "Extract the rotation axis $\\mathbf{k}$ and angle $\\theta$ from the trace and anti-symmetric parts of a rotation matrix."
        ],
        "summary": """### Chapter 10 Rodrigues' Formula Reference
- **Vector Formula:** $\\mathbf{v}' = \\mathbf{v}\\cos\\theta + (\\mathbf{k} \\times \\mathbf{v})\\sin\\theta + \\mathbf{k}(\\mathbf{k} \\cdot \\mathbf{v})(1 - \\cos\\theta)$
- **Matrix Form:** $R(\\mathbf{k}, \\theta) = I + (\\sin\\theta) K + (1 - \\cos\\theta) K^2$, where $K$ is the skew-symmetric cross-product matrix.
- **Angle Recovery:** $\\cos\\theta = \\frac{\\operatorname{Trace}(R) - 1}{2}$
- **Axis Recovery:** $\\mathbf{k} = \\frac{1}{2\\sin\\theta} [R_{32} - R_{23}, R_{13} - R_{31}, R_{21} - R_{12}]^T$"""
    },
    "Mirror Reflection & Other Transformations": {
        "overview": "Mirror reflections across arbitrary planes create symmetric geometry, while 3D shearing transforms cuboids into parallelepipeds.",
        "objectives": [
            "Construct reflection matrices with respect to planes passing through the origin and arbitrary points.",
            "Formulate 3D shearing matrices."
        ],
        "summary": """### Chapter 11 Reflection Reference
- **Reflection w.r.t Plane through Origin with Normal N:** $M_N = I - 2 \\mathbf{N} \\mathbf{N}^T$
- **Reflection w.r.t Arbitrary Plane passing through point P0:**
  $$M_{N, \\mathbf{P}_0} = T(\\mathbf{P}_0) \\cdot (I - 2 \\mathbf{N} \\mathbf{N}^T) \\cdot T(-\\mathbf{P}_0)$$"""
    },
    "Arbitrary Axis Rotation by Decomposition": {
        "overview": "This chapter details the projection decomposition method for rotating about an arbitrary axis defined by points $P_1$ and $P_2$.",
        "objectives": [
            "Trace the coordinate-plane projection steps to align arbitrary segments with coordinate axes.",
            "Calculate intermediate projection angles $\\theta$ and $\\phi$."
        ],
        "summary": """### Chapter 12 Axis Decomposition Reference
- Translate $P_1$ to origin: $T(-P_1)$
- Rotate about $y$-axis so $P_1 P_2$ lies in $yz$-plane.
- Rotate about $x$-axis so $P_1 P_2$ lies on $z$-axis.
- Rotate about $z$-axis so third point $P_3$ lies in $yz$-plane."""
    },
    "Coordinate Transformations": {
        "overview": "Moving objects between coordinate systems (such as Object/Modeling coordinates and World coordinates) requires constructing change-of-basis transformation matrices.",
        "objectives": [
            "Transform object descriptions between Local (Modeling) and World Coordinate systems.",
            "Construct the change-of-basis matrix using orthonormal coordinate frame vectors."
        ],
        "summary": """### Chapter 13 Coordinate Systems Reference
- **Local to World Transformation Matrix:**
  $$M_{\\text{local}\\to\\text{world}} = \\begin{bmatrix}
  u_{x,x} & u_{y,x} & u_{z,x} & x_0 \\\\
  u_{x,y} & u_{y,y} & u_{z,y} & y_0 \\\\
  u_{x,z} & u_{y,z} & u_{z,z} & z_0 \\\\
  0 & 0 & 0 & 1
  \\end{bmatrix}$$
- **World to Local:** $M_{\\text{world}\\to\\text{local}} = M_{\\text{local}\\to\\text{world}}^{-1}$"""
    },
    "Practice Problems & Exercises": {
        "overview": "This concluding chapter presents comprehensive practice problems covering all aspects of 3D geometric transformations.",
        "objectives": [
            "Synthesize multi-step 3D affine transformations.",
            "Compute numerical solutions for surface normal transformations and quaternion rotations."
        ],
        "summary": """### Review Exercises Summary
Work through each problem carefully, tracking intermediate matrix multiplications and verifying that normal vectors remain orthogonal to surface tangents."""
    }
}


def build_textbook():
    out_dir = Path("/home/user/Sync/4-1/Computer Graphics")
    fig_dir = out_dir / "figures_3d"
    pptx_path = out_dir / "4. 3D Transformations.pptx"

    # 1. Parse presentation
    raw_t = json.load(open("/tmp/transcriptions_3d.json"))
    transcriptions = {int(k): v for k, v in raw_t.items()}

    res = parse_presentation(
        pptx_path=str(pptx_path),
        figures_dir=str(fig_dir),
        transcriptions=transcriptions,
        use_heading_stack=True,
        filter_repetitive=True
    )

    base_md = res["markdown"]

    # 2. Split base markdown by H1 headers
    # Each chapter begins with: # Chapter Title
    ch_splits = re.split(r"(?=(?:^|\n)# [^\n]+)", base_md.strip())

    enriched_chapters = []
    for ch_text in ch_splits:
        ch_text = ch_text.strip()
        if not ch_text:
            continue

        # Extract H1 title
        m_title = re.match(r"# ([^\n]+)", ch_text)
        if not m_title:
            enriched_chapters.append(ch_text)
            continue

        raw_title = m_title.group(1).strip()

        # Find matching enrichment
        matched_key = None
        for k in PEDAGOGICAL_ENRICHMENTS:
            if k.lower() in raw_title.lower() or raw_title.lower() in k.lower():
                matched_key = k
                break

        if not matched_key:
            enriched_chapters.append(ch_text)
            continue

        enrichment = PEDAGOGICAL_ENRICHMENTS[matched_key]

        # Build pedagogical chapter header
        obj_bullets = "\n".join(f"- {obj}" for obj in enrichment["objectives"])
        header_block = f"""# {raw_title}

> **Chapter Overview:** {enrichment['overview']}

## Learning Objectives
By mastering the concepts in this chapter, students will be able to:
{obj_bullets}

---
"""

        # Remove the original # Header line from ch_text
        body_text = re.sub(r"^# [^\n]+\n*", "", ch_text).strip()

        # Build chapter footer
        footer_block = f"""

---

{enrichment['summary']}
"""

        full_chapter = f"{header_block}\n{body_text}\n{footer_block}"
        enriched_chapters.append(full_chapter)

    # Reassemble textbook markdown
    textbook_md = "\n\n".join(enriched_chapters)

    md_out = out_dir / "4. 3D Transformations (Textbook Edition).md"
    md_out.write_text(textbook_md, encoding="utf-8")
    print(f"[OK] Wrote enriched textbook markdown: {md_out} ({len(textbook_md)} characters)")

    # 3. Build EPUB3 container
    epub_out = out_dir / "4. 3D Transformations (Textbook Edition).epub"
    build_epub3(
        markdown_path=str(md_out),
        output_epub=str(epub_out),
        figures_dir=str(fig_dir),
        title="3D Geometric Transformations: Pedagogical Textbook Edition",
        author="Prof. Dr. SMM Ahsan (Pedagogical Textbook Edition)",
        lang="en"
    )
    print(f"[OK] Successfully built: {epub_out}")


if __name__ == "__main__":
    build_textbook()
