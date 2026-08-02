"""Gate: the supply funnel artefact may not quietly become flattering.

`.planning/evidence/upstream-supply-funnel-2026-08-02.md` reads three claims off
this artefact that would change what the P2 headline means if they drifted:

* the cross-source seed supply is **4** designs per control, not a healthy pool
  -- so 41/49 trials sharing one seed is a corpus fact, not a ranker bug;
* the corpus's own image-height gate still rejects rows the shipped index
  carries, and 15 of them sit inside the two-screen pool -- so widening the seed
  pool without re-applying that gate would import diverged traces;
* the diverged readings are separated from the real ones by a **void**, not by a
  tuned threshold.

Each is pinned as a *direction* (or as an identity that must keep holding),
never as a headline number, so a genuine corpus improvement can move them.

The recompute test needs the per-field census, which lives outside the
repository, so it skips in CI and says so. The artefact tests do not: they read
a committed file and run everywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.upstream_supply_funnel import DIVERGED_MAGNITUDE, FOV_BANDS, build, fov_band

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTEFACT = REPO_ROOT / ".planning" / "evidence" / "upstream-supply-funnel-2026-08-02.json"
CENSUS = Path("D:/atelier-stagec-runs/trace-census-20260728/perfield-census.jsonl")


@pytest.fixture(scope="module")
def artefact() -> dict:
    return json.loads(ARTEFACT.read_text(encoding="utf-8"))


def test_fov_bands_partition_the_line() -> None:
    """No gap and no overlap: a band census that drops designs is not a census."""
    edges = [(lo, hi) for _, lo, hi in FOV_BANDS]
    assert edges[0][0] == 0.0
    for (_, hi), (lo, _) in zip(edges, edges[1:], strict=False):
        assert hi == lo
    for value, expected in ((0.0, "<40"), (39.999, "<40"), (40.0, "40-60"), (84.9, "75-85"), (85.0, ">=85"), (180.0, ">=85")):
        assert fov_band(value) == expected


def test_funnel_is_monotone(artefact: dict) -> None:
    """Each screen is a subset of the one before it, or the funnel is not one."""
    f = artefact["funnel"]
    assert (
        f["case_index"]
        >= f["full_field_codev_reading"]
        >= f["trace_and_fidelity_clean"]
        >= f["and_in_product_domain"]
    )


def test_cross_source_seed_supply_is_the_binding_scarcity(artefact: dict) -> None:
    """The report's headline claim: a control can be seeded from a handful of
    designs, and screen 3 -- justified in its own docstring by what a *control*
    is -- is what makes it a handful."""
    supply = artefact["cross_source_seed_supply"]
    today = supply["today (3 screens)"]
    control_only = supply["screen 3 on controls only"]
    assert today["cross_source_seeds_median"] <= 10, (
        "the report is written around a starved cross-source pool; if this pool "
        "has genuinely grown, re-measure before quoting the report"
    )
    assert control_only["cross_source_seeds_median"] > today["cross_source_seeds_median"]


def test_widening_the_seed_pool_would_import_gate_rejected_rows(artefact: dict) -> None:
    """Fail-closed prerequisite. `scripts/image_height_gate.py` runs at generation
    time only; nothing re-applies it to the shipped index. Controls are already
    protected by the parameter guard (0 rejects inside the in-domain pool), but
    the two-screen pool is not -- so the widening described in the report must
    filter on this gate, not merely drop screen 3."""
    gate = artefact["image_height_gate"]
    assert gate["still_inside_in_domain_pool"] == [], (
        "a control is handing a gate-rejected image height to the optimiser as "
        "spec_imh_mm; that is a stop-the-line defect, not a pool-size question"
    )
    assert gate["still_inside_trace_and_fidelity_pool"], (
        "if this is empty the seed pool can be widened without the gate; update "
        "the report rather than deleting the requirement"
    )


def test_the_divergence_cut_sits_in_a_void_not_on_a_slope(artefact: dict) -> None:
    """The 1e6 cut is only defensible because nothing lives near it. If real data
    ever approaches it, the cut stops being definitional and must be re-derived."""
    for key in ("image_height_mm", "rms_spot_diameter_um"):
        row = artefact["diverged_traces"][key]
        assert row["over_cut"] > 0
        assert row["largest_under_cut"] is not None
        assert row["smallest_over_cut"] is not None
        assert row["largest_under_cut"] < DIVERGED_MAGNITUDE <= row["smallest_over_cut"]
        # The void is the gap between the largest real value and the smallest
        # diverged one -- the cut merely sits inside it. Measured 2026-08-02 that
        # gap is ~16 orders of magnitude on both quantities; four is the floor at
        # which the cut would stop being definitional and need re-deriving.
        assert row["smallest_over_cut"] / row["largest_under_cut"] > 1e4


def test_spot_over_image_height_is_reported_as_the_weak_screen(artefact: dict) -> None:
    """Kept because it is the intuitive screen and it *does not work here*: the
    numerator and the denominator diverge together, so it catches almost nothing.
    Pinned so nobody re-discovers it and promotes it to a gate."""
    spot = artefact["spot_vs_image_height"]
    diverged = artefact["diverged_traces"]
    assert spot["at_or_above_1.0"] < len(diverged["union"])


def test_batch_rows_carry_the_like_for_like_column(artefact: dict) -> None:
    """A quality census that only compares against a corpus-wide median cannot
    tell 'defective' from 'ultra-wide'. Every batch row must also carry the
    count measured against its own FOV band."""
    for batch, row in artefact["quality_by_intake_batch"].items():
        assert "at_or_below_own_fov_band_median" in row, batch
        assert row["at_or_below_own_fov_band_median"] <= row["n"], batch
        assert row["at_or_below_corpus_median"] <= row["n"], batch


@pytest.mark.skipif(
    not CENSUS.exists(),
    reason=(
        "needs the per-field traceability census held outside the repository "
        f"({CENSUS}); this is a local gate, not a CI gate"
    ),
)
def test_artefact_still_matches_a_fresh_recompute() -> None:
    """The committed artefact is evidence; evidence that no longer reproduces is
    a stale claim. Compares the structural findings, not floats."""
    fresh = build(CENSUS)
    stored = json.loads(ARTEFACT.read_text(encoding="utf-8"))
    assert fresh["funnel"] == stored["funnel"]
    assert fresh["diverged_traces"]["union"] == stored["diverged_traces"]["union"]
    assert (
        fresh["image_height_gate"]["verdicts_over_shipped_index"]
        == stored["image_height_gate"]["verdicts_over_shipped_index"]
    )
    assert fresh["inputs"]["case_index_sha256"] == stored["inputs"]["case_index_sha256"]
