from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.core.case_library import match_case
from app.core.lens_system import Scenario
from scripts.e2_golden import GOLDEN_BRIEFS, PATENT_GOLDEN_CASE_NAMES
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
    if isinstance(record, dict) and str(record.get("case_id", "")).startswith("US")
}


def test_eval_golden_contains_reanchored_patent_seeds():
    eval_case_names = {case.name for case in EVAL_CASES}

    assert len(PATENT_GOLDEN_CASE_NAMES) == 22
    assert set(PATENT_GOLDEN_CASE_NAMES).issubset(_EVAL_GOLDEN)
    assert set(EVAL_PATENT_GOLDEN_CASE_NAMES).issubset(PATENT_GOLDEN_CASE_NAMES)
    assert set(EVAL_PATENT_GOLDEN_CASE_NAMES).issubset(eval_case_names)

    for case_name in PATENT_GOLDEN_CASE_NAMES:
        entry = _EVAL_GOLDEN[case_name]
        assert entry["source_case_id"].startswith("US")
        assert entry["source_case_id"] in INDEX_BY_CASE_ID
        assert float(entry["quality_floor_gap"]) >= 0.0
        assert float(entry["quality_min250"]) >= 0.0


@pytest.mark.parametrize("case_name", PATENT_GOLDEN_CASE_NAMES)
def test_each_reanchored_patent_golden_runs(case_name: str) -> None:
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


@pytest.mark.parametrize("case_name", PATENT_GOLDEN_CASE_NAMES)
def test_each_reanchored_patent_index_imh_has_physical_anchor(case_name: str) -> None:
    source_case_id = GOLDEN_BRIEFS[case_name]["source_case_id"]
    record = INDEX_BY_CASE_ID[source_case_id]
    first_order = float(record["efl_mm"]) * math.tan(math.radians(float(record["fov_deg"]) / 2.0))
    deviation = abs(float(record["image_height_mm"]) - first_order) / first_order

    assert deviation <= 0.25


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
