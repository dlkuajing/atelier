"""Plausibility gate for a corpus row's real image height.

The image height a corpus row declares is a *real chief-ray* number: it comes
out of a ray trace, not out of the first-order prescription. That makes it the
right anchor for routing and for the P2 control spec -- and it also makes it
capable of being silently, arbitrarily wrong, because a ray trace can return a
finite float for a ray that never formed an image. `np.isfinite` is not a
validity test: a diverging ray is finite right up to overflow, and the corpus
carries eight rows near 6e17 mm to prove it.

So every real image height is screened against the design's own first-order
reference `f * tan(half-field)` before it is allowed to anchor anything.

The screen is a *containment* gate, not an accuracy check. Real distortion moves
the chief ray off the paraxial reference by design, and a deviation of tens of
percent is a property of the lens, not a defect -- an ultrawide with deliberate
barrel distortion is supposed to deviate. The band therefore has to sit outside
every mapping law an imaging lens actually uses:

    ratio = real_image_height / (f * tan(theta)) = 1 + relative distortion

    * f*sin(theta) -- orthographic, the most compressive projection ever built
      into a lens -- gives ratio = cos(theta). At the corpus's widest half
      fields (~60 deg) that is 0.50.
    * f*theta -- equidistant fisheye -- gives theta/tan(theta) = 0.60 there.
    * Pincushion past +100% (ratio 2.0) does not occur in a phone lens.

`RATIO_MIN` / `RATIO_MAX` leave a further factor of two below and above those,
so no real design can trip the gate. What trips it is divergence, which misses
by orders of magnitude rather than by percent -- see `.planning/evidence/
corpus-truth-audit-triage-2026-07-30.md` finding (2).

The reference has to be screened too. `tan` blows up as the half field
approaches 90 deg, and the corpus holds rows whose reference is 1.7e16 mm and
rows whose reference is *negative*; a gate that divides by those numbers passes
anything. A row whose reference is unusable is not "fine", it is unscreenable,
and is reported as its own outcome rather than folded into either verdict.
"""

from __future__ import annotations

import math
from enum import StrEnum

# Widest half field a real imaging lens reaches before `tan` stops being a
# usable reference at all. Beyond this the first-order image height is not a
# meaningful quantity, not merely a large one.
MAX_REFERENCE_HALF_FIELD_DEG = 85.0

RATIO_MIN = 0.25
RATIO_MAX = 4.0


class ImageHeightVerdict(StrEnum):
    PLAUSIBLE = "plausible"
    IMPLAUSIBLE = "implausible"
    REFERENCE_UNUSABLE = "reference-unusable"


def first_order_image_height_mm(focal_length_mm: float, half_field_deg: float) -> float | None:
    """First-order image height `f * tan(half-field)`, or None when unusable.

    Returns None rather than a large number when the half field is at or past
    the point where `tan` stops discriminating, so callers cannot accidentally
    divide by 1.7e16 and conclude everything is fine.
    """
    if not (math.isfinite(focal_length_mm) and math.isfinite(half_field_deg)):
        return None
    if focal_length_mm <= 0.0:
        return None
    if not (0.0 < half_field_deg < MAX_REFERENCE_HALF_FIELD_DEG):
        return None
    value = focal_length_mm * math.tan(math.radians(half_field_deg))
    if not math.isfinite(value) or value <= 0.0:
        return None
    return value


def screen_image_height(
    image_height_mm: float,
    first_order_mm: float | None,
) -> tuple[ImageHeightVerdict, float | None]:
    """Classify a real image height against its first-order reference.

    Returns the verdict and the ratio behind it (None when no ratio could be
    formed). Every caller has to handle REFERENCE_UNUSABLE explicitly -- it is
    neither a pass nor a failure of the image height.
    """
    if first_order_mm is None or not math.isfinite(first_order_mm) or first_order_mm <= 0.0:
        return ImageHeightVerdict.REFERENCE_UNUSABLE, None
    if not math.isfinite(image_height_mm) or image_height_mm <= 0.0:
        return ImageHeightVerdict.IMPLAUSIBLE, None
    ratio = image_height_mm / first_order_mm
    if RATIO_MIN <= ratio <= RATIO_MAX:
        return ImageHeightVerdict.PLAUSIBLE, ratio
    return ImageHeightVerdict.IMPLAUSIBLE, ratio


def describe_failure(
    image_height_mm: float,
    first_order_mm: float | None,
    verdict: ImageHeightVerdict,
    ratio: float | None,
) -> str:
    """One-line reason for a non-plausible verdict, for exceptions and reports."""
    if verdict is ImageHeightVerdict.REFERENCE_UNUSABLE:
        return (
            f"first-order image height reference is unusable ({first_order_mm!r}); "
            f"real image height {image_height_mm!r} cannot be screened"
        )
    if ratio is None:
        return f"real image height is not a positive finite length: {image_height_mm!r}"
    return (
        f"real image height {image_height_mm:.6g} mm is {ratio:.4g}x its first-order "
        f"reference {first_order_mm:.6g} mm, outside the plausible band "
        f"[{RATIO_MIN:g}, {RATIO_MAX:g}]"
    )
