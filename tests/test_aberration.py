"""Tests for app.core.aberration — Optiland MTF / spot RMS / Airy disc."""

import math

import pytest

from app.core.aberration import MTFResult, compute_mtf
from app.core.lens_system import Scenario
from app.core.optical_engine import build_optic_for_scenario


@pytest.fixture
def smartphone_tele_optic():
    return build_optic_for_scenario(
        Scenario.SMARTPHONE_TELEPHOTO, target_efl_mm=7.0, target_f_number=2.4
    )


# ---------------------------------------------------------------------------
# compute_mtf
# ---------------------------------------------------------------------------


def test_compute_mtf_returns_valid_result(smartphone_tele_optic):
    result = compute_mtf(smartphone_tele_optic)
    assert isinstance(result, MTFResult)


def test_mtf_freq_axis_starts_at_zero_and_increases(smartphone_tele_optic):
    result = compute_mtf(smartphone_tele_optic)
    freq = result.freq_lp_per_mm
    assert len(freq) > 10
    assert math.isclose(freq[0], 0.0, abs_tol=1e-9)
    assert freq == sorted(freq), "freq must be monotonically increasing"


def test_mtf_first_value_is_one_for_each_field(smartphone_tele_optic):
    """MTF at DC (freq=0) is always 1.0 by definition."""
    result = compute_mtf(smartphone_tele_optic)
    for field in result.fields:
        assert math.isclose(field.sagittal[0], 1.0, abs_tol=1e-3)
        assert math.isclose(field.tangential[0], 1.0, abs_tol=1e-3)


def test_mtf_values_in_zero_one_range(smartphone_tele_optic):
    """MTF values are always between 0 and 1."""
    result = compute_mtf(smartphone_tele_optic)
    for field in result.fields:
        for v in field.sagittal:
            assert 0.0 <= v <= 1.0 + 1e-6
        for v in field.tangential:
            assert 0.0 <= v <= 1.0 + 1e-6


def test_diffraction_limited_mtf_present(smartphone_tele_optic):
    result = compute_mtf(smartphone_tele_optic)
    assert len(result.diff_limited) == len(result.freq_lp_per_mm)
    # First value (DC) is 1.0; last value (at cutoff) should be near 0
    assert math.isclose(result.diff_limited[0], 1.0, abs_tol=1e-3)


def test_airy_disc_diameter_positive(smartphone_tele_optic):
    result = compute_mtf(smartphone_tele_optic)
    assert result.airy_disc_diameter_um > 0


def test_cutoff_freq_positive(smartphone_tele_optic):
    result = compute_mtf(smartphone_tele_optic)
    assert result.cutoff_freq_lp_per_mm > 0


def test_rms_spot_per_field_present_and_positive(smartphone_tele_optic):
    result = compute_mtf(smartphone_tele_optic)
    assert len(result.rms_spot_radius_um_by_field) == len(result.fields)
    for rms in result.rms_spot_radius_um_by_field:
        assert rms >= 0


def test_geometric_mtf_at_or_below_diffraction_limit(smartphone_tele_optic):
    """Geometric MTF can't exceed the diffraction limit by more than tiny noise."""
    result = compute_mtf(smartphone_tele_optic)
    for field in result.fields:
        for fi in range(len(result.freq_lp_per_mm)):
            limit = result.diff_limited[fi]
            # Sagittal/tangential should not exceed limit by > 5% (small slack
            # accounts for sampling artifacts at low freq).
            assert field.sagittal[fi] <= limit + 0.05
            assert field.tangential[fi] <= limit + 0.05
