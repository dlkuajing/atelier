"""C1 多产编排模块（Phase 10 探路阶第一里程碑）。

权威依据：
`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`

本铲（C1-b）落地骨架：`candidate.py`（数据模型 + 诚实不变量）+
`generators.py`（`CandidateGenerator` 抽象基类 + Mode1/Mode3）。
`scorecard.py` / `orchestrator.py` / `app/core/relative_illumination.py` /
`scripts/c1_orchestrate.py` 留给后续铲（C1-c 及之后）。
"""

from __future__ import annotations

from app.core.orchestration.candidate import (
    CONVERGED_FIELDS,
    NO_TARGET_CONVERGED_BANNER,
    CandidateSet,
    CandidateSetSummary,
    GeneratedCandidate,
    GenerationMode,
    ImageQualityMetrics,
    ManufacturabilityProxy,
    MetricValue,
    OpticalExtras,
    RankResult,
    ScorecardRow,
    ScoredCandidate,
    TargetDeviation,
    TargetSpec,
)
from app.core.orchestration.generators import (
    CandidateGenerator,
    RetrievalGenerator,
    TargetConvergedGenerator,
)

__all__ = [
    "CONVERGED_FIELDS",
    "NO_TARGET_CONVERGED_BANNER",
    "CandidateGenerator",
    "CandidateSet",
    "CandidateSetSummary",
    "GeneratedCandidate",
    "GenerationMode",
    "ImageQualityMetrics",
    "ManufacturabilityProxy",
    "MetricValue",
    "OpticalExtras",
    "RankResult",
    "RetrievalGenerator",
    "ScorecardRow",
    "ScoredCandidate",
    "TargetConvergedGenerator",
    "TargetDeviation",
    "TargetSpec",
]
