"""C1 多产编排模块（Phase 10 探路阶第一里程碑，M1 收口 · C1-d）。

权威依据：
`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`

模块布局（§4）：`candidate.py`（数据模型 + 诚实不变量，C1-b）+
`generators.py`（`CandidateGenerator` 抽象基类 + Mode1/Mode3，C1-b）+
`scorecard.py`（纯函数 `score_candidate`，C1-c）+ `orchestrator.py`
（编排入口 `orchestrate`，C1-d）。RI 补算见 `app/core/relative_illumination.py`
（C1-c）；离线 batch 报告见 `scripts/c1_orchestrate.py`（C1-d）。M1 至此收口。
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
from app.core.orchestration.orchestrator import orchestrate
from app.core.orchestration.scorecard import score_candidate

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
    "orchestrate",
    "score_candidate",
]
