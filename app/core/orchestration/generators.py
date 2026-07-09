"""C1 候选生成器（Phase 10 探路阶 · C1-b 骨架）。

权威依据：`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`
§6（Generator 契约）。本铲实现 §6.1 抽象基类 + §6.2 `RetrievalGenerator`
（Mode1）+ §6.4 `TargetConvergedGenerator`（Mode3 空插槽）。Mode2
（`SeedRefineGenerator`）按 §6.3 决定第一里程碑不实现、不预留枚举。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, final

from app.core.case_library import cases_for_scenario, rank_seeds
from app.core.optical_sample import OpticalSampleData
from app.core.orchestration.candidate import (
    GeneratedCandidate,
    GenerationMode,
    OpticalExtras,
    TargetSpec,
)

# Deferred import (inside `_generate`, not module top-level): `relative_illumination`
# imports `app.core.orchestration.candidate.MetricValue`, which forces loading this
# package's `__init__.py` — which imports `generators` (this module) — a genuine
# import cycle if done eagerly at module scope. Lazy import breaks it (both modules
# are fully initialized by the time `_generate` actually runs).

# ---------------------------------------------------------------------------
# 6.1 CandidateGenerator 抽象基类
# ---------------------------------------------------------------------------


class CandidateGenerator(ABC):
    """Mode 生成器抽象基类（§6.1）。

    `generate` 是 `@final` 模板方法：调用子类 `_generate` 拿到候选列表后，
    逐颗校验 `mode == cls.mode`，不一致直接 `raise`（诚实不变量 1，§5.5）。
    子类不得覆盖 `generate`——`__init_subclass__` 在子类 `__dict__` 出现
    `generate` 时运行时 `raise TypeError`（Python 无真 final，`@final`
    只是静态检查提示，必须加运行时防线，codex 轮1+2 修正）。
    """

    mode: ClassVar[GenerationMode]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "generate" in cls.__dict__:
            raise TypeError(f"{cls.__name__} 不得覆盖 final 方法 generate；请实现 _generate")

    @abstractmethod
    def _generate(
        self, spec: TargetSpec, target: TargetSpec, *, n: int
    ) -> list[GeneratedCandidate]:  # 子类只实现这个
        ...

    @final  # 静态检查器拦覆盖
    def generate(
        self, spec: TargetSpec, target: TargetSpec, *, n: int
    ) -> list[GeneratedCandidate]:
        candidates = self._generate(spec, target, n=n)
        for c in candidates:
            if c.mode is not type(self).mode:  # 显式 raise，-O 下不消失
                raise ValueError(
                    f"{type(self).__name__} 产出 mode={c.mode} != 声明 {type(self).mode}"
                )
        return candidates


# ---------------------------------------------------------------------------
# 6.2 RetrievalGenerator（Mode1，第一里程碑主力）
# ---------------------------------------------------------------------------


class RetrievalGenerator(CandidateGenerator):
    """Mode1：检索现建案例库最近邻 seed，零优化（§6.2）。

    复用 `case_library.rank_seeds`（唯一真相源，避免双份候选逻辑
    drift）——不重写排序/距离/role 选择本身。角色语义沿用 `match_case`：
    best_match / cost_variant / thin_variant / performance_variant /
    nearby_alternative_N。

    - `n <= 4`：直接取 `rank_seeds(...).selected_candidates[:n]`——与
      `match_case` 的 `candidate_comparison` 同源同序，保证"重构不改行为"
      （§6.2 测试断言）。
    - `n > 4`：在 top-4 之后，按 `ranked_cases`（全池、纯距离序）继续补
      未被选中的 case，角色标 `nearby_alternative_N`，编号从 top-4 已用到
      的最大编号续接——镜像 `rank_seeds` 内部对 `selected_candidates` 的
      消歧逻辑，扩展到任意 n，不重写排序/距离/role 选择本身（避免"复制
      排序=drift"与"抓 4 副产品=无法 N>4"的两难，§6.2）。

    只吃 `spec` 做检索排序查询（`target` 参数按 §6.1 抽象契约接收但不使
    用——Mode1 没有"朝 target 收敛"这回事，`target` 是下游 scorecard 的
    打分基准，不是 Mode1 的生成输入）。`optical_extras.ri_by_field`
    （C1-c）用重建的 optic 光追填（`relative_illumination.py`），逐候选
    fail closed——单颗 RI 算不出不拖垮整批检索。无 CODE V 依赖（检索 +
    Optiland）。

    `spec.efl_mm` / `spec.fov_deg` 是本 generator 的必填检索维——虽然
    `TargetSpec.efl_mm`/`fov_deg` 在类型层是 `float | None`（§7-E scorecard
    打分允许 target=None=unconstrained），但 `rank_seeds` 的检索排序查询
    没有"不检索这一维"的语义。二者为 `None` 时 `_generate` 直接
    `raise ValueError`（诚实 fail-fast，不静默降级成某个猜测默认值）。
    """

    mode: ClassVar[GenerationMode] = GenerationMode.RETRIEVED

    def _generate(
        self, spec: TargetSpec, target: TargetSpec, *, n: int
    ) -> list[GeneratedCandidate]:
        from app.core.relative_illumination import compute_relative_illumination

        if n <= 0:
            raise ValueError(f"n must be positive, got {n}")
        if spec.efl_mm is None or spec.fov_deg is None:
            raise ValueError(
                "RetrievalGenerator (Mode1) 检索需要 efl_mm/fov_deg（rank_seeds 检索排序"
                "查询必填维）；target=None 的 unconstrained 语义只在 scorecard 打分层"
                "可达（§7-E TargetSpec docstring），不下沉进 Mode1 检索契约"
            )

        cases = cases_for_scenario(spec.scenario)
        if not cases:
            return []

        seed_ranking = rank_seeds(
            cases,
            efl_mm=spec.efl_mm,
            fov_deg=spec.fov_deg,
            fnum=spec.fnum,
            image_height_mm=spec.image_height_mm,
            n_elements=spec.n_elements,
            max_total_track_mm=spec.max_total_track_mm,
            max_weight_g=spec.max_weight_g,
            manufacturing_tier=spec.manufacturing_tier,
            priority=spec.priority,
        )

        picked: list[tuple[OpticalSampleData, str]] = list(seed_ranking.selected_candidates[:n])

        if n > len(picked):
            used_ids = {c.metadata.case_id for c, _ in picked if c.metadata is not None}
            nearby_index = sum(
                1 for _, role in picked if role.startswith("nearby_alternative_")
            )
            for case in seed_ranking.ranked_cases:
                if len(picked) >= n:
                    break
                if case.metadata is None or case.metadata.case_id in used_ids:
                    continue
                nearby_index += 1
                picked.append((case, f"nearby_alternative_{nearby_index}"))
                used_ids.add(case.metadata.case_id)

        candidates: list[GeneratedCandidate] = []
        for case, role in picked:
            assert case.metadata is not None
            case_id = case.metadata.case_id
            candidates.append(
                GeneratedCandidate(
                    candidate_id=f"{case_id}::{role}",
                    mode=GenerationMode.RETRIEVED,
                    source_case_id=case_id,
                    payload=case,
                    optical_extras=OpticalExtras(ri_by_field=compute_relative_illumination(case)),
                    generation_notes=[
                        "检索最近邻 seed，未朝 target 优化",
                        f"role={role}",
                    ],
                )
            )
        return candidates


# ---------------------------------------------------------------------------
# 6.4 TargetConvergedGenerator（Mode3，空插槽 = ③ 接口锚）
# ---------------------------------------------------------------------------


class TargetConvergedGenerator(CandidateGenerator):
    """Mode3（③落地后真朝客户 target 收敛），本铲空插槽（§6.4）。

    第一里程碑：`_generate` 恒返回 `[]`（orchestrator 跳过 → 触发
    `honesty_banner`）。③ 依赖 CODE V（硬依赖），未接时跳过——不破坏无
    CODE V 降级（§8）。

    docstring 写死 ③ 接入契约（= §10 六接缝，作主公 ③ session 的接口
    锚）。Mode3 优化维 = `{EFL, F#, IMH, FOV}`（下列 1-3 接缝对应；
    **TTL 不在接缝**——per-field converged 对 TTL 恒 false，见
    `candidate.py::CONVERGED_FIELDS`）。

    六接缝（§10，file:line）：
    1. EFL 解锁朝 target：`codev_optimize.py:230`
       `EFL = ^baseline_efl_y_mm` → `EFL = {target_efl_mm}`
    2. 玻璃可变：`codev_optimize.py:257` `glass-not-varied` → varied；
       AUT 块加 `CHG GL`
    3. merit 加客户操作数：`codev_optimize.py:200-236` 加 F#/IMH/FOV
       操作数（现仅横向色差 + RMS 点列）
    4. `applied_to_payload` 真置 `True`：`local_optimizer.py`
       （~9 处硬编码 False）
    5. verification checklist → 自动 apply：`case_library.py:7080` +
       `:7139`（现 "not applied to delivered payload"）
    6. payload delivery 落地：`case_library.py:14053`
       `delivered_candidate_id` / `:14054` `delivered_payload` 状态机

    **现状警示（2026-07-09 attended spike 结论，见 project memory
    project-optimize-spike-setup-not-fundamental）**：`codev_optimize.py`
    的 `run_codev_target_standard` 已备接缝 1（EFL 解锁）、接缝 2（玻璃
    可变）、接缝 3a（FNO 锁 native F#），但 F#/IMH/FOV 尚未按客户 target
    验证达标。**真接入 Mode3 时，`CONVERGED_FIELDS[TARGET_CONVERGED]`
    必须按实际能力缩窄为 `frozenset({"efl"})`**——F#/IMH/FOV 现状不达
    target，虚标为已收敛 = 撒谎（违反诚实不变量）。
    """

    mode: ClassVar[GenerationMode] = GenerationMode.TARGET_CONVERGED

    def _generate(
        self, spec: TargetSpec, target: TargetSpec, *, n: int
    ) -> list[GeneratedCandidate]:
        return []
