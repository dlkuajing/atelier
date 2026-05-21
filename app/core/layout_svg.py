"""2D optical layout SVG renderer.

Wave 2 of Phase 2 (continued). Uses Optiland's matplotlib-backed `draw()`
to produce a publication-quality layout, then captures it as an SVG string
the frontend can drop straight into a `<div dangerouslySetInnerHTML>` or
serve as a static asset.

We choose matplotlib SVG (not a custom Three.js / Konva render) for this
endpoint because:
- Optiland already knows how to draw the lens cross-section + key rays
- SVG is vector, scales perfectly at any zoom on the Atelier report
- The frontend separately handles the *interactive* 3D scene via R3F;
  this endpoint is the static "engineering drawing" companion
"""

from __future__ import annotations

import io
import warnings

import matplotlib

# Force a headless backend before any other matplotlib import side-effects.
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app.core.lens_system import LayoutSVG  # noqa: E402

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from optiland.optic import Optic  # noqa: E402


def render_layout_svg(
    optic: Optic,
    width_px: int = 1200,
    height_px: int = 600,
    dpi: int = 100,
) -> LayoutSVG:
    """Render the optic's 2D layout as a self-contained SVG string."""
    if width_px <= 0 or height_px <= 0:
        raise ValueError("width_px and height_px must be positive")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        fig, _ax = optic.draw()

    # Resize to the requested viewport.
    fig.set_size_inches(width_px / dpi, height_px / dpi)
    fig.set_dpi(dpi)

    buf = io.StringIO()
    try:
        fig.savefig(
            buf,
            format="svg",
            bbox_inches="tight",
            transparent=True,
        )
        svg_content = buf.getvalue()
    finally:
        plt.close(fig)

    return LayoutSVG(
        width_px=width_px,
        height_px=height_px,
        svg_content=svg_content,
    )
