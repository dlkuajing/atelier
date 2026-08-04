"""Tests for the P2 seed-pool census.

Every test here exists because the measurement got it wrong first. Two of them
(`test_seed_distortion_reads_staging_designs`,
`test_dominating_alternatives_rejects_offspec_rectilinear`) each fail on a real
revision of this module that was run and believed before it was checked -- see
`.planning/evidence/p2-seed-pool-census-2026-08-05.md`.

All of them run off committed data. None needs a run directory, a real machine,
or CODE V, so none can quietly disarm itself by skipping.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from scripts import p2_pair_census
from scripts.p2_seed_pool_census import (
    RECTILINEAR_SWEEP_PCT,
    ControlSeedPool,
    SeedDistortion,
    distinct_prescriptions,
    dominating_alternatives,
    same_brand_counterfactual,
    seed_distortion,
    self_check_ratio_formula,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "app" / "data" / "p2_staging_seed_manifest.json"


# --------------------------------------------------------------------------
# A SeedSupply built by hand: no Optiland, no corpus load, no staging build.
# Only the lookups the functions under test actually read.
# --------------------------------------------------------------------------
def _supply(
    *,
    index: dict | None = None,
    staging: dict | None = None,
    brands: dict[str, str] | None = None,
    quality: dict[str, float] | None = None,
    limit: float = 10.0,
) -> p2_pair_census.SeedSupply:
    supply = object.__new__(p2_pair_census.SeedSupply)
    supply.index_by_case = index or {}
    supply.staging_facts = staging or {}
    supply.staging_by_id = dict.fromkeys(supply.staging_facts, object())
    supply.by_id = dict.fromkeys(supply.index_by_case, object())
    supply.usable_set = set(supply.index_by_case)
    supply.usable_ids = list(supply.index_by_case)
    supply.limit = limit
    supply.codev_rms = {}
    supply.seed_brand = lambda case_id: (brands or {}).get(case_id)  # type: ignore[method-assign]
    supply.seed_quality_um = lambda case_id: (quality or {}).get(case_id)  # type: ignore[method-assign]
    supply.seed_quality_ok = lambda case_id: (  # type: ignore[method-assign]
        (quality or {}).get(case_id) is not None and (quality or {})[case_id] <= limit
    )
    supply.seed_reachable = lambda case_id, target: True  # type: ignore[method-assign]
    return supply


class _Case:
    """The only two attributes `pool_for` touches on a built design."""

    def __init__(self, case_id: str, efl_mm: float = 3.0) -> None:
        self.metadata = type(
            "M", (), {"case_id": case_id, "computed_efl_mm": efl_mm}
        )()


def _entry(case_id: str, *, fov: float, efl: float, distortion_pct: float) -> SeedDistortion:
    return SeedDistortion(
        case_id=case_id,
        patent=case_id,
        pool="corpus",
        efl_mm=efl,
        fov_deg=fov,
        image_height_mm=1.0,
        first_order_image_height_mm=1.0,
        image_height_ratio=1.0 + distortion_pct / 100.0,
        proxy_distortion_pct=distortion_pct,
    )


# --------------------------------------------------------------------------
# The proxy has to be readable on staging designs. It was not, for one whole
# revision: `_case_image_height_mm` resolves through the corpus index, staging
# seeds are not in it, so every staging seed read image height 0.0 and produced
# an unreadable proxy -- on exactly the 54-of-59 seeds the router picks. The
# stage table built on top of that blamed the CODE V quality gate for 52 of 59
# controls, which was blindness rendered as a finding.
# --------------------------------------------------------------------------
def test_seed_distortion_reads_staging_designs() -> None:
    supply = _supply(
        staging={
            "S1": {
                "zmx": "S1.zmx",
                "efl_mm": 4.0,
                "fov_deg": 80.0,
                "image_height_mm": 2.0,
                "image_height_ratio": 0.5,
            }
        }
    )
    entry = seed_distortion(supply, "S1")
    assert entry.pool == "staging"
    assert entry.readable, "staging seeds must not read as unmeasurable"
    assert entry.image_height_mm == pytest.approx(2.0)


def test_seed_distortion_is_unreadable_only_when_data_is_missing() -> None:
    supply = _supply(staging={"S1": {"zmx": "S1.zmx", "efl_mm": 4.0, "fov_deg": 80.0}})
    assert not seed_distortion(supply, "S1").readable
    assert not seed_distortion(supply, "absent").readable


def test_real_staging_manifest_is_fully_readable() -> None:
    """The regression on committed data, not on a fixture."""
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    supply = _supply(
        staging={str(row["zmx"]).rsplit(".", 1)[0]: row for row in payload["seeds"]}
    )
    unreadable = [
        case_id for case_id in supply.staging_facts if not seed_distortion(supply, case_id).readable
    ]
    assert unreadable == [], f"{len(unreadable)} staging seeds have no distortion proxy"


def test_ratio_formula_agrees_with_the_manifest_it_claims_to_reproduce() -> None:
    """One ruler. If this drifts, every distortion number in the census is on
    a different scale than the rest of the repository."""
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    supply = _supply(
        staging={str(row["zmx"]).rsplit(".", 1)[0]: row for row in payload["seeds"]}
    )
    check = self_check_ratio_formula(supply)
    assert check["agrees"], check["mismatches"]
    assert check["checked"] == len(payload["seeds"])
    assert check["max_abs_delta"] == 0.0


# --------------------------------------------------------------------------
# Domination, and the objection it exists to survive: "the rectilinear option
# was off-spec, the router was right to skip it". A revision that ranked purely
# by |distortion| reported 56 of 59 pools as holding a better option -- and the
# winner for 51 of them was a 10-degree telephoto being offered to a 90-degree
# wide-angle spec.
# --------------------------------------------------------------------------
def test_dominating_alternatives_rejects_offspec_rectilinear() -> None:
    control = _entry("C", fov=90.0, efl=3.0, distortion_pct=0.0)
    chosen = _entry("chosen", fov=88.0, efl=3.1, distortion_pct=-18.5)
    telephoto = _entry("telephoto", fov=10.0, efl=9.0, distortion_pct=-0.4)
    assert dominating_alternatives([chosen, telephoto], chosen, control) == []


def test_dominating_alternatives_accepts_a_strictly_better_seed() -> None:
    control = _entry("C", fov=90.0, efl=3.0, distortion_pct=0.0)
    chosen = _entry("chosen", fov=82.0, efl=3.6, distortion_pct=-18.5)
    better = _entry("better", fov=89.0, efl=3.1, distortion_pct=-0.5)
    assert [e.case_id for e in dominating_alternatives([chosen, better], chosen, control)] == [
        "better"
    ]


def test_dominating_alternatives_rejects_a_tie_on_distortion() -> None:
    control = _entry("C", fov=90.0, efl=3.0, distortion_pct=0.0)
    chosen = _entry("chosen", fov=90.0, efl=3.0, distortion_pct=-4.0)
    tie = _entry("tie", fov=90.0, efl=3.0, distortion_pct=4.0)
    assert dominating_alternatives([chosen, tie], chosen, control) == []


def test_dominating_alternatives_rejects_a_worse_focal_length() -> None:
    control = _entry("C", fov=90.0, efl=3.0, distortion_pct=0.0)
    chosen = _entry("chosen", fov=90.0, efl=3.0, distortion_pct=-18.5)
    far = _entry("far", fov=90.0, efl=6.0, distortion_pct=-0.5)
    assert dominating_alternatives([chosen, far], chosen, control) == []


# --------------------------------------------------------------------------
# The counterfactual has to answer "what does the BRAND rule cost", so it must
# lift the brand screen and nothing else, and must not count seeds no family
# definition could ever admit.
# --------------------------------------------------------------------------
def _counterfactual_fixture():
    index = {
        "US-1111111-B2-e1": {"efl_mm": 3.0, "fov_deg": 80.0, "image_height_mm": 2.5169},
        # same brand, same patent as the control -> never admissible
        "US-1111111-B2-e2": {"efl_mm": 3.0, "fov_deg": 80.0, "image_height_mm": 2.5169},
        # same brand, different patent -> what a family rule might admit
        "US-2222222-B2-e1": {"efl_mm": 3.0, "fov_deg": 79.0, "image_height_mm": 2.4790},
        # different brand, rectilinear, but 40 degrees away -> out of the window
        "US-3333333-B2-e1": {"efl_mm": 3.0, "fov_deg": 40.0, "image_height_mm": 1.0919},
        # different brand, in window, but barrel -> fails the distortion screen
        "US-4444444-B2-e1": {"efl_mm": 3.0, "fov_deg": 80.0, "image_height_mm": 2.0},
    }
    brands = {
        "US-1111111-B2-e1": "A",
        "US-1111111-B2-e2": "A",
        "US-2222222-B2-e1": "A",
        "US-3333333-B2-e1": "B",
        "US-4444444-B2-e1": "B",
    }
    quality = dict.fromkeys(index, 5.0)
    supply = _supply(index=index, brands=brands, quality=quality)
    options = ControlSeedPool(
        control_id="US-1111111-B2-e1",
        control_brand="A",
        control=None,
        target_efl_mm=3.0,
        cross_source=(),
        reachable=(),
        preferred=(),
        pool=(),
        basis="reachable_and_quality",
        excluded=None,
    )
    return supply, options, seed_distortion(supply, "US-1111111-B2-e1")


def test_counterfactual_separates_own_patent_from_other_patent() -> None:
    supply, options, control = _counterfactual_fixture()
    result = same_brand_counterfactual(supply, options, control, threshold_pct=2.0)
    assert result["same_brand_own_patent"] == 1
    assert result["same_brand_other_patent"] == 1
    assert result["same_brand_other_patent_examples"] == ["US-2222222-B2-e1"]


def test_counterfactual_still_applies_every_screen_except_brand() -> None:
    supply, options, control = _counterfactual_fixture()
    result = same_brand_counterfactual(supply, options, control, threshold_pct=2.0)
    # B has two designs; one is out of the field window, one is barrel.
    assert result["cross_source"] == 0
    # Widening only the field window admits the rectilinear B design.
    wide = same_brand_counterfactual(
        supply, options, control, threshold_pct=2.0, field_window_deg=45.0
    )
    assert wide["cross_source_examples"] == ["US-3333333-B2-e1"]


def test_counterfactual_never_counts_the_control_itself() -> None:
    supply, options, control = _counterfactual_fixture()
    for threshold in RECTILINEAR_SWEEP_PCT:
        result = same_brand_counterfactual(supply, options, control, threshold_pct=threshold)
        assert options.control_id not in result["same_brand_other_patent_examples"]
        assert options.control_id not in result["cross_source_examples"]


def test_counterfactual_quality_screen_is_not_lifted() -> None:
    supply, options, control = _counterfactual_fixture()
    supply.seed_quality_ok = lambda case_id: False  # type: ignore[method-assign]
    result = same_brand_counterfactual(supply, options, control, threshold_pct=5.0)
    assert result["same_brand_other_patent"] == 0
    assert result["cross_source"] == 0


# --------------------------------------------------------------------------
# Continuations repeat one prescription across patent documents. Counting
# patents therefore overcounts the options a router actually has.
# --------------------------------------------------------------------------
def test_distinct_prescriptions_folds_a_real_continuation_pair() -> None:
    pair = ["US-10073249-B2-e12", "US-10191250-B2-e12"]
    supply = _supply(staging={case_id: {"zmx": f"{case_id}.zmx"} for case_id in pair})
    for case_id in pair:
        assert (p2_pair_census.STAGING_ZMX_DIR / f"{case_id}.zmx").is_file()
    assert distinct_prescriptions(supply, pair) == 1, (
        "these two documents carry one prescription; counting them as two "
        "inflates how many seeds a control can choose between"
    )


def test_distinct_prescriptions_counts_unreadable_files_individually() -> None:
    supply = _supply(staging={f"X{i}": {"zmx": f"no-such-file-{i}.zmx"} for i in range(3)})
    assert distinct_prescriptions(supply, ["X0", "X1", "X2"]) == 3


# --------------------------------------------------------------------------
# The refactor's contract: `census` must route out of `pool_for`, so a change
# to one cannot leave the other describing a different pool.
# --------------------------------------------------------------------------
def test_pool_for_stages_are_nested_and_basis_matches() -> None:
    supply = object.__new__(p2_pair_census.SeedSupply)
    supply.by_id = {
        name: _Case(name) for name in ("CTRL", "good", "far_efl", "poor")
    }
    supply.staging_by_id = {}
    supply.staging_facts = {}
    supply.usable_set = set(supply.by_id)
    supply.index_by_case = {}
    supply.provenance = type(
        "P", (), {"brand_of_case": staticmethod(lambda c: "A" if c == "CTRL" else "B")}
    )()
    supply.seed_brand = lambda case_id: "A" if case_id == "CTRL" else "B"  # type: ignore[method-assign]
    supply.seed_reachable = lambda case_id, target: case_id != "far_efl"  # type: ignore[method-assign]
    supply.seed_quality_ok = lambda case_id: case_id == "good"  # type: ignore[method-assign]

    options = supply.pool_for("CTRL")
    ids = lambda seq: [c.metadata.case_id for c in seq]  # noqa: E731
    assert sorted(ids(options.cross_source)) == ["far_efl", "good", "poor"]
    assert sorted(ids(options.reachable)) == ["good", "poor"]
    assert ids(options.preferred) == ["good"]
    assert ids(options.pool) == ["good"]
    assert options.basis == "reachable_and_quality"
    assert options.excluded is None
    assert set(ids(options.preferred)) <= set(ids(options.reachable)) <= set(
        ids(options.cross_source)
    )


def test_pool_for_falls_back_rather_than_dropping_the_control() -> None:
    supply = object.__new__(p2_pair_census.SeedSupply)
    supply.by_id = {name: _Case(name) for name in ("CTRL", "poor")}
    supply.staging_by_id = {}
    supply.staging_facts = {}
    supply.usable_set = set(supply.by_id)
    supply.index_by_case = {}
    supply.provenance = type(
        "P", (), {"brand_of_case": staticmethod(lambda c: "A" if c == "CTRL" else "B")}
    )()
    supply.seed_brand = lambda case_id: "A" if case_id == "CTRL" else "B"  # type: ignore[method-assign]
    supply.seed_reachable = lambda case_id, target: True  # type: ignore[method-assign]
    supply.seed_quality_ok = lambda case_id: False  # type: ignore[method-assign]

    options = supply.pool_for("CTRL")
    assert [c.metadata.case_id for c in options.pool] == ["poor"]
    assert options.basis == "reachable_only"
    assert options.excluded is None


def test_pool_for_reports_an_empty_pool_as_excluded() -> None:
    supply = object.__new__(p2_pair_census.SeedSupply)
    supply.by_id = {"CTRL": _Case("CTRL")}
    supply.staging_by_id = {}
    supply.staging_facts = {}
    supply.usable_set = {"CTRL"}
    supply.index_by_case = {}
    supply.provenance = type("P", (), {"brand_of_case": staticmethod(lambda c: "A")})()
    supply.seed_brand = lambda case_id: "A"  # type: ignore[method-assign]
    supply.seed_reachable = lambda case_id, target: True  # type: ignore[method-assign]
    supply.seed_quality_ok = lambda case_id: True  # type: ignore[method-assign]

    options = supply.pool_for("CTRL")
    assert options.pool == ()
    assert options.basis is None
    assert options.excluded == "no_cross_brand_seed_available"


def test_pool_for_reports_unknown_provenance_without_building_a_pool() -> None:
    supply = object.__new__(p2_pair_census.SeedSupply)
    supply.by_id = {"CTRL": _Case("CTRL")}
    supply.staging_by_id = {}
    supply.staging_facts = {}
    supply.usable_set = {"CTRL"}
    supply.index_by_case = {}
    supply.provenance = type("P", (), {"brand_of_case": staticmethod(lambda c: None)})()

    options = supply.pool_for("CTRL")
    assert options.excluded == "control_provenance_unknown"
    assert options.basis is None
    assert options.cross_source == ()


def test_magnitude_sorts_unreadable_to_the_bottom() -> None:
    readable = _entry("r", fov=80.0, efl=3.0, distortion_pct=-30.0)
    blind = SeedDistortion("b", "b", "corpus", None, None, None, None, None, None)
    assert blind.magnitude == math.inf
    assert min([blind, readable], key=lambda e: e.magnitude) is readable
