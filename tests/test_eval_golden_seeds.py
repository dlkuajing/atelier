from __future__ import annotations

import json

from scripts.evaluate_design_agent import (
    EVAL_CASES,
    PATENT_GOLDEN_CASE_NAMES,
    _EVAL_GOLDEN,
    main,
)


def test_eval_golden_contains_reanchored_patent_seeds():
    eval_case_names = {case.name for case in EVAL_CASES}

    assert len(PATENT_GOLDEN_CASE_NAMES) >= 5
    assert set(PATENT_GOLDEN_CASE_NAMES).issubset(_EVAL_GOLDEN)
    assert set(PATENT_GOLDEN_CASE_NAMES).issubset(eval_case_names)

    for case_name in PATENT_GOLDEN_CASE_NAMES:
        entry = _EVAL_GOLDEN[case_name]
        assert entry["source_case_id"].startswith("US")
        assert entry["selected_case_id"] == entry["source_case_id"]
        assert float(entry["quality_floor_gap"]) >= 0.0
        assert float(entry["quality_min250"]) >= 0.0


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
