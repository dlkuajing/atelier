"""Gate: the 异源 rule may only ever err toward 同源.

`.planning/NORTH-STAR.md` §1.1 spells out why. The pipeline is
`spec -> nearest seed -> optimise -> candidate`, so if the seed turns out to be
a relative of the control patent, "no worse than it" is circular reasoning and
异源打平率 -- the north star's main indicator -- rises for free. Excluding a
genuinely cross-family pair only costs sample size. Every test here therefore
pins the *direction* of the error, not a headline number.

Two fail-open bugs found by measurement while building the rule, both pinned
below because both would silently inflate the indicator:

* Raw assignee strings split one company across several buckets. The corpus
  spells Sunny three ways, AAC four ways, Ability twice (once with an em-dash)
  and Samsung twice. Unmerged, two same-company patents read as cross-family.
* A patent with no assignee record fell back to a per-patent bucket, which made
  it look cross-family against the entire corpus. Unknown provenance must be
  excluded instead.

The corpus-level test needs the per-field traceability census, which is
evidence held outside the repository (`D:/atelier-stagec-runs/...`), so it
skips where that file is absent -- including CI. It is a local gate, not a
CI gate, and is labelled as such rather than quietly passing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.p2_pair_census as census_mod
from scripts.p2_pair_census import (
    Provenance,
    assignee_tokens,
    brand_of_assignee,
    load_provenance,
    patent_id_of_case,
)

CENSUS = Path("D:/atelier-stagec-runs/trace-census-20260728/perfield-census.jsonl")

# Verbatim strings from data/patents/*.jsonl.
SUNNY = [
    "ZHEJIANG SUNNY OPTICS CO., LTD.",
    "ZHEJIANG SUNNY OPTICS CO., LTD",
    "Zhejiang Sunny Optical Co., Ltd",
]
AAC = [
    "CHANGZHOU AAC RAYTECH OPTRONICS CO., LTD.",
    "AAC Optics (Changzhou) Co., Ltd.",
    "AAC Technologies Pte. Ltd.",
    "AAC Optics Solutions Pte. Ltd.",
]
ABILITY = [
    "ABILITY OPTO-ELECTRONICS TECHNOLOGY CO., LTD.",
    "ABILITY OPTO\u2014ELECTRONICS TECHNOLOGY CO., LTD.",  # em-dash variant
]


# --------------------------------------------------------------------------
# assignee normalisation
# --------------------------------------------------------------------------


def test_em_dash_and_hyphen_normalise_identically() -> None:
    assert assignee_tokens(ABILITY[0]) == assignee_tokens(ABILITY[1])


def test_corporate_and_geographic_tokens_do_not_carry_identity() -> None:
    assert assignee_tokens("ZHEJIANG SUNNY OPTICS CO., LTD.") == frozenset({"sunny"})


@pytest.mark.parametrize("variants", [SUNNY, AAC, ABILITY], ids=["sunny", "aac", "ability"])
def test_spelling_variants_of_one_company_collapse_to_one_brand(variants: list[str]) -> None:
    brands = brand_of_assignee(set(variants))
    assert len({brands[v] for v in variants}) == 1, brands


def test_unrelated_companies_are_not_merged() -> None:
    brands = brand_of_assignee({SUNNY[0], AAC[0], "LARGAN PRECISION CO., LTD."})
    assert len(set(brands.values())) == 3


def test_a_brand_label_is_its_components_lexicographically_smallest_member() -> None:
    """Determinism has to be pinned as a property, not as "run it twice".

    An earlier revision named each component by its *shortest* member, which
    depends on set iteration order whenever two members tie in length. Two
    calls on equal inputs would still agree (equal sets iterate alike), so a
    repeat-call test proves nothing -- the invariant is the label rule itself.
    """
    brands = brand_of_assignee(set(SUNNY + AAC))
    for group in (SUNNY, AAC):
        assert {brands[m] for m in group} == {min(group)}


# --------------------------------------------------------------------------
# case-id shapes
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case_id", "expected"),
    [
        ("US-10120164-B2-e2", "US10120164B2"),
        ("US-12468127-B2", "US12468127B2"),
        ("US20170045714A1", "US20170045714A1"),
        ("US-20250216655-A1", "US20250216655A1"),
    ],
)
def test_every_patent_case_id_shape_in_the_index_is_parsed(case_id: str, expected: str) -> None:
    assert patent_id_of_case(case_id) == expected


def test_a_hand_built_real_design_has_no_patent_id() -> None:
    assert patent_id_of_case("3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56") is None


# --------------------------------------------------------------------------
# fail-closed direction
# --------------------------------------------------------------------------


def _provenance(assignees: dict[str, str], near: dict[str, str] | None = None) -> Provenance:
    return Provenance(assignees, near or {}, brand_of_assignee(set(assignees.values())))


def test_unknown_assignee_is_excluded_not_treated_as_cross_family() -> None:
    """The fail-open shape this replaced: falling back to a per-patent bucket
    made an unattributed patent look cross-family against everything."""
    prov = _provenance({"US10120164B2": SUNNY[0]})
    assert prov.brand_of_case("US-99999999-B2-e1") is None


def test_a_real_design_has_no_brand_so_it_never_forms_a_trial() -> None:
    prov = _provenance({"US10120164B2": SUNNY[0]})
    assert prov.brand_of_case("3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56") is None


def test_two_embodiments_of_one_patent_share_a_brand() -> None:
    prov = _provenance({"US10120164B2": SUNNY[0]})
    assert (
        prov.brand_of_case("US-10120164-B2-e1")
        == prov.brand_of_case("US-10120164-B2-e8")
        is not None
    )


def test_differently_spelled_same_company_patents_share_a_brand() -> None:
    prov = _provenance({"US1111111B2": SUNNY[0], "US2222222B2": SUNNY[2]})
    assert prov.brand_of_case("US-1111111-B2-e1") == prov.brand_of_case("US-2222222-B2-e1")


def test_a_near_duplicate_pointer_is_followed_to_its_head() -> None:
    prov = _provenance({"US2222222B2": SUNNY[0]}, {"US1111111B2": "US2222222B2"})
    assert prov.brand_of_case("US-1111111-B2-e1") == prov.brand_of_case("US-2222222-B2-e1")


def test_a_cyclic_near_duplicate_pointer_terminates() -> None:
    """A near-duplicate cycle must not hang. It resolves to whichever end of the
    cycle carries an assignee, which is still a same-brand answer -- the point
    is termination, not rejection."""
    prov = _provenance(
        {"US1111111B2": SUNNY[0]},
        {"US1111111B2": "US2222222B2", "US2222222B2": "US1111111B2"},
    )
    assert prov.brand_of_case("US-1111111-B2-e1") == prov.brand_of_case("US-2222222-B2-e1")


# --------------------------------------------------------------------------
# real provenance table
# --------------------------------------------------------------------------


def test_the_shipped_patent_pool_yields_a_usable_provenance_table() -> None:
    prov = load_provenance()
    assert prov.assignee_of_patent, "no assignee resolved from data/patents"
    assert prov.brand_of_case("US-10120164-B2-e1") is not None


@pytest.mark.parametrize("token", ["sunny", "aac", "largan", "kantatsu"])
def test_every_spelling_of_one_company_in_the_real_pool_maps_to_one_brand(token: str) -> None:
    """The bound that matters is a property, not a count.

    ``load_provenance`` covers all 714 discovery records (Apple, Amazon,
    university assignees and so on), so the brand count is ~45 -- only the 404
    that reach the case index collapse to 6. Pinning any count would pin the
    wrong thing; what must hold is that no company is split.
    """
    prov = load_provenance()
    spellings = {a for a in prov.assignee_of_patent.values() if token in assignee_tokens(a)}
    if not spellings:
        pytest.skip(f"no assignee containing {token!r} in the shipped pool")
    assert len({prov.brand_of[s] for s in spellings}) == 1, sorted(spellings)


@pytest.mark.skipif(not CENSUS.exists(), reason="per-field census evidence is outside the repo")
def test_no_trial_ever_pairs_two_cases_of_the_same_brand() -> None:
    from scripts.p2_pair_census import census

    result = census(CENSUS)
    assert result["trials"] > 0
    for pair in result["trial_pairs"]:
        assert pair["control_brand"] is not None
        assert pair["seed_brand"] is not None
        assert pair["control_brand"] != pair["seed_brand"], pair


@pytest.mark.skipif(not CENSUS.exists(), reason="per-field census evidence is outside the repo")
def test_trials_are_reported_as_non_independent() -> None:
    """167 trials drawing on 31 seeds is not 167 independent samples; the
    renderer must say so rather than let the count be quoted bare."""
    from scripts.p2_pair_census import census, render

    result = census(CENSUS)
    assert result["distinct_seeds_used"] < result["trials"]
    assert "NOT independent" in render(result)


def test_quarantine_evidence_is_present_for_the_usable_filter() -> None:
    from scripts.p2_pair_census import QUARANTINE

    payload = json.loads(QUARANTINE.read_text(encoding="utf-8"))
    assert "data/zmx" in payload["pools"]


# ---------------------------------------------------------------------------
# Third screen: the product must be willing to accept the control's own spec
# ---------------------------------------------------------------------------


def _record(**overrides: object) -> dict[str, object]:
    # A legitimate smartphone-wide request: inside SCENARIO_BOUNDS on every axis.
    record = {
        "case_id": "US-1-B2-e1",
        "source_zmx": "US-1-B2-e1.zmx",
        "scenario": "smartphone-wide",
        "efl_mm": 4.0,
        "fnum": 2.0,
        "fov_deg": 75.0,
        "image_height_mm": 3.5,
        "n_pieces": 6,
    }
    record.update(overrides)
    return record


def test_an_in_bounds_spec_is_accepted() -> None:
    """Negative screens are worthless if nothing passes them."""
    from scripts.p2_pair_census import spec_is_in_product_domain

    assert spec_is_in_product_domain(_record()) is True


def test_a_spec_the_product_would_reject_is_excluded() -> None:
    """A control defines the request a customer would make. If the product's own
    guard answers that request with HTTP 400, measuring against it says nothing
    about the product. Measured 2026-07-29: both 打平 trials in the 24-trial
    pilot sat on specs the guard rejects, so the 8.3% headline was carried
    entirely by out-of-domain designs; in-domain the rate was 0."""
    from scripts.p2_pair_census import spec_is_in_product_domain

    # 133.8 deg full field, labelled smartphone-ultrawide, whose ceiling is 105.
    assert (
        spec_is_in_product_domain(_record(scenario="smartphone-ultrawide", fov_deg=133.8)) is False
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("efl_mm", 40.0),
        ("fnum", 9.9),
        ("fov_deg", 5.0),
        ("image_height_mm", 40.0),
        ("n_pieces", 25),
    ],
)
def test_every_bounded_axis_can_reject(field: str, value: object) -> None:
    from scripts.p2_pair_census import spec_is_in_product_domain

    assert spec_is_in_product_domain(_record(**{field: value})) is False


def test_a_malformed_record_is_excluded_not_crashed_on() -> None:
    """Unknown scenario or missing key means we cannot show it is in domain."""
    from scripts.p2_pair_census import spec_is_in_product_domain

    assert spec_is_in_product_domain(_record(scenario="not-a-scenario")) is False
    assert spec_is_in_product_domain({"scenario": "smartphone-wide"}) is False


def test_the_domain_screen_is_on_by_default() -> None:
    """Reporting must not silently use the looser two-screen pool."""
    import inspect

    from scripts.p2_pair_census import load_usable_case_ids

    assert inspect.signature(load_usable_case_ids).parameters["require_in_domain"].default is True


# ---------------------------------------------------------------------------
# Seed-side quality gate: on the ruler the trial actually judges with
# ---------------------------------------------------------------------------

_PERFIELD = Path("D:/atelier-stagec-runs/trace-census-20260728/perfield-census.jsonl")


def test_codev_rms_uses_the_same_operand_as_the_judging_macro(tmp_path) -> None:
    """The census per-field value is `SPOTDATA(...) -> ^spot(1)` in mm, which is exactly
    `@rmssum`'s per-field operand before its `*1000`. Max over fields, x1000."""

    census = tmp_path / "pf.jsonl"
    census.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"seed": "a.zmx", "error": None, "num_fields": 2, "n_positive": 2,
                 "fields": [[0, 0.001], [0, 0.004]]},
                # partial coverage -> excluded: @rmssum skips failed fields and takes the
                # max over survivors, so a partial reading is optimistic.
                {"seed": "b.zmx", "error": None, "num_fields": 2, "n_positive": 1,
                 "fields": [[0, 0.001], [1, 0.0]]},
                {"seed": "c.zmx", "error": "boom", "num_fields": 1, "n_positive": 1,
                 "fields": [[0, 0.002]]},
            ]
        ),
        encoding="utf-8",
    )
    assert census_mod.codev_rms_by_zmx(census) == {"a.zmx": 4.0}


def test_the_default_limit_is_the_corpus_median_not_a_chosen_number() -> None:
    from app.core.corpus_quality import load_distribution

    assert census_mod.default_seed_quality_limit_um() == load_distribution()["percentiles"]["p50"]


def test_the_stretch_limit_comes_from_a_measurement_not_a_choice() -> None:
    """+25% is where the optimiser was measured to stop converging, both previously and
    again on 2026-07-30: a seed needing +17.7% converged to 5e-10 EFL deviation, while
    +46% / +59% / +75% all came back `aut_not_converged` at 14.0% / 17.0% / 22.6%."""

    assert census_mod.MAX_SEED_EFL_STRETCH == 0.25
    # Shrinking is deliberately unbounded: it was measured to converge across the board.
    assert census_mod.seed_efl_is_reachable(seed_efl_mm=20.0, target_efl_mm=2.0)
    assert census_mod.seed_efl_is_reachable(seed_efl_mm=4.0, target_efl_mm=5.0)  # +25%
    assert not census_mod.seed_efl_is_reachable(seed_efl_mm=4.0, target_efl_mm=5.1)
    # Degenerate inputs are unreachable, never silently allowed.
    assert not census_mod.seed_efl_is_reachable(seed_efl_mm=0.0, target_efl_mm=4.0)
    assert not census_mod.seed_efl_is_reachable(seed_efl_mm=4.0, target_efl_mm=0.0)


@pytest.mark.skipif(not _PERFIELD.is_file(), reason="runtime census not present")
def test_reachability_is_never_traded_away_for_quality() -> None:
    """THE regression this file exists to prevent, and it is not hypothetical.

    Gating the pool on quality ALONE pushed 53 of 59 trials past the stretch limit, and
    the first four real-machine trials came back `aut_not_converged`. An unreachable seed
    produces no candidate at all; a merely mediocre one still produces a judgeable trial.
    So reachability is filtered first and quality only chooses among what is left.
    """

    index = {r["case_id"]: r for r in json.loads(census_mod.CASE_INDEX.read_text("utf-8"))}
    result = census_mod.census(_PERFIELD)
    over = []
    for pair in result["trial_pairs"]:
        seed_efl = float(index[pair["seed"]]["efl_mm"])
        target_efl = float(index[pair["control"]]["efl_mm"])
        if (target_efl / seed_efl) - 1.0 > census_mod.MAX_SEED_EFL_STRETCH + 1e-9:
            over.append((pair["control"], pair["seed"], target_efl / seed_efl))
    assert not over, f"{len(over)} pairs exceed the measured stretch limit: {over[:3]}"


@pytest.mark.skipif(not _PERFIELD.is_file(), reason="runtime census not present")
def test_the_fallback_is_recorded_rather_than_silent() -> None:
    """Measured: only 6 of 59 controls have a seed that is BOTH reachable and at or
    below the corpus median. For the other 53 the two constraints genuinely conflict,
    and that conflict is the finding -- so it has to appear in the output, not be
    quietly absorbed by a fallback.
    """

    result = census_mod.census(_PERFIELD)
    basis = result["seed_pool_basis"]
    assert set(basis) <= {"reachable_and_quality", "reachable_only", "neither"}
    assert sum(basis.values()) == result["trials"]
    # Both states must actually occur, or this run is not exercising the conflict.
    assert basis.get("reachable_and_quality", 0) > 0
    assert basis.get("reachable_only", 0) > 0


@pytest.mark.skipif(not _PERFIELD.is_file(), reason="runtime census not present")
def test_quality_still_wins_where_it_is_available() -> None:
    """The fallback must not swallow the quality preference where it *can* be honoured."""

    rms = census_mod.codev_rms_by_zmx(_PERFIELD)
    index = {r["case_id"]: r for r in json.loads(census_mod.CASE_INDEX.read_text("utf-8"))}
    result = census_mod.census(_PERFIELD)
    limit = result["seed_quality_limit_um"]
    good = [
        pair
        for pair in result["trial_pairs"]
        if (rms.get(str(index[pair["seed"]]["source_zmx"])) or 1e9) <= limit
    ]
    assert len(good) == result["seed_pool_basis"].get("reachable_and_quality", 0)


def test_a_seed_with_unknown_codev_quality_is_excluded_not_admitted(tmp_path) -> None:
    """Fail closed. Admitting the unknown is exactly how a lens CODE V calls 101 um got
    into 41 of 49 trials -- its stored Optiland radius, measured over half the field,
    sailed under a 100 um gate."""

    rms: dict[str, float] = {"known.zmx": 5.0}
    index = {"KNOWN": {"source_zmx": "known.zmx"}, "UNKNOWN": {"source_zmx": "absent.zmx"}}

    def seed_quality_ok(case_id: str, limit: float = 10.0) -> bool:
        record = index.get(case_id)
        if record is None:
            return False
        value = rms.get(str(record.get("source_zmx")))
        return value is not None and value <= limit

    assert seed_quality_ok("KNOWN") is True
    assert seed_quality_ok("UNKNOWN") is False
    assert seed_quality_ok("MISSING") is False
