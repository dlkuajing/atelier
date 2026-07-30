from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.core.case_library import match_case
from app.core.lens_system import Scenario
from scripts.e2_golden import (
    CASE_GOLDEN_BRIEFS,
    CASE_GOLDEN_CASE_NAMES,
    CASE_GOLDEN_METADATA,
    GOLDEN_BRIEFS,
    ZMX_REAL_IMH_MAX_DEVIATION,
)
from scripts.evaluate_design_agent import (
    _EVAL_GOLDEN,
    EVAL_CASES,
    main,
)
from scripts.evaluate_design_agent import (
    PATENT_GOLDEN_CASE_NAMES as EVAL_PATENT_GOLDEN_CASE_NAMES,
)

INDEX_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "optical_cases" / "index.json"
INDEX_RECORDS = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
INDEX_BY_CASE_ID = {
    record["case_id"]: record
    for record in INDEX_RECORDS
    if isinstance(record, dict)
}


def _first_order_image_height_mm(record: dict) -> float | None:
    first_order = float(record["efl_mm"]) * math.tan(math.radians(float(record["fov_deg"]) / 2.0))
    return first_order if math.isfinite(first_order) and first_order != 0.0 else None


def _first_order_deviation(record: dict) -> float | None:
    first_order = _first_order_image_height_mm(record)
    if first_order is None:
        return None
    return abs(float(record["image_height_mm"]) - first_order) / abs(first_order)


def test_eval_golden_contains_reanchored_case_library():
    eval_case_names = {case.name for case in EVAL_CASES}
    source_case_ids = {
        CASE_GOLDEN_BRIEFS[name]["source_case_id"] for name in CASE_GOLDEN_CASE_NAMES
    }
    data06_case_ids = {
        record["case_id"]
        for record in INDEX_RECORDS
        if str(record.get("intake_batch", "")).startswith("DATA-06")
    }
    data09_case_ids = {
        record["case_id"]
        for record in INDEX_RECORDS
        if str(record.get("intake_batch", "")) == "DATA-09d1"
    }
    first_order_outliers = {
        record["case_id"]
        for record in INDEX_RECORDS
        if str(record.get("case_id", "")).startswith("US-")
        and (_first_order_deviation(record) or 0.0) > 0.25
    }

    assert len(INDEX_RECORDS) == 442
    assert len(CASE_GOLDEN_CASE_NAMES) == 442
    assert source_case_ids == set(INDEX_BY_CASE_ID)
    assert data06_case_ids.issubset(source_case_ids)
    assert data09_case_ids.issubset(source_case_ids)
    # 314 -> 164 on 2026-07-29, and the drop is this migration's independent
    # witness. A "first-order outlier" is a case whose declared image height
    # disagrees with its own `efl * tan(fov_deg / 2)` by more than 25% -- a
    # formula and a threshold that both predate the change. Re-anchoring
    # `fov_deg` from a half angle to the full FOV it was documented to be makes
    # `fov_deg / 2` the true half angle, so the geometry closes.
    #
    # Attribution is total, not partial: **every one** of the 153 cases that left
    # the outlier set was one the migration doubled (153/153), as were all 11 that
    # joined it. Nothing else moved.
    assert len(first_order_outliers) == 164
    assert first_order_outliers.issubset(source_case_ids)
    assert set(CASE_GOLDEN_CASE_NAMES).issubset(_EVAL_GOLDEN)
    assert set(EVAL_PATENT_GOLDEN_CASE_NAMES).issubset(CASE_GOLDEN_CASE_NAMES)
    assert set(EVAL_PATENT_GOLDEN_CASE_NAMES).issubset(eval_case_names)

    for case_name in CASE_GOLDEN_CASE_NAMES:
        entry = _EVAL_GOLDEN[case_name]
        assert entry["source_case_id"] == CASE_GOLDEN_BRIEFS[case_name]["source_case_id"]
        assert entry["source_case_id"] in INDEX_BY_CASE_ID
        assert entry["selected_case_id"] in INDEX_BY_CASE_ID
        assert "first_order_image_height_deviation_frac" in entry
        assert float(entry["quality_floor_gap"]) >= 0.0
        assert float(entry["quality_min250"]) >= 0.0


@pytest.mark.parametrize("case_name", CASE_GOLDEN_CASE_NAMES)
def test_each_reanchored_case_golden_runs(case_name: str) -> None:
    brief = dict(GOLDEN_BRIEFS[case_name])
    source_case_id = brief.pop("source_case_id")
    brief["scenario"] = getattr(Scenario, brief["scenario"])
    brief["lightweight_design_assessment"] = True

    sample = match_case(**brief)
    assert sample is not None
    assert sample.metadata is not None

    golden = _EVAL_GOLDEN[case_name]
    assert golden["source_case_id"] == source_case_id
    assert sample.metadata.case_id == golden["selected_case_id"]


@pytest.mark.parametrize("case_name", CASE_GOLDEN_CASE_NAMES)
def test_each_reanchored_case_records_first_order_sanity(case_name: str) -> None:
    source_case_id = CASE_GOLDEN_BRIEFS[case_name]["source_case_id"]
    record = INDEX_BY_CASE_ID[source_case_id]
    expected_first_order = _first_order_image_height_mm(record)
    expected_deviation = _first_order_deviation(record)
    entry = _EVAL_GOLDEN[case_name]

    assert entry["first_order_image_height_mm"] == pytest.approx(expected_first_order)
    assert entry["first_order_image_height_deviation_frac"] == pytest.approx(expected_deviation)


@pytest.mark.parametrize("case_name", CASE_GOLDEN_CASE_NAMES)
def test_each_reanchored_case_real_imh_anchor_matches_zmx_tail(case_name: str) -> None:
    metadata = CASE_GOLDEN_METADATA[case_name]
    entry = _EVAL_GOLDEN[case_name]
    source_case_id = metadata["source_case_id"]
    record = INDEX_BY_CASE_ID[source_case_id]

    assert entry["image_height_anchor_source"] == metadata["image_height_anchor_source"]
    if metadata["zmx_real_image_height_mm"] is None:
        assert entry["zmx_real_image_height_mm"] is None
        return

    deviation = abs(
        float(record["image_height_mm"]) - metadata["zmx_real_image_height_mm"]
    ) / metadata["zmx_real_image_height_mm"]
    assert entry["zmx_real_image_height_mm"] == pytest.approx(
        metadata["zmx_real_image_height_mm"]
    )
    assert entry["zmx_real_image_height_deviation_frac"] == pytest.approx(deviation)
    assert deviation <= ZMX_REAL_IMH_MAX_DEVIATION


def test_patent_golden_fail_on_regression_case_runs(capsys):
    case_name = "patent_ultrawide_6p_extreme_fov_reanchor"
    exit_code = main(["--case", case_name, "--json", "--fail-on-regression"])

    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert exit_code == 0
    assert report["summary"] == {
        "case_count": 1,
        "passed_count": 1,
        "failed_count": 0,
        "all_passed": True,
    }
    # Read the winner from the golden instead of repeating it here. This literal used
    # to be `US10330891B2`, duplicating a value `scripts/e2_golden.py` already owns --
    # so a routing re-anchor left the two out of step and this test failed for the one
    # reason it is not meant to police. (2026-07-30: the CODE V full-field routing gate
    # moved the winner to a measured 8.75 um seed because `US10330891B2` has no
    # full-field reading at all and the gate fails closed on that.)
    assert report["cases"][0]["matched_case_id"] == _EVAL_GOLDEN[case_name]["selected_case_id"]
