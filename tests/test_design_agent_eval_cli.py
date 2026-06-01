from __future__ import annotations

import json

from scripts.evaluate_design_agent import build_json_report, evaluate, main


def test_eval_json_report_filters_single_case():
    rows = evaluate(case_names={"low_cost_accepts_three_piece_seed"})

    report = build_json_report(rows)

    assert report["summary"] == {
        "case_count": 1,
        "passed_count": 1,
        "failed_count": 0,
        "all_passed": True,
    }
    case = report["cases"][0]
    assert case["eval_case"] == "low_cost_accepts_three_piece_seed"
    assert case["passed"] is True
    assert case["matched_case_id"].startswith("3P_F2.5")
    assert case["designer_readiness"]["status"] == "draft_ready"
    assert case["acceptance"]["status"] == "ready_for_review"
    assert case["acceptance_improvement_tasks"] == []


def test_eval_cli_json_case_filter(capsys):
    exit_code = main(
        [
            "--case",
            "low_cost_accepts_three_piece_seed",
            "--json",
            "--fail-on-regression",
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert report["summary"]["case_count"] == 1
    assert report["cases"][0]["eval_case"] == "low_cost_accepts_three_piece_seed"


def test_eval_cli_rejects_unknown_case(capsys):
    exit_code = main(["--case", "not-a-real-case", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "unknown eval case(s): not-a-real-case" in captured.err
