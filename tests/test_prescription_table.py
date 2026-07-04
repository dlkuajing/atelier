"""Tests for app.core.prescription_table: full lens prescription serialization."""

from __future__ import annotations

import json
import math
import warnings

import numpy as np
import pytest

from app.core.prescription_table import (
    PrescriptionTable,
    extract_prescription_table,
    load_prescription_table,
)
from app.core.zmx_ingest import ZMX_AMMO_DIR, load_normalized_zmx

_ZMX_FILENAME = "5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15.zmx"


@pytest.fixture(scope="module")
def real_phone_prescription() -> tuple[PrescriptionTable, object]:
    path = ZMX_AMMO_DIR / _ZMX_FILENAME
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        optic = load_normalized_zmx(path)
        table = extract_prescription_table(optic, source_zmx=path)
    return table, optic


def _finite_or_none(value) -> float | None:
    try:
        arr = np.asarray(value, dtype=float).flatten()
    except (TypeError, ValueError):
        return None
    if arr.size == 0:
        return None
    out = float(arr[0])
    return out if math.isfinite(out) else None


def _assert_float_or_none(actual: float | None, expected: float | None) -> None:
    if expected is None:
        assert actual is None
    else:
        assert actual == pytest.approx(expected, abs=1e-12)


def _material_scalar(material: dict, key: str) -> float | None:
    return _finite_or_none(material[key]) if key in material else None


def test_prescription_table_shape_and_json_safety(real_phone_prescription):
    table, optic = real_phone_prescription

    assert isinstance(table, PrescriptionTable)
    assert table.source_zmx == _ZMX_FILENAME
    assert table.surface_count == int(optic.surfaces.num_surfaces)
    assert table.stop_surface_index == int(optic.surfaces.stop_index)
    assert len(table.surfaces) == table.surface_count
    assert [surface.index for surface in table.surfaces] == list(range(table.surface_count))
    assert sum(1 for surface in table.surfaces if surface.is_stop) == 1
    assert table.surfaces[0].is_object
    assert table.surfaces[-1].is_image

    dumped = table.model_dump(mode="json")
    json.dumps(dumped, allow_nan=False)
    assert dumped["surfaces"][0]["radius_mm"] is None
    assert dumped["surfaces"][0]["thickness_mm"] is None


def test_prescription_values_match_zmx_ingest_surface_parse(real_phone_prescription):
    table, optic = real_phone_prescription
    positions = np.asarray(optic.surfaces.positions).flatten()

    for row, parsed_surface, position in zip(
        table.surfaces,
        optic.surfaces.surfaces,
        positions,
        strict=True,
    ):
        parsed = parsed_surface.to_dict()
        geometry = parsed["geometry"]
        material = parsed["material_post"]

        _assert_float_or_none(row.z_mm, _finite_or_none(position))
        _assert_float_or_none(row.radius_mm, _finite_or_none(geometry.get("radius")))
        _assert_float_or_none(row.thickness_mm, _finite_or_none(parsed.get("thickness")))
        assert row.conic == pytest.approx(_finite_or_none(geometry.get("conic")) or 0.0, abs=1e-12)
        assert row.asphere_coefficients == pytest.approx(
            [_finite_or_none(value) for value in geometry.get("coefficients", [])],
            abs=1e-12,
        )
        _assert_float_or_none(row.refractive_index_d, _material_scalar(material, "index"))
        _assert_float_or_none(row.abbe_number, _material_scalar(material, "abbe"))
        assert row.is_stop is bool(parsed.get("is_stop"))


def test_glass_names_are_preserved_from_source_zmx(real_phone_prescription):
    table, _optic = real_phone_prescription

    assert table.surfaces[3].glass == "APL5014CL_14"
    assert table.surfaces[5].glass == "EP8000"
    assert table.surfaces[7].glass == "APL5014CL_14"
    assert table.surfaces[4].glass == "air"
    assert table.surfaces[3].refractive_index_d == pytest.approx(1.544, abs=1e-12)
    assert table.surfaces[3].abbe_number == pytest.approx(56.0, abs=1e-12)


def test_xasphere_coefficients_are_complete_and_ordered(real_phone_prescription):
    table, optic = real_phone_prescription

    row = table.surfaces[8]
    parsed_coefficients = optic.surfaces.surfaces[8].to_dict()["geometry"]["coefficients"]
    assert len(parsed_coefficients) == 10
    assert len(row.asphere_coefficients) == 10
    assert row.asphere_coefficients == pytest.approx(parsed_coefficients, abs=1e-12)


def test_load_prescription_table_uses_zmx_ingest_loader():
    path = ZMX_AMMO_DIR / _ZMX_FILENAME
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from_loader = load_prescription_table(path)
        optic = load_normalized_zmx(path)
        direct = extract_prescription_table(optic, source_zmx=path)

    assert from_loader == direct
