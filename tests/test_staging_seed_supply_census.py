"""Gate: the staging seed-supply claim may not quietly turn into a headline.

`.planning/evidence/staging-seed-supply-2026-08-02.md` argues that the material
for the 异源 seed shortage is already in the repository. Three things about that
artefact would change what it means if they drifted, so they are pinned:

* the claim is a **feasibility** claim (is such a seed in the pool), never a
  par-rate claim -- nothing here may assert a quality outcome;
* the FOV cap is what separates the two pools. Without a cap both look fine, and
  the corpus-only pool looks fine for the wrong reason (its seeds miss the
  control's field by a median 43.9 deg);
* EFL for staging is derived from each file's own trailer rather than looked up
  through a conversion receipt, because the receipts are known to be misaligned
  on 3 patents. The derivation check must keep passing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.staging_seed_supply_census import (
    DEFAULT_FOV_CAPS,
    MAX_HALF_FIELD_DEG,
    build,
    check_derivation,
    read_first_order,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTEFACT = REPO_ROOT / ".planning" / "evidence" / "staging-seed-supply-2026-08-02.json"
CENSUS = Path("D:/atelier-stagec-runs/trace-census-20260728/perfield-census.jsonl")
STAGING_CENSUS = Path("D:/atelier-stagec-runs/trace-census-20260728/perfield-staging-census.jsonl")
STAGING_DIR = REPO_ROOT / "data" / "zmx-staging" / "patent-local-replay"


@pytest.fixture(scope="module")
def artefact() -> dict:
    return json.loads(ARTEFACT.read_text(encoding="utf-8"))


def test_the_staging_pool_is_actually_in_the_repository() -> None:
    """The whole argument is 'we already have this'. If the files are not tracked,
    the argument is about something the next machine will not have."""

    assert STAGING_DIR.is_dir()
    assert len(list(STAGING_DIR.glob("*.zmx"))) > 500


def test_staging_and_corpus_do_not_overlap() -> None:
    """Zero overlap is why staging is *additional* supply rather than a re-count."""

    corpus = {
        str(record["source_zmx"]).lower()
        for record in json.loads(
            (REPO_ROOT / "app" / "data" / "optical_cases" / "index.json").read_text(
                encoding="utf-8"
            )
        )
    }
    staging = {path.name.lower() for path in STAGING_DIR.glob("*.zmx")}
    assert staging and not (staging & corpus)


def test_first_order_reader_fails_closed_on_a_field_it_cannot_divide_by() -> None:
    """`tan` stops discriminating near 90 deg. A reader that returns a huge number
    there would hand every wide design a fabricated EFL."""

    assert MAX_HALF_FIELD_DEG < 90.0
    missing = read_first_order(STAGING_DIR / "does-not-exist.zmx")
    assert missing == {}


def test_the_derivation_check_covers_the_whole_index_not_a_head_slice(artefact: dict) -> None:
    """The failure this test exists because of.

    The first version checked `index[:200]` and reported 95.4% within 1%. The
    index is ordered by intake batch, so that head contains **zero** DATA-10b
    rows -- the batch where the formula is 29% accurate. The true figure is
    318/393 = 80.9%. A self-check calibrated on the cleanest slice of the data is
    not a self-check.
    """

    check = artefact["efl_derivation_check"]
    assert check["scope"] == "whole index"
    assert check["n"] > 350, "coverage shrank; the check is back on a slice"
    by_batch = check["within_1pct_by_intake_batch"]
    assert "DATA-10b" in by_batch, "the batch the formula fails on must be covered"
    assert sum(row["n"] for row in by_batch.values()) == check["n"]


def test_the_derivation_accuracy_is_reported_not_asserted_away(artefact: dict) -> None:
    """No threshold here on purpose. The formula is ~80% accurate corpus-wide and
    its accuracy tracks the parser family, so any pass/fail bar would just encode
    today's corpus mix. What must hold is that the *unevenness stays visible*."""

    check = artefact["efl_derivation_check"]
    rates = {
        batch: row["within_1pct"] / row["n"]
        for batch, row in check["within_1pct_by_intake_batch"].items()
        if row["n"] >= 5
    }
    assert len(rates) >= 3
    assert max(rates.values()) - min(rates.values()) > 0.3, (
        "the per-batch spread vanished; either the parser was fixed (update this "
        "test and the evidence page) or the breakdown stopped being computed"
    )


def test_staging_efl_comes_from_the_built_optic_not_the_declared_one(artefact: dict) -> None:
    """Both pools must be measured with one ruler or the reachability gate is
    comparing a declared focal length against a computed one -- and the
    disagreement is fail-open (a too-large seed EFL passes)."""

    source = artefact["staging_pool"]["efl_source"]
    assert source.get("receipt_built_optic", 0) > 0
    assert source["receipt_built_optic"] > 10 * source.get("trailer_declared_fallback", 0), (
        "the declared-EFL fallback is no longer a rounding error; the double-ruler "
        "caveat in the evidence page has to be re-measured"
    )


def test_the_fov_cap_is_what_separates_the_pools(artefact: dict) -> None:
    """THE claim. Uncapped, the corpus-only pool also serves everyone -- with seeds
    whose field is wrong. Capped, it collapses and staging does not. If this ever
    stops holding, the evidence page is stale, not merely imprecise."""

    comparison = artefact["comparison"]
    corpus_any = comparison["corpus seeds only (two-screen) @ any"]
    corpus_capped = comparison["corpus seeds only (two-screen) @ 20deg"]
    both_capped = comparison["corpus + staging @ 20deg"]

    assert corpus_capped["served"] < corpus_any["served"], (
        "the FOV cap no longer bites on the corpus-only pool"
    )
    assert both_capped["served"] > corpus_capped["served"]
    assert both_capped["distinct_options_median"] > corpus_capped["distinct_options_median"]
    assert both_capped["controls_with_zero_options"] <= corpus_capped["controls_with_zero_options"]


def test_every_cap_is_reported_not_just_the_flattering_one(artefact: dict) -> None:
    """A single cap could be picked to make the point. All of them ship."""

    caps = {"any"} | {f"{c:.0f}deg" for c in DEFAULT_FOV_CAPS if c is not None}
    for label in (
        "corpus seeds only (two-screen)",
        "staging seeds only",
        "corpus + staging",
    ):
        present = {key.split(" @ ")[1] for key in artefact["comparison"] if key.startswith(label)}
        assert present == caps, f"{label} is missing caps {caps - present}"


def test_the_artefact_states_its_own_diversity_limit(artefact: dict) -> None:
    """The pool being large does not make the *sample* independent. A greedy pick
    concentrates; the artefact has to carry that number rather than only the
    flattering per-control count."""

    row = artefact["comparison"]["corpus + staging @ 20deg"]
    assert row["lowest_rms_pick_concentration"]
    assert max(row["lowest_rms_pick_concentration"].values()) > 1


def test_dropped_rows_are_counted_by_reason(artefact: dict) -> None:
    """Fail-closed bookkeeping: a staging file that cannot be screened must show up
    as a named drop, never be silently absent from both numerator and denominator."""

    pool = artefact["staging_pool"]
    assert pool["dropped"]
    assert pool["admitted"] + sum(pool["dropped"].values()) == pool["full_field_readings"]
    assert pool["at_or_below_corpus_median"] <= pool["admitted"]


@pytest.mark.skipif(
    not (CENSUS.exists() and STAGING_CENSUS.exists()),
    reason=(
        "needs both per-field censuses, held outside the repository "
        "(D:/atelier-stagec-runs/...); local gate, not a CI gate"
    ),
)
def test_artefact_still_matches_a_fresh_recompute() -> None:
    fresh = build(CENSUS, STAGING_CENSUS)
    stored = json.loads(ARTEFACT.read_text(encoding="utf-8"))
    assert fresh["staging_pool"] == stored["staging_pool"]
    assert fresh["controls"] == stored["controls"]
    for key, row in stored["comparison"].items():
        assert fresh["comparison"][key]["served"] == row["served"], key


def test_the_derivation_only_covers_files_that_carry_the_trailer() -> None:
    """Coverage is not total and must not be assumed to be. The trailer
    `ATELIER_FTAN_IMH_SANITY_MM` is written by the patent conversion path, so the
    hand-built `NP_F...` designs at the head of `index.json` have no reference and
    yield no derived EFL. Measured: 40 records give 1, 200 give 153. Staging is
    entirely patent-derived, which is why the derivation is usable there -- and
    why this test exists rather than a blanket 'it works' assertion."""

    small = check_derivation(sample=40)
    large = check_derivation(sample=200)
    assert small["n"] < 10 < large["n"], (
        "coverage changed shape; re-read the caveat in the evidence page before "
        "quoting the derivation as general"
    )
