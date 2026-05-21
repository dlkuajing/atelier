"""Tests for app.core.parameter_guards — scenario-specific input bounds."""

import pytest

from app.core.lens_system import Scenario
from app.core.parameter_guards import (
    ParameterGuardError,
    SCENARIO_BOUNDS,
    suggest_efl_range,
    suggest_f_number_range,
    validate_scenario_params,
)


def test_valid_smartphone_telephoto_passes():
    validate_scenario_params(
        Scenario.SMARTPHONE_TELEPHOTO,
        efl_mm=7.0,
        f_number=2.4,
        fov_deg=30.0,
        image_height_mm=3.7,
        n_elements=7,
    )  # should not raise


def test_efl_too_small_for_smartphone_telephoto_rejected():
    """Classic LLM hallucination: proposing 0.5mm EFL for a phone tele."""
    with pytest.raises(ParameterGuardError) as exc:
        validate_scenario_params(
            Scenario.SMARTPHONE_TELEPHOTO,
            efl_mm=0.5,
            f_number=2.4,
            fov_deg=30.0,
            image_height_mm=3.7,
        )
    assert "EFL" in str(exc.value)
    assert "smartphone-telephoto" in str(exc.value)


def test_efl_too_large_for_smartphone_telephoto_rejected():
    with pytest.raises(ParameterGuardError):
        validate_scenario_params(
            Scenario.SMARTPHONE_TELEPHOTO,
            efl_mm=50.0,  # way too long for a phone tele
            f_number=2.4,
            fov_deg=30.0,
            image_height_mm=3.7,
        )


def test_f_number_too_aggressive_rejected():
    """f/0.5 is below what scenarios allow (except microscope NA)."""
    with pytest.raises(ParameterGuardError) as exc:
        validate_scenario_params(
            Scenario.SMARTPHONE_TELEPHOTO,
            efl_mm=7.0,
            f_number=0.8,
            fov_deg=30.0,
            image_height_mm=3.7,
        )
    assert "f/#" in str(exc.value)


def test_multiple_violations_aggregated():
    with pytest.raises(ParameterGuardError) as exc:
        validate_scenario_params(
            Scenario.SMARTPHONE_TELEPHOTO,
            efl_mm=0.5,
            f_number=10.0,
            fov_deg=180.0,
            image_height_mm=50.0,
        )
    assert len(exc.value.violations) >= 3  # at least 3 distinct violations


def test_dslr_prime_50mm_passes():
    validate_scenario_params(
        Scenario.DSLR_PRIME,
        efl_mm=50.0,
        f_number=1.8,
        fov_deg=46.8,
        image_height_mm=21.6,
        n_elements=8,
    )  # classic 50mm f/1.8 full-frame should pass


def test_ar_near_eye_passes():
    validate_scenario_params(
        Scenario.AR_NEAR_EYE,
        efl_mm=18.0,
        f_number=1.8,
        fov_deg=40.0,
        image_height_mm=8.0,
        n_elements=5,
    )


def test_suggest_helpers_return_bounds():
    lo, hi = suggest_efl_range(Scenario.SMARTPHONE_TELEPHOTO)
    assert lo > 0 and hi > lo
    assert (lo, hi) == (
        SCENARIO_BOUNDS[Scenario.SMARTPHONE_TELEPHOTO].efl_mm_min,
        SCENARIO_BOUNDS[Scenario.SMARTPHONE_TELEPHOTO].efl_mm_max,
    )

    lo_n, hi_n = suggest_f_number_range(Scenario.DSLR_PRIME)
    assert lo_n > 0 and hi_n > lo_n


def test_all_scenarios_have_bounds():
    """Every Scenario enum value must have bounds defined."""
    for scenario in Scenario:
        assert scenario in SCENARIO_BOUNDS, f"missing bounds for {scenario}"
