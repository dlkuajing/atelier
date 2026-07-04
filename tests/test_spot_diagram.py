"""Tests for app.core.spot_diagram: multi-field, multi-wavelength spot data."""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest
from optiland.visualization.system.utils import transform

from app.core import spot_diagram as spot_diagram_module
from app.core.spot_diagram import SpotDiagramResult, compute_spot_diagram
from app.core.zmx_ingest import (
    ZMX_AMMO_DIR,
    load_normalized_zmx,
    regularize_fields_to_angle,
)
from tests.data.zmx_manifest import ZMX_AMMO

_NUM_RINGS = 3
_FIELD_INDEX = 2
_WAVELENGTH_INDEX = 1


def test_center_spots_private_api_guard_rejects_unexpected_optiland_version(monkeypatch):
    monkeypatch.setattr(spot_diagram_module, "_installed_optiland_version", lambda: "0.7.0")

    with pytest.raises(RuntimeError, match="Optiland version"):
        spot_diagram_module._assert_center_spots_api_supported()


@pytest.fixture(scope="module")
def real_phone_spot_diagram():
    """Use a real case-library smartphone design with visible F/d/C wavelengths."""
    ammo = ZMX_AMMO[0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        optic = load_normalized_zmx(ZMX_AMMO_DIR / ammo["filename"])
        regularize_fields_to_angle(optic, ammo["nominal_fov_deg"])
        result = compute_spot_diagram(optic, num_rings=_NUM_RINGS)
    return result, optic


def test_real_case_payload_is_multi_field_multi_wavelength(real_phone_spot_diagram):
    result, _optic = real_phone_spot_diagram

    assert isinstance(result, SpotDiagramResult)
    assert result.coordinates == "local"
    assert result.reference == "chief_ray"
    assert result.distribution == "hexapolar"
    assert result.num_rings == _NUM_RINGS
    assert result.field_count == 4
    assert result.wavelength_count == 3

    wavelengths = [spot.wavelength_nm for spot in result.fields[0].spots_by_wavelength]
    assert wavelengths == pytest.approx([486.1, 587.6, 656.3], abs=1e-9)
    assert [field.field_fraction for field in result.fields] == pytest.approx(
        [0.0, 0.5, 0.7, 1.0],
        abs=1e-12,
    )

    for field in result.fields:
        assert len(field.spots_by_wavelength) == 3
        for spot in field.spots_by_wavelength:
            assert len(spot.x_um) > 10
            assert len(spot.x_um) == len(spot.y_um) == len(spot.intensity)
            assert all(math.isfinite(v) for v in spot.x_um)
            assert all(math.isfinite(v) for v in spot.y_um)
            assert all(math.isfinite(v) and v > 0 for v in spot.intensity)
            assert spot.rms_radius_um > 0
            assert spot.geometric_radius_um >= spot.rms_radius_um


def test_airy_radius_reference_is_present_for_each_field(real_phone_spot_diagram):
    result, _optic = real_phone_spot_diagram

    assert result.airy_reference_wavelength_nm == pytest.approx(587.6, abs=1e-9)
    for field in result.fields:
        assert field.airy_radius_x_um > 0
        assert field.airy_radius_y_um > 0

    assert result.fields[-1].airy_radius_x_um > result.fields[0].airy_radius_x_um
    assert result.fields[-1].airy_radius_y_um > result.fields[0].airy_radius_y_um


def test_spot_points_cross_check_against_optiland_native_trace(real_phone_spot_diagram):
    result, optic = real_phone_spot_diagram
    field = result.fields[_FIELD_INDEX]
    spot = field.spots_by_wavelength[_WAVELENGTH_INDEX]
    wavelength_um = spot.wavelength_nm / 1000.0

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        optic.trace(
            field.field_coordinate[0],
            field.field_coordinate[1],
            wavelength_um,
            _NUM_RINGS,
            "hexapolar",
        )

    x_global = np.asarray(optic.surfaces.x[-1, :], dtype=float)
    y_global = np.asarray(optic.surfaces.y[-1, :], dtype=float)
    z_global = np.asarray(optic.surfaces.z[-1, :], dtype=float)
    intensity = np.asarray(optic.surfaces.intensity[-1, :], dtype=float)
    passed = intensity > 0
    x_local, y_local, _z_local = transform(
        x_global[passed],
        y_global[passed],
        z_global[passed],
        optic.image_surface,
        is_global=True,
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        chief = optic.trace_generic(
            Hx=field.field_coordinate[0],
            Hy=field.field_coordinate[1],
            Px=0,
            Py=0,
            wavelength=wavelength_um,
        )
    chief_x, chief_y, _chief_z = transform(
        chief.x,
        chief.y,
        chief.z,
        optic.image_surface,
        is_global=True,
    )
    expected_x_um = (np.asarray(x_local) - np.asarray(chief_x).ravel()[0]) * 1000.0
    expected_y_um = (np.asarray(y_local) - np.asarray(chief_y).ravel()[0]) * 1000.0
    expected_intensity = intensity[passed]

    np.testing.assert_allclose(spot.x_um, expected_x_um, rtol=0, atol=1e-9)
    np.testing.assert_allclose(spot.y_um, expected_y_um, rtol=0, atol=1e-9)
    np.testing.assert_allclose(spot.intensity, expected_intensity, rtol=0, atol=1e-12)

    expected_radius_um = np.hypot(expected_x_um, expected_y_um)
    assert spot.rms_radius_um == pytest.approx(
        float(np.sqrt(np.mean(expected_radius_um**2))),
        abs=1e-9,
    )
    assert spot.geometric_radius_um == pytest.approx(
        float(np.max(expected_radius_um)),
        abs=1e-9,
    )


def test_compute_spot_diagram_rejects_invalid_inputs(real_phone_spot_diagram):
    _result, optic = real_phone_spot_diagram

    with pytest.raises(ValueError, match="num_rings"):
        compute_spot_diagram(optic, num_rings=0)
    with pytest.raises(ValueError, match="wavelengths_nm"):
        compute_spot_diagram(optic, wavelengths_nm=[0.0])
