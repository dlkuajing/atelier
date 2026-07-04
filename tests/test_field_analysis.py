"""Tests for app.core.field_analysis: real-design field curvature + distortion."""

from __future__ import annotations

import math
import warnings

import pytest

from app.core.field_analysis import FieldAnalysisResult, compute_field_analysis
from app.core.zmx_ingest import (
    ZMX_AMMO_DIR,
    load_normalized_zmx,
    regularize_fields_to_angle,
)
from tests.data.zmx_manifest import ZMX_AMMO

_NUM_POINTS = 16


@pytest.fixture(scope="module")
def real_phone_field_analysis() -> tuple[FieldAnalysisResult, dict]:
    """Use a real case-library smartphone design, not a synthetic sample optic."""
    ammo = ZMX_AMMO[0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        optic = load_normalized_zmx(ZMX_AMMO_DIR / ammo["filename"])
        regularize_fields_to_angle(optic, ammo["nominal_fov_deg"])
        result = compute_field_analysis(optic, num_points=_NUM_POINTS)
    return result, ammo


def test_real_case_field_axis_and_shape(real_phone_field_analysis):
    result, ammo = real_phone_field_analysis

    assert isinstance(result, FieldAnalysisResult)
    assert result.field_unit == "deg"
    assert len(result.field_fraction) == _NUM_POINTS
    assert len(result.field_coordinate) == _NUM_POINTS
    assert len(result.tangential_field_curvature_mm) == _NUM_POINTS
    assert len(result.sagittal_field_curvature_mm) == _NUM_POINTS
    assert len(result.distortion_pct) == _NUM_POINTS

    assert math.isclose(result.field_fraction[0], 0.0, abs_tol=1e-12)
    assert math.isclose(result.field_fraction[-1], 1.0, abs_tol=1e-12)
    assert result.field_fraction == sorted(result.field_fraction)
    assert math.isclose(result.field_coordinate[0], 0.0, abs_tol=1e-12)
    assert math.isclose(
        result.field_coordinate[-1],
        ammo["nominal_fov_deg"] / 2.0,
        rel_tol=1e-9,
    )


def test_real_case_field_curvature_values_are_finite_and_reasonable(real_phone_field_analysis):
    result, _ammo = real_phone_field_analysis
    tangential = result.tangential_field_curvature_mm
    sagittal = result.sagittal_field_curvature_mm

    assert all(math.isfinite(v) for v in tangential)
    assert all(math.isfinite(v) for v in sagittal)
    # Real phone lenses have measurable field curvature, but this known healthy
    # case stays in the tens-of-microns image-plane delta range.
    assert max(abs(v) for v in tangential) < 0.1
    assert max(abs(v) for v in sagittal) < 0.1
    assert max(tangential) - min(tangential) > 0.005
    assert max(abs(t - s) for t, s in zip(tangential[1:], sagittal[1:], strict=False)) > 0.005


def test_real_case_distortion_pct_values_are_reasonable(real_phone_field_analysis):
    result, _ammo = real_phone_field_analysis
    distortion = result.distortion_pct

    assert result.distortion_model == "f-tan"
    assert math.isclose(result.wavelength_nm, 587.6, abs_tol=1e-6)
    assert all(math.isfinite(v) for v in distortion)
    assert math.isclose(distortion[0], 0.0, abs_tol=1e-8)
    assert max(abs(v) for v in distortion) < 5.0
    assert 0.5 < abs(distortion[-1]) < 2.5


def test_compute_field_analysis_rejects_too_few_points(real_phone_field_analysis):
    _result, ammo = real_phone_field_analysis
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        optic = load_normalized_zmx(ZMX_AMMO_DIR / ammo["filename"])
        regularize_fields_to_angle(optic, ammo["nominal_fov_deg"])
        with pytest.raises(ValueError, match="num_points"):
            compute_field_analysis(optic, num_points=1)
