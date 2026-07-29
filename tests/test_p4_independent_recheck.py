"""P4's recheck must not let a failed second engine look like agreement."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.p4_independent_recheck import _ratio, recheck


def _worker(tmp_path: Path, payload: dict | None, *, exit_code: int = 0) -> Path:
    """A stand-in engine, so the harness is testable without Optiland."""
    worker = tmp_path / "worker.py"
    if payload is None:
        worker.write_text(f"import sys\nsys.exit({exit_code})\n", encoding="utf-8")
    else:
        worker.write_text(
            f"import json, sys\nprint(json.dumps({payload!r}))\n", encoding="utf-8"
        )
    return worker


def _run_dir(tmp_path: Path, *, control_quality: dict | None, candidate_zmx: Path | None) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    (run / "trial_X.json").write_text(
        json.dumps(
            {
                "plan": {"control_case_id": "X", "control_zmx": "nope.zmx"},
                "candidate_zmx": str(candidate_zmx) if candidate_zmx else None,
                "candidate_quality": control_quality,
                "control_quality": control_quality,
            }
        ),
        encoding="utf-8",
    )
    return run


def test_a_failed_second_engine_is_recorded_not_scored(tmp_path: Path) -> None:
    zmx = tmp_path / "cand.zmx"
    zmx.write_text("stub", encoding="utf-8")
    run = _run_dir(
        tmp_path,
        control_quality={"efl_y_mm": 4.0, "f_number": 2.0, "rms_spot_um": 10.0},
        candidate_zmx=zmx,
    )
    result = recheck(run_dir=run, worker=_worker(tmp_path, None, exit_code=1), timeout_s=30)
    assert result["engine_failed"] == result["sides_checked"] >= 1
    for spread in result["reproduction_ratio_optiland_over_codev"].values():
        assert spread["n"] == 0
        assert spread["median"] is None


def test_agreement_is_reported_as_a_ratio_not_a_verdict(tmp_path: Path) -> None:
    zmx = tmp_path / "cand.zmx"
    zmx.write_text("stub", encoding="utf-8")
    run = _run_dir(
        tmp_path,
        control_quality={"efl_y_mm": 4.0, "f_number": 2.0, "rms_spot_um": 10.0},
        candidate_zmx=zmx,
    )
    worker = _worker(
        tmp_path, {"efl_mm": 4.004, "f_number": 2.0, "max_rms_spot_um": 5.0}
    )
    result = recheck(run_dir=run, worker=worker, timeout_s=30)
    ratios = result["reproduction_ratio_optiland_over_codev"]
    assert ratios["efl_mm"]["median"] == pytest.approx(1.001)
    assert ratios["f_number"]["median"] == pytest.approx(1.0)
    assert ratios["max_rms_spot_um"]["median"] == pytest.approx(0.5)
    # No pass/fail threshold anywhere: 红线③ forbids inventing one.
    assert "verdict" not in result
    assert "third party" in str(result["caveat"])


def test_a_withheld_codev_metric_is_never_reproduced_by_the_other_engine(
    tmp_path: Path,
) -> None:
    """None on our side means "not measured"; a number from Optiland cannot fill it."""
    zmx = tmp_path / "cand.zmx"
    zmx.write_text("stub", encoding="utf-8")
    run = _run_dir(
        tmp_path,
        control_quality={"efl_y_mm": 4.0, "f_number": 2.0, "rms_spot_um": None},
        candidate_zmx=zmx,
    )
    worker = _worker(tmp_path, {"efl_mm": 4.0, "f_number": 2.0, "max_rms_spot_um": 5.0})
    result = recheck(run_dir=run, worker=worker, timeout_s=30)
    assert result["reproduction_ratio_optiland_over_codev"]["max_rms_spot_um"]["n"] == 0
    assert result["reproduction_ratio_optiland_over_codev"]["efl_mm"]["n"] >= 1


def test_ratio_refuses_to_divide_by_a_missing_or_zero_reading() -> None:
    assert _ratio(0.0, 1.0) is None
    assert _ratio(None, 1.0) is None
    assert _ratio(1.0, None) is None
    assert _ratio(float("nan"), 1.0) is None
    assert _ratio(2.0, 1.0) == pytest.approx(0.5)
