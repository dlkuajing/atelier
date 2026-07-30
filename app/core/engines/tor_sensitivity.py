"""Tolerance sensitivity as a reading, instead of one pass/fail against a rail.

The problem this closes, measured 2026-07-30 on the stored P2 exports: the only
P2 trial with both sides toleranced read ``yield = 0.0`` on **both**, and a
both-zero comparison discriminates nothing. The cause is not that the 0.25-wave
threshold is too tight for a manufacturing spread -- it is that the threshold
sits *below the nominal design*. The PER exports say so directly:

    trial_US-12436366-B2-e11   candidate nominal 0.3482 / 0.2825 waves
                               control   nominal 1.0011 / 1.9405 waves

Once the unperturbed lens already fails, the yield stops answering「how
manufacturable is this design」and starts answering「how often does a random
perturbation accidentally rescue a design that is already out of spec」. That is
not a yield. Across all 45 stored TOR run dirs, 13/118 field rows have a nominal
past the rail, and they are concentrated on the candidate side (2.71/7.13 and
5.05/4.40 waves) while controls sit at 0.03-0.21 -- so with candidates currently
imaging far worse than controls, an absolute-threshold yield reads 0.0 on the
candidate side no matter how the design behaves under perturbation. P3 would
report nothing of its own; it would re-report P2.

The two axes really are independent. ``four-piece-v2/trial_US-12210142-B2-e1``:
candidate nominal 2.71/7.13 waves (hopeless) yet its 97.7% degradation is
0.63/0.33, i.e. on field 2 *less* tolerance-sensitive than its own control
(0.31). A hopeless design can be tolerance-robust, and a good one fragile.

So this module reports the degradation itself. NORTH-STAR forbids picking
threshold numbers a priori, and the honest reading needs none:

* :func:`tolerance_sensitivity` -- CODE V's own PER degradation columns at its
  own cumulative probability levels. Zero invented numbers.
* :func:`relative_yield_curve` -- yield as a function of a *dimensionless*
  multiple of each field's own nominal, so a reader draws their own line.
* :func:`yield_is_informative` -- whether an absolute-threshold yield is
  answering the tolerance question at all for this lens.

Deliberately absent: a percentile against a stored population, the shape
``corpus_quality`` uses for image quality. The 45 stored run dirs are not one
population -- they were run with different tolerance tables (``DLR`` vs ``DLS``,
0.005 vs 0.010) -- and ranking a sensitivity against incomparable runs would
fabricate the denominator rather than name it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Literal

from app.core.engines.codev_tolerance import TorParseResult

Direction = Literal["min", "max"]

#: CODE V 11.5's own PER columns: cumulative probability that the perturbed
#: criterion is no worse than the listed value (1σ/2σ/3σ at the last three).
PROBABILITY_LEVELS: tuple[float, ...] = (50.0, 84.1, 97.7, 99.9)

#: Dimensionless ladder for :func:`relative_yield_curve`. Ratios of each field's
#: own nominal, so no absolute wave count is chosen. Uncalibrated and reported
#: as a curve precisely so that no single entry has to be defended -- 1.0 is the
#: floor ("no worse than the nominal design"), not a recommendation.
DEFAULT_NOMINAL_MULTIPLES: tuple[float, ...] = (1.0, 1.25, 1.5, 2.0, 3.0)


@dataclass(frozen=True)
class FieldSensitivity:
    zoom: int
    field: int
    nominal: float
    #: Absolute criterion at each level of :data:`PROBABILITY_LEVELS`.
    perturbed: tuple[float, ...]
    #: Degradation at each level, oriented so **positive always means worse**.
    #:
    #: CODE V's raw Change column is ``perturbed - nominal``, whose sign means
    #: opposite things for the two criteria: for RMS (lower is better) a
    #: degradation is positive, for MTF (higher is better) it is negative. A real
    #: run confirms both signs occur -- ``sns-verify/mtf`` carries -6.7220 at the
    #: 97.7% level. Comparing raw columns across criteria would silently invert.
    degradation: tuple[float, ...]


@dataclass(frozen=True)
class TorSensitivity:
    status: Literal["unavailable", "measured"]
    reason: str
    direction: Direction | None = None
    criterion: str | None = None
    probability_levels: tuple[float, ...] = ()
    fields: tuple[FieldSensitivity, ...] = ()
    #: Per level, the worst degradation over all fields. A build is as fragile as
    #: its most sensitive field, so the max is the whole-lens reading.
    worst_degradation: tuple[float, ...] = ()
    #: The nominal that is furthest onto the failing side, i.e. the field that
    #: decides whether an absolute threshold can say anything (see
    #: :func:`yield_is_informative`).
    worst_nominal: float | None = None


@dataclass(frozen=True)
class RelativeYieldPoint:
    #: Threshold as a multiple of each field's own nominal.
    nominal_multiple: float
    yield_fraction: float


@dataclass(frozen=True)
class RelativeYieldCurve:
    status: Literal["unavailable", "measured"]
    reason: str
    direction: Direction | None = None
    judged_samples: int = 0
    out_of_model_samples: int = 0
    points: tuple[RelativeYieldPoint, ...] = ()
    nominal_by_field: dict[str, float] = dataclass_field(default_factory=dict)


def _worse(value: float, other: float, direction: Direction) -> bool:
    """Is `value` worse than `other` under `direction`?"""

    return value > other if direction == "max" else value < other


def tolerance_sensitivity(result: TorParseResult, direction: Direction) -> TorSensitivity:
    """Per-field degradation read straight off the PER export.

    Nominal-independent by construction, which is the whole point: it separates
    「this design degrades badly under perturbation」from「this design was already
    bad」. `direction` must be given rather than inferred from the criterion
    name -- the orientation decides the sign of every number returned.
    """

    rows = result.performance_rows
    if not rows:
        return TorSensitivity("unavailable", "TOR PER rows are missing")
    criteria = {row.criterion.strip() for row in rows}
    if len(criteria) != 1:
        return TorSensitivity("unavailable", f"PER mixes criteria: {sorted(criteria)}")
    sign = 1.0 if direction == "max" else -1.0
    fields: list[FieldSensitivity] = []
    for row in rows:
        columns = row.probability_columns
        if len(columns) != 2 * len(PROBABILITY_LEVELS):
            return TorSensitivity(
                "unavailable",
                f"PER carries {len(columns)} probability columns, expected "
                f"{2 * len(PROBABILITY_LEVELS)}",
            )
        perturbed = columns[: len(PROBABILITY_LEVELS)]
        changes = columns[len(PROBABILITY_LEVELS) :]
        if not math.isfinite(row.design):
            return TorSensitivity("unavailable", "PER nominal is not finite")
        fields.append(
            FieldSensitivity(
                zoom=row.zoom,
                field=row.field,
                nominal=row.design,
                perturbed=perturbed,
                degradation=tuple(sign * change for change in changes),
            )
        )
    worst_degradation = tuple(
        max(entry.degradation[index] for entry in fields)
        for index in range(len(PROBABILITY_LEVELS))
    )
    worst_nominal = max(
        (entry.nominal for entry in fields),
        key=lambda value: value if direction == "max" else -value,
    )
    return TorSensitivity(
        "measured",
        f"{len(fields)} field(s) from the TOR PER export",
        direction,
        next(iter(criteria)),
        PROBABILITY_LEVELS,
        tuple(fields),
        worst_degradation,
        worst_nominal,
    )


def yield_is_informative(
    sensitivity: TorSensitivity, threshold: float, direction: Direction
) -> bool | None:
    """Can an absolute-threshold yield answer the tolerance question here?

    ``False`` when the *unperturbed* design already fails the threshold. Such a
    yield is not zero-by-arithmetic -- a perturbation can improve a field, and one
    real sample did (e11 candidate f2 nominal 0.2825, one of 20 samples read
    0.2030, giving a 0.05 per-field "yield") -- but a number produced that way
    measures luck, not manufacturability. It must never be compared side to side.

    ``None`` when there is no sensitivity to judge.
    """

    if sensitivity.status != "measured" or sensitivity.worst_nominal is None:
        return None
    if not math.isfinite(threshold):
        return None
    # Informative iff the threshold is strictly on the *worse* side of the
    # nominal, i.e. the unperturbed design has headroom to lose.
    return _worse(threshold, sensitivity.worst_nominal, direction)


def _group_samples(
    result: TorParseResult,
) -> tuple[dict[int, dict[tuple[int, int], float]], set[tuple[int, int]]] | None:
    """MC rows as sample -> field -> value, or ``None`` if coverage is malformed."""

    samples: dict[int, dict[tuple[int, int], float]] = {}
    fields: set[tuple[int, int]] = set()
    for row in result.monte_carlo_rows:
        key = (row.zoom, row.field)
        if key in samples.setdefault(row.sample, {}):
            return None
        samples[row.sample][key] = row.value
        fields.add(key)
    if not samples or result.declared_trials != len(samples):
        return None
    if any(set(values) != fields for values in samples.values()):
        return None
    return samples, fields


def relative_yield_curve(
    result: TorParseResult,
    sensitivity: TorSensitivity,
    direction: Direction,
    multiples: tuple[float, ...] = DEFAULT_NOMINAL_MULTIPLES,
) -> RelativeYieldCurve:
    """Yield versus a dimensionless multiple of each field's own nominal.

    Each field is judged against its own nominal scaled by the multiple, and a
    sample passes only if every field passes -- a build cannot be called good
    while one of its fields is out. Because every threshold is derived from the
    lens's own nominal, the curve is comparable between a candidate and a control
    that image very differently, which is exactly what the absolute-threshold
    yield cannot do.

    Samples sitting exactly on the metric's ideal value are excluded and
    disclosed: TOR extrapolates a linear OPD model and clamps at the bound, so
    0.0 waves RMS (or 1.0 MTF) on a *perturbed* build is not a measurement. Same
    rule as ``tor_yield``; kept here so a curve can never be built on them.
    """

    if sensitivity.status != "measured":
        return RelativeYieldCurve("unavailable", f"no sensitivity: {sensitivity.reason}")
    if not result.monte_carlo_rows:
        return RelativeYieldCurve("unavailable", "TOR MC rows are missing")
    if any(not math.isfinite(value) or value <= 0.0 for value in multiples):
        return RelativeYieldCurve("unavailable", "nominal multiples must be finite and positive")
    grouped = _group_samples(result)
    if grouped is None:
        return RelativeYieldCurve("unavailable", "TOR MC sample/field coverage is malformed")
    samples, fields = grouped
    nominal = {(entry.zoom, entry.field): entry.nominal for entry in sensitivity.fields}
    if set(nominal) != fields:
        return RelativeYieldCurve(
            "unavailable", "PER and MC exports disagree about which fields exist"
        )
    if any(value == 0.0 for value in nominal.values()):
        return RelativeYieldCurve(
            "unavailable", "a nominal of 0 cannot anchor a relative threshold"
        )
    ideal = 0.0 if direction == "max" else 1.0
    out_of_model = {
        sample for sample, values in samples.items() if any(v == ideal for v in values.values())
    }
    judged = {s: v for s, v in samples.items() if s not in out_of_model}
    if not judged:
        return RelativeYieldCurve(
            "unavailable",
            "every TOR MC sample fell outside the linear model",
            direction,
            0,
            len(out_of_model),
        )
    points = []
    for multiple in multiples:
        passing = sum(
            all(
                not _worse(value, nominal[key] * multiple, direction)
                for key, value in sample.items()
            )
            for sample in judged.values()
        )
        points.append(RelativeYieldPoint(multiple, passing / len(judged)))
    return RelativeYieldCurve(
        "measured",
        f"computed over {len(judged)}/{len(samples)} samples inside TOR's linear model",
        direction,
        len(judged),
        len(out_of_model),
        tuple(points),
        {f"z{z}:f{f}": value for (z, f), value in sorted(nominal.items())},
    )
