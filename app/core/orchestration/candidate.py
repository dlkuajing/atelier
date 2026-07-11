"""C1 候选/scorecard 数据模型（Phase 10 探路阶 · C1-b 骨架）。

权威依据：`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`
§5（数据模型 + provenance 诚实不变量）。本文件照 spec §5 原文实现类型层，
不含 scorecard 计算/RI 实现（那是 C1-c，见 §4 模块布局的 `scorecard.py`）。

诚实不变量（§5.5，类型/校验层钉死，不靠人自觉）：
1. mode 钉死于 generator（见 `generators.py` 的 `CandidateGenerator`）。
2. `ScorecardRow` 无 pass/fail 字段——AI 越权代判也无处可写。
3. `CandidateSet.modes_present` / `honesty_banner` 均为 `computed_field`
   派生，调用方无法从构造器传入伪造值。
4. `ScoredCandidate` 的 `_enforce_consistency` validator 校验
   `scorecard.mode == generated.mode`，且每个 `TargetDeviation` 的
   `converged_toward_target` 与 `CONVERGED_FIELDS[mode]`（per-field）一致。
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

from app.core.lens_system import Scenario
from app.core.optical_sample import OpticalSampleData

# ---------------------------------------------------------------------------
# 5.1 GenerationMode
# ---------------------------------------------------------------------------


class GenerationMode(StrEnum):
    """Provenance 核心，每颗候选必带（§5.1）。

    不预留 `SEED_REFINED`：现有 `protected_efl_refinement` 是"仅 EFL 维朝
    target"，与全局 `converged_toward_target` 模型矛盾（逼后续实现失败或
    撒谎，codex 轮3）。将来若需 Mode2，须先把 converged 改 per-field 策略
    表（本文件已是 per-field，见 `CONVERGED_FIELDS`）再引入枚举。
    """

    RETRIEVED = "retrieved"  # Mode1 检索现成 seed，零优化
    TARGET_CONVERGED = "target-converged"  # Mode3 ③落地后真朝客户 target 收敛


# ---------------------------------------------------------------------------
# TargetSpec — 客户需求 + scorecard 打分基准（§4 数据流 spec/target）
# ---------------------------------------------------------------------------


class TargetSpec(BaseModel):
    """客户需求数值（§4 数据流："spec(客户需求)+target(EFL/FOV/F#/IMH/TTL…)"）。

    本骨架阶段（C1-b）合并 `spec`/`target` 两个数据流角色为一型：
    generator 用其数值做检索排序查询（字段与 `case_library.rank_seeds` 的
    关键字参数一一对齐），scorecard（C1-c）用同一实例的 5 维做 §7-A
    target-deviation 基准。

    `efl_mm` / `fov_deg` 为 exact 目标，均可选=unconstrained（§7-E，
    `target=None` 的维不进 `_rank` 必需维分母——同 `image_height_mm` 既有
    语义）。但 `RetrievalGenerator`（Mode1 检索，`generators.py`）对二者仍
    fail-fast 必填：`rank_seeds` 的检索排序查询没有"不检索这一维"的语义，
    None 时直接 `raise ValueError`（诚实 fail-fast，不猜默认值）——这两层
    看似矛盾实为分工：scorecard 打分层允许 unconstrained，Mode1 检索层
    要求确定的查询锚点。`fnum` 恒必填 exact。`image_height_mm` 为 exact
    （IMH，可选=unconstrained）；`max_total_track_mm` 为 ceiling（TTL，
    §5.3 constraint_kind，低于上限不罚，`case_library.py:1466-1471`）。
    末四个字段是检索专用旋钮（`rank_seeds` 消费），不进入 §7-A 5 维打分。
    """

    scenario: Scenario
    efl_mm: float | None = Field(None, gt=0)
    fov_deg: float | None = Field(None, gt=0, le=180)
    fnum: float = Field(..., gt=0)
    image_height_mm: float | None = Field(None, gt=0)
    max_total_track_mm: float | None = Field(None, gt=0)
    n_elements: int | None = Field(None, ge=1)
    max_weight_g: float | None = Field(None, gt=0)
    manufacturing_tier: str | None = None
    priority: str | None = None


# ---------------------------------------------------------------------------
# MetricValue — 可能缺失的量化度量（§5.3 / §7-E，fail closed）
# ---------------------------------------------------------------------------


class MetricValue(BaseModel):
    """一个可能缺失的量化度量。`unavailable` 时不参与排序加权、不填默认值
    （§7-E fail closed）。"""

    value: float | None
    status: Literal["available", "unavailable"]

    @model_validator(mode="after")
    def _value_status_consistent(self) -> MetricValue:
        if self.status == "unavailable" and self.value is not None:
            raise ValueError(
                "status=unavailable 时 value 必须为 None（fail closed，不可静默填值）"
            )
        if self.status == "available" and self.value is None:
            raise ValueError("status=available 时 value 不可为 None")
        return self


# ---------------------------------------------------------------------------
# 5.3 ScorecardRow 及其组成部分
# ---------------------------------------------------------------------------


class TargetDeviation(BaseModel):
    """一个 target 维（efl/fov/fnum/imh/ttl）的偏差（§5.3/§7-A）。"""

    field: str
    constraint_kind: Literal["exact", "ceiling", "floor", "unconstrained"]
    target: float | None  # exact=目标值 / ceiling=上限 / floor=下限 / unconstrained=None
    achieved: float
    violation: float  # exact:|a-t| ; ceiling:max(0,a-上限) ; floor:max(0,下限-a) ; unconstr:0
    rel_violation: float | None  # violation/|target|（unconstrained=None）
    converged_toward_target: bool  # per-field：field ∈ CONVERGED_FIELDS[mode]（§5.2）


class ImageQualityMetrics(BaseModel):
    """像质摘要（§7-B），全取现有真算度量的摘要标量。

    每个字段是跨视场（{0, 0.5, 0.8, 1.0}）/跨方向（sag/tan）聚合后的代表
    值；具体聚合口径由 `scorecard.py`（C1-c）的 `score_candidate` 定，本
    骨架只定型不定算法。
    """

    mtf_sag: MetricValue = Field(..., description="代表频率点 sag MTF（跨视场聚合）")
    mtf_tan: MetricValue = Field(..., description="代表频率点 tan MTF（跨视场聚合）")
    diffraction_cutoff_lp_per_mm: MetricValue
    rms_spot_radius_max_um: MetricValue
    rms_spot_radius_mean_um: MetricValue
    min_strehl_ratio: MetricValue
    rms_wavefront_error_waves: MetricValue
    field_curvature_tangential_delta_mm: MetricValue
    field_curvature_sagittal_delta_mm: MetricValue
    max_distortion_pct: MetricValue
    relative_illumination: MetricValue = Field(
        ..., description="RI，见 §7-D；来自 generated.optical_extras 聚合"
    )


class ManufacturabilityProxy(BaseModel):
    """可制造性 proxy（§7-C）。`is_proxy` 硬标非真公差良率。

    C1-c 实施偏离（见 scorecard.py 实现说明）：`aspheric_term_count` /
    `aspheric_surface_count` 在 C1-b 骨架里是必填 `int`，但 payload 的
    `SurfaceDescriptor`（`optical_engine.py`）不携带 `aspheric_coeffs`/
    `conic`——这两个量结构性地无法从 `generated.payload + optical_extras`
    算出（§7 纯函数契约不碰 optic/ZMX）。硬编码 0 会是撒谎（库内案例全部
    含非球面），因此改为 `MetricValue`，`score_candidate` 恒标
    `unavailable`（fail closed），不猜测。`has_special_glass` 保持 `bool`
    ——可从 `metadata.materials` + `zmx_materials.lookup_nd_vd` 的真实数据表
    确定性推导，不属于同一缺口。
    """

    is_proxy: Literal[True] = True
    total_track_mm: float
    n_pieces: int
    has_special_glass: bool
    aspheric_term_count: MetricValue = Field(
        ..., description="非球面系数项数（跨所有非球面面求和）；payload 无持久化系数，恒 unavailable"
    )
    aspheric_surface_count: MetricValue = Field(
        ..., description="非球面面数；payload 无持久化 conic/系数，恒 unavailable"
    )
    chief_ray_angle_deg: MetricValue = Field(
        ..., description="主光线角 vs 传感器 CRA 匹配（几何可算）"
    )
    note: str = Field(
        default=(
            "非真公差良率(无 Monte-Carlo/补偿器/TOR，C2=CODE V 未接)，仅几何+材料 proxy"
        ),
        description="强制说明（§7-C）",
    )


class RankResult(BaseModel):
    """建议排序结果（§5.3/§7-E）。coverage 不足或必需维缺失 → withheld。"""

    score: float | None  # coverage 不足 → None（withheld）
    status: Literal["ranked", "withheld"]
    coverage_pct: float = Field(..., ge=0.0, le=1.0)
    missing_metrics: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _withheld_has_no_score(self) -> RankResult:
        if self.status == "withheld" and self.score is not None:
            raise ValueError("status=withheld 时 score 必须为 None（§7-E fail closed）")
        if self.status == "ranked" and self.score is None:
            raise ValueError("status=ranked 时 score 不可为 None")
        return self


class RepeatabilityMetrics(BaseModel):
    """跨重复跑次的分布（Phase 17 子项3）。一次 `orchestrate` 默认只跑一次
    （`repeat_runs=1`，现行为零变化）——`run_count` 恒 1、`status` 恒
    `"unavailable"`，直到调用方显式提供 ≥2 组重复跑样本
    （`score_candidate` 的 `repeat_rms_samples_um`/`repeat_wfe_samples_waves`
    关键字参数，见 `scorecard.py`）。

    本铲（P17-3）只交付这份 schema + fail-closed 默认路径 + mock 链测试；
    真机多跑执行引擎（重复调用 CODE V 拿分布）不在本铲范围，由
    `orchestrator.orchestrate` 的 `repeat_runs` 参数另行排窗接入（见其
    docstring）。历史依据：opt3 handoff 限制#8 记录候选2 三跑 RMS
    12.6/71/188µm——单次跑数字可能极不具代表性，这正是加这维的动机。

    无 verdict 字段（同 `ScorecardRow` 诚实不变量2）——纯分布量化数据，"跑了几次
    / 分布多宽"不代表"是否可用"，量产可用性判断权仍在资深手里。
    """

    run_count: int = Field(..., ge=1)
    status: Literal["available", "unavailable"]
    rms_spot_radius_um_min: MetricValue
    rms_spot_radius_um_max: MetricValue
    rms_spot_radius_um_spread: MetricValue
    wfe_waves_min: MetricValue
    wfe_waves_max: MetricValue
    wfe_waves_spread: MetricValue
    note: str = Field(..., description="人读一句话说明（如 'run_count=1，未做重复性验证'）")

    @model_validator(mode="after")
    def _unavailable_has_no_stats(self) -> RepeatabilityMetrics:
        if self.status == "unavailable":
            fields = (
                self.rms_spot_radius_um_min,
                self.rms_spot_radius_um_max,
                self.rms_spot_radius_um_spread,
                self.wfe_waves_min,
                self.wfe_waves_max,
                self.wfe_waves_spread,
            )
            if any(m.status != "unavailable" for m in fields):
                raise ValueError(
                    "status=unavailable 时全部分布字段必须 unavailable（fail closed，"
                    "不可静默填值）"
                )
        return self


class ToleranceYieldMetrics(BaseModel):
    """True CODE V TOR yield only; routing-level proxy values are not comparable."""

    status: Literal["unavailable", "measured"]
    yield_fraction: MetricValue
    per_field_yield: dict[str, float] = Field(default_factory=dict)
    trials: int = Field(ge=0)
    saturation_fraction: MetricValue
    provenance: str
    reason: str

    @model_validator(mode="after")
    def _fail_closed(self) -> ToleranceYieldMetrics:
        if self.status == "unavailable" and (
            self.yield_fraction.status != "unavailable"
            or self.saturation_fraction.status != "unavailable"
            or self.per_field_yield
        ):
            raise ValueError("unavailable tolerance yield cannot carry measured values")
        if self.status == "measured" and (
            self.yield_fraction.status != "available"
            or self.saturation_fraction.status != "available"
            or not self.provenance.strip()
        ):
            raise ValueError("measured tolerance yield requires values and provenance")
        return self


_UNAVAILABLE_METRIC = MetricValue(value=None, status="unavailable")


def _default_repeatability() -> RepeatabilityMetrics:
    """安全的 fail-closed 默认——`run_count=1`/`status=unavailable` 是"我们还
    不知道"的诚实表达，不是编造数据；不经 `score_candidate` 直接构造
    `ScorecardRow`（既有测试 fixture 等）落到这个默认值，与
    `repeat_runs=1`（现行为零变化）时 `score_candidate` 自己算出的结果完全
    一致（见 `scorecard.py::_repeatability`）。"""
    return RepeatabilityMetrics(
        run_count=1,
        status="unavailable",
        rms_spot_radius_um_min=_UNAVAILABLE_METRIC,
        rms_spot_radius_um_max=_UNAVAILABLE_METRIC,
        rms_spot_radius_um_spread=_UNAVAILABLE_METRIC,
        wfe_waves_min=_UNAVAILABLE_METRIC,
        wfe_waves_max=_UNAVAILABLE_METRIC,
        wfe_waves_spread=_UNAVAILABLE_METRIC,
        note="run_count=1，未做重复性验证",
    )


def _default_tolerance_yield() -> ToleranceYieldMetrics:
    return ToleranceYieldMetrics(
        status="unavailable",
        yield_fraction=_UNAVAILABLE_METRIC,
        per_field_yield={},
        trials=0,
        saturation_fraction=_UNAVAILABLE_METRIC,
        provenance="TOR unavailable; policy evidence: none",
        reason="TOR yield semantics are not ratified",
    )


class ScorecardRow(BaseModel):
    """纯量化打分（§5.3）。无 verdict/合格/passed 字段——诚实不变量 2。"""

    candidate_id: str
    mode: GenerationMode  # 每行都带 provenance
    target_deviations: list[TargetDeviation]  # EFL/FOV/F#/IMH/TTL
    image_quality: ImageQualityMetrics
    manufacturability: ManufacturabilityProxy
    rank: RankResult  # 带 coverage 的排序结果（非裸 float，codex 轮3）
    rank_explanation: str
    repeatability: RepeatabilityMetrics = Field(default_factory=_default_repeatability)
    tolerance_yield: ToleranceYieldMetrics = Field(default_factory=_default_tolerance_yield)
    # ↑ 无 verdict / 合格 / passed 字段（诚实不变量 2）


# ---------------------------------------------------------------------------
# OpticalExtras — generator 阶段算出、payload 缺失的量（§7-D，首要 RI）
# ---------------------------------------------------------------------------


class OpticalExtras(BaseModel):
    """generator 阶段用 optic 对象算出、payload 里没有的量（§7-D）。

    RI(field) = cos⁴θ × 边缘光束渐晕因子；payload/`RayTraceResult` 只有
    `has_vignetting` bool（`lens_system.py:240`），无持久化渐晕系数——RI
    必须在有 optic 对象的 generator 阶段算（复用/重建 optic 光追），存入
    这里；`score_candidate`（C1-c，纯函数）只从这里消费，不自行触碰 optic。

    本铲（C1-b）RI 未实现：`ri_by_field` 恒 `None`（C1-c 用 optic 光追
    填）。缺失/算不出时 fail closed（`None`，不猜、不静默降级），不是空
    dict 占位。
    """

    ri_by_field: dict[str, MetricValue] | None = Field(
        None,
        description="按视场点(如 '0.0'/'0.5'/'0.7'/'1.0')的相对照度；None=本 generator 未提供 RI",
    )
    codev_post_aut: dict[str, float | str | None] | None = Field(
        None,
        description=(
            "Mode3（TargetConvergedGenerator）专属：CODE V `run_codev_target_standard` "
            "preferred 配置的 post_aut 快照数字 + autovig/AUT 误差诊断（真机裸出，非"
            "score_candidate 消费——打分口径保持 payload/Optiland 一致性，见"
            "generators.py `_codev_post_aut_snapshot`）。只作为离线报告 provenance 区"
            "如实展示的 side-channel；CODE V 裁瞳(vignetted pupil)口径与 payload 侧"
            "Optiland 满口径口径不可直接横比，报告须如实标注。None=本 generator 未提供"
            "（如 RetrievalGenerator）。"
        ),
    )


# ---------------------------------------------------------------------------
# 5.2 GeneratedCandidate → ScoredCandidate（两阶段，打破契约成环）
# ---------------------------------------------------------------------------


class GeneratedCandidate(BaseModel):
    """阶段一：generator 输出（无 scorecard）。

    `mode` 由 generator 构造时钉死；`generate`（`generators.py`）返回前会
    显式 `raise ValueError` 校验每颗 `mode == cls.mode`，只有 Mode3
    generator 能产 `TARGET_CONVERGED`。
    """

    candidate_id: str
    mode: GenerationMode  # 必填，由 generator 构造时钉死
    source_case_id: str | None  # 检索来源 seed
    payload: OpticalSampleData  # 复用现有统一 payload（光路/MTF/点列/波前/…）
    optical_extras: OpticalExtras  # generator 阶段用 optic 算的、payload 缺失的量（RI 等）
    generation_notes: list[str]  # 诚实注记，如 "检索最近邻 seed，未朝 target 优化"

    @property
    def is_target_converged(self) -> bool:  # 派生只读，不可单独伪造
        return self.mode is GenerationMode.TARGET_CONVERGED


# 每个 mode 实际朝 target 优化/收敛的 field 集合（per-field provenance · codex 轮5）。
# `MappingProxyType`（不是裸 dict）——诚实不变量真值表运行时不可被绕过类型层
# 改写（`ScoredCandidate._enforce_consistency` 校验就靠这张表当唯一真相源）。
CONVERGED_FIELDS: MappingProxyType[GenerationMode, frozenset[str]] = MappingProxyType(
    {
        GenerationMode.RETRIEVED: frozenset(),  # 检索不优化任何维
        # 缩窄（真接入时按实际能力收紧，2026-07-10 · TargetConvergedGenerator 填实）：
        # spec §10 原文把 Mode3 优化维定义为 {EFL, F#, IMH, FOV}（六接缝对应），但
        # `codev_optimize.run_codev_target_standard`（③ 标准入口）目前只有接缝1
        # （EFL 解锁朝 target，真机 E1 验证）实际达标；接缝3a 是 FNO 模式锁 native F#
        # （"保持"不是"朝 target 收敛"）；IMH/FOV 的 Stage C 场重建完全未落地。虚标
        # F#/IMH/FOV 为已收敛 = 撒谎（违反诚实不变量，见本文件 docstring 不变量4 与
        # generators.py::TargetConvergedGenerator 接入警示段）。
        # 将来 Stage B（F# 真优化，需宽视场 CRA 前置工程）/ Stage C（IMH/FOV 场重建）
        # 落地时，按该字段实际达标的那一刻扩这张表（同步 §10 file:line 接缝清单）。
        GenerationMode.TARGET_CONVERGED: frozenset({"efl"}),
    }
)


class ScoredCandidate(BaseModel):
    """阶段二：打分后的最终候选（`CandidateSet` 消费此型）。"""

    generated: GeneratedCandidate
    scorecard: ScorecardRow

    @model_validator(mode="after")
    def _enforce_consistency(self) -> ScoredCandidate:  # raise 非 assert
        if self.scorecard.mode is not self.generated.mode:
            raise ValueError("scorecard.mode != generated.mode")
        conv = CONVERGED_FIELDS[self.generated.mode]  # per-field，非全局 bool
        for dev in self.scorecard.target_deviations:
            if dev.converged_toward_target != (dev.field in conv):
                raise ValueError(
                    f"{dev.field} converged 与 mode {self.generated.mode} 优化维不一致"
                )
        return self

    @property
    def mode(self) -> GenerationMode:
        return self.generated.mode


# ---------------------------------------------------------------------------
# 5.4 CandidateSet
# ---------------------------------------------------------------------------


class CandidateSetSummary(BaseModel):
    """`CandidateSet` 的批级摘要，供离线报告渲染消费。

    本铲（C1-b）为纯数据容器骨架；`orchestrator.py`（C1-c）负责实际填充。
    """

    candidate_count: int = Field(..., ge=0)
    mode_counts: dict[GenerationMode, int] = Field(default_factory=dict)
    ranked_count: int = Field(0, ge=0)
    withheld_count: int = Field(0, ge=0)
    ri_missing_count: int = Field(0, ge=0)
    notes: list[str] = Field(default_factory=list)


NO_TARGET_CONVERGED_BANNER = (
    "本批候选均未朝客户 target 收敛（③/Mode3 未接），scorecard 偏差为检索基线，"
    "非量产设计引擎真实产能，良品率仅供参考基线。"
)


class CandidateSet(BaseModel):
    """一次编排的完整产出（§5.4）。"""

    target: TargetSpec
    candidates: list[ScoredCandidate]  # 已按 rank 排序
    summary: CandidateSetSummary

    @computed_field  # 派生，不接受外部传入 —— 调用方无法塞 TARGET_CONVERGED 跳过 banner
    @property
    def modes_present(self) -> set[GenerationMode]:
        return {c.mode for c in self.candidates}

    @computed_field  # 派生固定文本，不可伪造
    @property
    def honesty_banner(self) -> str | None:
        if GenerationMode.TARGET_CONVERGED not in self.modes_present:
            return NO_TARGET_CONVERGED_BANNER
        return None
