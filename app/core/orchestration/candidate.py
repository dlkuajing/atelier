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

    `efl_mm` / `fov_deg` / `fnum` 为 exact 目标；`image_height_mm` 为 exact
    （IMH，可选=unconstrained）；`max_total_track_mm` 为 ceiling（TTL，
    §5.3 constraint_kind，低于上限不罚，`case_library.py:1466-1471`）。
    末四个字段是检索专用旋钮（`rank_seeds` 消费），不进入 §7-A 5 维打分。
    """

    scenario: Scenario
    efl_mm: float = Field(..., gt=0)
    fov_deg: float = Field(..., gt=0, le=180)
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


class ScorecardRow(BaseModel):
    """纯量化打分（§5.3）。无 verdict/合格/passed 字段——诚实不变量 2。"""

    candidate_id: str
    mode: GenerationMode  # 每行都带 provenance
    target_deviations: list[TargetDeviation]  # EFL/FOV/F#/IMH/TTL
    image_quality: ImageQualityMetrics
    manufacturability: ManufacturabilityProxy
    rank: RankResult  # 带 coverage 的排序结果（非裸 float，codex 轮3）
    rank_explanation: str
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
        description="按视场点(如 '0.0'/'0.5'/'0.8'/'1.0')的相对照度；None=本 generator 未提供 RI",
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


# 每个 mode 实际朝 target 优化/收敛的 field 集合（per-field provenance · codex 轮5）
CONVERGED_FIELDS: dict[GenerationMode, frozenset[str]] = {
    GenerationMode.RETRIEVED: frozenset(),  # 检索不优化任何维
    GenerationMode.TARGET_CONVERGED: frozenset(
        {"efl", "fnum", "imh", "fov"}
    ),  # = §10 Mode3 六接缝优化维；TTL 不在接缝
}


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
