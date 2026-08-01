"""The census must be able to say "the market disagrees with this bound"."""

from __future__ import annotations

from pathlib import Path

from scripts.domain_rejection_census import census, render

CENSUS = Path("D:/atelier-stagec-runs/trace-census-20260728/perfield-census.jsonl")


def test_violation_key_groups_by_bound_not_by_offending_value() -> None:
    from scripts.domain_rejection_census import _violation_key

    assert _violation_key("f/# 4.4 out of [1.8, 4.0] for smartphone-telephoto") == (
        "f/#",
        "smartphone-telephoto",
    )
    assert _violation_key("f/# 1.45 out of [1.8, 4.0] for smartphone-telephoto") == (
        "f/#",
        "smartphone-telephoto",
    )
    assert _violation_key("image_height 6.68mm out of [1.7, 4.7]mm for smartphone-wide") == (
        "image_height",
        "smartphone-wide",
    )
    assert _violation_key("no bound here") is None


def test_absurd_readings_are_counted_apart_from_market_evidence(tmp_path: Path) -> None:
    """A 5.9e+17 mm image height is a corpus defect; counting it as a bound the
    market crosses would turn a known degenerate mode into an argument."""
    from scripts.domain_rejection_census import _ABSURD_IMAGE_HEIGHT_MM

    assert _ABSURD_IMAGE_HEIGHT_MM < 1e3


def test_the_real_corpus_shows_bounds_crossed_by_several_independent_assignees() -> None:
    """Measured 2026-07-29: 13 of 14 rejecting bounds, four of them by 4 brands."""
    if not CENSUS.is_file():
        import pytest

        pytest.skip("perfield census not present on this machine")
    rows, summary = census(census_path=CENSUS)
    multi = [r for r in rows if r.brands >= 2]
    assert len(multi) >= 10
    assert max(r.brands for r in rows) >= 4
    # Not a vacuous screen: single-assignee bounds must still be reported apart.
    assert summary["bounds_crossed_by_one_brand"] + len(multi) == len(rows)
    assert "describe our window" in render(rows, summary)


def test_summary_accounts_for_every_considered_case() -> None:
    if not CENSUS.is_file():
        import pytest

        pytest.skip("perfield census not present on this machine")
    _, summary = census(census_path=CENSUS)
    assert (
        summary["accepted"] + summary["rejected"] + summary["absurd_image_height"]
        == summary["considered"]
    )
