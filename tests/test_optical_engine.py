"""Tests for app.core.optical_engine — Optiland integration."""

import math

import pytest

from app.core.lens_system import Scenario
from app.core.optical_engine import (
    build_optic_for_scenario,
    compute_paraxial_summary,
    extract_surface_descriptors,
    raytrace_from_spec,
    trace_optic,
)

# ---------------------------------------------------------------------------
# build_optic_for_scenario
# ---------------------------------------------------------------------------


def test_build_smartphone_telephoto_hits_target_efl():
    optic = build_optic_for_scenario(
        Scenario.SMARTPHONE_TELEPHOTO,
        target_efl_mm=7.0,
        target_f_number=2.4,
    )
    summary = compute_paraxial_summary(optic)
    assert math.isclose(summary.effective_focal_length_mm, 7.0, rel_tol=1e-3)


def test_build_dslr_prime_50mm():
    optic = build_optic_for_scenario(
        Scenario.DSLR_PRIME, target_efl_mm=50.0, target_f_number=1.8
    )
    summary = compute_paraxial_summary(optic)
    assert math.isclose(summary.effective_focal_length_mm, 50.0, rel_tol=1e-3)


def test_build_smartphone_wide():
    optic = build_optic_for_scenario(
        Scenario.SMARTPHONE_WIDE, target_efl_mm=5.0, target_f_number=1.8
    )
    summary = compute_paraxial_summary(optic)
    assert math.isclose(summary.effective_focal_length_mm, 5.0, rel_tol=1e-3)
    # Cooke Triplet has 3 elements + object + stop + image = 7+ surfaces
    assert summary.n_surfaces >= 6


def test_build_unknown_scenario_raises():
    with pytest.raises((ValueError, KeyError)):
        # Use a fake Scenario-like sentinel
        build_optic_for_scenario("not-a-scenario", target_efl_mm=10.0)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Paraxial summary
# ---------------------------------------------------------------------------


def test_paraxial_summary_has_sane_values_smartphone_tele():
    optic = build_optic_for_scenario(
        Scenario.SMARTPHONE_TELEPHOTO, target_efl_mm=7.0, target_f_number=2.4
    )
    s = compute_paraxial_summary(optic)
    assert s.effective_focal_length_mm > 0
    assert s.f_number > 0
    assert s.entrance_pupil_diameter_mm > 0
    assert s.total_track_mm > 0
    # Total track for a 7mm phone tele should be < ~20mm
    assert s.total_track_mm < 20.0
    assert s.n_surfaces >= 4


def test_paraxial_summary_dslr_total_track_larger():
    """50mm DSLR prime should have bigger total_track than 7mm phone tele."""
    s_phone = compute_paraxial_summary(
        build_optic_for_scenario(
            Scenario.SMARTPHONE_TELEPHOTO, target_efl_mm=7.0, target_f_number=2.4
        )
    )
    s_dslr = compute_paraxial_summary(
        build_optic_for_scenario(
            Scenario.DSLR_PRIME, target_efl_mm=50.0, target_f_number=1.8
        )
    )
    assert s_dslr.total_track_mm > s_phone.total_track_mm


# ---------------------------------------------------------------------------
# Surface descriptors
# ---------------------------------------------------------------------------


def test_surface_descriptors_have_increasing_z():
    optic = build_optic_for_scenario(
        Scenario.SMARTPHONE_TELEPHOTO, target_efl_mm=7.0, target_f_number=2.4
    )
    surfs = extract_surface_descriptors(optic)
    # Skip object surface (z is sentinel -1e9)
    real_surfs = [s for s in surfs if not s.is_object]
    z_values = [s.z_mm for s in real_surfs]
    assert z_values == sorted(z_values), "surface Z positions should be monotonically increasing"


def test_surface_descriptors_have_one_stop_one_image_one_object():
    optic = build_optic_for_scenario(
        Scenario.SMARTPHONE_TELEPHOTO, target_efl_mm=7.0, target_f_number=2.4
    )
    surfs = extract_surface_descriptors(optic)
    assert sum(1 for s in surfs if s.is_stop) == 1
    assert sum(1 for s in surfs if s.is_image) == 1
    assert sum(1 for s in surfs if s.is_object) == 1


# ---------------------------------------------------------------------------
# Ray trace
# ---------------------------------------------------------------------------


def test_trace_optic_returns_three_paths():
    optic = build_optic_for_scenario(
        Scenario.SMARTPHONE_TELEPHOTO, target_efl_mm=7.0, target_f_number=2.4
    )
    result = trace_optic(optic, assembly_name="test")
    assert len(result.sampled_paths) == 3
    # Chief + marginal upper + marginal lower
    ray_ids = {p.ray_id for p in result.sampled_paths}
    assert ray_ids == {"chief-axial", "marginal-upper", "marginal-lower"}


def test_trace_optic_paths_have_finite_points():
    optic = build_optic_for_scenario(
        Scenario.SMARTPHONE_TELEPHOTO, target_efl_mm=7.0, target_f_number=2.4
    )
    result = trace_optic(optic, assembly_name="test")
    for path in result.sampled_paths:
        assert len(path.points_mm) > 0
        for z, y in path.points_mm:
            assert math.isfinite(z)
            assert math.isfinite(y)


def test_trace_optic_marginal_rays_symmetric():
    """Upper marginal and lower marginal should be mirror images across z axis."""
    optic = build_optic_for_scenario(
        Scenario.SMARTPHONE_TELEPHOTO, target_efl_mm=7.0, target_f_number=2.4
    )
    result = trace_optic(optic, assembly_name="test")
    upper = next(p for p in result.sampled_paths if p.ray_id == "marginal-upper")
    lower = next(p for p in result.sampled_paths if p.ray_id == "marginal-lower")
    assert len(upper.points_mm) == len(lower.points_mm)
    for (zu, yu), (zl, yl) in zip(upper.points_mm, lower.points_mm, strict=True):
        assert math.isclose(zu, zl, abs_tol=1e-9)
        assert math.isclose(yu, -yl, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# raytrace_from_spec — top-level entry
# ---------------------------------------------------------------------------


def test_raytrace_from_spec_smartphone_telephoto_end_to_end():
    summary, surfaces, trace = raytrace_from_spec(
        scenario=Scenario.SMARTPHONE_TELEPHOTO,
        target_efl_mm=7.0,
        target_f_number=2.4,
    )
    assert math.isclose(summary.effective_focal_length_mm, 7.0, rel_tol=1e-3)
    assert len(surfaces) >= 4
    assert len(trace.sampled_paths) == 3
    assert trace.assembly_name.startswith("smartphone-telephoto")


def test_raytrace_from_spec_dslr_prime_50mm_end_to_end():
    summary, surfaces, trace = raytrace_from_spec(
        scenario=Scenario.DSLR_PRIME,
        target_efl_mm=50.0,
        target_f_number=1.8,
    )
    assert math.isclose(summary.effective_focal_length_mm, 50.0, rel_tol=1e-3)
    assert len(surfaces) >= 6
    assert len(trace.sampled_paths) == 3
