"""Deterministic optical calculations.

CRITICAL: NEVER let the LLM estimate these. All formulas have analytic ground
truth and unit tests (see tests/test_health.py). When the agent needs a numerical
optical answer, the LLM picks the formula and supplies inputs — but the *math*
runs here.

Phase 0: paraxial / thin-lens / diffraction-limited fundamentals.
Phase 2: extended by Optiland for full ray trace (this module stays the
sanity-check ground truth).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ThinLensSpec:
    """A single thin-lens specification (paraxial approximation)."""

    focal_length_mm: float
    aperture_diameter_mm: float

    @property
    def f_number(self) -> float:
        """f/# = focal_length / aperture_diameter."""
        return self.focal_length_mm / self.aperture_diameter_mm


def thin_lens_image_distance(
    object_distance_mm: float, focal_length_mm: float
) -> float:
    """1/s + 1/s' = 1/f → returns s'.

    Raises ValueError when object sits at the focal point (image at infinity).
    """
    if object_distance_mm <= 0 or focal_length_mm <= 0:
        raise ValueError("object_distance and focal_length must be positive")
    denom = 1.0 / focal_length_mm - 1.0 / object_distance_mm
    if abs(denom) < 1e-9:
        raise ValueError("object at focal point — image at infinity")
    return 1.0 / denom


def angular_field_of_view_deg(
    focal_length_mm: float, image_diagonal_mm: float
) -> float:
    """2 * atan(image_diagonal / (2 * focal_length))."""
    if focal_length_mm <= 0 or image_diagonal_mm <= 0:
        raise ValueError("focal_length and image_diagonal must be positive")
    return 2.0 * math.degrees(math.atan(image_diagonal_mm / (2.0 * focal_length_mm)))


def image_height_mm(focal_length_mm: float, field_angle_deg: float) -> float:
    """h' = f * tan(theta). Image height for an off-axis object at angle theta."""
    if focal_length_mm <= 0:
        raise ValueError("focal_length must be positive")
    return focal_length_mm * math.tan(math.radians(field_angle_deg))


def airy_disk_diameter_um(wavelength_nm: float, f_number: float) -> float:
    """Diffraction-limited Airy disk diameter (first zero): 2.44 * lambda * f/#.

    Wavelength in nm, returns diameter in microns.
    """
    if wavelength_nm <= 0 or f_number <= 0:
        raise ValueError("wavelength and f_number must be positive")
    return 2.44 * wavelength_nm * f_number / 1000.0


def depth_of_field_mm(
    focal_length_mm: float,
    f_number: float,
    subject_distance_mm: float,
    circle_of_confusion_mm: float,
) -> tuple[float, float]:
    """Returns (near_limit_mm, far_limit_mm) of depth of field.

    Hyperfocal H = f^2 / (N * c) + f
    near = s * (H - f) / (H + s - 2f)
    far  = s * (H - f) / (H - s); +inf if denominator <= 0.
    """
    if min(focal_length_mm, f_number, subject_distance_mm, circle_of_confusion_mm) <= 0:
        raise ValueError("all inputs must be positive")
    H = focal_length_mm**2 / (f_number * circle_of_confusion_mm) + focal_length_mm
    near = subject_distance_mm * (H - focal_length_mm) / (
        H + subject_distance_mm - 2 * focal_length_mm
    )
    far_denom = H - subject_distance_mm
    far = (
        float("inf")
        if far_denom <= 0
        else subject_distance_mm * (H - focal_length_mm) / far_denom
    )
    return (near, far)
