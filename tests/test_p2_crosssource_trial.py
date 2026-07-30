"""Offline guards for the P2 异源打平率 comparator.

Nothing here touches CODE V. The pieces that decide what a *number* means --
which readings are withheld, which side wins a metric, what the denominator of
the headline is -- are all pure and are pinned here, because those are the
places where a false-green would survive undetected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.p2_crosssource_trial import (
    MTF_FREQUENCY_LPMM,
    MTF_NRD,
    P2_METRICS,
    ImageQuality,
    build_probe_sequence,
    compare,
    sessions_from_snapshot,
    summarise,
)

HEALTHY = {
    "efl_y_mm": "5.68",
    "f_number": "1.6",
    "num_wavelengths": "3",
    "num_fields": "2",
    "image_height_mm": "2.32",
    "rms_spot_um": "10.4",
    "rms_wavefront_waves": "0.31",
    "distortion_pct": "1.72",
    "lateral_color_um": "0.68",
    "mtf_min": "0.312",
    # Every declared field produced a reading -- the healthy case.
    "rms_fields_ok": "2",
    "mtf_fields_ok": "2",
}


def q(**overrides: str) -> ImageQuality:
    data = dict(HEALTHY)
    data.update(overrides)
    return ImageQuality.from_data(data, source="probe.zmx")


# ---------------------------------------------------------------------------
# Withholding rules -- one test per degenerate mode the project has paid for
# ---------------------------------------------------------------------------


def test_a_healthy_reading_survives_every_screen() -> None:
    """Negative controls are worthless without this: the screens must let real data through."""
    quality = q()
    assert quality.comparable
    assert quality.withheld == ()
    assert quality.rms_spot_um == pytest.approx(10.4)
    assert quality.mtf_min == pytest.approx(0.312)
    assert quality.distortion_pct == pytest.approx(1.72)


def test_zero_rms_spot_is_the_accumulator_seed_not_a_perfect_point() -> None:
    quality = q(rms_spot_um="0", rms_wavefront_waves="0")
    assert quality.rms_spot_um is None
    assert quality.rms_wavefront_waves is None
    assert "rms_spot_seed_value" in quality.withheld
    assert not quality.comparable


def test_mtf_of_one_is_the_accumulator_seed_not_a_perfect_lens() -> None:
    quality = q(mtf_min="1.0")
    assert quality.mtf_min is None
    assert "mtf_seed_value" in quality.withheld


def test_distortion_is_withheld_when_no_positive_definite_metric_witnesses_a_trace() -> None:
    """0.0 distortion is physically legal, so it needs an independent witness."""
    quality = q(rms_spot_um="0", rms_wavefront_waves="0", distortion_pct="0", lateral_color_um="0")
    assert quality.distortion_pct is None
    assert quality.lateral_color_um is None
    assert "distortion_no_positive_definite_witness" in quality.withheld


def test_distortion_survives_when_one_positive_definite_metric_survives() -> None:
    """Withholding must not over-reach: one surviving witness is enough."""
    quality = q(rms_wavefront_waves="0", distortion_pct="0.0")
    assert quality.rms_spot_um == pytest.approx(10.4)
    assert quality.distortion_pct == pytest.approx(0.0)


def test_lateral_color_is_withheld_below_three_wavelengths() -> None:
    quality = q(num_wavelengths="1", lateral_color_um="0")
    assert quality.lateral_color_um is None
    assert "lateral_color_below_three_wavelengths" in quality.withheld


# --- degenerate mode 6: runs away toward +inf, not toward the ideal value ---


@pytest.mark.parametrize(
    ("case_id", "rms_spot_um", "mtf_min"),
    [
        ("US-11719917-B2-e4", "5.578e+20", "1.451e-37"),
        ("US-11719917-B2-e5", "8.261e+20", "2.713e-37"),
        ("US-11719917-B2-e6", "7.811e+20", "5.764e-38"),
    ],
)
def test_real_machine_absurd_spot_radii_are_withheld(
    case_id: str, rms_spot_um: str, mtf_min: str
) -> None:
    """Vectors taken verbatim from the 2026-07-28 control baseline run.

    1e+20 µm is 1e+14 metres -- fourteen orders of magnitude wider than the image
    circle. Every prior degenerate mode collapsed *toward* the ideal reading, so
    the project's screens were all of the form "<= 0 is impossible"; this one
    sails through them. The bound is the lens' own image circle, not a constant.
    """
    quality = q(rms_spot_um=rms_spot_um, mtf_min=mtf_min, rms_wavefront_waves="0")
    assert quality.rms_spot_um is None, (
        f"{case_id} absurd spot radius was reported as a measurement"
    )
    assert "rms_spot_exceeds_image_circle" in quality.withheld
    assert not quality.comparable
    # And the joint criterion must then also withhold distortion, since both
    # positive-definite metrics are now unusable.
    assert quality.distortion_pct is None


def test_spot_radius_just_inside_the_image_circle_is_kept() -> None:
    """The bound must not be a quality gate: a bad-but-real lens still reports."""
    quality = q(image_height_mm="2.0", rms_spot_um="3999")
    assert quality.rms_spot_um == pytest.approx(3999)
    assert "rms_spot_exceeds_image_circle" not in quality.withheld


def test_spot_radius_just_outside_the_image_circle_is_withheld() -> None:
    quality = q(image_height_mm="2.0", rms_spot_um="4001")
    assert quality.rms_spot_um is None
    assert "rms_spot_exceeds_image_circle" in quality.withheld


def test_spot_radius_is_unboundable_without_an_image_height() -> None:
    """No scale anchor -> the absurd-value screen cannot run -> withhold, not trust."""
    quality = q(image_height_mm="0")
    assert quality.image_height_mm is None
    assert quality.rms_spot_um is None
    assert "rms_spot_unboundable" in quality.withheld


def test_non_finite_readings_are_withheld() -> None:
    quality = q(rms_spot_um="nan", mtf_min="inf")
    assert quality.rms_spot_um is None
    assert quality.mtf_min is None


# ---------------------------------------------------------------------------
# Comparison and denominators
# ---------------------------------------------------------------------------


def test_par_requires_all_three_metrics() -> None:
    control = q()
    candidate = q(rms_spot_um="9.0", mtf_min="0.4", distortion_pct="1.0")
    assert compare(candidate, control)["verdict"] == "par"


def test_one_worse_metric_loses_the_trial() -> None:
    control = q()
    candidate = q(rms_spot_um="9.0", mtf_min="0.4", distortion_pct="2.5")
    result = compare(candidate, control)
    assert result["verdict"] == "worse"
    assert result["metrics"]["distortion_pct"]["verdict"] == "worse"


def test_equal_metrics_count_as_par_because_the_criterion_is_not_worse() -> None:
    assert compare(q(), q())["verdict"] == "par"


def test_mtf_is_the_only_higher_is_better_metric() -> None:
    assert P2_METRICS == {"rms_spot_um": True, "mtf_min": False, "distortion_pct": True}


def test_an_unmeasurable_side_makes_the_trial_unmeasurable_not_a_win() -> None:
    control = q()
    candidate = q(rms_spot_um="0", rms_wavefront_waves="0")
    result = compare(candidate, control)
    assert result["verdict"] == "unmeasurable"
    assert result["metrics"]["rms_spot_um"]["verdict"] == "unmeasurable"


def test_headline_denominator_includes_unmeasurable_trials() -> None:
    """Dropping unjudgeable trials would inflate the headline -- the flattering direction."""
    records = [
        {"verdict": "par", "plan": {"seed_case_id": "s1"}, "metrics": {}},
        {"verdict": "worse", "plan": {"seed_case_id": "s1"}, "metrics": {}},
        {"verdict": "unmeasurable", "plan": {"seed_case_id": "s2"}, "blocked_at": "probe"},
    ]
    summary = summarise(records)
    assert summary["trials"] == 3
    assert summary["par_rate_over_all_trials"] == pytest.approx(1 / 3)
    assert summary["par_rate_over_judged"] == pytest.approx(1 / 2)
    assert summary["distinct_seeds_used"] == 2
    assert summary["blocked_at"] == {"probe": 1}


def test_summary_reports_both_denominators_so_neither_can_be_quoted_alone() -> None:
    summary = summarise([{"verdict": "unmeasurable", "plan": {"seed_case_id": "s1"}}])
    assert summary["par_rate_over_all_trials"] == pytest.approx(0.0)
    assert summary["par_rate_over_judged"] is None


def test_a_candidate_that_missed_the_spec_is_not_judged() -> None:
    """20% off the target EFL is a different lens, and a shorter lens wins for free."""
    records = [
        {
            "verdict": "spec_not_met",
            "plan": {"seed_case_id": "s1"},
            "metrics": {m: {"verdict": "par"} for m in P2_METRICS},
        },
        {"verdict": "par", "plan": {"seed_case_id": "s2"}, "metrics": {}},
    ]
    summary = summarise(records)
    assert summary["judged"] == 1
    assert summary["par_rate_over_judged"] == pytest.approx(1.0)
    assert summary["par_rate_over_all_trials"] == pytest.approx(0.5)
    # The spec-missing candidate won every metric, and none of them counted.
    for metric in P2_METRICS:
        assert summary[f"{metric}_par"] == 0


def test_vignetting_stratification_separates_clipped_candidates() -> None:
    """autovig clipping is written into the candidate ZMX and biases the headline up."""
    records = [
        {"verdict": "par", "plan": {"seed_case_id": "s1"}, "autovig_edge_used": "0", "metrics": {}},
        {
            "verdict": "worse",
            "plan": {"seed_case_id": "s2"},
            "autovig_edge_used": "0",
            "metrics": {},
        },
        {
            "verdict": "par",
            "plan": {"seed_case_id": "s3"},
            "autovig_edge_used": "0.6",
            "metrics": {},
        },
    ]
    summary = summarise(records)
    assert summary["par_rate_over_judged"] == pytest.approx(2 / 3)
    assert summary["judged_unclipped"] == 2
    assert summary["par_rate_unclipped_only"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Probe macro
# ---------------------------------------------------------------------------


def test_probe_uses_the_production_metric_functions(tmp_path: Path) -> None:
    """Candidate and control must be judged by the production instrument."""
    from app.core.engines.codev_optimize import _metric_function_block

    zmx = tmp_path / "seed.zmx"
    zmx.write_text("", encoding="ascii")
    sequence = build_probe_sequence(source_zmx=zmx, result_path=tmp_path / "out.tsv")
    for line in _metric_function_block():
        assert line in sequence


def test_probe_exports_every_key_the_reader_requires(tmp_path: Path) -> None:
    from scripts.p2_crosssource_trial import _PROBE_REQUIRED_KEYS

    zmx = tmp_path / "seed.zmx"
    zmx.write_text("", encoding="ascii")
    sequence = build_probe_sequence(source_zmx=zmx, result_path=tmp_path / "out.tsv")
    for key in _PROBE_REQUIRED_KEYS:
        assert f'"{key}"' in sequence


def test_probe_mtf_settings_match_the_production_tolerance_block() -> None:
    """A different frequency or ray density silently changes what "MTF" means."""
    from app.core.engines.codev_optimize import (
        _DEFAULT_TOLERANCE_MTF_FREQUENCY_LPMM,
        _DEFAULT_TOLERANCE_NRD,
    )

    assert MTF_FREQUENCY_LPMM == _DEFAULT_TOLERANCE_MTF_FREQUENCY_LPMM
    assert MTF_NRD == _DEFAULT_TOLERANCE_NRD


def test_probe_imports_through_the_staging_helper_not_the_raw_file() -> None:
    """A raw import collapses to one wavelength (PR #93) and quietly falsifies colour."""
    source = Path("scripts/p2_crosssource_trial.py").read_text(encoding="utf-8")
    assert "stage_zmx_for_codev" in source
    assert "measure_image_quality" in source


# ---------------------------------------------------------------------------
# 红线① session counting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _P:
    pid: int
    ppid: int
    name: str


def test_one_codev_instance_with_two_processes_counts_as_one_session() -> None:
    snapshot = [_P(1, 0, "explorer.exe"), _P(10, 1, "codev.exe"), _P(11, 10, "codevm.exe")]
    assert len(sessions_from_snapshot(snapshot)) == 1


def test_two_independent_instances_count_as_two_sessions() -> None:
    snapshot = [
        _P(1, 0, "explorer.exe"),
        _P(10, 1, "codev.exe"),
        _P(11, 10, "codevm.exe"),
        _P(20, 1, "codev.exe"),
        _P(21, 20, "codevm.exe"),
    ]
    assert len(sessions_from_snapshot(snapshot)) == 2


def test_codex_processes_are_never_counted_or_touched() -> None:
    snapshot = [_P(1, 0, "codex.exe"), _P(2, 1, "codex.exe")]
    assert sessions_from_snapshot(snapshot) == []


# ---------------------------------------------------------------------------
# Planning inputs
# ---------------------------------------------------------------------------


def test_case_index_supplies_every_field_the_spec_needs() -> None:
    index = json.loads(Path("app/data/optical_cases/index.json").read_text(encoding="utf-8"))
    required = {"case_id", "source_zmx", "efl_mm", "fnum", "fov_deg", "image_height_mm", "n_pieces"}
    assert required <= set(index[0])
    assert all(required <= set(record) for record in index)


def test_the_comparator_reports_tolerance_yield_as_the_fourth_piece() -> None:
    """Not built ahead of a consumer: the P2 comparator emits it per trial."""
    from pathlib import Path

    source = Path("scripts/p2_crosssource_trial.py").read_text(encoding="utf-8")
    assert '_tolerance_pair(' in source
    assert 'record["tolerance"]' in source


def test_both_sides_get_the_same_tolerance_table() -> None:
    """NORTH-STAR §3's 「表错了两边一起错，排序不变」 only holds if the table is
    literally the same object for candidate and control, so there is one module
    constant and no per-side parameter."""
    import inspect

    import scripts.p2_crosssource_trial as trial

    src = inspect.getsource(trial._tolerance_pair)
    # one loop over both sides, one table constant referenced inside it
    assert 'for side, zmx in (("candidate", candidate_zmx), ("control", control_zmx))' in src
    assert src.count("TorToleranceTable(TOLERANCE_COMMANDS") == 1
    assert inspect.signature(trial._tolerance_pair).parameters.keys() == {
        "candidate_zmx", "control_zmx", "work_dir", "timeout_seconds"
    }


def test_the_tolerance_table_is_declared_uncalibrated() -> None:
    """It is an order-of-magnitude starter set, not a manufacturing budget."""
    import scripts.p2_crosssource_trial as trial

    assert trial._tolerance_pair.__doc__
    out_keys = {"tolerance_commands", "trials", "yield_threshold_waves", "calibrated"}
    from pathlib import Path

    source = Path("scripts/p2_crosssource_trial.py").read_text(encoding="utf-8")
    for key in out_keys:
        assert f'"{key}"' in source
    assert '"calibrated": False' in source


# ---------------------------------------------------------------------------
# Trial roll-up: a confirmed "worse" settles the trial (2026-07-29)
# ---------------------------------------------------------------------------


def _iq(**kw: object) -> object:
    from scripts.p2_crosssource_trial import ImageQuality

    base = {
        "source": "probe", "efl_y_mm": 4.0, "f_number": 2.0, "num_wavelengths": 3,
        "num_fields": 3, "image_height_mm": 3.0, "rms_spot_um": 10.0,
        "rms_wavefront_waves": 0.1, "distortion_pct": 1.0, "lateral_color_um": 1.0,
        "mtf_min": 0.5, "withheld": (),
    }
    base.update(kw)
    return ImageQuality(**base)  # type: ignore[arg-type]


def test_a_confirmed_worse_settles_the_trial_even_with_an_unmeasurable_metric() -> None:
    """打平 needs every metric 不劣于, so one worse decides it regardless of the
    rest. Real case US-11906710-B2-e5: RMS 30.5x worse, distortion 14.1x worse,
    MTF withheld -- no MTF reading could have rescued it."""
    from scripts.p2_crosssource_trial import compare

    result = compare(_iq(rms_spot_um=300.0, mtf_min=None), _iq())
    assert result["verdict"] == "worse"


def test_unmeasurable_still_wins_when_nothing_is_confirmed_worse() -> None:
    """Withholding must not be quietly resolved into a pass."""
    from scripts.p2_crosssource_trial import compare

    result = compare(_iq(rms_spot_um=1.0, distortion_pct=0.1, mtf_min=None), _iq())
    assert result["verdict"] == "unmeasurable"


def test_par_still_requires_every_metric_measured_and_not_worse() -> None:
    from scripts.p2_crosssource_trial import compare

    assert compare(_iq(rms_spot_um=1.0, distortion_pct=0.1, mtf_min=0.9), _iq())["verdict"] == "par"


def test_the_correction_can_never_manufacture_a_par() -> None:
    """It only moves trials out of unmeasurable into worse."""
    from scripts.p2_crosssource_trial import compare

    for cand in (_iq(rms_spot_um=300.0, mtf_min=None), _iq(distortion_pct=99.0, mtf_min=None)):
        assert compare(cand, _iq())["verdict"] != "par"


# ---------------------------------------------------------------------------
# Conformance screen: the candidate must not have been handed an easier job
# (2026-07-29 -- `codev_optimize` never enforces IMH/FOV, so the candidate
# inherits its seed's field definition)
# ---------------------------------------------------------------------------


def test_field_tangent_is_image_height_over_efl_from_the_same_side() -> None:
    from scripts.p2_crosssource_trial import field_tangent

    assert field_tangent(_iq(image_height_mm=3.0, efl_y_mm=4.0)) == pytest.approx(0.75)
    assert field_tangent(_iq(image_height_mm=None)) is None
    assert field_tangent(_iq(efl_y_mm=None)) is None
    assert field_tangent(_iq(efl_y_mm=0.0)) is None


def test_same_field_and_aperture_passes_the_conformance_screen() -> None:
    """The negative control: a like-for-like pair must not be screened out."""
    from scripts.p2_crosssource_trial import conformance_screen

    blocked, details = conformance_screen(_iq(), _iq())
    assert blocked is None
    assert details["field_coverage_ratio"] == pytest.approx(1.0)


def test_a_candidate_covering_less_field_than_the_control_is_not_judged() -> None:
    """The measured case: candidate at 18.35 deg against a control at 37.5 deg."""
    from scripts.p2_crosssource_trial import conformance_screen

    candidate = _iq(efl_y_mm=5.312, image_height_mm=1.762)
    control = _iq(efl_y_mm=5.312, image_height_mm=4.078)
    blocked, details = conformance_screen(candidate, control)
    assert blocked == "field_not_covered"
    assert details["field_coverage_ratio"] == pytest.approx(1.762 / 4.078)


def test_a_candidate_covering_more_field_is_still_judged() -> None:
    """Over-delivery only makes the candidate's own numbers harder to win with."""
    from scripts.p2_crosssource_trial import conformance_screen

    assert conformance_screen(_iq(image_height_mm=4.0), _iq(image_height_mm=3.0))[0] is None


def test_a_slower_candidate_is_not_judged_because_a_small_pupil_is_a_free_win() -> None:
    from scripts.p2_crosssource_trial import conformance_screen

    assert conformance_screen(_iq(f_number=2.8), _iq(f_number=2.0))[0] == "f_number_not_met"
    assert conformance_screen(_iq(f_number=1.8), _iq(f_number=2.0))[0] is None


def test_an_unreadable_field_or_aperture_blocks_rather_than_passes() -> None:
    """Fail-closed: a pair we cannot prove comparable is not quietly compared."""
    from scripts.p2_crosssource_trial import conformance_screen

    assert conformance_screen(_iq(image_height_mm=None), _iq())[0] == "field_not_comparable"
    # A missing EFL is now caught one leg earlier, by the scale check that runs
    # first -- still fail-closed, just named for the leg that actually saw it.
    assert conformance_screen(_iq(), _iq(efl_y_mm=None))[0] == "efl_not_comparable"
    assert conformance_screen(_iq(f_number=None), _iq())[0] == "f_number_not_comparable"


def test_the_screen_slack_is_readout_rounding_not_a_quality_threshold() -> None:
    """A hair under counts as covered; a real shortfall does not."""
    from scripts.p2_crosssource_trial import CONFORMANCE_RELATIVE_SLACK, conformance_screen

    assert CONFORMANCE_RELATIVE_SLACK < 1e-2
    hair = _iq(image_height_mm=3.0 * (1.0 - CONFORMANCE_RELATIVE_SLACK / 2.0))
    assert conformance_screen(hair, _iq(image_height_mm=3.0))[0] is None
    real = _iq(image_height_mm=3.0 * (1.0 - CONFORMANCE_RELATIVE_SLACK * 10.0))
    assert conformance_screen(real, _iq(image_height_mm=3.0))[0] == "field_not_covered"


def test_the_screen_can_only_remove_trials_from_the_headline_never_add_a_par() -> None:
    """Same guarantee the 2026-07-29 roll-up correction carries."""
    from scripts.p2_crosssource_trial import conformance_screen

    # A candidate that would have scored par on every metric, but on half the field.
    winner = _iq(rms_spot_um=1.0, distortion_pct=0.1, mtf_min=0.9, image_height_mm=1.5)
    assert conformance_screen(winner, _iq(image_height_mm=3.0))[0] == "field_not_covered"


def test_summary_reports_field_coverage_so_the_missing_trials_are_explained() -> None:
    records = [
        {
            "verdict": "spec_not_met",
            "plan": {"seed_case_id": "s1"},
            "conformance": {"field_coverage_ratio": 0.43},
        },
        {
            "verdict": "spec_not_met",
            "plan": {"seed_case_id": "s2"},
            "conformance": {"field_coverage_ratio": 0.51},
        },
    ]
    summary = summarise(records)
    assert summary["field_coverage_ratio_n"] == 2
    assert summary["field_coverage_ratio_median"] == pytest.approx(0.47)
    assert summary["field_coverage_ratio_min"] == pytest.approx(0.43)
    assert summary["judged"] == 0
    assert summary["par_rate_over_judged"] is None


# ---------------------------------------------------------------------------
# Seed field re-aim: refuse *before* spending CODE V time (2026-07-29)
# ---------------------------------------------------------------------------


_REBUILD_ZMX = "\r\n".join(
    [
        "VERS 190513",
        "MODE SEQ",
        "FTYP 0 0 3 3 0 0 0",
        "XFLN 0 0 0",
        "YFLN 0 12.5 25",
        "SURF 0",
        "",
    ]
)


def _rebuild_plan():
    from scripts.p2_crosssource_trial import TrialPlan

    return TrialPlan(
        control_case_id="CTL", control_zmx="ctl.zmx", control_brand="A",
        seed_case_id="SEED", seed_zmx="seed.zmx", seed_brand="B",
        spec_efl_mm=3.0, spec_f_number=2.0, spec_imh_mm=2.5,
        spec_fov_deg=75.0, spec_n_pieces=6,
    )


def _stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, control: str, seed: str) -> Path:
    import scripts.p2_crosssource_trial as trial_module

    zmx_dir = tmp_path / "zmx"
    zmx_dir.mkdir()
    (zmx_dir / "ctl.zmx").write_bytes(control.encode("latin-1"))
    (zmx_dir / "seed.zmx").write_bytes(seed.encode("latin-1"))
    monkeypatch.setattr(trial_module, "ZMX_DIR", zmx_dir)

    def _never(*args: object, **kwargs: object) -> None:
        raise AssertionError("CODE V must not be started for a seed that cannot be re-aimed")

    monkeypatch.setattr(
        "app.core.engines.codev_optimize.run_codev_target_standard", _never
    )
    _stub_control_probe(monkeypatch)
    return zmx_dir


def test_a_non_angular_control_blocks_the_trial_before_any_codev_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A FTYP 3 control states millimetres; there is no spec angle to aim at."""
    from scripts.p2_crosssource_trial import run_trial

    _stage(
        tmp_path, monkeypatch,
        control=_REBUILD_ZMX.replace("FTYP 0 ", "FTYP 3 "), seed=_REBUILD_ZMX,
    )
    record = run_trial(_rebuild_plan(), out_dir=tmp_path / "out")
    assert record["verdict"] == "spec_not_met"
    assert record["blocked_at"] == "control_field_not_angular"
    assert record["seed_field_rebuild"]["rebuilt"] is False


def test_a_seed_that_cannot_be_re_aimed_blocks_before_any_codev_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.p2_crosssource_trial import run_trial

    _stage(
        tmp_path, monkeypatch,
        control=_REBUILD_ZMX, seed=_REBUILD_ZMX.replace("XFLN 0 0 0", "XFLN 0 1 2"),
    )
    record = run_trial(_rebuild_plan(), out_dir=tmp_path / "out")
    assert record["verdict"] == "spec_not_met"
    assert record["blocked_at"] == "seed_field_not_rebuildable"


def test_the_re_aimed_seed_is_what_gets_optimised_not_the_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 2026-07-29 bug in one assertion: the optimiser must see the new field."""
    import scripts.p2_crosssource_trial as trial_module
    from app.core.engines.seed_field_rebuild import max_field_angle_deg
    from app.core.engines.zmx_import_prep import decode_zmx_text

    zmx_dir = tmp_path / "zmx"
    zmx_dir.mkdir()
    control = _REBUILD_ZMX.replace("YFLN 0 12.5 25", "YFLN 0 18.75 37.5")
    (zmx_dir / "ctl.zmx").write_bytes(control.encode("latin-1"))
    (zmx_dir / "seed.zmx").write_bytes(_REBUILD_ZMX.encode("latin-1"))
    monkeypatch.setattr(trial_module, "ZMX_DIR", zmx_dir)
    _stub_control_probe(monkeypatch)

    seen: dict[str, Path] = {}

    def _capture(**kwargs: object) -> dict[str, object]:
        seen["source"] = Path(str(kwargs["source_zmx"]))
        return {"preferred": None, "configs": {}}

    monkeypatch.setattr("app.core.engines.codev_optimize.run_codev_target_standard", _capture)
    record = run_trial_entry = trial_module.run_trial(_rebuild_plan(), out_dir=tmp_path / "out")
    assert run_trial_entry is record
    assert seen["source"].name != "seed.zmx"
    rebuilt_text = decode_zmx_text(seen["source"].read_bytes())[0]
    assert max_field_angle_deg(rebuilt_text) == pytest.approx(37.5)
    assert record["seed_field_rebuild"]["scale"] == pytest.approx(1.5)


def test_the_old_behaviour_is_still_reachable_for_a_b_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.p2_crosssource_trial as trial_module

    zmx_dir = tmp_path / "zmx"
    zmx_dir.mkdir()
    (zmx_dir / "ctl.zmx").write_bytes(_REBUILD_ZMX.encode("latin-1"))
    (zmx_dir / "seed.zmx").write_bytes(_REBUILD_ZMX.encode("latin-1"))
    monkeypatch.setattr(trial_module, "ZMX_DIR", zmx_dir)
    _stub_control_probe(monkeypatch)
    seen: dict[str, Path] = {}

    def _capture(**kwargs: object) -> dict[str, object]:
        seen["source"] = Path(str(kwargs["source_zmx"]))
        return {"preferred": None, "configs": {}}

    monkeypatch.setattr("app.core.engines.codev_optimize.run_codev_target_standard", _capture)
    record = trial_module.run_trial(
        _rebuild_plan(), out_dir=tmp_path / "out", rebuild_seed_field=False
    )
    assert seen["source"].name == "seed.zmx"
    assert "seed_field_rebuild" not in record


# ---------------------------------------------------------------------------
# Per-trial wall-clock budget (2026-07-29). 46 trials x 46 minutes is 35 hours;
# a bounded run needs a stop that does not lie about why it stopped.
# ---------------------------------------------------------------------------


def _stub_control_probe(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> object:
    """The control probe runs first now -- the spec is taken from it."""
    import scripts.p2_crosssource_trial as trial_module

    # EFL matches `_rebuild_plan().spec_efl_mm` so the engine-agreement gate is
    # satisfied by default; tests that want the disagreement path override it.
    base = {
        "source": "ctl.zmx", "efl_y_mm": 3.0, "f_number": 2.0, "num_wavelengths": 3,
        "num_fields": 2, "image_height_mm": 2.5, "rms_spot_um": 10.0,
        "rms_wavefront_waves": 0.1, "distortion_pct": 1.0, "lateral_color_um": 1.0,
        "mtf_min": 0.5,
    }
    base.update(overrides)
    probed = trial_module.ImageQuality(**base)  # type: ignore[arg-type]
    monkeypatch.setattr(trial_module, "measure_image_quality", lambda **k: probed)
    return probed


def _budget_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.p2_crosssource_trial as trial_module

    zmx_dir = tmp_path / "zmx"
    zmx_dir.mkdir()
    for name in ("ctl.zmx", "seed.zmx"):
        (zmx_dir / name).write_bytes(_REBUILD_ZMX.encode("latin-1"))
    monkeypatch.setattr(trial_module, "ZMX_DIR", zmx_dir)
    _stub_control_probe(monkeypatch)


def test_a_trial_out_of_clock_gets_its_own_verdict_not_worse_or_unmeasurable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Filing it as `worse` would invent a loss; as `unmeasurable`, blame the optics."""
    import scripts.p2_crosssource_trial as trial_module

    _budget_corpus(tmp_path, monkeypatch)

    def _never(**kwargs: object) -> None:
        raise AssertionError("CODE V must not be started once the budget is spent")

    monkeypatch.setattr("app.core.engines.codev_optimize.run_codev_target_standard", _never)
    monkeypatch.setattr(
        "scripts.p2_crosssource_trial.measure_image_quality",
        lambda **k: (_ for _ in ()).throw(
            AssertionError("no probe may run once the budget is spent")
        ),
    )
    record = trial_module.run_trial(
        _rebuild_plan(), out_dir=tmp_path / "out", wall_clock_budget_s=0.0
    )
    assert record["verdict"] == "budget_exhausted"
    assert record["blocked_at"] == "before_control_probe"
    assert record["wall_clock_budget_s"] == 0.0


def test_no_budget_means_no_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The negative control: the default path must be untouched."""
    import scripts.p2_crosssource_trial as trial_module

    _budget_corpus(tmp_path, monkeypatch)
    called: list[str] = []

    def _capture(**kwargs: object) -> dict[str, object]:
        called.append(str(kwargs["source_zmx"]))
        return {"preferred": None, "configs": {}}

    monkeypatch.setattr("app.core.engines.codev_optimize.run_codev_target_standard", _capture)
    record = trial_module.run_trial(_rebuild_plan(), out_dir=tmp_path / "out")
    assert called
    assert record["verdict"] == "unmeasurable"


def test_budget_exhausted_is_outside_judged_and_reported_on_its_own() -> None:
    records = [
        {"verdict": "budget_exhausted", "plan": {"seed_case_id": "s1"}},
        {"verdict": "worse", "plan": {"seed_case_id": "s2"}, "metrics": {}},
        {"verdict": "par", "plan": {"seed_case_id": "s3"}, "metrics": {}},
    ]
    summary = summarise(records)
    assert summary["judged"] == 2
    assert summary["budget_exhausted"] == 1
    assert summary["par_rate_over_judged"] == pytest.approx(0.5)
    # Still in the honest denominator: a trial we ran out of time on is a trial
    # we did not win.
    assert summary["par_rate_over_all_trials"] == pytest.approx(1 / 3)


def test_a_budget_skipped_tolerance_is_named_not_merely_absent() -> None:
    from scripts.p2_crosssource_trial import render

    records = [
        {
            "verdict": "worse",
            "plan": {"seed_case_id": "s1"},
            "metrics": {},
            "tolerance": {"skipped": "wall_clock_budget", "budget_s": 60.0},
        }
    ]
    summary = summarise(records)
    assert summary["tolerance_skipped_for_budget"] == 1
    # The trial keeps its P2 verdict: the three metrics were measured.
    assert summary["judged"] == 1
    assert "budget_exhausted" in render(summary)


# ---------------------------------------------------------------------------
# Idle watchdog coverage: it landed for the optimiser only (2026-07-29)
# ---------------------------------------------------------------------------


def test_the_probe_runs_under_the_idle_watchdog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Two probes per trial, one per side -- a stalled one burned its whole timeout."""
    from scripts.p2_crosssource_trial import IDLE_TIMEOUT_SECONDS, measure_image_quality

    seen: dict[str, object] = {}

    class _Batch:
        data = dict(HEALTHY)

    def fake_batch(**kwargs: object) -> object:
        seen.update(kwargs)
        return _Batch()

    monkeypatch.setattr("app.core.engines.codev_batch.run_codev_batch", fake_batch)
    monkeypatch.setattr(
        "app.core.engines.zmx_import_prep.stage_zmx_for_codev",
        lambda *a, **k: tmp_path / "staged.zmx",
    )
    source = tmp_path / "src.zmx"
    source.write_text("stub", encoding="utf-8")
    measure_image_quality(source_zmx=source, work_dir=tmp_path / "w", tag="candidate")
    assert seen["idle_timeout_seconds"] == IDLE_TIMEOUT_SECONDS


def test_every_codev_stage_in_a_trial_names_the_watchdog() -> None:
    """A stage added later without it is the failure this test exists to catch.

    Source-level rather than behavioural on purpose: the tolerance and optimise
    stages both need a real CODE V to exercise, and the thing worth pinning is
    that no call site is left without the argument.
    """
    source = Path("scripts/p2_crosssource_trial.py").read_text(encoding="utf-8")
    assert source.count("idle_timeout_seconds=IDLE_TIMEOUT_SECONDS") >= 3


# ---------------------------------------------------------------------------
# Absolute scale (2026-07-29 adversarial audit): the spec came from Optiland
# while the control was scored by CODE V, and both existing legs are ratios.
# ---------------------------------------------------------------------------


def test_a_smaller_candidate_at_the_same_field_and_aperture_is_not_judged() -> None:
    """The measured case: 2.84 mm against 4.40 mm, F/# 2.0 both sides, scored par."""
    from scripts.p2_crosssource_trial import conformance_screen

    # Uniform scale: same tan(theta), same F/#, 0.646x the focal length.
    candidate = _iq(efl_y_mm=2.84062, image_height_mm=2.84062 * 1.131, rms_spot_um=1.848)
    control = _iq(efl_y_mm=4.39859, image_height_mm=4.39859 * 1.131, rms_spot_um=51.4502)
    blocked, details = conformance_screen(candidate, control)
    assert blocked == "efl_not_matched"
    assert details["efl_ratio"] == pytest.approx(0.646, abs=1e-3)
    # The two older legs really are blind to it -- that is why this one exists.
    assert details["field_coverage_ratio"] == pytest.approx(1.0)
    assert details["candidate_f_number"] == details["control_f_number"]


def test_scale_is_checked_before_field_so_the_reason_names_the_real_problem() -> None:
    from scripts.p2_crosssource_trial import conformance_screen

    both_wrong = _iq(efl_y_mm=2.0, image_height_mm=1.0)
    assert conformance_screen(both_wrong, _iq(efl_y_mm=4.0, image_height_mm=3.0))[0] == (
        "efl_not_matched"
    )


def test_the_efl_leg_uses_the_engines_own_achieved_target_tolerance() -> None:
    """A candidate the optimiser itself calls converged must not fail here."""
    from scripts.p2_crosssource_trial import EFL_PARITY_TOLERANCE, conformance_screen

    assert pytest.approx(0.02) == EFL_PARITY_TOLERANCE
    inside = _iq(efl_y_mm=4.0 * 1.019, image_height_mm=3.0 * 1.019)
    assert conformance_screen(inside, _iq(efl_y_mm=4.0, image_height_mm=3.0))[0] is None
    outside = _iq(efl_y_mm=4.0 * 1.03, image_height_mm=3.0 * 1.03)
    assert conformance_screen(outside, _iq(efl_y_mm=4.0, image_height_mm=3.0))[0] == (
        "efl_not_matched"
    )


def test_an_unreadable_efl_blocks_rather_than_passes() -> None:
    from scripts.p2_crosssource_trial import conformance_screen

    assert conformance_screen(_iq(efl_y_mm=None), _iq())[0] == "efl_not_comparable"
    assert conformance_screen(_iq(), _iq(efl_y_mm=None))[0] == "efl_not_comparable"
    assert conformance_screen(_iq(), _iq(efl_y_mm=0.0))[0] == "efl_not_comparable"


def test_a_control_the_two_engines_disagree_about_is_refused_before_the_expensive_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """41/440 of the corpus disagrees, 37 of them at exactly the cover-glass index."""
    import scripts.p2_crosssource_trial as trial_module

    _budget_corpus(tmp_path, monkeypatch)
    # Manifest (Optiland) says 3.0; the CODE V probe reads 1.5177x that.
    _stub_control_probe(monkeypatch, efl_y_mm=3.0 * 1.5177, image_height_mm=3.0 * 1.5177)
    monkeypatch.setattr(
        "app.core.engines.codev_optimize.run_codev_target_standard",
        lambda **k: (_ for _ in ()).throw(
            AssertionError("no CODE V time may be spent on a control we cannot trust")
        ),
    )
    record = trial_module.run_trial(_rebuild_plan(), out_dir=tmp_path / "out")
    assert record["verdict"] == "unmeasurable"
    assert record["blocked_at"] == "control_engine_disagreement"
    assert record["control_engine_agreement"]["probe_over_manifest"] == pytest.approx(1.5177)


def test_an_agreeing_control_supplies_the_spec_from_the_engine_that_scores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When both engines agree there is no choice to make -- and none is invented."""
    import scripts.p2_crosssource_trial as trial_module

    _budget_corpus(tmp_path, monkeypatch)
    _stub_control_probe(monkeypatch, efl_y_mm=3.0, image_height_mm=2.5)
    seen: dict[str, object] = {}

    def _capture(**kwargs: object) -> dict[str, object]:
        seen.update(kwargs)
        return {"preferred": None, "configs": {}}

    monkeypatch.setattr("app.core.engines.codev_optimize.run_codev_target_standard", _capture)
    record = trial_module.run_trial(_rebuild_plan(), out_dir=tmp_path / "out")
    assert seen["target_efl_mm"] == pytest.approx(3.0)
    assert record["control_engine_agreement"]["probe_over_manifest"] == pytest.approx(1.0)
    assert record["blocked_at"] != "control_engine_disagreement"


def test_an_unprobeable_control_ends_the_trial_before_the_expensive_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.p2_crosssource_trial as trial_module
    from app.core.engines.codev_batch import CodeVBatchError

    _budget_corpus(tmp_path, monkeypatch)

    def _boom(**kwargs: object) -> object:
        raise CodeVBatchError("failure", "control will not import")

    monkeypatch.setattr(trial_module, "measure_image_quality", _boom)
    monkeypatch.setattr(
        "app.core.engines.codev_optimize.run_codev_target_standard",
        lambda **k: (_ for _ in ()).throw(
            AssertionError("the optimiser must not run without a measured control")
        ),
    )
    record = trial_module.run_trial(_rebuild_plan(), out_dir=tmp_path / "out")
    assert record["verdict"] == "unmeasurable"
    assert record["blocked_at"] == "control_probe"


# ---------------------------------------------------------------------------
# Partial-field extrema (2026-07-29 adversarial audit, 8 findings, one root)
# ---------------------------------------------------------------------------


def test_a_max_over_fewer_fields_than_declared_is_not_the_max_we_report() -> None:
    """@rmssum skips a field whose SPOTDATA errors and returns the survivors' max."""
    quality = q(num_fields="4", rms_fields_ok="3")
    assert quality.rms_spot_um is None
    assert "rms_spot_partial_field_coverage" in quality.withheld
    # The other metrics are untouched: only the extremum over fields is affected.
    assert quality.efl_y_mm == pytest.approx(5.68)


def test_a_min_over_fewer_fields_than_declared_is_not_the_min_we_report() -> None:
    """Every dropped field moves MTF UP, and higher is better."""
    quality = q(num_fields="4", mtf_fields_ok="1")
    assert quality.mtf_min is None
    assert "mtf_partial_field_coverage" in quality.withheld


def test_full_field_coverage_passes_so_the_screen_is_not_a_blanket() -> None:
    """The negative control: a screen that withholds everything measures nothing."""
    quality = q(num_fields="4", rms_fields_ok="4", mtf_fields_ok="4")
    assert quality.rms_spot_um == pytest.approx(10.4)
    assert quality.mtf_min == pytest.approx(0.312)
    assert quality.withheld == ()


def test_a_missing_witness_withholds_rather_than_assumes_full_coverage() -> None:
    """Fail-closed: a probe that did not report the witness proves nothing."""
    data = dict(HEALTHY)
    data.pop("rms_fields_ok")
    data.pop("mtf_fields_ok")
    quality = ImageQuality.from_data(data, source="probe.zmx")
    assert quality.rms_spot_um is None
    assert quality.mtf_min is None


def test_the_witness_counts_are_required_probe_keys() -> None:
    """A probe build that forgets them must fail loudly, not silently pass."""
    from scripts.p2_crosssource_trial import _PROBE_REQUIRED_KEYS

    assert "rms_fields_ok" in _PROBE_REQUIRED_KEYS
    assert "mtf_fields_ok" in _PROBE_REQUIRED_KEYS


def test_the_probe_sequence_asks_code_v_for_the_witness_counts() -> None:
    from scripts.p2_crosssource_trial import build_probe_sequence

    seq = build_probe_sequence(source_zmx="D:/x/a.zmx", result_path="D:/x/r.tsv")
    assert "@rmsnf(1)" in seq
    assert "@mtfnf(" in seq
    assert '"rms_fields_ok"' in seq
    assert '"mtf_fields_ok"' in seq


def test_the_counting_macros_mirror_the_functions_they_witness() -> None:
    """A witness that succeeds where its metric fails would be worse than none."""
    from app.core.engines.codev_optimize import _metric_function_block

    block = "\n".join(_metric_function_block())
    assert "FCT @rmsnf(NUM ^dummy)" in block
    assert "FCT @mtfnf(NUM ^freq, NUM ^nrd)" in block
    # Same guard expressions as @rmssum / @mtfmin.
    assert block.count("^err == SPOTDATA(1,^f,1,0.01,'CEN',0,0,^spot)") == 2
    assert block.count("IF ^xmtf >= 0 and ^ymtf >= 0") == 2


def test_the_rebuilt_seed_filename_is_code_v_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`f"{angle:g}"` gave `_field45.1`, and CODE V aborts the macro on a
    `.<digits>` infix. The guard caught it on the first real-machine run; this
    pins the fix so it cannot come back by way of a tidier-looking format."""
    import scripts.p2_crosssource_trial as trial_module
    from app.core.engines.codev_batch import ensure_buf_exp_safe_filename

    zmx_dir = tmp_path / "zmx"
    zmx_dir.mkdir()
    # Control at 45.1 deg half field -- the exact value that broke.
    control = _REBUILD_ZMX.replace("YFLN 0 12.5 25", "YFLN 0 22.55 45.1")
    (zmx_dir / "ctl.zmx").write_bytes(control.encode("latin-1"))
    (zmx_dir / "seed.zmx").write_bytes(_REBUILD_ZMX.encode("latin-1"))
    monkeypatch.setattr(trial_module, "ZMX_DIR", zmx_dir)
    _stub_control_probe(monkeypatch, efl_y_mm=3.0, image_height_mm=2.5)

    seen: dict[str, Path] = {}

    def _capture(**kwargs: object) -> dict[str, object]:
        seen["source"] = Path(str(kwargs["source_zmx"]))
        return {"preferred": None, "configs": {}}

    monkeypatch.setattr("app.core.engines.codev_optimize.run_codev_target_standard", _capture)
    trial_module.run_trial(_rebuild_plan(), out_dir=tmp_path / "out")

    name = seen["source"].name
    assert "_field0451" in name
    assert "45.1" not in name
    # The real contract: the guard that fired on the real machine must accept it,
    # both for this file and for the optimiser's derived candidate name.
    ensure_buf_exp_safe_filename(seen["source"], role="rebuilt_seed")
    derived = seen["source"].with_name(
        seen["source"].stem + "_target002837_vig0000_optimized.zmx"
    )
    ensure_buf_exp_safe_filename(derived, role="optimized_zmx_path")


def test_both_optimiser_arms_are_always_recorded_not_only_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_select_preferred` chooses on RMS spot -- a judged metric -- and ignores
    the pupil clip each arm needed. Until the rule changes, the record must at
    least show what was chosen over what."""
    import scripts.p2_crosssource_trial as trial_module

    _budget_corpus(tmp_path, monkeypatch)
    configs = {
        "asphere": {
            "aut_converged": "1",
            "autovig.edge_used": "0",
            "post_aut.max_rms_spot_diameter_um": "75.08",
            "optimized_zmx_path": None,
        },
        "both": {
            "aut_converged": "1",
            "autovig.edge_used": "0.3",
            "post_aut.max_rms_spot_diameter_um": "43.77",
            "optimized_zmx_path": None,
        },
    }
    monkeypatch.setattr(
        "app.core.engines.codev_optimize.run_codev_target_standard",
        lambda **k: {"preferred": "both", "preferred_reason": "both wins on RMS", "configs": configs},
    )
    record = trial_module.run_trial(_rebuild_plan(), out_dir=tmp_path / "out")

    assert record["preferred_config"] == "both"
    assert set(record["configs"]) == {"asphere", "both"}
    # The two numbers that make the choice auditable.
    assert record["configs"]["both"]["autovig.edge_used"] == "0.3"
    assert record["configs"]["asphere"]["autovig.edge_used"] == "0"
    assert record["configs"]["both"]["post_aut.max_rms_spot_diameter_um"] == "43.77"
    # The winning arm was clipped harder than the loser -- exactly the confound
    # the disclosure exists to make visible.
    assert float(record["configs"]["both"]["autovig.edge_used"]) > float(
        record["configs"]["asphere"]["autovig.edge_used"]
    )


# ---------------------------------------------------------------------------
# Criterion ③: 交付物四件套完整度（缺一不算交付）
# ---------------------------------------------------------------------------

import scripts.p2_crosssource_trial as trial  # noqa: E402


def _four_piece_record(tmp_path, **overrides):
    zmx = tmp_path / "cand.zmx"
    zmx.write_bytes(b"VERS 1\n")
    record = {
        "plan": {
            "control_zmx": "c.zmx",
            "seed_zmx": "s.zmx",
            "control_case_id": "CTRL-1",
            "seed_case_id": "SEED-1",
        },
        "candidate_zmx": str(zmx),
        "metrics": {
            "rms_spot_um": {"candidate": 4.0, "control": 5.0, "verdict": "par"},
            "mtf_min": {"candidate": 0.5, "control": 0.4, "verdict": "par"},
            "distortion_pct": {"candidate": 1.0, "control": 1.1, "verdict": "par"},
        },
        "tolerance": {"candidate": {"yield_fraction": 0.6}},
        "relative_cost_index": {"ratio": 0.99},
        "verdict": "par",
    }
    record.update(overrides)
    return record


def test_all_four_pieces_present_counts_as_delivered(tmp_path) -> None:
    pieces = trial._deliverable_pieces(_four_piece_record(tmp_path))
    assert pieces == {
        "prescription_zmx": True,
        "image_quality": True,
        "tolerance_yield": True,
        "relative_cost": True,
    }


def test_a_recorded_zmx_path_that_is_not_on_disk_is_not_a_deliverable(tmp_path) -> None:
    """A path is a promise; the file is the deliverable."""
    record = _four_piece_record(tmp_path, candidate_zmx=str(tmp_path / "absent.zmx"))
    assert trial._deliverable_pieces(record)["prescription_zmx"] is False


def test_one_withheld_metric_makes_image_quality_undelivered(tmp_path) -> None:
    """Counting a partial metric set would report exactly the flattering number the
    witness gates exist to refuse."""
    record = _four_piece_record(tmp_path)
    record["metrics"]["mtf_min"]["candidate"] = None
    assert trial._deliverable_pieces(record)["image_quality"] is False


@pytest.mark.parametrize(
    "candidate_tolerance",
    [
        {"error": "CodeVBatchError: TOR produced no export"},
        {},
        None,
        {"yield_fraction": None},
        {"yield_fraction": "0.6"},  # a string is not a measurement
    ],
)
def test_a_missing_or_unusable_yield_is_not_a_deliverable(tmp_path, candidate_tolerance) -> None:
    record = _four_piece_record(tmp_path, tolerance={"candidate": candidate_tolerance})
    assert trial._deliverable_pieces(record)["tolerance_yield"] is False


@pytest.mark.parametrize("ratio", [None, float("inf"), float("nan"), "0.99"])
def test_a_non_finite_cost_ratio_is_not_a_deliverable(tmp_path, ratio) -> None:
    record = _four_piece_record(tmp_path, relative_cost_index={"ratio": ratio})
    assert trial._deliverable_pieces(record)["relative_cost"] is False


def test_a_skipped_tolerance_run_reports_not_assessable_not_zero(tmp_path) -> None:
    """"We did not measure it" and "it did not work" must not share a number.

    A `--skip-tolerance` phase-1 run cannot reach four by construction, so reporting
    `all_four = 0` would read as a total failure of the deliverable chain.
    """
    records = [
        _four_piece_record(tmp_path, tolerance={"skipped": "cli_request"}),
        _four_piece_record(tmp_path, tolerance={"skipped": "cli_request"}),
    ]
    result = trial._deliverable_completeness(records)
    assert result["status"] == "not_assessable"
    assert result["all_four"] is None
    assert "tolerance skipped by request on 2/2" in result["reason"]
    # The other three pieces are still counted -- the run is not uninformative.
    assert result["per_piece"]["prescription_zmx"] == 2
    assert result["per_piece"]["relative_cost"] == 2
    assert result["per_piece"]["tolerance_yield"] == 0


def test_a_full_run_reports_a_measured_all_four_count(tmp_path) -> None:
    """Negative control: with no request-skip, the count is a real measurement."""
    good = _four_piece_record(tmp_path)
    missing_cost = _four_piece_record(tmp_path, relative_cost_index={"ratio": None})
    result = trial._deliverable_completeness([good, missing_cost])
    assert result["status"] == "measured"
    assert result["all_four"] == 1
    assert result["per_piece"]["relative_cost"] == 1


def test_the_summary_carries_the_deliverable_block(tmp_path) -> None:
    summary = trial.summarise([_four_piece_record(tmp_path)])
    assert set(summary["deliverables"]) == {"trials", "per_piece", "all_four", "status", "reason"}
    assert "四件套" in trial.render(summary)
