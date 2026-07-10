"""Offline tests for deterministic fictitious-to-real glass proposals."""

from __future__ import annotations

import math

import pytest

from app.core.engines.glass_snap import (
    DEFAULT_SNAP_TOLERANCE,
    PLASTIC_GLASS_NAMES,
    CatalogEntry,
    build_plastic_catalog,
    snap_glass,
)
from app.core.zmx_materials import MATERIAL_ND_VD

SPECTRAL = "C-d-F@20C"


def entry(name: str, nd: float, vd: float, *, catalog: str = "cat", version: str = "v1") -> CatalogEntry:
    return CatalogEntry(catalog, name, version, nd, vd)


def propose(nd: object, vd: object, catalog: object, *, weight: object = 1.0):
    return snap_glass(  # type: ignore[arg-type]
        nd,
        vd,
        catalog,
        spectral_definition=SPECTRAL,
        catalog_spectral_definition=SPECTRAL,
        dispersion_weight=weight,
    )


def test_metric_uses_nd_and_dn_euclidean_distance() -> None:
    result = propose(1.6, 30.0, [entry("REAL", 1.59, 29.0)])
    expected_delta_dn = (1.6 - 1) / 30.0 - (1.59 - 1) / 29.0
    assert result.distance == pytest.approx(math.hypot(0.01, expected_delta_dn))
    assert result.delta_nd == pytest.approx(0.01)
    assert result.delta_dn == pytest.approx(expected_delta_dn)


def test_dispersion_weight_changes_nearest_proposal() -> None:
    catalog = build_plastic_catalog()
    low = propose(1.53, 20.0, catalog, weight=1.0)
    macro_scale = propose(1.53, 20.0, catalog, weight=50.0)
    assert low.entry and low.entry.glass_name == "ZEONEX-E48R"
    assert macro_scale.entry and macro_scale.entry.glass_name == "SP3810"


def test_tolerance_boundary_is_strictly_inclusive() -> None:
    delta_dn = (1.6 - 1) / 20.0 - (1.6 - 1) / 30.0
    result = propose(
        1.6,
        20.0,
        [entry("REAL", 1.6, 30.0)],
        weight=DEFAULT_SNAP_TOLERANCE / delta_dn,
    )
    assert result.distance == DEFAULT_SNAP_TOLERANCE
    assert result.within_tolerance


def test_nextafter_above_tolerance_is_outside() -> None:
    delta_dn = (1.6 - 1) / 20.0 - (1.6 - 1) / 30.0
    above = math.nextafter(DEFAULT_SNAP_TOLERANCE, math.inf)
    result = propose(1.6, 20.0, [entry("REAL", 1.6, 30.0)], weight=above / delta_dn)
    assert result.distance > DEFAULT_SNAP_TOLERANCE
    assert not result.within_tolerance


def test_outside_tolerance_still_reports_nearest_proposal() -> None:
    result = propose(1.52, 50.0, [entry("REAL", 1.5, 50.0)], weight=0)
    assert result.entry and result.entry.glass_name == "REAL"
    assert result.distance == pytest.approx(0.02)
    assert not result.within_tolerance


def test_equal_distance_tie_breaks_by_full_catalog_identity() -> None:
    result = propose(1.5, 50.0, [entry("Z", 1.49, 50), entry("A", 1.51, 50)], weight=0)
    assert result.entry and result.entry.glass_name == "A"


def test_empty_catalog_returns_empty_proposal() -> None:
    result = propose(1.5, 50.0, [])
    assert result.entry is None
    assert result.distance is None
    assert not result.within_tolerance


@pytest.mark.parametrize("bad", [None, math.nan, math.inf, -math.inf, "bad"])
def test_invalid_target_values_raise_value_error(bad: object) -> None:
    with pytest.raises(ValueError):
        propose(bad, 50.0, [entry("REAL", 1.5, 50.0)])


@pytest.mark.parametrize("bad", [None, math.nan, math.inf, -1, "bad"])
def test_invalid_weight_raises_value_error(bad: object) -> None:
    with pytest.raises(ValueError):
        propose(1.5, 50.0, [entry("REAL", 1.5, 50.0)], weight=bad)


def test_non_catalog_entry_rejected_instead_of_mapping_compatibility() -> None:
    with pytest.raises(ValueError):
        propose(1.5, 50.0, {"REAL": (1.5, 50.0)})


def test_none_catalog_raises_value_error() -> None:
    with pytest.raises(ValueError):
        propose(1.5, 50.0, None)


def test_bad_entry_fails_entire_operation() -> None:
    catalog = [entry("GOOD", 1.5, 50), entry("BAD", math.nan, 50)]
    with pytest.raises(ValueError):
        propose(1.5, 50.0, catalog)


def test_duplicate_full_identity_fails_closed() -> None:
    duplicate = entry("SAME", 1.5, 50)
    with pytest.raises(ValueError):
        propose(1.5, 50.0, [duplicate, duplicate])


def test_same_name_across_catalogs_is_expressible() -> None:
    result = propose(
        1.5,
        50.0,
        [entry("SAME", 1.5, 50, catalog="B"), entry("SAME", 1.5, 50, catalog="A")],
    )
    assert result.entry and result.entry.catalog_id == "A"


def test_catalog_order_does_not_change_result() -> None:
    first = [entry("B", 1.51, 50), entry("A", 1.49, 50)]
    assert propose(1.5, 50, first, weight=0) == propose(1.5, 50, reversed(first), weight=0)


def test_spectral_definition_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="spectral definitions must match"):
        snap_glass(
            1.5,
            50,
            [entry("REAL", 1.5, 50)],
            spectral_definition="C-d-F",
            catalog_spectral_definition="FGW-custom",
        )


def test_missing_spectral_definition_fails_closed() -> None:
    with pytest.raises(ValueError):
        snap_glass(
            1.5,
            50,
            [entry("REAL", 1.5, 50)],
            spectral_definition="",
            catalog_spectral_definition=SPECTRAL,
        )


def test_plastic_catalog_builder_selects_exactly_five_real_names() -> None:
    catalog = build_plastic_catalog()
    assert tuple(item.glass_name for item in catalog) == PLASTIC_GLASS_NAMES
    assert len(catalog) == 5
    assert all((item.nd, item.vd) == MATERIAL_ND_VD[item.glass_name] for item in catalog)


@pytest.mark.parametrize("catalog_entry", [
    CatalogEntry("", "REAL", "v1", 1.5, 50),
    CatalogEntry("cat", "", "v1", 1.5, 50),
    CatalogEntry("cat", "REAL", "", 1.5, 50),
])
def test_blank_catalog_identity_fields_raise_value_error(catalog_entry: CatalogEntry) -> None:
    with pytest.raises(ValueError):
        propose(1.5, 50, [catalog_entry])
