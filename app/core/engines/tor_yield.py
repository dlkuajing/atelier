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
    #: Ceiling on the fraction of samples allowed to fall outside TOR's linear
    #: model before the yield is refused outright. Disclosure is not a licence
    #: to report a yield derived from a handful of survivors, so a ratified
    #: policy must state this explicitly -- there is deliberately no default.
    max_out_of_model_fraction: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.threshold):
            raise ValueError("threshold must be finite")
        if self.semantics_ratified and not self.semantics_evidence.strip():
            raise ValueError("ratified policy requires semantics_evidence")
        if self.semantics_ratified and self.max_saturation_fraction is None:
            raise ValueError("ratified policy requires max_saturation_fraction")
        if self.semantics_ratified and self.max_out_of_model_fraction is None:
            raise ValueError("ratified policy requires max_out_of_model_fraction")
        if self.max_out_of_model_fraction is not None and not 0 <= self.max_out_of_model_fraction <= 1:
            raise ValueError("max_out_of_model_fraction must be in [0, 1]")
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
    #: Samples dropped because at least one of their readings sat on the
    #: metric's ideal value -- TOR's linear OPD model extrapolated past the
    #: bound and clamped. Never silently absorbed: ``yield_fraction`` is
    #: computed over ``trials`` (the judged samples), and this pair is what
    #: makes that denominator honest.
    out_of_model_samples: int = 0
    out_of_model_fraction: float = 0.0


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
    # TOR models the change in OPD linearly, and says so: 「appropriate only
    # when the tolerance changes cause a small change in performance」
    # (Tolerancing.pdf, "Limitations of the Linear Model"). At realistic mobile
    # tolerances that extrapolation runs past the metric's bound on some samples
    # and is clamped -- 0.0 waves RMS, or 1.0 MTF. Measured across 26 real runs
    # (2026-07-29), the rate tracks how much headroom a field has: 11.7% at the
    # field with the smallest nominal RMS, 4.4%, then 2.9%. That gradient is the
    # signature; these are not trace failures.
    #
    # Ratified 2026-07-29: report the yield over the samples that *are* inside
    # the model, and disclose the rest. A whole sample is dropped when any one of
    # its fields is out of model -- a build cannot be called passing while one of
    # its fields is unmeasurable. Dropped samples count as neither pass nor fail,
    # which is why the fraction has to travel with the number.
    ideal = _IDEAL_READING.get(policy.direction)
    out_of_model = {
        sample for sample, values in samples.items()
        if ideal is not None and any(value == ideal for value in values.values())
    }
    out_fraction = len(out_of_model) / len(samples)
    if policy.max_out_of_model_fraction is not None and out_fraction > policy.max_out_of_model_fraction:
        return TorYieldResult(
            "unavailable", None, {}, 0, saturation, provenance,
            f"{len(out_of_model)}/{len(samples)} samples fall outside TOR's linear model "
            f"({out_fraction:.6g} > policy maximum {policy.max_out_of_model_fraction:.6g})",
            len(out_of_model), out_fraction,
        )
    judged = {s: v for s, v in samples.items() if s not in out_of_model}
    if not judged:
        return TorYieldResult(
            "unavailable", None, {}, 0, saturation, provenance,
            "every TOR MC sample fell outside the linear model",
            len(out_of_model), out_fraction,
        )

    def passes(value: float) -> bool:
        return value >= policy.threshold if policy.direction == "min" else value <= policy.threshold
    per_field = {f"z{z}:f{f}": sum(passes(s[(z, f)]) for s in judged.values()) / len(judged) for z, f in sorted(fields)}
    overall = sum(all(passes(value) for value in sample.values()) for sample in judged.values()) / len(judged)
    assert policy.max_saturation_fraction is not None
    if saturation is not None and saturation > policy.max_saturation_fraction:
        return TorYieldResult(
            "unavailable", None, {}, 0, saturation, provenance,
            f"TOR MC saturation_fraction {saturation:.6g} exceeds policy maximum {policy.max_saturation_fraction:.6g}",
            len(out_of_model), out_fraction,
        )
    return TorYieldResult(
        "measured", overall, per_field, len(judged), saturation, provenance,
        f"computed over {len(judged)}/{len(samples)} samples inside TOR's linear model",
        len(out_of_model), out_fraction,
    )
