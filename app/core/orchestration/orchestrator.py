"""C1 编排入口（Phase 10 探路阶 · C1-d，M1 收口）。

权威依据：
`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`
§4（数据流）+ §7-E（排序）+ §8（降级能力）+ §9（测试策略）。

`orchestrate(spec, target, *, n, modes)` 是本模块唯一公开入口：对每个注册
mode 跑 generator → 逐颗候选 `score_candidate` 打分 → 组装
`ScoredCandidate` → 按 `RankResult` 排序（ranked 按 score 降序在前，
withheld 沉底）→ 组装派生 `summary` → 返回 `CandidateSet`。

**Registry**：`{RETRIEVED: RetrievalGenerator, TARGET_CONVERGED:
TargetConvergedGenerator}`（§4/§6）。Mode2 不在 registry（§6.3）。

**隔离策略（generator 抛错不炸整批）**：每个 mode 的 "generate + 逐颗打分"
是一个原子单元——`generator.generate()` 本身或其中任一候选的
`score_candidate()` 抛错，都视为该 mode 整体本轮失败：丢弃该 mode 本轮已
产出的候选（不做部分提交，避免"半颗候选"混入排序），把错误如实记入
`summary.notes`（fail-open：不重试、不吞异常堆栈信息、不让一个 mode 的
故障连累其它 mode）。这与 spec §8 的降级契约一致：即便 Mode1
（`RetrievalGenerator`，唯一无 CODE V 依赖的 mode）本身出故障，
`orchestrate` 仍返回一个合法（可能是空候选列表的）`CandidateSet`，而不是
让调用方直接吃一个未处理异常。
"""

from __future__ import annotations

from collections.abc import Iterable

from app.core.orchestration.candidate import (
    CandidateSet,
    CandidateSetSummary,
    GenerationMode,
    ScoredCandidate,
    TargetSpec,
)
from app.core.orchestration.generators import (
    CandidateGenerator,
    RetrievalGenerator,
    TargetConvergedGenerator,
)
from app.core.orchestration.scorecard import score_candidate

# Mode -> generator *class* (not instance): storing classes lets tests
# monkeypatch a class's `_generate` in place (`monkeypatch.setattr(
# RetrievalGenerator, "_generate", ...)`) and have that reflected here without
# a separate injection seam, since dict lookup resolves the class fresh on
# every `orchestrate()` call.
_REGISTRY: dict[GenerationMode, type[CandidateGenerator]] = {
    GenerationMode.RETRIEVED: RetrievalGenerator,
    GenerationMode.TARGET_CONVERGED: TargetConvergedGenerator,
}

DEFAULT_N = 4


def orchestrate(
    spec: TargetSpec,
    target: TargetSpec,
    *,
    n: int = DEFAULT_N,
    modes: Iterable[GenerationMode] | None = None,
) -> CandidateSet:
    """Run every registered (or explicitly selected) generator against
    `spec`, score each produced candidate against `target`, and return a
    fully-ranked `CandidateSet`.

    `spec`/`target` are both `TargetSpec` (the type already unifies the two
    data-flow roles, see `candidate.py` §4 docstring): generators consume
    `spec` for retrieval/generation, `score_candidate` consumes `target` as
    the scoring basis. Callers with a single combined spec pass the same
    instance for both (as every test + `scripts/c1_orchestrate.py` do).

    `modes=None` runs every registered mode. An explicit `modes` iterable
    restricts (and dedupes, order-preserving) which generators run —
    generators outside the selection are never instantiated, so their
    failures (if any) never surface.
    """
    selected_modes = (
        list(_REGISTRY.keys()) if modes is None else list(dict.fromkeys(modes))
    )
    unknown = [m for m in selected_modes if m not in _REGISTRY]
    if unknown:
        raise ValueError(f"orchestrate: unregistered generation mode(s): {unknown}")

    scored: list[ScoredCandidate] = []
    errors: list[str] = []

    for mode in selected_modes:
        generator_cls = _REGISTRY[mode]
        batch: list[ScoredCandidate] = []
        try:
            generator = generator_cls()
            generated_candidates = generator.generate(spec, target, n=n)
            for generated in generated_candidates:
                scorecard = score_candidate(generated, target)
                batch.append(ScoredCandidate(generated=generated, scorecard=scorecard))
        except Exception as exc:  # noqa: BLE001 - isolate this mode's failure (fail-open, recorded below), never sink the whole batch
            errors.append(
                f"mode={mode.value} generator={generator_cls.__name__} 失败，本轮已跳过："
                f"{type(exc).__name__}: {exc}"
            )
        else:
            scored.extend(batch)

    ranked = [sc for sc in scored if sc.scorecard.rank.status == "ranked"]
    withheld = [sc for sc in scored if sc.scorecard.rank.status == "withheld"]
    ranked.sort(key=lambda sc: sc.scorecard.rank.score, reverse=True)  # score is non-None for "ranked" (RankResult invariant)
    ordered = ranked + withheld  # withheld sinks to the bottom, stable within each group

    mode_counts: dict[GenerationMode, int] = {}
    for sc in ordered:
        mode_counts[sc.mode] = mode_counts.get(sc.mode, 0) + 1

    ri_missing_count = sum(
        1
        for sc in ordered
        if sc.scorecard.image_quality.relative_illumination.status == "unavailable"
    )

    notes = list(errors)
    if ordered and ri_missing_count == len(ordered):
        notes.append(
            f"整批候选 RI 全缺（{ri_missing_count}/{len(ordered)}），"
            "像质排序未计入 RI 分量——本批像质排序基线比正常情况更粗略，需资深留意。"
        )

    summary = CandidateSetSummary(
        candidate_count=len(ordered),
        mode_counts=mode_counts,
        ranked_count=len(ranked),
        withheld_count=len(withheld),
        ri_missing_count=ri_missing_count,
        notes=notes,
    )

    return CandidateSet(target=target, candidates=ordered, summary=summary)
