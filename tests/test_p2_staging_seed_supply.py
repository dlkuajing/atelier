"""Gate: extra seeds may improve the seed, never move the denominator.

The P2 cross-source par rate is 0, and the measured cause is the seed supply: in
the 2026-08-02 round 48 of 59 trials optimised from one seed whose own CODE V
reading is 101 um, against controls at 2-11 um. `data/zmx-staging` holds 613
git-tracked designs from this repo's own converter that nothing consumes.

Admitting them is only safe if it cannot flatter the headline. A par rate is a
fraction over controls, so the rule these tests enforce is narrow and absolute:
**a staging design may be chosen as a seed and may never appear as a control.**
If that holds, a par rate measured after the change is comparable with one
measured before it; if it slips, every comparison across the change is void.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.p2_pair_census import (
    STAGING_SEED_MANIFEST,
    census,
    load_staging_seeds,
    load_usable_case_ids,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CENSUS = Path("D:/atelier-stagec-runs/trace-census-20260728/perfield-census.jsonl")
needs_census = pytest.mark.skipif(
    not CENSUS.is_file(), reason="per-field census is a runtime product, absent here"
)


def test_the_manifest_admits_seeds_only_and_says_so() -> None:
    payload = json.loads(STAGING_SEED_MANIFEST.read_text(encoding="utf-8"))
    assert payload["schema"] == "atelier.p2_staging_seed_manifest/v1"
    assert "seed only" in payload["role"]
    assert payload["n"] == len(payload["seeds"]) > 0
    assert payload["census"]["sha256"], "a screened set with no stated census cannot be rebuilt"


def test_no_staging_seed_shares_a_name_with_a_corpus_case() -> None:
    """A collision would let one design answer to two provenances, and the
    cross-source rule is decided by provenance."""

    index = json.loads(
        (REPO_ROOT / "app" / "data" / "optical_cases" / "index.json").read_text(encoding="utf-8")
    )
    corpus = {r["case_id"] for r in index} | {str(r["source_zmx"]) for r in index}
    for row in load_staging_seeds():
        assert row["zmx"] not in corpus
        assert str(row["zmx"]).rsplit(".", 1)[0] not in corpus


def test_every_staging_seed_carries_what_the_gates_need() -> None:
    """Missing fields must not silently fail open into "unknown quality, admit"."""

    for row in load_staging_seeds():
        assert float(row["codev_rms_um"]) > 0.0
        assert float(row["efl_mm"]) > 0.0
        assert row["brand"], "the cross-source rule needs a brand"
        assert int(row["glass_elements"]) >= 1


@needs_census
def test_admitting_staging_seeds_does_not_change_the_denominator() -> None:
    """The load-bearing assertion. Same controls, same trial count -- only the
    seed each control is paired with may differ."""

    without = census(CENSUS, admit_staging_seeds=False)
    with_ = census(CENSUS, admit_staging_seeds=True)

    assert with_["cases_total"] == without["cases_total"]
    assert with_["cases_usable"] == without["cases_usable"]
    assert with_["trials"] == without["trials"]
    assert {t["control"] for t in with_["trial_pairs"]} == {
        t["control"] for t in without["trial_pairs"]
    }


@needs_census
def test_no_staging_design_is_ever_a_control() -> None:
    result = census(CENSUS, admit_staging_seeds=True)
    staging_ids = {str(r["zmx"]).rsplit(".", 1)[0] for r in load_staging_seeds()}
    usable, _ = load_usable_case_ids(CENSUS)

    assert not staging_ids & set(usable)
    assert not staging_ids & {t["control"] for t in result["trial_pairs"]}


@needs_census
def test_the_seeds_actually_get_used_and_are_labelled() -> None:
    """A no-op change would pass every test above. This one fails if the seeds
    are admitted but never chosen, or chosen but not attributable."""

    result = census(CENSUS, admit_staging_seeds=True)
    assert result["staging_seeds_admitted"] > 0
    assert result["trials_seeded_from_staging"] > 0
    assert result["staging_seeds_unbuildable"] == []
    for trial in result["trial_pairs"]:
        assert trial["seed_pool"] in ("corpus", "staging")
    from_staging = {t["seed"] for t in result["trial_pairs"] if t["seed_pool"] == "staging"}
    assert from_staging <= {str(r["zmx"]).rsplit(".", 1)[0] for r in load_staging_seeds()}


@needs_census
def test_the_fallback_to_an_unscreened_seed_gets_rarer_not_commoner() -> None:
    """`pool = preferred or reachable or cross_source` fails open by design. The
    point of more seeds is that it fires less often; if it fired *more*, the extra
    supply would be making the seed worse, not better."""

    without = census(CENSUS, admit_staging_seeds=False)["seed_pool_basis"]
    with_ = census(CENSUS, admit_staging_seeds=True)["seed_pool_basis"]

    assert with_.get("reachable_and_quality", 0) > without.get("reachable_and_quality", 0)
    assert with_.get("reachable_only", 0) < without.get("reachable_only", 0)


@needs_census
def test_disabling_admission_reproduces_the_pre_change_reading() -> None:
    """The escape hatch has to actually reproduce the old numbers, or no
    before/after comparison made with it means anything."""

    without = census(CENSUS, admit_staging_seeds=False)
    assert without["seed_pool_basis"] == {"reachable_only": 53, "reachable_and_quality": 6}
    assert without["trials"] == 59
    assert without["distinct_seeds_used"] == 6


def test_no_staging_seed_republishes_a_design_the_corpus_already_has() -> None:
    """Screen 6, and the reason it is not optional.

    Zero *filename* overlap between the two pools says nothing about *design*
    identity -- `prescription_identity` exists because 442 corpus files carry only
    354 distinct prescriptions, patent continuations republishing one embodiment
    under a new number. Measured 2026-08-03: 30 of the 187 designs that pass
    screens 1-5 are byte-identical to a corpus design.

    They add no supply, since that design is already reachable as a corpus seed.
    What they add is the risk that a "cross-source" trial is seeded from its own
    control -- the most flattering reading the comparator could possibly produce,
    and one that only the assignee-brand rule would stand between us and.
    """
    from app.core.engines.prescription_identity import fingerprint_zmx
    from scripts.p2_pair_census import CASE_INDEX, STAGING_ZMX_DIR

    corpus = set()
    for record in json.loads(CASE_INDEX.read_text(encoding="utf-8")):
        fingerprint = fingerprint_zmx(REPO_ROOT / "data" / "zmx" / str(record["source_zmx"]))
        if fingerprint is not None:
            corpus.add(fingerprint)
    assert corpus, "no corpus fingerprints -- this test would be vacuous"

    duplicated = [
        row["zmx"]
        for row in load_staging_seeds()
        if fingerprint_zmx(STAGING_ZMX_DIR / str(row["zmx"])) in corpus
    ]
    assert not duplicated, f"{len(duplicated)} staging seeds republish a corpus design: {duplicated[:3]}"


@needs_census
def test_the_planner_resolves_staging_seeds_instead_of_dropping_them() -> None:
    """The defect this exists for, found by running the planner rather than by
    reading it.

    `plan_trials` looked both control and seed up in the case index and `continue`d
    when either was missing. Staging seeds are deliberately not in the index, so
    admitting them turned 59 planned trials into **5** -- silently. Nothing failed;
    the plan just came back short, which reads as a smaller corpus rather than as a
    bug, and the real-machine round would have measured 5 trials while every
    artefact said 59 were available.
    """
    from scripts.p2_crosssource_trial import plan_trials

    plans, result = plan_trials(CENSUS)

    assert len(plans) == result["trials"], "the plan is shorter than the census it came from"
    assert {p.seed_pool for p in plans} <= {"corpus", "staging"}
    assert sum(1 for p in plans if p.seed_pool == "staging") > 0


@needs_census
def test_every_planned_seed_file_exists_where_the_plan_says_it_does() -> None:
    """A plan that names a file nobody can open is a run that fails hours in."""
    from scripts.p2_crosssource_trial import plan_trials, seed_zmx_path

    plans, _ = plan_trials(CENSUS)
    missing = [p.seed_case_id for p in plans if not seed_zmx_path(p).is_file()]
    assert not missing, f"{len(missing)} planned seeds have no file: {missing[:3]}"


def test_the_honest_denominator_counts_staging_seeds_too() -> None:
    """`distinct_seed_designs` is the number the run artifact labels as its own
    honest denominator -- every ratio is supposed to be read next to it.

    It resolved every seed through `data/zmx`, so a staging-seeded trial silently
    contributed nothing and the count read **2** where the truth was **12**. That
    is the same silent-drop defect `plan_trials` had, one function away, landing
    on the one number a reader uses to judge whether the sample is independent.
    """
    from scripts.p2_crosssource_trial import _distinct_design_counts

    records = [
        {"plan": {"control_zmx": "US-11668898-B2-e6.zmx", "seed_zmx": "US20210165194A1.zmx",
                  "seed_pool": "corpus"}},
        {"plan": {"control_zmx": "US-11906710-B2-e1.zmx", "seed_zmx": "US-12560782-B2-e1.zmx",
                  "seed_pool": "staging"}},
    ]
    counts = _distinct_design_counts(records)

    assert counts["unfingerprinted"] == [], counts["unfingerprinted"]
    assert counts["seeds"] == 2, "a staging seed was dropped from the honest denominator"


# ---------------------------------------------------------------------------
# The same two invariants, on a committed fixture, so CI actually runs them
# ---------------------------------------------------------------------------

FIXTURE = REPO_ROOT / "tests" / "data" / "perfield_census_fixture.jsonl"


def test_the_fixture_exercises_both_seed_pools() -> None:
    """A gate on an input that produces no trials is not a gate.

    Guards the guard: if the fixture ever stops yielding staging-seeded trials --
    because the manifest changed, or the corpus moved under it -- the two tests
    below would keep passing while testing nothing.
    """
    result = census(FIXTURE, admit_staging_seeds=True)

    assert result["trials"] > 0
    assert result["trials_seeded_from_staging"] > 0
    assert result["staging_seeds_unbuildable"] == []


def test_the_denominator_holds_on_the_fixture() -> None:
    """`test_admitting_staging_seeds_does_not_change_the_denominator`, minus the
    dependency on a runtime product that exists on exactly one machine.

    This is the invariant the PR rests on: a par rate measured after admitting
    staging seeds is comparable with one measured before. It was previously
    enforced only behind a `D:/` skipif, i.e. never on CI -- the failure mode this
    repository already has a written post-mortem for.
    """
    with_ = census(FIXTURE, admit_staging_seeds=True)
    without = census(FIXTURE, admit_staging_seeds=False)

    assert with_["cases_usable"] == without["cases_usable"]
    assert with_["trials"] == without["trials"]
    assert {t["control"] for t in with_["trial_pairs"]} == {
        t["control"] for t in without["trial_pairs"]
    }


def test_no_staging_design_is_ever_a_control_on_the_fixture() -> None:
    """The other load-bearing invariant, likewise freed from the skipif."""
    result = census(FIXTURE, admit_staging_seeds=True)
    staging_ids = {str(r["zmx"]).rsplit(".", 1)[0] for r in load_staging_seeds()}
    usable, _ = load_usable_case_ids(FIXTURE)

    assert not staging_ids & set(usable)
    assert not staging_ids & {t["control"] for t in result["trial_pairs"]}
