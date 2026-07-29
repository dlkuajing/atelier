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
