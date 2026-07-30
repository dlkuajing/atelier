"""The control's corpus rank -- the threshold-free answer to the open audit item.

The item: a par verdict says nothing useful if the control it beat is itself a bad
lens, and a reader had no way to tell. An absolute floor needs a number nobody has
measured (and the only reusable constant was tried and does not fit -- it is an RMS
*radius* at 50 lp/mm while the probe reports a *diameter* at 100). A rank needs no
threshold at all, so these tests pin what a rank must never do: fabricate a reading
for a sentinel, or travel without its denominator.
"""

from __future__ import annotations

import json
import math

import pytest

from app.core.corpus_quality import (
    DISTRIBUTION_SCHEMA,
    load_distribution,
    reference_population,
    rms_percentile,
)
from scripts.corpus_quality_distribution import build, collect


@pytest.fixture
def distribution() -> dict:
    return load_distribution()


def test_the_committed_artifact_is_loadable_and_non_empty(distribution: dict) -> None:
    assert distribution["schema"] == DISTRIBUTION_SCHEMA
    assert distribution["n"] == len(distribution["sorted_rms_spot_um"]) > 0


def test_the_values_are_sorted_and_strictly_positive(distribution: dict) -> None:
    """Sorted is load-bearing: `rms_percentile` uses bisect, which silently returns
    nonsense on an unsorted list rather than failing."""

    values = distribution["sorted_rms_spot_um"]
    assert values == sorted(values)
    assert all(v > 0.0 for v in values)


def test_the_rank_is_monotone_and_spans_the_population(distribution: dict) -> None:
    values = distribution["sorted_rms_spot_um"]
    assert rms_percentile(values[0]) == 0.0
    assert rms_percentile(values[-1] * 10) == 100.0
    ranks = [rms_percentile(v) for v in (values[0], values[len(values) // 2], values[-1])]
    assert ranks == sorted(ranks)


@pytest.mark.parametrize(
    "sentinel",
    [0.0, -1.0, float("nan"), float("inf"), float("-inf"), None, "", "abc"],
)
def test_a_sentinel_never_gets_a_rank(sentinel) -> None:
    """`0.0` is the project's `@rmssum` all-fields-failed sentinel and `+inf` is the
    fail-closed one. Ranking either would turn "not measured" into "best in corpus"
    (0.0 would land at p0) -- the exact degenerate-value-as-ideal-reading trap this
    codebase has hit repeatedly."""

    assert rms_percentile(sentinel) is None


def test_the_denominator_travels_with_the_rank() -> None:
    """A percentile without its population is a number that reads better than it is."""

    population = reference_population()
    assert population["n"] > 0
    assert "data/zmx" in population["pool"]
    assert "n_positive == num_fields" in population["criterion"]
    assert population["census_run"]
    assert population["caveats"]


def test_the_caveats_name_the_pool_mismatch_and_the_tail() -> None:
    """Both were measured while building the artifact; silence about either would let a
    reader assume the reference is the P2-eligible population and the spread is real."""

    joined = " ".join(reference_population()["caveats"])
    assert "NOT the P2-eligible control population" in joined
    assert "8.3e20" in joined


def test_partial_field_coverage_is_excluded_from_the_reference_population(tmp_path) -> None:
    """`@rmssum` skips failed fields and takes the max over survivors, so a partially
    traced case reports a *smaller* number than it deserves. Admitting those would bias
    the reference optimistic exactly where it matters."""

    census = tmp_path / "perfield.jsonl"
    census.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                # full coverage -> admitted, max field wins
                {"seed": "a", "error": None, "num_fields": 2, "n_positive": 2,
                 "fields": [[0, 0.001], [0, 0.004]]},
                # one field failed -> excluded even though it looks excellent
                {"seed": "b", "error": None, "num_fields": 2, "n_positive": 1,
                 "fields": [[0, 0.001], [1, 0.0]]},
                # CODE V error -> excluded
                {"seed": "c", "error": "boom", "num_fields": 2, "n_positive": 2,
                 "fields": [[0, 0.002], [0, 0.002]]},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    values, stats = collect(census)
    assert values == [4.0]  # 0.004 mm -> 4.0 um, and only case "a" qualifies
    assert stats["excluded"]["errored_or_partial_coverage"] == 2


def test_the_builder_records_a_census_digest(tmp_path) -> None:
    """Provenance has to identify the exact bytes: the census is a runtime product
    outside the worktree, so "which census" cannot be answered by a path alone."""

    census = tmp_path / "perfield.jsonl"
    census.write_text(
        json.dumps(
            {"seed": "a", "error": None, "num_fields": 1, "n_positive": 1, "fields": [[0, 0.003]]}
        )
        + "\n",
        encoding="utf-8",
    )
    payload = build(census)
    assert payload["n"] == 1
    assert len(payload["provenance"]["census_sha256"]) == 64
    assert payload["percentiles"]["p0"] == payload["percentiles"]["p100"] == 3.0


def test_the_quantity_is_documented_as_a_diameter(distribution: dict) -> None:
    """The radius/diameter ambiguity already produced one wrong conclusion in this
    project; a percentile against the wrong convention would produce another."""

    assert "diameter, not a radius" in distribution["quantity"]


def test_the_percentiles_match_the_stored_values(distribution: dict) -> None:
    """Guards against a hand-edited artifact: the summary must be derivable from the
    payload it summarises."""

    values = distribution["sorted_rms_spot_um"]
    assert math.isclose(distribution["percentiles"]["p0"], values[0], rel_tol=1e-12)
    assert math.isclose(distribution["percentiles"]["p100"], values[-1], rel_tol=1e-12)
