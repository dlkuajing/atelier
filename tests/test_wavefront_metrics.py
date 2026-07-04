"""Tests for wavefront RMS, Strehl, and Zernike-backed metric exposure."""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest
from optiland.wavefront import OPD, Wavefront
from optiland.zernike import ZernikeFit

from app.core.wavefront_metrics import (
    WavefrontMetricsResult,
    compute_wavefront_metrics,
    strehl_from_rms_waves,
)
from app.core.zmx_ingest import (
    ZMX_AMMO_DIR,
    load_normalized_zmx,
    regularize_fields_to_angle,
)
from scripts.evaluate_design_agent import build_json_report, evaluate
from tests.data.zmx_manifest import ZMX_AMMO

_NUM_RAYS = 6
_NUM_ZERNIKE_TERMS = 12
_FIELD_INDEX = 2


@pytest.fixture(scope="module")
def real_phone_wavefront_metrics():
    """Use a real phone design because synthetic demo optics return NaN OPD."""
    ammo = ZMX_AMMO[0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        optic = load_normalized_zmx(ZMX_AMMO_DIR / ammo["filename"])
        regularize_fields_to_angle(optic, ammo["nominal_fov_deg"])
        result = compute_wavefront_metrics(
            optic,
            num_rays=_NUM_RAYS,
            num_zernike_terms=_NUM_ZERNIKE_TERMS,
        )
    return result, optic


def _native_processed_opd(optic, field_coordinate: tuple[float, float]):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        opd = OPD(
            optic,
            field=field_coordinate,
            wavelength="primary",
            num_rays=_NUM_RAYS,
            remove_tilt=False,
        )
    data = opd.get_data(opd.fields[0], opd.wavelengths[0])
    detrended = np.asarray(
        Wavefront.fit_and_remove_tilt(data, remove_piston=True),
        dtype=float,
    ).flatten()
    intensity = np.asarray(data.intensity, dtype=float).flatten()
    valid = np.isfinite(detrended) & np.isfinite(intensity) & (intensity > 0)
    return opd, detrended, valid


def test_real_case_wavefront_payload_is_finite(real_phone_wavefront_metrics):
    result, _optic = real_phone_wavefront_metrics

    assert isinstance(result, WavefrontMetricsResult)
    assert result.wavelength_nm == pytest.approx(587.6, abs=1e-9)
    assert result.num_rays == _NUM_RAYS
    assert result.remove_piston is True
    assert result.remove_tilt is True
    assert result.strehl_model == "marechal"
    assert len(result.fields) == 4
    assert [field.field_fraction for field in result.fields] == pytest.approx(
        [0.0, 0.5, 0.7, 1.0],
        abs=1e-12,
    )

    for field in result.fields:
        assert math.isfinite(field.rms_wavefront_error_waves)
        assert field.rms_wavefront_error_waves >= 0.0
        assert 0.0 <= field.strehl_ratio <= 1.0
        assert field.valid_ray_count > 10
        assert field.zernike_type == "fringe"
        assert len(field.zernike_coefficients_waves) == _NUM_ZERNIKE_TERMS
        assert all(math.isfinite(value) for value in field.zernike_coefficients_waves)


def test_rms_and_strehl_cross_check_against_optiland_native_wavefront(
    real_phone_wavefront_metrics,
):
    result, optic = real_phone_wavefront_metrics
    field = result.fields[_FIELD_INDEX]

    _opd, native_opd, valid = _native_processed_opd(optic, field.field_coordinate)
    expected_rms = float(np.sqrt(np.mean(native_opd[valid] ** 2)))

    assert field.rms_wavefront_error_waves == pytest.approx(expected_rms, abs=1e-10)
    assert field.strehl_ratio == pytest.approx(
        strehl_from_rms_waves(expected_rms),
        abs=1e-15,
    )
    assert field.valid_ray_count == int(valid.sum())


def test_zernike_coefficients_cross_check_against_optiland_native_fit(
    real_phone_wavefront_metrics,
):
    result, optic = real_phone_wavefront_metrics
    field = result.fields[_FIELD_INDEX]

    opd, native_opd, valid = _native_processed_opd(optic, field.field_coordinate)
    expected_fit = ZernikeFit(
        np.asarray(opd.distribution.x, dtype=float).flatten()[valid],
        np.asarray(opd.distribution.y, dtype=float).flatten()[valid],
        native_opd[valid],
        "fringe",
        _NUM_ZERNIKE_TERMS,
    )

    np.testing.assert_allclose(
        field.zernike_coefficients_waves,
        np.asarray(expected_fit.coeffs, dtype=float),
        rtol=0,
        atol=1e-9,
    )


def test_strehl_formula_handles_diffraction_and_underflow_cases():
    assert strehl_from_rms_waves(0.0) == pytest.approx(1.0, abs=1e-15)
    assert strehl_from_rms_waves(0.07) == pytest.approx(
        math.exp(-((2.0 * math.pi * 0.07) ** 2)),
        abs=1e-15,
    )
    assert strehl_from_rms_waves(20.0) == 0.0

    with pytest.raises(ValueError, match="finite non-negative"):
        strehl_from_rms_waves(-0.01)


def test_compute_wavefront_metrics_rejects_invalid_inputs(real_phone_wavefront_metrics):
    _result, optic = real_phone_wavefront_metrics

    with pytest.raises(ValueError, match="num_rays"):
        compute_wavefront_metrics(optic, num_rays=1)
    with pytest.raises(ValueError, match="wavelength_nm"):
        compute_wavefront_metrics(optic, wavelength_nm=0.0)
    with pytest.raises(ValueError, match="num_zernike_terms"):
        compute_wavefront_metrics(optic, num_zernike_terms=-1)


def test_eval_json_report_exposes_wavefront_metric_summary():
    rows = evaluate(case_names={"low_cost_accepts_three_piece_seed"})

    report = build_json_report(rows)

    packet = report["cases"][0]["wavefront_metrics"]
    assert packet["status"] == "available"
    assert packet["wavelength_nm"] == pytest.approx(587.6, abs=1e-9)
    assert packet["field_count"] >= 1
    assert packet["max_rms_wavefront_error_waves"] >= 0.0
    assert 0.0 <= packet["min_strehl_ratio"] <= 1.0
    assert packet["strehl_model"] == "marechal"
