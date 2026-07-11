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


def mc_saturation_fraction(result: TorParseResult) -> float | None:
    """Return the policy-independent fraction of MC values saturated at 0 or 1."""
    rows = result.monte_carlo_rows
    if not rows:
        return None
    return sum(row.value in {0.0, 1.0} for row in rows) / len(rows)


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
