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
import math
import warnings

import matplotlib

# Force a headless backend before any other matplotlib import side-effects.
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app.core.lens_system import LayoutSVG  # noqa: E402

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from optiland.optic import Optic  # noqa: E402


def _finite_lens_positions(optic: Optic) -> list[float]:
    try:
        positions = list(getattr(optic.surfaces, "positions", []))
    except Exception:
        return []
    flattened: list[float] = []
    for value in positions:
        try:
            if hasattr(value, "flatten"):
                flattened.extend(float(item) for item in value.flatten())
            elif isinstance(value, (list, tuple)):
                flattened.extend(float(item) for item in value)
            else:
                flattened.append(float(value))
        except (TypeError, ValueError):
            continue
    # Surface 0 is the object plane in Optiland's stack. It may be infinity,
    # a long finite object distance, or a sentinel; none of those should set
    # the engineering drawing viewport for compact phone-camera lenses.
    return [value for value in flattened[1:] if math.isfinite(value) and abs(value) < 1_000_000]


def _frame_lens_stack(ax: object, optic: Optic) -> None:
    positions = _finite_lens_positions(optic)
    if len(positions) < 2:
        return
    min_z = min(positions)
    max_z = max(positions)
    span = max(max_z - min_z, 0.1)
    margin = max(0.1, span * 0.08)
    try:
        ax.set_xlim(min_z - margin, max_z + margin)
    except Exception:
        return


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
        fig, ax = optic.draw()
    _frame_lens_stack(ax, optic)

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
