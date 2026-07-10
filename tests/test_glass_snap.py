"""Offline tests for deterministic fictitious-to-real glass matching."""

from __future__ import annotations

import math

import pytest

from app.core.engines.glass_snap import DEFAULT_SNAP_TOLERANCE, snap_glass
from app.core.zmx_materials import MATERIAL_ND_VD


def test_metric_uses_nd_and_dn_euclidean_distance() -> None:
    target_nd, target_vd = 1.6, 30.0
    result = snap_glass(target_nd, target_vd, {"REAL": (1.59, 29.0)})

    expected_delta_dn = (target_nd - 1) / target_vd - (1.59 - 1) / 29.0
    assert result.distance == pytest.approx(math.hypot(0.01, expected_delta_dn))
    assert result.delta_nd == pytest.approx(0.01)
    assert result.delta_dn == pytest.approx(expected_delta_dn)


def test_disp_factor_weights_dn_component() -> None:
    catalog = {"REAL": (1.6, 40.0)}
    unweighted = snap_glass(1.6, 20.0, catalog, disp_factor=0.0)
    weighted = snap_glass(1.6, 20.0, catalog, disp_factor=2.0)

    assert unweighted.distance == 0.0
    assert weighted.distance == pytest.approx(0.03)
    assert unweighted.snapped
    assert not weighted.snapped


def test_tolerance_boundary_is_inclusive() -> None:
    result = snap_glass(
        1.5 + DEFAULT_SNAP_TOLERANCE,
        50.0,
        {"REAL": (1.5, 49.0)},
        disp_factor=0,
    )

    assert result.distance == pytest.approx(DEFAULT_SNAP_TOLERANCE)
    assert result.glass_name == "REAL"


def test_outside_tolerance_fails_closed_but_reports_nearest_distance() -> None:
    result = snap_glass(
        1.5 + DEFAULT_SNAP_TOLERANCE + 1e-6,
        50.0,
        {"REAL": (1.5, 50.0)},
        disp_factor=0,
    )

    assert result.glass_name is None
    assert not result.snapped
    assert result.distance == pytest.approx(DEFAULT_SNAP_TOLERANCE + 1e-6)


@pytest.mark.parametrize(
    "glass_name",
    ["ZEONEX-E48R", "OKP1", "EP8000", "APL5014CL", "SP3810"],
)
def test_real_plastic_catalog_entries_round_trip(glass_name: str) -> None:
    nd, vd = MATERIAL_ND_VD[glass_name]
    result = snap_glass(nd, vd, MATERIAL_ND_VD)

    assert result.glass_name == glass_name
    assert result.distance == 0.0
