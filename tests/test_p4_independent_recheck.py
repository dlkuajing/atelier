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
    result = recheck(
        run_dir=run,
        worker=_worker(tmp_path, None, exit_code=1),
        timeout_s=30,
        arms=("reported",),
    )
    assert result["engine_failed"] == result["sides_checked"] >= 1
    for spread in result["reproduction_ratio_optiland_over_codev"]["reported"].values():
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
    result = recheck(run_dir=run, worker=worker, timeout_s=30, arms=("reported",))
    ratios = result["reproduction_ratio_optiland_over_codev"]["reported"]
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
    result = recheck(run_dir=run, worker=worker, timeout_s=30, arms=("reported",))
    ratios = result["reproduction_ratio_optiland_over_codev"]["reported"]
    assert ratios["max_rms_spot_um"]["n"] == 0
    assert ratios["efl_mm"]["n"] >= 1


def test_ratio_refuses_to_divide_by_a_missing_or_zero_reading() -> None:
    assert _ratio(0.0, 1.0) is None
    assert _ratio(None, 1.0) is None
    assert _ratio(1.0, None) is None
    assert _ratio(float("nan"), 1.0) is None
    assert _ratio(2.0, 1.0) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Two arms: as we report it, versus as the shipped recipe says it was measured
# ---------------------------------------------------------------------------


def _arm_echoing_worker(tmp_path: Path) -> Path:
    """Reports a different RMS per arm, so pooling the arms would be visible."""
    worker = tmp_path / "arm_worker.py"
    worker.write_text(
        "import json, sys\n"
        "arm = sys.argv[3] if len(sys.argv) > 3 else 'reported'\n"
        "print(json.dumps({'arm': arm, 'efl_mm': 4.0, 'f_number': 2.0,\n"
        "                  'max_rms_spot_um': 8.0 if arm == 'recipe' else 4.0}))\n",
        encoding="utf-8",
    )
    return worker


def test_the_arm_reaches_the_worker(tmp_path: Path) -> None:
    """If the arm never arrives as an argument, both arms silently measure the same
    thing and the comparison is a fabrication."""

    quality = {"efl_y_mm": 4.0, "f_number": 2.0, "rms_spot_um": 8.0}
    zmx = tmp_path / "cand.zmx"
    zmx.write_bytes(b"VERS 1\n")
    run = _run_dir(tmp_path, control_quality=quality, candidate_zmx=zmx)
    result = recheck(run_dir=run, worker=_arm_echoing_worker(tmp_path), timeout_s=30)
    arms_seen = {row["optiland"]["arm"] for row in result["rows"] if not isinstance(row["optiland"], str)}
    assert arms_seen == {"reported", "recipe"}


def test_the_two_arms_are_reported_separately_and_never_pooled(tmp_path: Path) -> None:
    """Pooling would average away the exact comparison this exists to make: the delta
    between the arms IS the share of P4's irreproducibility that publishing the
    measurement recipe removes."""

    quality = {"efl_y_mm": 4.0, "f_number": 2.0, "rms_spot_um": 8.0}
    zmx = tmp_path / "cand.zmx"
    zmx.write_bytes(b"VERS 1\n")
    run = _run_dir(tmp_path, control_quality=quality, candidate_zmx=zmx)
    result = recheck(run_dir=run, worker=_arm_echoing_worker(tmp_path), timeout_s=30)

    ratios = result["reproduction_ratio_optiland_over_codev"]
    assert set(ratios) == {"reported", "recipe"}
    # The stand-in reports 4.0 under 'reported' and 8.0 under 'recipe' against a
    # recorded 8.0, so the arms must land on 0.5 and 1.0 -- not on a pooled 0.75.
    assert ratios["reported"]["max_rms_spot_um"]["median"] == 0.5
    assert ratios["recipe"]["max_rms_spot_um"]["median"] == 1.0


def test_running_one_arm_is_still_possible_and_reports_only_that_arm(tmp_path: Path) -> None:
    quality = {"efl_y_mm": 4.0, "f_number": 2.0, "rms_spot_um": 8.0}
    zmx = tmp_path / "cand.zmx"
    zmx.write_bytes(b"VERS 1\n")
    run = _run_dir(tmp_path, control_quality=quality, candidate_zmx=zmx)
    result = recheck(
        run_dir=run, worker=_arm_echoing_worker(tmp_path), timeout_s=30, arms=("recipe",)
    )
    assert list(result["reproduction_ratio_optiland_over_codev"]) == ["recipe"]
    assert result["arms"] == ["recipe"]


def test_only_the_recipe_arm_disables_our_outlier_clip() -> None:
    """Source-level: the clip must be switched off in the recipe arm and left alone in
    the reported arm. Getting this backwards would make the 'as we report it' arm stop
    reproducing what we actually report -- a silent inversion no ratio would reveal."""

    from scripts.p4_independent_recheck import _WORKER

    assert '_ab._robust_clip_spot_data = lambda geometric_mtf: None' in _WORKER
    clip_line = _WORKER.index("_robust_clip_spot_data")
    guard = _WORKER.rindex('if arm == "recipe":', 0, clip_line)
    # The guard must be the nearest preceding conditional, i.e. nothing else can reach
    # the clip-disabling line.
    assert "\nif " not in _WORKER[guard + len('if arm == "recipe":') : clip_line]


def test_sides_checked_counts_sides_not_recomputes(tmp_path: Path) -> None:
    """With two arms a naive count doubles. Reporting 4 sides for 2 lenses would
    overstate coverage by exactly the number of arms."""

    quality = {"efl_y_mm": 4.0, "f_number": 2.0, "rms_spot_um": 8.0}
    zmx = tmp_path / "cand.zmx"
    zmx.write_bytes(b"VERS 1\n")
    run = _run_dir(tmp_path, control_quality=quality, candidate_zmx=zmx)
    result = recheck(run_dir=run, worker=_arm_echoing_worker(tmp_path), timeout_s=30)
    assert result["sides_checked"] == 1  # only the candidate zmx exists on disk
    assert result["recomputes"] == 2  # one per arm


def test_the_recipe_arm_uses_the_declared_field_set_and_the_reported_arm_does_not() -> None:
    """Source-level, because the branch lives inside the worker string.

    Measured on US-11906710-B2-e2: CODE V measures the 2 declared fields (0.0 and
    39.0 deg) while the recheck's Optiland side was measuring 4 (0, 19.5, 27.3, 39.0)
    via MTF_CANONICAL_FIELD_FRACS. For a max-over-fields metric the two extra mid-fields
    can only raise Optiland's answer, so part of the first P4 pass's "the engines
    disagree" was our own recheck measuring a field set CODE V never sees. The recipe
    arm has to honour what the recipe states ("every field declared in the ZMX").
    """

    from scripts.p4_independent_recheck import _WORKER

    assert "_use_declared_fields" in _WORKER
    # Gated on the recipe arm only: the reported arm must keep reproducing what our own
    # Optiland pipeline says, canonical fractions included.
    assert "_use_declared_fields(optic, text) if arm == 'recipe' else False" in _WORKER
    # The canonical substitution must remain as the fallback, not be deleted -- a
    # real-image-height file aimed at its declared heights makes Optiland solve an
    # inverse that does not terminate on a multi-element design.
    assert "regularize_fields_to_angle(optic, 2.0 * half)" in _WORKER
    # And the row must say which set was used, or the arms are indistinguishable.
    assert "out['field_set']" in _WORKER


def test_the_worker_source_is_valid_python() -> None:
    """The worker is a triple-quoted string, so a nested docstring silently truncates it
    -- that happened once while writing the field-set fix. Parse it here rather than
    discovering it in a subprocess that just exits non-zero."""

    import ast

    from scripts.p4_independent_recheck import _WORKER

    ast.parse(_WORKER)
