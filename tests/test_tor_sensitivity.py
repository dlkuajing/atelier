"""Offline tests for threshold-free tolerance sensitivity.

Every fixture is a real CODE V 11.5 export kept from a P2 trial, so the numbers
pinned here are machine readings rather than hand-built shapes.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from app.core.engines.codev_tolerance import (
    TorMonteCarloRow,
    TorParseResult,
    TorParseStatus,
    TorPerformanceRow,
    TorProvenance,
    parse_codev_tor_exports,
)
from app.core.engines.tor_sensitivity import (
    DEFAULT_NOMINAL_MULTIPLES,
    PROBABILITY_LEVELS,
    relative_yield_curve,
    tolerance_sensitivity,
    yield_is_informative,
)

FIXTURES = Path(__file__).parent / "data" / "codev_tor"


def _at(curve, multiple: float) -> float:
    """Yield at one point of the relative curve."""
    return {point.nominal_multiple: point.yield_fraction for point in curve.points}[multiple]


def _e11(side: str) -> TorParseResult:
    """The only P2 trial with both sides toleranced -- and both read yield 0.0."""
    return parse_codev_tor_exports(
        FIXTURES / f"real_sample_per_p2gated_e11_{side}_rms_ntr20.txt",
        FIXTURES / f"real_sample_mc_p2gated_e11_{side}_rms_ntr20.txt",
    )


def test_real_candidate_degradation_is_read_off_the_per_export() -> None:
    sensitivity = tolerance_sensitivity(_e11("candidate"), "max")

    assert sensitivity.status == "measured"
    assert sensitivity.criterion == "RMS"
    assert sensitivity.probability_levels == PROBABILITY_LEVELS
    assert [(row.zoom, row.field) for row in sensitivity.fields] == [(1, 1), (1, 2)]
    assert sensitivity.fields[0].nominal == pytest.approx(0.348154)
    assert sensitivity.fields[0].degradation == pytest.approx(
        (0.0104817, 0.0637251, 0.110833, 0.153537)
    )
    # A build is as fragile as its most sensitive field, so the whole-lens
    # reading is the max over fields -- here field 2 dominates at every level.
    assert sensitivity.worst_degradation == pytest.approx(
        (0.361122, 0.577996, 0.750293, 0.897701)
    )
    assert sensitivity.worst_nominal == pytest.approx(0.348154)


def test_degradation_separates_a_bad_design_from_a_fragile_one() -> None:
    """The finding this module exists for.

    Both sides of this trial read ``yield = 0.0`` against the 0.25-wave rail, so
    the shipped metric said the two lenses were indistinguishable. They are not:
    the control degrades 5x less at the 97.7% level despite a far worse nominal.
    """
    candidate = tolerance_sensitivity(_e11("candidate"), "max")
    control = tolerance_sensitivity(_e11("control"), "max")

    assert control.worst_nominal > candidate.worst_nominal  # control images worse
    assert control.worst_degradation[2] < candidate.worst_degradation[2]  # yet is sturdier
    assert candidate.worst_degradation[2] / control.worst_degradation[2] == pytest.approx(
        5.026, rel=1e-3
    )


def test_absolute_threshold_is_refused_when_the_nominal_already_fails() -> None:
    """Neither e11 side has headroom at 0.25 waves, so neither yield means anything."""
    for side in ("candidate", "control"):
        sensitivity = tolerance_sensitivity(_e11(side), "max")
        assert yield_is_informative(sensitivity, 0.25, "max") is False
    # A threshold with headroom over the same lens is informative again -- the
    # guard keys off the nominal, not off the lens being a candidate.
    control = tolerance_sensitivity(_e11("control"), "max")
    assert yield_is_informative(control, 2.5, "max") is True
    assert yield_is_informative(control, control.worst_nominal, "max") is False


def test_informativeness_is_direction_aware() -> None:
    """For MTF the threshold is a floor, so headroom means nominal *above* it."""
    mtf = TorParseResult(
        TorParseStatus.UNAVAILABLE, TorProvenance.UNAVAILABLE, "fixture",
        performance_rows=(
            TorPerformanceRow(1, 1, 100.0, 90.0, "MTF", 0.60, (0.55, 0.5, 0.45, 0.4, -0.05, -0.1, -0.15, -0.2)),
        ),
    )
    sensitivity = tolerance_sensitivity(mtf, "min")
    # CODE V's raw Change column is negative for MTF (a real run, sns-verify/mtf,
    # reads -6.7220 at the 97.7% level); positive must always mean worse, or a
    # cross-criterion comparison silently inverts.
    assert sensitivity.fields[0].degradation == pytest.approx((0.05, 0.1, 0.15, 0.2))
    assert yield_is_informative(sensitivity, 0.3, "min") is True
    assert yield_is_informative(sensitivity, 0.8, "min") is False


def test_unmeasurable_sensitivity_has_no_informativeness_verdict() -> None:
    empty = TorParseResult(TorParseStatus.UNAVAILABLE, TorProvenance.UNAVAILABLE, "fixture")
    sensitivity = tolerance_sensitivity(empty, "max")
    assert sensitivity.status == "unavailable"
    assert yield_is_informative(sensitivity, 0.25, "max") is None
    assert yield_is_informative(tolerance_sensitivity(_e11("control"), "max"), float("nan"), "max") is None


def test_sensitivity_fails_closed_on_mixed_criteria_and_bad_columns() -> None:
    row = TorPerformanceRow(1, 1, None, None, "RMS", 0.1, tuple(range(8)))
    mixed = TorParseResult(
        TorParseStatus.UNAVAILABLE, TorProvenance.UNAVAILABLE, "fixture",
        performance_rows=(row, replace(row, field=2, criterion="MTF")),
    )
    assert "mixes criteria" in tolerance_sensitivity(mixed, "max").reason

    narrow = TorParseResult(
        TorParseStatus.UNAVAILABLE, TorProvenance.UNAVAILABLE, "fixture",
        performance_rows=(replace(row, probability_columns=(1.0, 2.0)),),
    )
    assert "probability columns" in tolerance_sensitivity(narrow, "max").reason

    infinite = TorParseResult(
        TorParseStatus.UNAVAILABLE, TorProvenance.UNAVAILABLE, "fixture",
        performance_rows=(replace(row, design=float("inf")),),
    )
    assert "not finite" in tolerance_sensitivity(infinite, "max").reason


def test_relative_curve_ranks_the_two_real_sides_the_absolute_yield_tied() -> None:
    candidate, control = _e11("candidate"), _e11("control")
    candidate_curve = relative_yield_curve(
        candidate, tolerance_sensitivity(candidate, "max"), "max"
    )
    control_curve = relative_yield_curve(control, tolerance_sensitivity(control, "max"), "max")

    assert candidate_curve.status == control_curve.status == "measured"
    assert candidate_curve.judged_samples == control_curve.judged_samples == 20
    assert [point.nominal_multiple for point in candidate_curve.points] == list(
        DEFAULT_NOMINAL_MULTIPLES
    )
    # The reading the absolute rail destroyed: within 1.25x of its own nominal the
    # control holds every build, the candidate fewer than a third.
    assert _at(control_curve, 1.25) == 1.0
    assert _at(candidate_curve, 1.25) == pytest.approx(0.3)
    # Monotone non-decreasing: a looser threshold cannot pass fewer builds.
    for curve in (candidate_curve, control_curve):
        fractions = [point.yield_fraction for point in curve.points]
        assert fractions == sorted(fractions)
    assert control_curve.nominal_by_field == {
        "z1:f1": pytest.approx(1.00107),
        "z1:f2": pytest.approx(1.9405),
    }


def _synthetic(values: dict[int, dict[int, float]], nominal: float = 1.0) -> TorParseResult:
    rows = tuple(
        TorMonteCarloRow(sample=s, zoom=1, field=f, criterion="RMS", value=v)
        for s, fields in values.items()
        for f, v in fields.items()
    )
    fields = sorted({f for entry in values.values() for f in entry})
    return TorParseResult(
        TorParseStatus.UNAVAILABLE, TorProvenance.UNAVAILABLE, "fixture",
        declared_trials=len(values),
        performance_rows=tuple(
            TorPerformanceRow(1, f, None, None, "RMS", nominal, (0,) * 8) for f in fields
        ),
        monte_carlo_rows=rows,
    )


def test_relative_curve_excludes_and_discloses_out_of_model_samples() -> None:
    """A perturbed build reading exactly 0.0 waves is a clamp, not a measurement."""
    parsed = _synthetic({1: {1: 1.1}, 2: {1: 0.0}, 3: {1: 1.2}, 4: {1: 4.0}})
    curve = relative_yield_curve(parsed, tolerance_sensitivity(parsed, "max"), "max")

    assert curve.judged_samples == 3
    assert curve.out_of_model_samples == 1
    assert "3/4 samples" in curve.reason
    # 1.1 and 1.2 pass at 1.25x nominal; 4.0 does not. The excluded 0.0 would
    # have passed every threshold and inflated the curve.
    assert _at(curve, 1.25) == pytest.approx(2 / 3)


def test_relative_curve_requires_every_field_to_pass() -> None:
    parsed = _synthetic({1: {1: 1.1, 2: 4.0}, 2: {1: 1.1, 2: 1.1}})
    curve = relative_yield_curve(parsed, tolerance_sensitivity(parsed, "max"), "max")
    assert _at(curve, 1.25) == 0.5


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda r: replace(r, monte_carlo_rows=()), "MC rows are missing"),
        (lambda r: replace(r, declared_trials=99), "coverage is malformed"),
        (
            lambda r: replace(r, monte_carlo_rows=r.monte_carlo_rows + (r.monte_carlo_rows[0],)),
            "coverage is malformed",
        ),
        (
            lambda r: replace(
                r,
                performance_rows=(
                    TorPerformanceRow(1, 7, None, None, "RMS", 1.0, (0,) * 8),
                ),
            ),
            "disagree about which fields exist",
        ),
        (
            lambda r: replace(
                r,
                performance_rows=(
                    TorPerformanceRow(1, 1, None, None, "RMS", 0.0, (0,) * 8),
                ),
            ),
            "cannot anchor a relative threshold",
        ),
    ],
)
def test_relative_curve_fails_closed(mutate, reason: str) -> None:
    parsed = mutate(_synthetic({1: {1: 1.1}, 2: {1: 1.2}}))
    curve = relative_yield_curve(parsed, tolerance_sensitivity(parsed, "max"), "max")
    assert curve.status == "unavailable"
    assert reason in curve.reason


def test_relative_curve_refuses_bad_multiples_and_a_dead_sample_set() -> None:
    parsed = _synthetic({1: {1: 1.1}, 2: {1: 1.2}})
    sensitivity = tolerance_sensitivity(parsed, "max")
    for bad in ((0.0,), (-1.0,), (float("inf"),)):
        assert "finite and positive" in relative_yield_curve(parsed, sensitivity, "max", bad).reason

    dead = _synthetic({1: {1: 0.0}, 2: {1: 0.0}})
    curve = relative_yield_curve(dead, tolerance_sensitivity(dead, "max"), "max")
    assert curve.status == "unavailable"
    assert "every TOR MC sample fell outside" in curve.reason
    assert curve.out_of_model_samples == 2


def test_relative_curve_needs_a_sensitivity() -> None:
    empty = TorParseResult(TorParseStatus.UNAVAILABLE, TorProvenance.UNAVAILABLE, "fixture")
    curve = relative_yield_curve(empty, tolerance_sensitivity(empty, "max"), "max")
    assert curve.status == "unavailable"
    assert "no sensitivity" in curve.reason
