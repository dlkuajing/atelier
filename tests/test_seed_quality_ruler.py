"""Gate: routing and the P2 comparator must call the same lens good.

The defect this pins down. `_seed_has_floor_violation` compared an **Optiland RMS
spot radius**, computed over whatever field set the case's MTF happened to be built
on, against a 100.0 um bar -- while `scripts/p2_pair_census.py::seed_quality_ok`
screens the same seeds on **CODE V's max-over-fields RMS spot diameter**. Two parts
of one system with two definitions of a usable seed, and the looser one was the one
routing used.

It is not a small discrepancy. Measured 2026-08-03 over the 218 corpus rows where
both instruments have a reading, CODE V-diameter / Optiland-radius has median 4.02
and maximum 379.6; a pure radius-to-diameter conversion would be exactly 2.00. The
concrete casualty: `US-12044826-B2-e4` stores 25.55 um here and reads 101.27 um on
CODE V, and it went on to carry 48 of the 59 P2 trials.

These tests do not assert that the bar is right -- that is a separate, queued
decision. They assert that the *quantity* is right, that absence is not silently
treated as health, and that the artefact carrying the readings stays honest about
its own coverage.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.core.case_library import (
    _SEED_ROUTING_MAX_RMS_UM,
    _seed_max_rms_spot_diameter_um,
    load_case_library,
)
from app.core.corpus_quality import (
    SEED_QUALITY_PATH,
    codev_rms_spot_diameter_um,
    load_seed_quality,
    seed_quality_limit_um,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "app" / "data" / "optical_cases" / "index.json"


def test_the_gate_reads_code_v_when_code_v_has_a_reading() -> None:
    """The whole point: the seed that cleared the gate and then carried 48 of 59
    P2 trials must now be measured at what CODE V says it is."""

    cases = {c.metadata.case_id: c for c in load_case_library()}
    case = cases["US-12044826-B2-e4"]

    stored_radius = max(v for v in case.mtf.rms_spot_radius_um_by_field if math.isfinite(v))
    assert stored_radius < _SEED_ROUTING_MAX_RMS_UM, "premise: the old instrument cleared it"
    assert 2.0 * stored_radius < _SEED_ROUTING_MAX_RMS_UM, "premise: even doubled, it cleared"

    assert _seed_max_rms_spot_diameter_um(case) == pytest.approx(101.27)
    assert _seed_max_rms_spot_diameter_um(case) > _SEED_ROUTING_MAX_RMS_UM


def test_the_fallback_converts_a_radius_to_a_diameter() -> None:
    """224 of 442 rows have no CODE V reading and must still be routable. Comparing
    their stored *radius* against a *diameter* bar would keep the old error for
    exactly the seeds we know least about."""

    cases = {c.metadata.case_id: c for c in load_case_library()}
    uncovered = [
        c
        for cid, c in cases.items()
        if codev_rms_spot_diameter_um(str(c.metadata.source_zmx)) is None
        and any(math.isfinite(v) for v in c.mtf.rms_spot_radius_um_by_field)
    ]
    assert uncovered, "no uncovered rows -- this test would be vacuous"

    case = uncovered[0]
    radius = max(v for v in case.mtf.rms_spot_radius_um_by_field if math.isfinite(v))
    assert _seed_max_rms_spot_diameter_um(case) == pytest.approx(2.0 * radius)


def test_a_seed_no_instrument_can_measure_is_not_healthy() -> None:
    """Returning None has to mean "unknown", and the caller has to read unknown as
    a violation. A seed we cannot measure is not a seed we can show."""

    class _NoReading:
        class _Meta:
            source_zmx = "does-not-exist.zmx"

        class _Mtf:
            rms_spot_radius_um_by_field = [float("nan"), float("inf")]

        metadata = _Meta()
        mtf = _Mtf()

    assert _seed_max_rms_spot_diameter_um(_NoReading()) is None  # type: ignore[arg-type]


def test_the_artifact_covers_exactly_the_two_seed_pools() -> None:
    """A reading for a ZMX nothing can route to is dead weight, and a coverage
    number that is not the artefact's own `n` is a second number waiting to drift.

    "The corpus" is two pools since 2026-08-03: the case index, and the seed-only
    staging manifest. The artifact must cover both and nothing else -- covering
    less is what left 157 seeds on the optimistic fallback; covering more would
    mean carrying readings for designs no consumer can reach.
    """

    payload = load_seed_quality()
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    reachable = {str(r["source_zmx"]) for r in index}

    manifest = REPO_ROOT / "app" / "data" / "p2_staging_seed_manifest.json"
    staging = (
        {str(r["zmx"]) for r in json.loads(manifest.read_text(encoding="utf-8"))["seeds"]}
        if manifest.is_file()
        else set()
    )
    reachable |= staging

    assert set(payload["readings"]) <= reachable
    assert payload["n"] == len(payload["readings"])
    assert payload["corpus_rows"] == len(index)
    assert payload["staging_seed_rows"] == len(staging & set(payload["readings"]))
    assert sum(payload["coverage_by_intake_batch"].values()) == payload["n"]
    # Partial coverage of the *index* is the expected state, not a defect -- full
    # coverage would make the fallback branch dead, zero would make the gate a
    # no-op. The staging pool, by contrast, is admitted only when it has a full
    # CODE V reading, so it should be covered completely.
    corpus_covered = payload["n"] - payload["staging_seed_rows"]
    assert 0 < corpus_covered < payload["corpus_rows"]
    assert payload["staging_seed_rows"] == len(staging)


def test_every_reading_is_a_positive_finite_number() -> None:
    """The project's recurring failure mode is a sentinel that reads as an ideal
    value. A 0.0 here would be a perfect lens; an inf would be an unroutable one."""

    for name, value in load_seed_quality()["readings"].items():
        assert isinstance(value, (int, float)), name
        assert value > 0.0 and math.isfinite(value), f"{name}: {value}"


def test_the_routing_bar_and_the_p2_screen_quote_the_same_number() -> None:
    """`seed_quality_limit_um` exists so that the day the bar moves, it moves in
    one place. It is not what the gate compares against yet -- that step is queued
    -- but it must not be allowed to drift from the comparator's number meanwhile."""

    from scripts.p2_pair_census import default_seed_quality_limit_um

    assert seed_quality_limit_um() == pytest.approx(default_seed_quality_limit_um())


def test_the_artifact_records_which_census_it_came_from() -> None:
    """A per-seed reading with no stated source cannot be rebuilt or challenged."""

    payload = load_seed_quality()
    assert payload["provenance"], "no census recorded"
    for entry in payload["provenance"]:
        assert entry["census"] and entry["sha256"] and entry["rows_admitted"] > 0
    assert "diameter" in payload["quantity"]
    assert "n_positive == num_fields" in payload["criterion"]


def test_the_committed_artifact_is_what_the_builder_produces() -> None:
    """Regenerating from the same censuses must be a no-op, or the committed file
    is not the thing the script documents."""

    census_dir = Path("D:/atelier-stagec-runs/trace-census-20260728")
    census = census_dir / "perfield-census.jsonl"
    if not census.is_file():
        pytest.skip("per-field census is a runtime product, absent on this machine")

    from scripts.build_seed_quality_artifact import build

    rebuilt = build([census])
    committed = json.loads(SEED_QUALITY_PATH.read_text(encoding="utf-8"))
    assert rebuilt["readings"] == committed["readings"]
    assert rebuilt["n"] == committed["n"]


def test_the_staging_seed_pool_is_not_left_on_the_optimistic_instrument() -> None:
    """The two halves of this change have to compose.

    `_seed_max_rms_spot_diameter_um` prefers CODE V and falls back to twice an
    Optiland radius. The artifact was built by filtering to `index.json`
    `source_zmx`, and the P2 seed pool admitted from `data/zmx-staging` is by
    construction absent from that index -- so every one of those seeds fell back
    to the instrument this module exists to retire. Measured on one of them: the
    fallback reads 14.08 um where CODE V measures 526.09, so routing would call
    healthy a seed the comparator kills, and would prefer the staging pool for a
    reason that has nothing to do with quality.
    """
    import json

    manifest = REPO_ROOT / "app" / "data" / "p2_staging_seed_manifest.json"
    if not manifest.is_file():
        pytest.skip("staging seed manifest not present")

    seeds = json.loads(manifest.read_text(encoding="utf-8"))["seeds"]
    assert seeds, "empty manifest would make this vacuous"

    missing = [r["zmx"] for r in seeds if codev_rms_spot_diameter_um(str(r["zmx"])) is None]
    assert not missing, (
        f"{len(missing)} of {len(seeds)} staging seeds have no CODE V reading and "
        f"would fall back to 2x an Optiland radius: {missing[:3]}"
    )


def test_the_artifact_reading_agrees_with_the_manifest_it_came_from() -> None:
    """One number, two files. If they drift, the gate and the P2 screen are back
    to disagreeing about the same lens -- the exact defect this module fixes."""
    import json

    manifest = REPO_ROOT / "app" / "data" / "p2_staging_seed_manifest.json"
    if not manifest.is_file():
        pytest.skip("staging seed manifest not present")

    for row in json.loads(manifest.read_text(encoding="utf-8"))["seeds"]:
        assert codev_rms_spot_diameter_um(str(row["zmx"])) == pytest.approx(
            float(row["codev_rms_um"])
        ), row["zmx"]
