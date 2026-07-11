"""C1 候选生成器（Phase 10 探路阶 · C1-b 骨架）。

权威依据：`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`
§6（Generator 契约）。本铲实现 §6.1 抽象基类 + §6.2 `RetrievalGenerator`
（Mode1）+ §6.4 `TargetConvergedGenerator`（Mode3 空插槽）。Mode2
（`SeedRefineGenerator`）按 §6.3 决定第一里程碑不实现、不预留枚举。
"""

from __future__ import annotations

import math
import shutil
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import ClassVar, final

import structlog

from app.core.case_library import build_sample_from_optic, cases_for_scenario, rank_seeds
from app.core.engines.codev_batch import DEFAULT_CODEV_EXECUTABLE, CodeVBatchError
from app.core.engines.codev_optimize import run_codev_target_standard
from app.core.engines.seed_target_score import SeedTargetScore, score_seed_target_match
from app.core.optical_sample import OpticalSampleData
from app.core.orchestration.candidate import (
    GeneratedCandidate,
    GenerationMode,
    OpticalExtras,
    TargetSpec,
)
from app.core.zmx_ingest import ZMX_AMMO_DIR, load_normalized_zmx

logger = structlog.get_logger(__name__)

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

    def __init__(self, *, artifact_dir: Path | None = None, repeat_runs: int = 1) -> None:
        self.artifact_dir = artifact_dir
        self.repeat_runs = repeat_runs

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
# 6.4 TargetConvergedGenerator（Mode3，③ 真接入 · 2026-07-10）
# ---------------------------------------------------------------------------

#: 真机成本控制（③ 每颗 seed = {asphere,both} × autovig 阶梯，单颗数十秒到
#: 数分钟）：无论调用方请求多大的 `n`，Mode3 每次编排最多真机跑这么多颗
#: seed。不是"产出候选数上限"（每颗 seed 若跑通只产 1 颗候选），是"愿意为
#: 这次编排花多少次 CODE V 批跑"的硬顶。
_TARGET_MAX_SEEDS = 2

#: seed-target 匹配 band 的机器排序权重（数字越小=越优先尝试），镜像
#: `seed_target_score.py` 的分桶语义（lt5 < 5to15 < 15to30 < gt30）。
_BAND_RANK: dict[str, int] = {"lt5": 0, "5to15": 1, "15to30": 2, "gt30": 3}

#: Stage-1（FOV 近邻预筛）候选池宽度（fix/mode3-seed-fov-prefilter，
#: 2026-07-10）。真机实锤：`_rank_seeds_by_target_match` 曾只按 EFL-only 的
#: `score_seed_target_match`（N=24 真机数据边界）排序，选中 FOV 36° 的 seed
#: 去优化 FOV 78° 的 target（violation 53.8%——scorecard 如实暴露但候选本身
#: 注定不良配，见任务报告）。`case_library.rank_seeds` 是路由层唯一真相源
#: 的多维规格距离（FOV 权重 0.46 主导 / IMH 0.30 / EFL 0.20，见其 `weights`
#: dict），stage 1 先用它把场景池收窄到这么多颗规格最近邻 seed，stage 2
#: 才在这个邻域内按 EFL 收敛风险重排序（§ `_rank_seeds_by_target_match`
#: docstring）。K=10 是 `_TARGET_MAX_SEEDS`（2）的 5 倍留白：宽到 stage 2
#: 仍有真实候选可选，窄到不会把远 FOV 的 seed 重新放回候选池。
_FOV_PREFILTER_TOP_K = 10

#: `score_seed_target_match` 的两档"EFL 已经很接近"分桶（P11 甜区覆盖率
#: 漏斗调优，2026-07-11），供 `_fov_bounded_efl_close_extras` 甜区召回补齐
#: 使用——直接复用 `seed_target_score.py` 已有的 N=24 真机标定分桶边界
#: （score<15），不发明新阈值。
_EFL_CLOSE_BANDS_FOR_RECALL: frozenset[str] = frozenset({"lt5", "5to15"})


def _stage2_sort_key(
    case: OpticalSampleData, match: SeedTargetScore, target_fov_deg: float | None
) -> tuple[int, float, float, str]:
    """Stage 2 排序全键（对抗审 MINOR 修复，2026-07-11）。

    主键不变：band 优先（`_BAND_RANK`）、band 内 score 升序——既有 N=24
    真机依据的 EFL 收敛风险排序语义原样保留。新增两级显式 tie-break 终键：
    |FOV 失配|（同 band 同 score 时 FOV 更近者优先，与 stage 1 的 FOV 主导
    距离语义方向一致）、case_id（字典序，最终裁决键）。

    动机：旧实现同 band/同 score 时由 `cases_for_scenario`/索引文件顺序经
    stable sort 隐式裁决——库重排会改变 top-2，即改变 CODE V 真机对象。
    显式全键保证"输入集合相同即输出相同"（置换不变，见
    test_rank_seeds_by_target_match_output_invariant_under_pool_permutation）。

    `target_fov_deg is None`（FOV unconstrained 降级路径）时 FOV 键恒
    0.0（无失配可言），tie 落到 case_id 终键。
    """
    assert case.metadata is not None
    fov_mismatch = (
        abs(case.metadata.fov_deg - target_fov_deg) if target_fov_deg is not None else 0.0
    )
    return (_BAND_RANK[match.band], match.score, fov_mismatch, case.metadata.case_id)


def _score_cases_for_target(
    cases: Sequence[OpticalSampleData], target_efl_mm: float
) -> list[tuple[OpticalSampleData, SeedTargetScore]]:
    """对一组 case 逐颗跑 `score_seed_target_match`，非法 EFL（非有限/非正/
    打分 raise）静默跳过（与 `_rank_seeds_by_target_match` 既有过滤语义
    一致）。不排序——调用方自选排序键。"""
    scored: list[tuple[OpticalSampleData, SeedTargetScore]] = []
    for case in cases:
        if case.metadata is None:
            continue
        seed_efl_mm = case.paraxial.effective_focal_length_mm
        if not math.isfinite(seed_efl_mm) or seed_efl_mm <= 0:
            continue
        try:
            match = score_seed_target_match(seed_efl_mm, target_efl_mm)
        except ValueError:
            continue
        scored.append((case, match))
    return scored


#: post_aut 质量三键的 0.0 是"追迹全失败"哨兵，不是真实测量值：CODE V 宏累加器
#: （`codev_optimize._metric_function_block` 的 `FCT @rmssum` 等）以 `^max == 0`
#: 起始，只在对应查询返回 `^err = 0`（追迹成功）的场次才更新；全部场次追迹失败
#: 时初值 0 被原样写出（哨兵结案详见 `codev_optimize._standard_config_rms`
#: docstring）。物理上 RMS 点列/波前精确为 0 不存在（衍射极限设下界 >0），把它
#: 渲染成 "0" 会被资深读成"完美结果"——诚实红线，必须归 `None`（下游 web
#: `main._fmt_codev_value` 与离线报告 `scripts/c1_orchestrate.py::_fmt_codev_value`
#: 对 `None` 均渲染 N/A）。**逐键独立**：同一快照里 distortion=43.86 与 rms=0.0
#: （哨兵）可并存，只有恰好 0.0 的键被映射。不含 post_aut.efl_y_mm / fno /
#: maximh_mm / efl_target_deviation_pct / autovig.edge_used——那些键的 0.0 是
#: 合法值（edge_used=0 表示无渐晕裁切、EFL 偏差可能就是极小）。
_POST_AUT_ZERO_SENTINEL_KEYS = frozenset(
    {
        "post_aut.max_rms_spot_diameter_um",
        "post_aut.max_rms_wavefront_error_waves",
        "post_aut.max_distortion_pct",
    }
)


def _codev_post_aut_snapshot(config: Mapping[str, object]) -> dict[str, float | str | None]:
    """从 `run_codev_target_standard` 某配置的原始 dict 里摘出 CODE V 真机
    快照数字（post_aut 三快照 + autovig/AUT 误差诊断），供
    `OpticalExtras.codev_post_aut` 存放——纯诊断 side-channel，不参与打分
    （`score_candidate` 只读 payload/optical_extras.ri_by_field，不读这里，
    见 `candidate.py::OpticalExtras.codev_post_aut` docstring）。缺失/非数
    一律 `None`，不猜测（fail closed，同 `codev_optimize._standard_config_rms`
    的风格）；质量三键的 0.0 追迹全失败哨兵同样归 `None`
    （`_POST_AUT_ZERO_SENTINEL_KEYS` 注记）。"""

    def _float(key: str) -> float | None:
        raw = config.get(key)
        if raw is None:
            return None
        try:
            value = float(str(raw))
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        if value == 0.0 and key in _POST_AUT_ZERO_SENTINEL_KEYS:
            return None
        return value

    def _text(key: str) -> str | None:
        raw = config.get(key)
        return str(raw) if raw is not None else None

    err_f_ratio: float | None = None
    termination: str | None = None
    aut_error_trace = config.get("aut_error_trace")
    if isinstance(aut_error_trace, Mapping):
        raw_ratio = aut_error_trace.get("err_f_ratio")
        if isinstance(raw_ratio, int | float) and math.isfinite(float(raw_ratio)):
            err_f_ratio = float(raw_ratio)
        raw_termination = aut_error_trace.get("termination")
        termination = str(raw_termination) if raw_termination is not None else None

    return {
        "post_aut.efl_y_mm": _float("post_aut.efl_y_mm"),
        "post_aut.max_rms_spot_diameter_um": _float("post_aut.max_rms_spot_diameter_um"),
        "post_aut.max_rms_wavefront_error_waves": _float(
            "post_aut.max_rms_wavefront_error_waves"
        ),
        "post_aut.max_distortion_pct": _float("post_aut.max_distortion_pct"),
        "post_aut.fno": _float("post_aut.fno"),
        "post_aut.maximh_mm": _float("post_aut.maximh_mm"),
        "efl_target_deviation_pct": _float("efl_target_deviation_pct"),
        "aut_converged": _text("aut_converged"),
        "autovig.edge_used": _float("autovig.edge_used"),
        "err_f_ratio": err_f_ratio,
        "aut_termination": termination,
    }


def _mode3_generation_notes(
    *,
    seed: OpticalSampleData,
    match: SeedTargetScore,
    preferred: str,
    preferred_reason: str,
    config: Mapping[str, object],
    provenance: Mapping[str, object],
    fov_prefiltered: bool,
) -> list[str]:
    """诚实 provenance 注记（离线报告/资深读的第一手线索），非量产判定。

    `fov_prefiltered`：`_rank_seeds_by_target_match` 是否跑了 stage 1
    FOV 近邻预筛（`spec.fov_deg is not None`）。`False` 时 seed 选择退化为
    纯 EFL 收敛风险排序（原行为）——诚实注明，不静默掩盖"这颗候选没做 FOV
    近邻过滤"这件事。
    """
    assert seed.metadata is not None
    glass_model_label = "unknown"
    raw_glass_model = provenance.get("glass_model")
    if isinstance(raw_glass_model, Mapping):
        glass_model_label = str(raw_glass_model.get(preferred, "unknown"))
    edge_used = config.get("autovig.edge_used", "N/A")
    notes = [
        "Mode3：③ target 优化标准入口（codev_optimize.run_codev_target_standard），"
        f"seed={seed.metadata.case_id}",
        f"seed-target 匹配 band={match.band}（score={match.score:.2f}, "
        f"ΔEFL={match.delta_efl_pct:+.1f}%；{match.evidence_note}）",
        f"preferred 配置=\"{preferred}\"（{preferred_reason}）",
        f"玻璃 provenance（preferred=\"{preferred}\"）：{glass_model_label}",
        f"渐晕 edge_used（preferred 配置，autovig 裁瞳量）={edge_used}",
        "CONVERGED_FIELDS[TARGET_CONVERGED] 已缩窄为 {efl}：F# 现状锁 native（非达"
        "target）、IMH/FOV Stage C 场重建未落地——本候选 5 维 target-deviation 中"
        "只有 efl 标 converged=True，其余如实标 False（见 candidate.py "
        "CONVERGED_FIELDS 缩窄注记）",
        "optical_extras.ri_by_field 按优化后 ZMX 显式路径实算（P17-4 接线，"
        "relative_illumination.py 的 zmx_path 参数）——loop3 遗留#4（临时目录致"
        "RI 复算结构性 miss）已闭合；追迹失败时仍 fail-closed 全 unavailable，"
        "不猜值",
        "optical_extras.codev_post_aut 携带 CODE V 侧真机快照数字（裁瞳口径），"
        "与本候选 payload 的 Optiland 满口径口径不可直接横比，见字段 docstring",
    ]
    if not fov_prefiltered:
        notes.append(
            "seed 选择未做 FOV 近邻过滤（target FOV 未约束，spec.fov_deg=None）："
            "本候选仅按 EFL 收敛风险排序选中，未验证与 target FOV 的规格接近度"
            "（fix/mode3-seed-fov-prefilter，2026-07-10）"
        )
    return notes


def _fov_bounded_efl_close_extras(
    primary: Sequence[OpticalSampleData],
    pool: Sequence[OpticalSampleData],
    *,
    target_efl_mm: float,
    target_fov_deg: float,
) -> list[OpticalSampleData]:
    """P11 甜区覆盖率漏斗调优（2026-07-11，对抗审 BLOCKER 修复版）：
    stage 1b 甜区召回补齐。

    实锤（`scripts/sweet_zone_coverage.py` 量化，PR#60）：两段式匹配把场景
    池收窄到 `rank_seeds` 全维距离 top-`_FOV_PREFILTER_TOP_K`（FOV 权重
    0.46 主导）后，wide/tele/uw 三场景分别有 88/300、135/300、51/300 格点
    因为"库内存在 EFL 甜区带内 seed，但它没进 top-K"而 miss（存在性扫描口
    径的 `efl_material_exists_but_not_selected`，三场景 EFL 维真空洞均=0，
    证明这是漏斗宽度问题，不是库缺料）。

    本函数在 stage 1 之后、stage 2 之前，把"EFL 距离已经很近
    （`score_seed_target_match` band ∈ `_EFL_CLOSE_BANDS_FOR_RECALL`，直接
    复用其 N=24 真机标定分桶，不发明新阈值）但被 top-K 挡在外面"的 seed
    纳入候选，**FOV 上限锚定旧路径真机席位**：

        cap = 旧路径（primary-only）按 stage 2 全键排序后真正会送 CODE V
              的前 `_TARGET_MAX_SEEDS` 颗（"旧席位"）的最差 |FOV 失配|

    **安全证明**（对抗审 BLOCKER：第一版 cap 取 primary 全体最差 |FOV
    失配|，可被 top-10 内单颗 FOV 离群点撑大——合成反例 9 颗 78° + 1 颗
    20° → cap=58° → FOV 36° 的 lt5 extra 被纳入且 EFL score 碾压 primary
    = PR#48 盲区回归。现版本锚点消除该路径）：

    1. 旧路径 CODE V 席位 = stage 2 全键排序后 primary 的前
       `_TARGET_MAX_SEEDS` 颗；
    2. 任何 extra 的 |FOV 失配| ≤ cap = 旧席位的最差 |FOV 失配|；
    3. 新路径最终席位 ⊆（旧席位按序前缀）∪（满足 2 的 extras）——extras
       只能把 primary 成员向后挤，primary 成员间的 stage 2 相对序不变
       （同一排序键）；
    4. 故新席位的最差 |FOV 失配| ≤ 旧席位的最差 |FOV 失配|：**结构上不可能
       比旧路径实际送真机的 seed 更差**。这是"不比旧路径最终胜者差"的强
       声明，不是第一版"不比 primary 最差成员差"（可被离群点偷换）的弱
       声明。

    退化边界（对抗审同条指出，接受为 fail-safe 方向）：旧席位全部精确贴合
    target FOV 时 cap→0，召回补齐退化为空——宁可少召回，不可回退 FOV，见
    test_fov_bounded_efl_close_extras_all_tight_seats_give_zero_cap_no_extras。

    量化验证（改后复测数字见 `.planning/loop/mode3-funnel-tuning-report.md`
    与重新生成的 `sweet-zone-coverage-report.md`；报告同时含独立安全指标：
    新旧路径最终 top-1/top-2 席位的 |FOV 失配| 回退分布）。

    Args:
        primary: stage 1（`rank_seeds` top-K）已选中的候选，用于确定旧路径
            席位（cap 锚点）与去重。
        pool: 场景全池（ZMX-backed），补齐候选从这里筛选。
        target_efl_mm / target_fov_deg: 与 `_rank_seeds_by_target_match`
            同源的 target 值。

    Returns:
        `primary` 之外、满足 band+FOV 上限的补齐候选（未排序——调用方与
        `primary` 拼接后交给 stage 2 统一按全键重排，不在本函数内二次
        排序，避免和 stage 2 的排序语义打架）。
    """
    primary_ids = {c.metadata.case_id for c in primary if c.metadata is not None}

    scored_primary = _score_cases_for_target(primary, target_efl_mm)
    scored_primary.sort(key=lambda item: _stage2_sort_key(item[0], item[1], target_fov_deg))
    old_codev_seats = scored_primary[:_TARGET_MAX_SEEDS]
    fov_cap = max(
        (
            abs(case.metadata.fov_deg - target_fov_deg)
            for case, _ in old_codev_seats
            if case.metadata is not None
        ),
        default=0.0,
    )

    extras: list[OpticalSampleData] = []
    for case in pool:
        if case.metadata is None or case.metadata.case_id in primary_ids:
            continue
        native_efl_mm = case.paraxial.effective_focal_length_mm
        if not math.isfinite(native_efl_mm) or native_efl_mm <= 0:
            continue
        try:
            match = score_seed_target_match(native_efl_mm, target_efl_mm)
        except ValueError:
            continue
        if match.band not in _EFL_CLOSE_BANDS_FOR_RECALL:
            continue
        if abs(case.metadata.fov_deg - target_fov_deg) > fov_cap:
            continue
        extras.append(case)
    return extras


class TargetConvergedGenerator(CandidateGenerator):
    """Mode3（③落地后真朝客户 target 收敛），真接入（§6.4，2026-07-10）。

    ③ 依赖 CODE V（硬依赖）：`DEFAULT_CODEV_EXECUTABLE` 不可用时 `_generate`
    返回 `[]`（降级语义保留，不破坏无 CODE V 全链路，§8）。`spec.efl_mm`
    是必填检索/优化锚点：`None` 时同样返回 `[]`（Mode3 无 target EFL 无法
    定义"朝哪收敛"，与 `RetrievalGenerator` 的 fail-fast `raise` 不同——这里
    是"本 mode 对这条需求不适用"的正常降级，不是调用方传参错误）。

    **流程**：
    1. `cases_for_scenario(spec.scenario)` 取场景池，过滤出
       `metadata.source_zmx` 在 `ZMX_AMMO_DIR` 下真实存在的 seed。
    2. `_rank_seeds_by_target_match` 两段式排序（fix/mode3-seed-fov-
       prefilter，2026-07-10，闭合 FOV 盲区——见其 docstring 的真机实锤
       细节）：`spec.fov_deg` 非 None 时先用 `case_library.rank_seeds`
       （多维规格距离，FOV 权重主导）收窄到前 `_FOV_PREFILTER_TOP_K` 颗
       近邻，再用 `seed_target_score.score_seed_target_match`（seed 原生
       EFL ← `payload.paraxial.effective_focal_length_mm` vs `spec.efl_mm`）
       在邻域内按 band 优先、band 内 score 升序重排；`spec.fov_deg is None`
       时退化为纯 EFL 排序（原行为，诚实降级）。取前
       `min(n, _TARGET_MAX_SEEDS)` 颗——真机成本控制（每颗 seed 一次
       `run_codev_target_standard` 批跑，数十秒到数分钟）。
    3. 每颗 seed 跑 `codev_optimize.run_codev_target_standard`
       （`emit_optimized_zmx=True`，标准 {asphere,both} 双配置并跑取优，
       §10 接缝 1/2/3a）。单颗 seed 报 `CodeVBatchError`（tooling-blocked/
       timeout/no_license 等）→ 跳过该 seed（结构化日志留痕），不炸整个
       generator（不炸其余 seed，也不炸 `orchestrate` 的其它 mode）。
    4. `preferred` 配置的 `optimized_zmx_path` 现算 payload：
       `zmx_ingest.load_normalized_zmx` → `case_library.build_sample_from_optic`
       （仓里现有"单 ZMX → OpticalSampleData"管线，`app/api/optical.py` 的
       seed-preflight 端点同款用法）。`nominal_efl_mm=spec.efl_mm`（客户
       target，① EFL 已收敛）；`nominal_fov_deg=seed.metadata.fov_deg`
       （seed 原生 FOV——Stage C 场重建未落地，FOV 未真朝 target 收敛，不
       能虚标 target FOV 当 nominal）；`n_pieces=seed.metadata.n_pieces`
       （AUT 优化不改变元件数）。**已知风险（真机验证，见任务报告）**：
       `even_asphere` 满口径追迹在部分优化后 ZMX 上可能数值异常——整段
       `load_normalized_zmx`+`build_sample_from_optic` 包在 try/except 里，
       任何异常都 fail closed：该颗 seed 的候选**不产出**（跳过，不用假
       数据填充 payload 的必填字段），结构化日志记录原因，继续下一颗
       seed，不炸整个 generator。
    5. CODE V 侧真机数字（post_aut 快照/edge_used/err_f_ratio/AUT 终止措
       辞）无论 Optiland payload 是否算出，都摘进
       `optical_extras.codev_post_aut`（`_codev_post_aut_snapshot`）——这些
       数字来自已经成功落盘的 tsv 读数，与 Optiland 二次追迹是否成功无关；
       `score_candidate` 不消费它（打分口径保持 payload/Optiland 一致
       性），只在离线报告的 provenance 区如实展示（`scripts/c1_orchestrate.py`）。

    **诚实红线**：`CONVERGED_FIELDS[TARGET_CONVERGED]` 已缩窄为
    `frozenset({"efl"})`（`candidate.py`，2026-07-10）——F#/IMH/FOV 现状不
    达 target（F# 只锁 native，IMH/FOV Stage C 未落地），虚标为已收敛 =
    撒谎，违反诚实不变量。TTL 从未在优化维内。

    六接缝原文（§10，作后续 Stage B/C session 的接口锚，未落地部分保留
    file:line）：
    1. EFL 解锁朝 target——已落地：`codev_optimize.py`
       `build_codev_target_sequence` 内 `EFL = {target_efl_mm}`（真机 E1
       验证）。
    2. 玻璃可变——已落地：`extra_dof="both"` 走塑料域 GLA 边界（`codev_
       optimize.py` "玻璃可变域修复"章节，commit 7b504c6）。
    3. merit 加客户操作数——部分落地：3a F# 走 FNO 模式锁 native（真机 E1
       实测）；IMH/FOV 操作数未加（Stage C 场重建，未落地）。
    4. `applied_to_payload` 真置 `True`：`local_optimizer.py`（~9 处硬编码
       False，未落地——本 generator 走独立 payload 现算路径，不经
       `local_optimizer`，该接缝仍待 case_library 侧收口）。
    5. verification checklist → 自动 apply：`case_library.py:7080` +
       `:7139`（现 "not applied to delivered payload"，未落地）。
    6. payload delivery 落地：`case_library.py:14053`
       `delivered_candidate_id` / `:14054` `delivered_payload` 状态机
       （未落地——本 generator 产出的候选走 C1 报告，不经这条 delivery
       状态机）。
    """

    mode: ClassVar[GenerationMode] = GenerationMode.TARGET_CONVERGED

    def _generate(
        self, spec: TargetSpec, target: TargetSpec, *, n: int
    ) -> list[GeneratedCandidate]:
        if spec.efl_mm is None:
            logger.info(
                "mode3_skipped_no_efl_target",
                scenario=spec.scenario.value,
                reason="TargetConvergedGenerator 需要 spec.efl_mm 作为优化锚点",
            )
            return []
        if not DEFAULT_CODEV_EXECUTABLE.is_file():
            logger.info(
                "mode3_skipped_no_codev",
                scenario=spec.scenario.value,
                reason="CODE V 不可用（DEFAULT_CODEV_EXECUTABLE 不存在），降级跳过",
            )
            return []

        scored_seeds = self._rank_seeds_by_target_match(spec)
        if not scored_seeds:
            logger.info(
                "mode3_skipped_no_scoreable_seeds",
                scenario=spec.scenario.value,
                efl_mm=spec.efl_mm,
            )
            return []

        num_seeds = min(n, _TARGET_MAX_SEEDS, len(scored_seeds))
        selected = scored_seeds[:num_seeds]

        candidates: list[GeneratedCandidate] = []
        with tempfile.TemporaryDirectory(prefix="atelier-c1-mode3-") as tmpdir_str:
            tmpdir = Path(tmpdir_str)
            for seed, match in selected:
                assert seed.metadata is not None
                attempts: list[GeneratedCandidate | None] = []
                for run_index in range(1, self.repeat_runs + 1):
                    candidate = self._candidate_for_seed(
                        seed=seed,
                        match=match,
                        spec=spec,
                        work_dir=tmpdir / seed.metadata.case_id / f"run-{run_index}",
                        artifact_dir=self.artifact_dir,
                        run_index=run_index,
                    )
                    attempts.append(candidate)
                successful = [attempt for attempt in attempts if attempt is not None]
                if successful:
                    primary = successful[0]
                    if self.repeat_runs == 1:
                        candidates.append(primary)
                        continue
                    rms_samples: list[float] = []
                    wfe_samples: list[float] = []
                    dropped: list[str] = []
                    primary_config = primary.codev_preferred_config
                    artifact_paths = [
                        attempt.optimized_zmx_path
                        for attempt in successful
                        if attempt.optimized_zmx_path is not None
                    ]
                    for run_index, attempt in enumerate(attempts, 1):
                        if attempt is None:
                            rms_samples.append(math.nan)
                            wfe_samples.append(math.nan)
                            dropped.append(f"repeat run {run_index}: candidate generation failed")
                            continue
                        if attempt.codev_preferred_config != primary_config:
                            dropped.append(
                                f"repeat run {run_index}: preferred flip "
                                f"{attempt.codev_preferred_config}->{primary_config}; "
                                "sampled primary config"
                            )
                        snapshot = attempt.codev_config_snapshots.get(primary_config or "")
                        if snapshot is None:
                            rms_samples.append(math.nan)
                            wfe_samples.append(math.nan)
                            dropped.append(
                                f"repeat run {run_index}: config-missing ({primary_config})"
                            )
                            continue
                        rms = snapshot.get("post_aut.max_rms_spot_diameter_um")
                        wfe = snapshot.get("post_aut.max_rms_wavefront_error_waves")
                        if isinstance(rms, (int, float)) and math.isfinite(rms):
                            rms_samples.append(float(rms) / 2.0)
                        else:
                            rms_samples.append(math.nan)
                            dropped.append(f"repeat run {run_index}: RMS sample non-finite/missing")
                        if isinstance(wfe, (int, float)) and math.isfinite(wfe):
                            wfe_samples.append(float(wfe))
                        else:
                            wfe_samples.append(math.nan)
                            dropped.append(f"repeat run {run_index}: WFE sample non-finite/missing")
                    primary = primary.model_copy(
                        update={
                            "repeat_rms_samples_um": rms_samples,
                            "repeat_wfe_samples_waves": wfe_samples,
                            "generation_notes": [*primary.generation_notes, *dropped],
                            "repeat_run_artifact_paths": artifact_paths,
                        }
                    )
                    candidates.append(primary)
        return candidates

    @staticmethod
    def _rank_seeds_by_target_match(
        spec: TargetSpec,
    ) -> list[tuple[OpticalSampleData, SeedTargetScore]]:
        """场景池 → 过滤出 ZMX 真实存在的 seed → 两段式排序（不合成新权重，
        复用两个已验证排序器，各管各最有依据的一段）：

        1. **FOV 近邻预筛**（`spec.fov_deg` 非 None 时）：`case_library.
           rank_seeds`——路由层唯一真相源的多维规格距离（FOV 权重 0.46
           主导 / IMH 0.30 / EFL 0.20）——把 ZMX 真实存在的场景池收窄到距离
           最近的前 `_FOV_PREFILTER_TOP_K` 颗（stage 1 primary）。闭合的正
           是 FOV 盲区：EFL 单维打分对"seed 原生 FOV 36° vs target FOV
           78°"这种规格错配视而不见，rank_seeds 的全维距离能看见。
        1b. **甜区召回补齐**（`_fov_bounded_efl_close_extras`，P11 甜区覆盖
           率漏斗调优，2026-07-11，对抗审 BLOCKER 修复版）：stage 1 primary
           之外，把"EFL 已经很接近但被 top-K 挡在外面"的 seed 纳入候选，
           |FOV 失配| 上限锚定**旧路径真机席位**（primary-only stage 2 排序
           后的前 `_TARGET_MAX_SEEDS` 颗）的最差 |FOV 失配|——结构保证新
           路径最终席位的最差 FOV 失配不劣于旧路径（安全证明见该函数
           docstring）。量化证实这类 seed 是三场景 miss 的主因（EFL 维真
           空洞=0）。
        2. **EFL 收敛风险重排**：在 stage 1+1b 候选池内（或 `spec.
           fov_deg is None` 时的整个 ZMX-backed 池——见下），按
           `_stage2_sort_key` 全键排序：band 优先、band 内 score 升序
           （`seed_target_score.score_seed_target_match`，EFL 收敛风险
           代理，N=24 真机数据依据）为主键；|FOV 失配|、case_id 为显式
           tie-break 终键（对抗审 MINOR：消除库文件顺序的隐式裁决，
           置换不变）。

        `spec.fov_deg is None`（target FOV 未约束，§7-E unconstrained 语义）
        时 `rank_seeds` 的检索排序查询没有"不检索这一维"的语义（同
        `RetrievalGenerator` docstring）：跳过 stage 1 与 1b，退化为纯
        stage 2（2026-07-10 前唯一路径）。调用方 `_generate` 通过
        `_mode3_generation_notes` 如实注明"FOV 未约束，seed 选择未做 FOV
        近邻过滤"——诚实降级，不是 bug。

        `spec.efl_mm` 保证非 None（调用方 `_generate` 已 guard）。
        """
        assert spec.efl_mm is not None
        zmx_backed_cases: list[OpticalSampleData] = []
        for case in cases_for_scenario(spec.scenario):
            if case.metadata is None or not case.metadata.source_zmx:
                continue
            source_path = ZMX_AMMO_DIR / case.metadata.source_zmx
            if not source_path.is_file():
                continue
            zmx_backed_cases.append(case)
        if not zmx_backed_cases:
            return []

        pool = zmx_backed_cases
        if spec.fov_deg is not None:
            seed_ranking = rank_seeds(
                zmx_backed_cases,
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
            primary = seed_ranking.ranked_cases[:_FOV_PREFILTER_TOP_K]
            extras = _fov_bounded_efl_close_extras(
                primary,
                zmx_backed_cases,
                target_efl_mm=spec.efl_mm,
                target_fov_deg=spec.fov_deg,
            )
            pool = primary + extras

        scored = _score_cases_for_target(pool, spec.efl_mm)
        scored.sort(key=lambda item: _stage2_sort_key(item[0], item[1], spec.fov_deg))
        return scored

    @staticmethod
    def _candidate_for_seed(
        *,
        seed: OpticalSampleData,
        match: SeedTargetScore,
        spec: TargetSpec,
        work_dir: Path,
        artifact_dir: Path | None = None,
        run_index: int = 1,
    ) -> GeneratedCandidate | None:
        """一颗 seed 的完整 ③ 批跑 + payload 现算，失败一律 `None`（fail
        closed，调用方跳过、不炸整个 generator）。"""
        assert spec.efl_mm is not None
        assert seed.metadata is not None
        source_zmx_path = ZMX_AMMO_DIR / seed.metadata.source_zmx

        try:
            result = run_codev_target_standard(
                source_zmx=source_zmx_path,
                work_dir=work_dir,
                target_efl_mm=spec.efl_mm,
                emit_optimized_zmx=True,
                timeout_seconds=180.0,
                num_fields=3,
            )
        except CodeVBatchError as exc:
            logger.warning(
                "mode3_seed_codev_failed",
                case_id=seed.metadata.case_id,
                kind=exc.kind,
                message=exc.message,
            )
            return None

        preferred = result.get("preferred")
        preferred_reason = str(result.get("preferred_reason", ""))
        configs = result.get("configs")
        if not isinstance(preferred, str) or not isinstance(configs, Mapping):
            logger.warning(
                "mode3_seed_no_preferred_config",
                case_id=seed.metadata.case_id,
                reason=preferred_reason,
            )
            return None
        config = configs.get(preferred)
        if not isinstance(config, Mapping) or "error" in config:
            logger.warning(
                "mode3_seed_preferred_config_errored",
                case_id=seed.metadata.case_id,
                preferred=preferred,
            )
            return None

        optimized_zmx_path_raw = config.get("optimized_zmx_path")
        if not optimized_zmx_path_raw:
            logger.warning(
                "mode3_seed_zmx_rebuild_unavailable",
                case_id=seed.metadata.case_id,
                preferred=preferred,
                zmx_rebuild_error=config.get("zmx_rebuild_error"),
            )
            return None
        optimized_zmx_path = Path(str(optimized_zmx_path_raw))
        artifact_warnings: list[str] = []
        if artifact_dir is not None:
            candidate_key = f"{seed.metadata.case_id}--{preferred}--run-{run_index}"
            persistent_dir = artifact_dir / "candidates" / candidate_key
            persistent_path = persistent_dir / "candidate.zmx"
            try:
                persistent_dir.mkdir(parents=True, exist_ok=False)
                shutil.copyfile(optimized_zmx_path, persistent_path)
                optimized_zmx_path = persistent_path
                if isinstance(config, dict):
                    config["optimized_zmx_path"] = str(persistent_path)
            except Exception as exc:  # noqa: BLE001 - one missing artifact must not sink the candidate
                warning = (
                    f"优化 ZMX 持久化失败，保留临时路径并由导出层 fail-closed："
                    f"{type(exc).__name__}: {exc}"
                )
                artifact_warnings.append(warning)
                logger.warning("mode3_zmx_persist_failed", case_id=seed.metadata.case_id, error=warning)

        try:
            optic = load_normalized_zmx(optimized_zmx_path)
            payload = build_sample_from_optic(
                optic,
                source_zmx=optimized_zmx_path.name,
                n_pieces=seed.metadata.n_pieces,
                nominal_efl_mm=spec.efl_mm,
                nominal_fov_deg=seed.metadata.fov_deg,
                source_path=optimized_zmx_path,
            )
        except Exception as exc:  # noqa: BLE001 - Optiland 满口径追迹在优化后 ZMX 上可能数值异常（even_asphere），fail closed 逐颗 seed 隔离，不炸整个 generator
            logger.warning(
                "mode3_seed_payload_build_failed",
                case_id=seed.metadata.case_id,
                preferred=preferred,
                error=f"{type(exc).__name__}: {exc}",
            )
            return None

        provenance_raw = result.get("provenance")
        provenance = provenance_raw if isinstance(provenance_raw, Mapping) else {}
        from app.core.relative_illumination import compute_relative_illumination

        config_snapshots = {
            str(name): _codev_post_aut_snapshot(raw_config)
            for name, raw_config in configs.items()
            if isinstance(raw_config, Mapping) and "error" not in raw_config
        }
        return GeneratedCandidate(
            candidate_id=f"{seed.metadata.case_id}::target-converged-{preferred}",
            mode=GenerationMode.TARGET_CONVERGED,
            source_case_id=seed.metadata.case_id,
            payload=payload,
            optical_extras=OpticalExtras(
                # P17-4 接线：优化后 ZMX 落在本次批跑的临时目录（不在
                # ZMX_AMMO_DIR 下），`payload.metadata.source_zmx` 只有文件名、
                # 默认解析必然 miss —— 显式把真实路径递给 RI 复算（此刻文件
                # 仍存在：还在 `_generate` 的 TemporaryDirectory 上下文内）。
                # 追迹失败仍 fail-closed 全 unavailable，不猜值。
                ri_by_field=compute_relative_illumination(
                    payload, zmx_path=optimized_zmx_path
                ),
                codev_post_aut=_codev_post_aut_snapshot(config),
            ),
            generation_notes=_mode3_generation_notes(
                seed=seed,
                match=match,
                preferred=preferred,
                preferred_reason=preferred_reason,
                fov_prefiltered=spec.fov_deg is not None,
                config=config,
                provenance=provenance,
            ),
            optimized_zmx_path=str(optimized_zmx_path),
            artifact_warnings=artifact_warnings,
            repeat_run_artifact_paths=[str(optimized_zmx_path)],
            codev_preferred_config=preferred,
            codev_config_snapshots=config_snapshots,
        )
