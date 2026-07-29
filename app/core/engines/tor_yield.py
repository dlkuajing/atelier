"""Explicit, default-off policy for deriving yield from TOR Monte-Carlo rows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from app.core.engines.codev_tolerance import TorParseResult


@dataclass(frozen=True)
class TorYieldPolicy:
    metric: str
    threshold: float
    direction: Literal["min", "max"]
    semantics_ratified: bool
    semantics_evidence: str
    max_saturation_fraction: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.threshold):
            raise ValueError("threshold must be finite")
        if self.semantics_ratified and not self.semantics_evidence.strip():
            raise ValueError("ratified policy requires semantics_evidence")
        if self.semantics_ratified and self.max_saturation_fraction is None:
            raise ValueError("ratified policy requires max_saturation_fraction")
        if self.max_saturation_fraction is not None and not 0 <= self.max_saturation_fraction <= 1:
            raise ValueError("max_saturation_fraction must be in [0, 1]")


@dataclass(frozen=True)
class TorYieldResult:
    status: Literal["unavailable", "measured"]
    yield_fraction: float | None
    per_field_yield: dict[str, float]
    trials: int
    saturation_fraction: float | None
    provenance: str
    reason: str


UNRATIFIED_TOR_YIELD_POLICY = TorYieldPolicy(
    metric="unratified", threshold=0.0, direction="min", semantics_ratified=False,
    semantics_evidence="",
)


#: The reading each metric direction would produce if the design were *perfect*.
#:
#: ``direction="max"`` means the threshold is an upper bound, so lower is better
#: and the metric is an error (RMS wavefront, spot size): perfection is 0.0.
#: ``direction="min"`` means the threshold is a lower bound, so higher is better
#: and the metric is bounded at unity (MTF, Strehl): perfection is 1.0.
_IDEAL_READING: dict[str, float] = {"max": 0.0, "min": 1.0}


def mc_saturation_fraction(result: TorParseResult) -> float | None:
    """Return the policy-independent fraction of MC values sitting at 0 or 1.

    Policy-independent because it cannot know which of the two bounds means
    "perfect" without the metric direction. Use :func:`ideal_reading_count` for
    the direction-aware judgement; this stays as a reportable diagnostic.
    """
    rows = result.monte_carlo_rows
    if not rows:
        return None
    return sum(row.value in {0.0, 1.0} for row in rows) / len(rows)


def ideal_reading_count(result: TorParseResult, direction: str) -> int:
    """Count MC readings sitting exactly on the metric's perfect value.

    A *perturbed* system cannot be perfect. A tolerance sample reading exactly
    0.0 waves RMS, or exactly 1.0 MTF, is a failed evaluation that the engine
    reported as the best possible outcome -- this project's recurring trap,
    where the degenerate value is indistinguishable from an excellent reading.

    Real-machine evidence (US-12124006-B2-e2, 2026-07-29): the zeros appear
    **per field, not per sample**. One sample read f1=1.4161 (a plausible
    degraded value) alongside f2=0.0; another read f1=0.0 alongside f2=0.8581.
    A single field failing while its twin reads sensibly rules out "the whole
    trace failed" and leaves only "this reading is not a measurement".
    """
    ideal = _IDEAL_READING.get(direction)
    if ideal is None:
        return 0
    return sum(row.value == ideal for row in result.monte_carlo_rows)


def compute_mc_yield(result: TorParseResult, policy: TorYieldPolicy) -> TorYieldResult:
    provenance = f"TOR MC; policy evidence: {policy.semantics_evidence or 'none'}"
    saturation = mc_saturation_fraction(result)
    if not policy.semantics_ratified:
        return TorYieldResult("unavailable", None, {}, 0, saturation, provenance, "TOR yield semantics are not ratified")
    rows = result.monte_carlo_rows
    if not rows or result.declared_trials is None:
        return TorYieldResult("unavailable", None, {}, 0, None, provenance, "TOR MC rows are missing")
    if any(row.criterion.casefold() != policy.metric.casefold() for row in rows):
        return TorYieldResult("unavailable", None, {}, 0, None, provenance, "TOR MC criterion does not match policy metric")
    samples: dict[int, dict[tuple[int, int], float]] = {}
    fields: set[tuple[int, int]] = set()
    for row in rows:
        key = (row.zoom, row.field)
        if key in samples.setdefault(row.sample, {}):
            return TorYieldResult("unavailable", None, {}, 0, None, provenance, "duplicate TOR MC sample field")
        samples[row.sample][key] = row.value
        fields.add(key)
    if len(samples) != result.declared_trials or any(set(values) != fields for values in samples.values()):
        return TorYieldResult("unavailable", None, {}, 0, None, provenance, "TOR MC sample/field coverage is malformed")
    # Fail closed on impossible readings *before* scoring, and unconditionally --
    # deliberately not behind max_saturation_fraction. That knob tolerates a
    # fraction of bound-sitting samples, which is defensible for genuine MTF
    # saturation but never for a reading that cannot physically occur. The
    # contamination is not even direction-neutral: under direction="max" a fake
    # 0.0 passes every threshold and *inflates* the yield. One impossible
    # reading also means the evaluation chain emitted a non-measurement, so the
    # remaining samples have no claim to being trustworthy either.
    impossible = ideal_reading_count(result, policy.direction)
    if impossible:
        return TorYieldResult(
            "unavailable", None, {}, 0, saturation, provenance,
            f"{impossible} TOR MC reading(s) sit exactly on the metric's ideal value "
            f"({_IDEAL_READING[policy.direction]:g}); a perturbed system cannot be perfect",
        )

    def passes(value: float) -> bool:
        return value >= policy.threshold if policy.direction == "min" else value <= policy.threshold
    per_field = {f"z{z}:f{f}": sum(passes(s[(z, f)]) for s in samples.values()) / len(samples) for z, f in sorted(fields)}
    overall = sum(all(passes(value) for value in sample.values()) for sample in samples.values()) / len(samples)
    assert policy.max_saturation_fraction is not None
    if saturation is not None and saturation > policy.max_saturation_fraction:
        return TorYieldResult(
            "unavailable", None, {}, 0, saturation, provenance,
            f"TOR MC saturation_fraction {saturation:.6g} exceeds policy maximum {policy.max_saturation_fraction:.6g}",
        )
    return TorYieldResult("measured", overall, per_field, len(samples), saturation, provenance, "computed from complete TOR MC rows")
