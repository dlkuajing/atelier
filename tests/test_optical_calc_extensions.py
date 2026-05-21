"""Tests for the Phase 2 extensions to optical_calc.py.

Each test has an analytic ground truth.
"""

import math

import pytest

from app.core.optical_calc import (
    aperture_diameter_mm,
    critical_angle_deg,
    magnification,
    numerical_aperture,
    paraxial_refraction_matrix,
    paraxial_translation_matrix,
    refract_snell,
)


# ---------------------------------------------------------------------------
# Aperture diameter
# ---------------------------------------------------------------------------


def test_aperture_diameter_50mm_f_2():
    """50mm f/2 → 25mm aperture."""
    assert math.isclose(aperture_diameter_mm(50.0, 2.0), 25.0, rel_tol=1e-9)


def test_aperture_diameter_7mm_f_2_4():
    """7mm f/2.4 phone tele → ~2.917mm aperture."""
    d = aperture_diameter_mm(7.0, 2.4)
    assert math.isclose(d, 7.0 / 2.4, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Snell's law
# ---------------------------------------------------------------------------


def test_snell_normal_incidence_no_deflection():
    """Normal incidence (θ=0) → θ2=0 regardless of indices."""
    assert math.isclose(refract_snell(0.0, 1.0, 1.5), 0.0, abs_tol=1e-12)


def test_snell_air_to_glass_30deg():
    """Air (n=1) → glass (n=1.5) at 30° → arcsin(sin(30°)/1.5) ≈ 19.47°."""
    theta_2 = refract_snell(math.radians(30.0), 1.0, 1.5)
    expected = math.asin(math.sin(math.radians(30.0)) / 1.5)
    assert math.isclose(theta_2, expected, rel_tol=1e-9)
    assert math.isclose(math.degrees(theta_2), 19.471, abs_tol=0.005)


def test_snell_glass_to_air_above_critical_angle_raises():
    """At 45° in glass→air (critical ~41.8°), TIR."""
    with pytest.raises(ValueError, match="total internal reflection"):
        refract_snell(math.radians(45.0), 1.5, 1.0)


def test_snell_negative_index_raises():
    with pytest.raises(ValueError):
        refract_snell(0.1, -1.0, 1.5)


# ---------------------------------------------------------------------------
# Critical angle
# ---------------------------------------------------------------------------


def test_critical_angle_n_1_5_to_air():
    """Critical angle from BK7 (n≈1.5) to air ≈ 41.81°."""
    angle = critical_angle_deg(1.5, 1.0)
    assert math.isclose(angle, math.degrees(math.asin(1.0 / 1.5)), rel_tol=1e-9)
    assert math.isclose(angle, 41.81, abs_tol=0.01)


def test_critical_angle_high_index():
    """For higher-index glass, critical angle is smaller."""
    a_low = critical_angle_deg(1.5, 1.0)
    a_high = critical_angle_deg(1.9, 1.0)
    assert a_high < a_low


def test_critical_angle_requires_n_dense_greater():
    with pytest.raises(ValueError):
        critical_angle_deg(1.0, 1.5)  # backwards


# ---------------------------------------------------------------------------
# Paraxial matrices
# ---------------------------------------------------------------------------


def test_paraxial_translation_matrix_shape():
    M = paraxial_translation_matrix(5.0)
    assert M == ((1.0, 5.0), (0.0, 1.0))


def test_paraxial_translation_negative_distance_raises():
    with pytest.raises(ValueError):
        paraxial_translation_matrix(-1.0)


def test_paraxial_refraction_plane_surface_has_zero_power():
    """A plane surface (R=inf) has zero refractive power."""
    M = paraxial_refraction_matrix(math.inf, 1.0, 1.5)
    assert math.isclose(M[1][0], 0.0, abs_tol=1e-12)
    assert math.isclose(M[1][1], 1.0 / 1.5, rel_tol=1e-9)


def test_paraxial_refraction_curved_surface_has_power():
    """Convex surface (R>0) should have positive power (negative C in matrix)."""
    M = paraxial_refraction_matrix(50.0, 1.0, 1.5)
    # power = (n2-n1)/(R*n2) = 0.5/(50*1.5) = 1/150
    expected_C = -(1.5 - 1.0) / (50.0 * 1.5)
    assert math.isclose(M[1][0], expected_C, rel_tol=1e-9)


def test_paraxial_refraction_zero_radius_raises():
    with pytest.raises(ValueError):
        paraxial_refraction_matrix(0.0, 1.0, 1.5)


# ---------------------------------------------------------------------------
# Magnification
# ---------------------------------------------------------------------------


def test_magnification_at_2f_is_minus_1():
    """Object at 2f → image at 2f → m = -1 (inverted, same size)."""
    m = magnification(100.0, 100.0)
    assert math.isclose(m, -1.0, rel_tol=1e-9)


def test_magnification_close_object_large_image():
    m = magnification(60.0, 600.0)
    assert math.isclose(m, -10.0, rel_tol=1e-9)


def test_magnification_negative_object_distance_raises():
    with pytest.raises(ValueError):
        magnification(-1.0, 100.0)


# ---------------------------------------------------------------------------
# Numerical aperture
# ---------------------------------------------------------------------------


def test_na_f_2_in_air():
    """NA at f/2 in air ≈ sin(arctan(1/4)) ≈ 0.2425."""
    na = numerical_aperture(2.0)
    expected = math.sin(math.atan(1.0 / 4.0))
    assert math.isclose(na, expected, rel_tol=1e-9)
    assert math.isclose(na, 0.2425, abs_tol=0.0005)


def test_na_high_fnumber_low_na():
    """Higher f/# → lower NA."""
    na_low = numerical_aperture(2.0)
    na_high = numerical_aperture(22.0)
    assert na_high < na_low


def test_na_invalid_inputs_raise():
    with pytest.raises(ValueError):
        numerical_aperture(-1.0)
    with pytest.raises(ValueError):
        numerical_aperture(2.0, n_image_space=0.0)
