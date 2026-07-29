"""Guards for the relative cost index (NORTH-STAR §1.1's fourth deliverable).

The weights here are deliberately coarse and the North Star says that is fine
(§3: same table on both sides, 排序不变). So these tests do not check accuracy.
They check the three properties the module actually owes: the ratio is
self-consistent, the drivers move it in the right direction, and it fails closed
rather than totalling a smaller number when a prescription cannot be read.
"""

from __future__ import annotations

import pytest

from app.core.cost_index import (
    CostIndex,
    cost_index_from_zmx,
    cost_ratio,
    element_cost_units,
    material_cost_units,
)

_ZMX = """SURF 0
  TYPE STANDARD
SURF 1
  TYPE EVENASPH
  GLAS APL5014CL 1 0 1.54 56.0 0 0 0 0 0 0
  DIAM 1.0 0 0 0 1 ""
  DISZ 0.5
SURF 2
  TYPE EVENASPH
  DIAM 1.0 0 0 0 1 ""
  DISZ 0.2
SURF 3
  TYPE STANDARD
"""


def test_a_prescription_costs_the_same_as_itself() -> None:
    """The one property that must hold exactly, whatever the weights are."""
    index = cost_index_from_zmx(_ZMX)
    assert index is not None
    assert cost_ratio(index, index) == 1.0


def test_more_elements_cost_more() -> None:
    one = cost_index_from_zmx(_ZMX)
    two = cost_index_from_zmx(
        _ZMX.replace("SURF 3\n  TYPE STANDARD\n", _ZMX.split("SURF 0\n  TYPE STANDARD\n")[1])
    )
    assert one is not None and two is not None
    assert two.total_units > one.total_units


def test_aspheric_surfaces_cost_more_than_spherical() -> None:
    spherical = cost_index_from_zmx(_ZMX.replace("EVENASPH", "STANDARD"))
    aspheric = cost_index_from_zmx(_ZMX)
    assert spherical is not None and aspheric is not None
    assert aspheric.total_units > spherical.total_units
    assert aspheric.aspheric_surface_count > spherical.aspheric_surface_count


def test_exotic_glass_costs_more_than_moulded_plastic() -> None:
    assert material_cost_units("H-ZLAF50") > material_cost_units("BK7")
    assert material_cost_units("BK7") > material_cost_units("APL5014CL")
    assert material_cost_units("ZEONEX-E48R") == material_cost_units("APL5014CL")


def test_an_unknown_glass_is_not_free() -> None:
    """Charging 0 would make an unparsable prescription look like the cheapest."""
    assert material_cost_units("SOME-NEW-GLASS-2030") > 0.0
    assert material_cost_units("") > 0.0


def test_bigger_and_thicker_elements_cost_more() -> None:
    base = {"material": "APL", "aspheric_surfaces": 0, "semi_diameter_mm": 1.0, "thickness_mm": 0.5}
    assert element_cost_units(**{**base, "semi_diameter_mm": 4.0}) > element_cost_units(**base)
    assert element_cost_units(**{**base, "thickness_mm": 2.0}) > element_cost_units(**base)


# --- fail-closed -----------------------------------------------------------


def test_a_prescription_with_no_glass_is_unknown_not_free() -> None:
    """Every driver is additive, so a parse failure totals a *lower* cost and
    would read as the cheaper, better design -- this project's recurring trap."""
    assert cost_index_from_zmx("SURF 0\n  TYPE STANDARD\nSURF 1\n  TYPE STANDARD\n") is None
    assert cost_index_from_zmx("") is None


def test_a_missing_side_makes_the_ratio_unknown() -> None:
    index = cost_index_from_zmx(_ZMX)
    assert cost_ratio(index, None) is None
    assert cost_ratio(None, index) is None
    assert cost_ratio(None, None) is None


@pytest.mark.parametrize("total", [0.0, -1.0, float("nan"), float("inf")])
def test_a_non_positive_or_non_finite_total_yields_no_ratio(total: float) -> None:
    """Cost is positive-definite; anything else is a broken read, not a bargain."""
    broken = CostIndex(total_units=total, element_count=1, aspheric_surface_count=0, elements=())
    good = cost_index_from_zmx(_ZMX)
    assert cost_ratio(broken, good) is None
    assert cost_ratio(good, broken) is None


def test_real_corpus_prescriptions_produce_a_ratio() -> None:
    """Positive control: the screens must let real data through."""
    from pathlib import Path

    from app.core.engines.zmx_import_prep import decode_zmx_text

    def read(name: str) -> CostIndex | None:
        return cost_index_from_zmx(decode_zmx_text(Path(f"data/zmx/{name}").read_bytes())[0])

    a = read("US-12124006-B2-e2.zmx")
    b = read("US-11262555-B2-e2.zmx")
    assert a is not None and b is not None
    assert a.element_count == 7 and b.element_count == 8
    ratio = cost_ratio(a, b)
    assert ratio is not None and 0.0 < ratio < 10.0


def test_the_comparator_reports_the_cost_ratio() -> None:
    """Not built ahead of a consumer: the P2 comparator emits it per trial."""
    from pathlib import Path

    source = Path("scripts/p2_crosssource_trial.py").read_text(encoding="utf-8")
    assert "relative_cost_index" in source
    assert "_relative_cost(" in source
