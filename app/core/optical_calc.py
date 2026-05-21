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


def aperture_diameter_mm(focal_length_mm: float, f_number: float) -> float:
    """Entrance pupil diameter D = f / N. The LLM is forbidden to estimate this —
    when the Wizard records f/# and EFL, the diameter MUST come from here."""
    if focal_length_mm <= 0 or f_number <= 0:
        raise ValueError("focal_length and f_number must be positive")
    return focal_length_mm / f_number


def refract_snell(
    incident_angle_rad: float, n_incident: float, n_refracted: float
) -> float:
    """Snell's law: n1 * sin(θ1) = n2 * sin(θ2). Returns θ2 in radians.

    Raises ValueError on total internal reflection (sin(θ2) > 1).
    """
    import math

    if n_incident <= 0 or n_refracted <= 0:
        raise ValueError("refractive indices must be positive")
    sin_t2 = n_incident * math.sin(incident_angle_rad) / n_refracted
    if abs(sin_t2) > 1.0:
        raise ValueError(
            f"total internal reflection: sin(θ2) = {sin_t2}, "
            f"incident angle {math.degrees(incident_angle_rad):.2f}° exceeds critical "
            f"angle for n1={n_incident}, n2={n_refracted}"
        )
    return math.asin(sin_t2)


def critical_angle_deg(n_dense: float, n_rare: float) -> float:
    """Critical angle for total internal reflection (n_dense > n_rare).
    Below this incidence the ray refracts; above it, total internal reflection.
    """
    import math

    if n_dense <= n_rare:
        raise ValueError(
            f"n_dense ({n_dense}) must be > n_rare ({n_rare}) for TIR to exist"
        )
    return math.degrees(math.asin(n_rare / n_dense))


def paraxial_refraction_matrix(
    radius_mm: float, n_incident: float, n_refracted: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """ABCD matrix for paraxial refraction at a single spherical surface.

    [ 1                            0           ]
    [ -(n2-n1)/(R*n2)         n1/n2           ]

    Returns ((A, B), (C, D)). For a plane surface (radius=+∞), pass +math.inf.
    """
    import math

    if n_incident <= 0 or n_refracted <= 0:
        raise ValueError("refractive indices must be positive")
    if math.isinf(radius_mm):
        power = 0.0
    else:
        if radius_mm == 0:
            raise ValueError("radius cannot be 0 (use math.inf for plane)")
        power = (n_refracted - n_incident) / (radius_mm * n_refracted)
    return ((1.0, 0.0), (-power, n_incident / n_refracted))


def paraxial_translation_matrix(
    distance_mm: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """ABCD matrix for paraxial translation through a homogeneous medium.

    [ 1   t ]
    [ 0   1 ]
    """
    if distance_mm < 0:
        raise ValueError("distance must be non-negative")
    return ((1.0, distance_mm), (0.0, 1.0))


def magnification(
    object_distance_mm: float, image_distance_mm: float
) -> float:
    """Lateral magnification m = -s'/s. Negative = inverted image."""
    if object_distance_mm <= 0:
        raise ValueError("object_distance must be positive")
    return -image_distance_mm / object_distance_mm


def numerical_aperture(f_number: float, n_image_space: float = 1.0) -> float:
    """NA = n * sin(θ_max) ≈ n / (2 * f/#) for moderate f/#.

    For high-NA microscope objectives, NA = n * sin(arctan(1/(2N)))."""
    import math

    if f_number <= 0 or n_image_space <= 0:
        raise ValueError("f_number and n_image_space must be positive")
    return n_image_space * math.sin(math.atan(1.0 / (2.0 * f_number)))
