"""Tests for app.core.parameter_guards — scenario-specific input bounds."""

import pytest

from app.core.lens_system import Scenario
from app.core.parameter_guards import (
    SCENARIO_BOUNDS,
    ParameterGuardError,
    suggest_efl_range,
    suggest_f_number_range,
    validate_scenario_params,
)
from tests.data.zmx_manifest import ZMX_AMMO


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


def test_real_designs_pass_calibrated_bounds():
    """Every v2-02 real design's nominal params fall inside its calibrated bounds."""
    failures = []
    for a in [entry for entry in ZMX_AMMO if entry.get("bounds_checked", True)]:
        scenario = (
            Scenario.SMARTPHONE_ULTRAWIDE
            if a["nominal_fov_deg"] >= 85.0
            else Scenario.SMARTPHONE_WIDE
        )
        try:
            validate_scenario_params(
                scenario,
                efl_mm=a["nominal_efl_mm"],
                f_number=a["nominal_fnum"],
                fov_deg=a["nominal_fov_deg"],
                image_height_mm=a["nominal_imh_mm"],
                n_elements=a["n_pieces"],
            )
        except ParameterGuardError as e:
            failures.append(f"{a['filename']}: {e.violations}")
    assert not failures, "real designs rejected by calibrated bounds:\n" + "\n".join(failures)


def test_smartphone_bounds_calibrated_from_real_data():
    """Calibration markers: wide allows 3-element designs and small image heights;
    ultrawide is backed by the real ~100 deg US10330891B2 design (E2-01 batch 1)."""
    wide = SCENARIO_BOUNDS[Scenario.SMARTPHONE_WIDE]
    assert wide.n_elements_min == 3  # real ammo has 3P designs (was 5)
    assert wide.image_height_mm_min < 3.5  # real IMH down to 1.8 (was floored at 3.5)
    uw = SCENARIO_BOUNDS[Scenario.SMARTPHONE_ULTRAWIDE]
    # E2-01 batch 1: US10330891B2 is a real 6P design (cross-validation PASS), so the
    # ultrawide FOV ceiling is backed by real ammo -- no longer the unbacked 100-130
    # guess, nor capped at the old ~89.5 deg ammo.
    #
    # The design's manifest nominal moved 100.0 -> 101.6 on 2026-07-30 (the ZMX's own
    # 2 x YFLN, replacing the patent text's rounded value; PATENT_PROVENANCE keeps the
    # declared 100.0, which is a different quantity). Re-deriving this ceiling the way
    # compute_bounds_stats.py suggests would now read 106.7 rather than 105.0, but the
    # bound is left alone: widening SCENARIO_BOUNDS changes which specs the product
    # accepts and is a standing owner decision, not a side effect of a corpus fix.
    assert uw.fov_deg_max == 105.0
    assert uw.fov_deg_max > 101.6  # still covers the design it is calibrated from
