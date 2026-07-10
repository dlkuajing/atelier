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
    EVAL_CASES,
    _EVAL_GOLDEN,
    PATENT_GOLDEN_CASE_NAMES as EVAL_PATENT_GOLDEN_CASE_NAMES,
    main,
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

    assert len(INDEX_RECORDS) == 436
    assert len(CASE_GOLDEN_CASE_NAMES) == 436
    assert source_case_ids == set(INDEX_BY_CASE_ID)
    assert data06_case_ids.issubset(source_case_ids)
    assert data09_case_ids.issubset(source_case_ids)
    assert len(first_order_outliers) == 313
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
    exit_code = main(
        [
            "--case",
            "patent_ultrawide_6p_extreme_fov_reanchor",
            "--json",
            "--fail-on-regression",
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert exit_code == 0
    assert report["summary"] == {
        "case_count": 1,
        "passed_count": 1,
        "failed_count": 0,
        "all_passed": True,
    }
    assert report["cases"][0]["matched_case_id"] == "US10330891B2"
