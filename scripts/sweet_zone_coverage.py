"""Phase 11 — 甜区覆盖率热图（sweet-zone coverage sweep）。

背景与目的
----------
真机交叉矩阵（`.planning/loop/seed-target-matching-report.md`，N=24）锁定了
seed→target EFL 收敛的方向不对称：缩焦（ΔEFL%<0）12/12 全收敛，最深 -35.6%
仍收；拉焦（ΔEFL%>0）自 +25.1% 起首次收敛失败。这条边界喂进了
`app/core/engines/seed_target_score.py` 的分桶 heuristic，但"库内现有 436
颗可路由 seed，到底能覆盖多少典型客户 spec"从未算过——这正是良品率
go/no-go 闸选题集的前置量化缺口。

本脚本对 wide / telephoto / ultrawide 三场景各铺 EFL×F#×FOV×IMH 网格，每个
格点用生产 Mode3 (`TargetConvergedGenerator`) 同款两段式排序（stage 1
`case_library.rank_seeds` FOV/IMH 近邻预筛 → stage 1b 甜区召回补齐
（`_fov_bounded_efl_close_extras`，P11 甜区覆盖率漏斗调优，2026-07-11）→
stage 2 `seed_target_score.score_seed_target_match` EFL band 排序，见
`app/core/orchestration/generators.py::_rank_seeds_by_target_match`
docstring）算出"库内最佳匹配"，按 ΔEFL%=(target-native)/native 是否落在
[-15%, 0]（主口径"甜区"）分类，产出覆盖率数字、空洞清单、markdown 热图报告
与良品率闸选题集 JSON。

刻意不做的事
------------
- 不改 `case_library.py` / `seed_target_score.py` / eval golden——纯只读复用
  现成两段式排序，不发明新权重。
- 不直接 import `app.core.orchestration.generators`——那个模块顶层 import
  `codev_optimize.run_codev_target_standard`（CODE V 批跑路径），本脚本要求
  "无 CODE V 依赖、可离线重跑"，避免耦合一个只为拿两个常量/一段排序逻辑的
  重依赖模块。两段式排序在本文件本地重实现（`_rank_pool_by_target`），语义
  与 `_rank_seeds_by_target_match` 逐步对齐，仅去掉了 Mode3 特有的真机批跑
  经济性约束（`_TARGET_MAX_SEEDS`——那是"愿意为一次编排花几次 CODE V 批跑"
  的硬顶，与"库内是否存在好匹配"这个覆盖率问题无关）。
- 不合成/估算缺失维度：seed 缺 IMH（`_case_image_height_mm` 回落到 0.0
  sentinel）或缺 FOV（结构上不应发生，仍防御性检查）时，该格点归入
  `missing_dimension` 桶，不参与甜区/miss 判定，如实在报告里量化。

用法
----
    uv run python scripts/sweet_zone_coverage.py
    uv run python scripts/sweet_zone_coverage.py --efl-points 6 --fov-points 6

默认网格密度（5 EFL × 3 F# × 5 FOV × 4 IMH = 300 格点/场景，3 场景共 900
格点）经验测算全脚本运行在一分钟量级（`rank_seeds` 单次调用在 302 颗 wide/
ultrawide 家族池上 ~0.08s，134 颗 tele 池上 ~0.045s）。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.case_library import (  # noqa: E402
    _case_image_height_mm,
    cases_for_scenario,
    rank_seeds,
)
from app.core.engines.seed_target_score import (  # noqa: E402
    SeedTargetScore,
    score_seed_target_match,
)
from app.core.lens_system import Scenario  # noqa: E402
from app.core.optical_sample import OpticalSampleData  # noqa: E402
from app.core.parameter_guards import SCENARIO_BOUNDS  # noqa: E402
from app.core.zmx_ingest import ZMX_AMMO_DIR  # noqa: E402

# ---------------------------------------------------------------------------
# 判据常量
# ---------------------------------------------------------------------------

#: 主口径"甜区"：最佳 seed 的 ΔEFL% 落在此闭区间才算「甜区原料」覆盖（任务
#: 简报给定，非本脚本自定）。
SWEET_ZONE_DELTA_EFL_PCT: tuple[float, float] = (-15.0, 0.0)

#: 宽松参考带（任务简报给定），仅作参考口径，不作为覆盖率主数字。
LOOSE_BAND_DELTA_EFL_PCT: tuple[float, float] = (-35.0, 10.0)

#: stage 1（`rank_seeds` FOV/IMH 近邻预筛）收窄到的候选池宽度。镜像
#: `app/core/orchestration/generators.py::_FOV_PREFILTER_TOP_K`（写死本文件
#: 生产实际值 2026-07-10，而非 import 该私有常量——见模块 docstring "刻意不
#: 做的事"）。
FOV_PREFILTER_TOP_K = 10

#: seed-target band 的机器排序权重，镜像
#: `app/core/orchestration/generators.py::_BAND_RANK`。
_BAND_RANK: dict[str, int] = {"lt5": 0, "5to15": 1, "15to30": 2, "gt30": 3}

#: `score_seed_target_match` 的两档"EFL 已经很接近"分桶，镜像
#: `app/core/orchestration/generators.py::_EFL_CLOSE_BANDS_FOR_RECALL`（P11
#: 甜区覆盖率漏斗调优，2026-07-11）——写死本文件生产实际值，而非 import
#: 该私有常量，同 `FOV_PREFILTER_TOP_K` 的镜像口径。
_EFL_CLOSE_BANDS_FOR_RECALL: frozenset[str] = frozenset({"lt5", "5to15"})

_SCENARIOS: tuple[Scenario, ...] = (
    Scenario.SMARTPHONE_WIDE,
    Scenario.SMARTPHONE_TELEPHOTO,
    Scenario.SMARTPHONE_ULTRAWIDE,
)

DEFAULT_REPORT_PATH = REPO_ROOT / ".planning" / "loop" / "sweet-zone-coverage-report.md"
DEFAULT_TOPIC_SET_PATH = REPO_ROOT / ".planning" / "loop" / "sweet-zone-topic-set.json"


# ---------------------------------------------------------------------------
# 网格
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GridResolution:
    """每维网格点数。EFL/FOV 权重最大（甜区判据即 EFL；stage1 FOV 权重
    0.46 主导），给更高密度；F# 对甜区判据零影响、对 stage1 影响权重仅
    0.05，3 点（min/mid/max）足够体现"F# 基本不改变覆盖结论"这件事本身。"""

    efl: int = 5
    fnum: int = 3
    fov: int = 5
    imh: int = 4


DEFAULT_GRID_RESOLUTION = GridResolution()


@dataclass(frozen=True)
class GridPoint:
    scenario: Scenario
    efl_mm: float
    fnum: float
    fov_deg: float
    image_height_mm: float | None


def _linspace(lo: float, hi: float, n: int) -> list[float]:
    """n=1 时退化为区间中点；n>1 时含端点均匀取 n 个值。纯手写（不依赖
    numpy）避免给这个离线小脚本添加不必要的依赖面。"""
    if n < 1:
        raise ValueError(f"grid resolution must be >= 1, got {n}")
    if n == 1:
        return [(lo + hi) / 2.0]
    step = (hi - lo) / (n - 1)
    return [lo + i * step for i in range(n)]


def build_grid(
    scenario: Scenario, resolution: GridResolution = DEFAULT_GRID_RESOLUTION
) -> list[GridPoint]:
    """场景边界（`parameter_guards.SCENARIO_BOUNDS`，非本脚本编造）×网格
    密度 → 全量 EFL×F#×FOV×IMH 交叉网格。四维各自独立取值（不做 EFL/FOV/IMH
    的近轴一致性推导 IMH=EFL*tan(HFOV/2)——`rank_seeds`/`TargetSpec` 本身
    也不强制这条关系，见模块 docstring 的诚实降级立场：不发明生产代码没有
    的约束）。"""
    bounds = SCENARIO_BOUNDS[scenario]
    efl_values = _linspace(bounds.efl_mm_min, bounds.efl_mm_max, resolution.efl)
    fnum_values = _linspace(bounds.f_number_min, bounds.f_number_max, resolution.fnum)
    fov_values = _linspace(bounds.fov_deg_min, bounds.fov_deg_max, resolution.fov)
    imh_values = _linspace(bounds.image_height_mm_min, bounds.image_height_mm_max, resolution.imh)
    return [
        GridPoint(scenario=scenario, efl_mm=efl, fnum=fnum, fov_deg=fov, image_height_mm=imh)
        for efl in efl_values
        for fnum in fnum_values
        for fov in fov_values
        for imh in imh_values
    ]


# ---------------------------------------------------------------------------
# 候选池（ZMX-backed，镜像 `_rank_seeds_by_target_match` 的可路由过滤）
# ---------------------------------------------------------------------------


def _zmx_backed_pool(scenario: Scenario) -> list[OpticalSampleData]:
    """`cases_for_scenario(scenario)` 收窄到 `metadata.source_zmx` 在
    `ZMX_AMMO_DIR` 下真实存在的 seed——与
    `TargetConvergedGenerator._rank_seeds_by_target_match` 第一步过滤逐字
    一致（那才是 Mode3 实际会路由到的候选池；未落盘 ZMX 的 seed 无法
    `run_codev_target_standard`，纳入统计会虚报覆盖率）。"""
    pool: list[OpticalSampleData] = []
    for case in cases_for_scenario(scenario):
        if case.metadata is None or not case.metadata.source_zmx:
            continue
        if not (ZMX_AMMO_DIR / case.metadata.source_zmx).is_file():
            continue
        pool.append(case)
    return pool


# ---------------------------------------------------------------------------
# 两段式匹配（本地重实现，语义镜像
# `TargetConvergedGenerator._rank_seeds_by_target_match`）
# ---------------------------------------------------------------------------


def _fov_bounded_efl_close_extras(
    primary: Sequence[OpticalSampleData],
    pool: Sequence[OpticalSampleData],
    *,
    target_efl_mm: float,
    target_fov_deg: float,
) -> list[OpticalSampleData]:
    """stage 1b 甜区召回补齐，镜像
    `app/core/orchestration/generators.py::_fov_bounded_efl_close_extras`
    （P11 甜区覆盖率漏斗调优，2026-07-11）——本地重实现（同文件顶部
    docstring "刻意不做的事"：不直接 import generators 模块），语义逐字
    对齐：`primary` 之外，EFL band ∈ `_EFL_CLOSE_BANDS_FOR_RECALL` 且
    |FOV 失配| 不超过 `primary` 自身最差成员的 seed 纳入候选，上限自适应，
    不引入新的全局幅度常数。"""
    primary_ids = {c.metadata.case_id for c in primary if c.metadata is not None}
    fov_cap = max(
        (abs(c.metadata.fov_deg - target_fov_deg) for c in primary if c.metadata is not None),
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


def _rank_pool_by_target(
    pool: Sequence[OpticalSampleData],
    grid_point: GridPoint,
    *,
    top_k: int = FOV_PREFILTER_TOP_K,
) -> list[tuple[OpticalSampleData, SeedTargetScore]]:
    """stage 1：`rank_seeds` 全维规格距离（FOV 权重主导）收窄到最近 `top_k`
    颗（primary）；stage 1b：`_fov_bounded_efl_close_extras` 甜区召回补齐；
    stage 2：在 primary+extras 候选池内按 `score_seed_target_match` band
    优先、band 内 score 升序重排。`list.sort` 稳定排序，stage2 打平时保留
    候选池的原始序（primary 在前、extras 在后）——同
    `_rank_seeds_by_target_match` 的 tie-break 语义。"""
    if not pool:
        return []

    seed_ranking = rank_seeds(
        list(pool),
        efl_mm=grid_point.efl_mm,
        fov_deg=grid_point.fov_deg,
        fnum=grid_point.fnum,
        image_height_mm=grid_point.image_height_mm,
    )
    primary = seed_ranking.ranked_cases[:top_k]
    extras = _fov_bounded_efl_close_extras(
        primary,
        pool,
        target_efl_mm=grid_point.efl_mm,
        target_fov_deg=grid_point.fov_deg,
    )
    narrowed = primary + extras

    scored: list[tuple[OpticalSampleData, SeedTargetScore]] = []
    for case in narrowed:
        assert case.metadata is not None
        seed_efl_mm = case.paraxial.effective_focal_length_mm
        if not math.isfinite(seed_efl_mm) or seed_efl_mm <= 0:
            continue
        try:
            match = score_seed_target_match(seed_efl_mm, grid_point.efl_mm)
        except ValueError:
            continue
        scored.append((case, match))
    scored.sort(key=lambda item: (_BAND_RANK[item[1].band], item[1].score))
    return scored


def _in_band(value: float, band: tuple[float, float]) -> bool:
    lo, hi = band
    return lo <= value <= hi


@dataclass(frozen=True)
class EflBandMaterial:
    """target EFL 在场景池内的「EFL 维原料」存在性扫描结果。

    对池内每颗合法正 EFL seed 直接算 ΔEFL%=(target-native)/native，统计闭
    区间 `SWEET_ZONE_DELTA_EFL_PCT` 内的全部 seed——存在任意一颗即「EFL 维
    有原料」。**不是 band-rank 第一名判定**（对抗审 BLOCKER 1 修复）：
    band-rank 会让"更近的轻微拉焦 seed"压过"稍远的带内缩焦 seed"，把有原料
    误判成真空洞（真库反例：wide target 5.2mm，US-10120164-B2-e6 ΔEFL
    +0.38% 按 band-rank 排第一，掩盖了带内的 US-11719917-B2-e6 -3.06%）。

    `min_fov_mismatch_deg`：带内 seed 与 target FOV 的最小绝对失配（纯数据，
    不设阈值不加权）。EFL 有料 ≠ 可用原料——Mode3 现状只有 EFL 真收敛
    （`CONVERGED_FIELDS={"efl"}`，见 candidate.py），FOV 靠 seed 原生匹配，
    带内 seed 可能 FOV 差 30°，候选虽诚实但规格错配。
    """

    in_band_count: int
    min_fov_mismatch_deg: float | None
    min_fov_mismatch_case_id: str | None


def _efl_band_material(
    pool: Sequence[OpticalSampleData], target_efl_mm: float, target_fov_deg: float
) -> EflBandMaterial:
    """EFL 维原料存在性扫描（见 `EflBandMaterial` docstring）。ΔEFL% 复用
    `score_seed_target_match`（与两段式排序同一公式源，不重写算式）。"""
    in_band_count = 0
    min_mismatch: float | None = None
    min_case_id: str | None = None
    for case in pool:
        assert case.metadata is not None
        seed_efl_mm = case.paraxial.effective_focal_length_mm
        if not math.isfinite(seed_efl_mm) or seed_efl_mm <= 0:
            continue
        try:
            delta_pct = score_seed_target_match(seed_efl_mm, target_efl_mm).delta_efl_pct
        except ValueError:
            continue
        if not _in_band(delta_pct, SWEET_ZONE_DELTA_EFL_PCT):
            continue
        in_band_count += 1
        seed_fov = case.metadata.fov_deg
        if math.isfinite(seed_fov):
            mismatch = abs(seed_fov - target_fov_deg)
            if min_mismatch is None or mismatch < min_mismatch:
                min_mismatch = mismatch
                min_case_id = case.metadata.case_id
    return EflBandMaterial(
        in_band_count=in_band_count,
        min_fov_mismatch_deg=min_mismatch,
        min_fov_mismatch_case_id=min_case_id,
    )


# ---------------------------------------------------------------------------
# 格点评估
# ---------------------------------------------------------------------------

CoverageLabel = str  # "sweet_zone" | "loose_band" | "miss" | "missing_dimension" | "no_seed_available"


@dataclass(frozen=True)
class MatchResult:
    grid_point: GridPoint
    coverage: CoverageLabel
    seed_case_id: str | None = None
    seed_native_efl_mm: float | None = None
    delta_efl_pct: float | None = None
    band: str | None = None
    imh_data_real: bool | None = None
    fov_data_real: bool | None = None
    #: EFL 维原料存在性扫描（`_efl_band_material`）：池内 ΔEFL 落甜区闭区间
    #: 的 seed 总数 + 这些带内 seed 与 target FOV 的最小绝对失配。
    efl_band_seed_count: int = 0
    efl_band_min_fov_mismatch_deg: float | None = None
    efl_band_min_fov_mismatch_case_id: str | None = None
    #: 严格口径（对抗审 BLOCKER 2 修复）：**仅** `coverage == "miss"` 且
    #: EFL 维有原料（存在性扫描 in_band_count > 0）时为 True。loose_band /
    #: missing_dimension 一律 False——报告口径"其中漏斗致 miss"必须真的是
    #: miss 的子集。
    funnel_caused_miss: bool = False


def evaluate_grid_point(
    pool: Sequence[OpticalSampleData],
    grid_point: GridPoint,
    *,
    top_k: int = FOV_PREFILTER_TOP_K,
) -> MatchResult:
    """一个格点的完整判定：两段式选出"库内最佳匹配"，按 ΔEFL% 分类，附带
    缺维 fail-closed 降级与漏斗/真空洞区分标记（存在性扫描口径）。"""
    if not pool:
        return MatchResult(grid_point=grid_point, coverage="no_seed_available")

    material = _efl_band_material(pool, grid_point.efl_mm, grid_point.fov_deg)

    scored = _rank_pool_by_target(pool, grid_point, top_k=top_k)
    if not scored:
        # stage1 收窄后没有任何候选给出有限正 EFL 的合法打分（schema 上
        # 不应发生，防御性 fail-closed，不炸整个 sweep）。
        return MatchResult(
            grid_point=grid_point,
            coverage="no_seed_available",
            efl_band_seed_count=material.in_band_count,
            efl_band_min_fov_mismatch_deg=material.min_fov_mismatch_deg,
            efl_band_min_fov_mismatch_case_id=material.min_fov_mismatch_case_id,
        )

    seed, match = scored[0]
    assert seed.metadata is not None

    imh_real = _case_image_height_mm(seed) > 0.0
    fov_real = math.isfinite(seed.metadata.fov_deg) and seed.metadata.fov_deg > 0.0

    if not (imh_real and fov_real):
        coverage: CoverageLabel = "missing_dimension"
    elif _in_band(match.delta_efl_pct, SWEET_ZONE_DELTA_EFL_PCT):
        coverage = "sweet_zone"
    elif _in_band(match.delta_efl_pct, LOOSE_BAND_DELTA_EFL_PCT):
        coverage = "loose_band"
    else:
        coverage = "miss"

    funnel_caused_miss = coverage == "miss" and material.in_band_count > 0

    return MatchResult(
        grid_point=grid_point,
        coverage=coverage,
        seed_case_id=seed.metadata.case_id,
        seed_native_efl_mm=seed.paraxial.effective_focal_length_mm,
        delta_efl_pct=match.delta_efl_pct,
        band=match.band,
        imh_data_real=imh_real,
        fov_data_real=fov_real,
        efl_band_seed_count=material.in_band_count,
        efl_band_min_fov_mismatch_deg=material.min_fov_mismatch_deg,
        efl_band_min_fov_mismatch_case_id=material.min_fov_mismatch_case_id,
        funnel_caused_miss=funnel_caused_miss,
    )


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioSummary:
    scenario: Scenario
    total_points: int
    sweet_zone: int
    loose_band: int
    miss: int
    missing_dimension: int
    no_seed_available: int
    #: 严格口径：miss 且 EFL 维有原料（存在性扫描），恒 <= miss。
    funnel_caused_miss: int = 0
    #: 真空洞：miss 且 EFL 存在性扫描无带内 seed（需要补库的那种缺料）。
    true_gap: int = 0

    def _pct(self, count: int) -> float:
        return count / self.total_points * 100.0 if self.total_points else 0.0

    @property
    def sweet_zone_pct(self) -> float:
        return self._pct(self.sweet_zone)

    @property
    def loose_band_or_better_pct(self) -> float:
        return self._pct(self.sweet_zone + self.loose_band)

    @property
    def miss_pct(self) -> float:
        return self._pct(self.miss)

    @property
    def missing_dimension_pct(self) -> float:
        return self._pct(self.missing_dimension)


def summarize(results: Sequence[MatchResult], scenario: Scenario) -> ScenarioSummary:
    total = len(results)
    return ScenarioSummary(
        scenario=scenario,
        total_points=total,
        sweet_zone=sum(1 for r in results if r.coverage == "sweet_zone"),
        loose_band=sum(1 for r in results if r.coverage == "loose_band"),
        miss=sum(1 for r in results if r.coverage == "miss"),
        missing_dimension=sum(1 for r in results if r.coverage == "missing_dimension"),
        no_seed_available=sum(1 for r in results if r.coverage == "no_seed_available"),
        funnel_caused_miss=sum(1 for r in results if r.funnel_caused_miss),
        true_gap=sum(
            1 for r in results if r.coverage == "miss" and r.efl_band_seed_count == 0
        ),
    )


# ---------------------------------------------------------------------------
# 良品率闸选题集（JSON，仅甜区覆盖点）
# ---------------------------------------------------------------------------


def build_topic_set(results: Sequence[MatchResult]) -> list[dict[str, object]]:
    topics: list[dict[str, object]] = []
    for r in results:
        if r.coverage != "sweet_zone":
            continue
        gp = r.grid_point
        topics.append(
            {
                "scenario": gp.scenario.value,
                "efl_mm": round(gp.efl_mm, 4),
                "fnum": round(gp.fnum, 4),
                "fov_deg": round(gp.fov_deg, 4),
                "image_height_mm": round(gp.image_height_mm, 4)
                if gp.image_height_mm is not None
                else None,
                "seed_case_id": r.seed_case_id,
                "seed_native_efl_mm": round(r.seed_native_efl_mm, 4)
                if r.seed_native_efl_mm is not None
                else None,
                "delta_efl_pct": round(r.delta_efl_pct, 4) if r.delta_efl_pct is not None else None,
                "band": r.band,
            }
        )
    return topics


# ---------------------------------------------------------------------------
# markdown 热图（EFL 行 × FOV 列，格子=该(EFL,FOV)切片下 F#×IMH 子网格的
# 甜区覆盖率）
# ---------------------------------------------------------------------------


def _heat_symbol(pct: float) -> str:
    if pct >= 90.0:
        return "█"  # full block
    if pct >= 60.0:
        return "▓"  # dark shade
    if pct >= 30.0:
        return "▒"  # medium shade
    if pct > 0.0:
        return "░"  # light shade
    return "·"  # middle dot


def render_heatmap_table(results: Sequence[MatchResult]) -> str:
    if not results:
        return "_(no grid points)_"
    efl_values = sorted({r.grid_point.efl_mm for r in results})
    fov_values = sorted({r.grid_point.fov_deg for r in results})

    header = "| EFL \\ FOV | " + " | ".join(f"{fov:.1f}" for fov in fov_values) + " |"
    separator = "|---|" + "---|" * len(fov_values)
    lines = [header, separator]
    for efl in efl_values:
        cells = []
        for fov in fov_values:
            subset = [
                r
                for r in results
                if r.grid_point.efl_mm == efl and r.grid_point.fov_deg == fov
            ]
            covered = sum(1 for r in subset if r.coverage == "sweet_zone")
            pct = covered / len(subset) * 100.0 if subset else 0.0
            cells.append(f"{_heat_symbol(pct)} {pct:.0f}%")
        lines.append(f"| {efl:.2f}mm | " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 空洞清单 / 定向补库
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellHole:
    """一个 (EFL, FOV) 切片的空洞——与热图 0% 格子逐一对应，是
    "未覆盖格点"的量化，而不是粗粒度的 EFL 边际聚合（后者会被同一 EFL 行
    里任何一个覆盖的 FOV 列掩盖，稀释掉真正的空洞）。"""

    efl_mm: float
    fov_deg: float
    total_points: int
    avg_delta_efl_pct: float | None
    nearest_miss_delta_efl_pct: float | None
    #: 严格口径：miss 且 EFL 维有原料。
    funnel_caused_miss_points: int
    #: miss 且 EFL 存在性扫描无带内 seed。
    true_gap_points: int
    #: EFL 维原料存在性扫描（切片内所有格点共享同一 target EFL/FOV/池，值
    #: 恒一致）：带内 seed 数 + 带内 seed 最小 |FOV 失配|（纯数据列，不设
    #: 阈值不加权——"EFL 有料但最近的 FOV 差 X°"是漏斗调优与补库的真输入）。
    efl_band_seed_count: int = 0
    efl_band_min_fov_mismatch_deg: float | None = None
    efl_band_min_fov_mismatch_case_id: str | None = None


def _nearest_boundary_distance_pct(delta_efl_pct: float) -> float:
    """miss/loose 格点的 ΔEFL% 距甜区边界 [-15%, 0] 最近一侧的距离
    （量化"最近 miss 有多远"，恒 >= 0；甜区内为 0，理论上不会传入本函数）。"""
    lo, hi = SWEET_ZONE_DELTA_EFL_PCT
    if delta_efl_pct < lo:
        return lo - delta_efl_pct
    if delta_efl_pct > hi:
        return delta_efl_pct - hi
    return 0.0


def _cell_holes(results: Sequence[MatchResult]) -> list[CellHole]:
    """按 (EFL, FOV) 网格值对聚合（跨 F#/IMH 子网格），列出甜区覆盖率为 0
    的切片——这些格点与 markdown 热图的 "· 0%" 格子逐一对应，是"库里这个
    EFL×FOV 组合完全打不中甜区"的直接量化，供 Phase 12 定向补库方向参考。
    `nearest_miss_delta_efl_pct` 取该切片内离甜区边界最近的一个 miss，量化
    "最近 miss 有多远"（任务要求的"未覆盖格点+最近 miss 的量化距离"）。"""
    efl_values = sorted({r.grid_point.efl_mm for r in results})
    fov_values = sorted({r.grid_point.fov_deg for r in results})
    holes: list[CellHole] = []
    for efl in efl_values:
        for fov in fov_values:
            subset = [
                r for r in results if r.grid_point.efl_mm == efl and r.grid_point.fov_deg == fov
            ]
            if not subset:
                continue
            sweet = sum(1 for r in subset if r.coverage == "sweet_zone")
            if sweet > 0:
                continue
            deltas = [r.delta_efl_pct for r in subset if r.delta_efl_pct is not None]
            avg_delta = sum(deltas) / len(deltas) if deltas else None
            nearest = (
                min(_nearest_boundary_distance_pct(d) for d in deltas) if deltas else None
            )
            funnel = sum(1 for r in subset if r.funnel_caused_miss)
            true_gap = sum(
                1 for r in subset if r.coverage == "miss" and r.efl_band_seed_count == 0
            )
            # 切片内所有格点共享同一 target EFL/FOV/池 → 存在性扫描结果一致，
            # 取第一个格点的值即可。
            probe = subset[0]
            holes.append(
                CellHole(
                    efl_mm=efl,
                    fov_deg=fov,
                    total_points=len(subset),
                    avg_delta_efl_pct=avg_delta,
                    nearest_miss_delta_efl_pct=nearest,
                    funnel_caused_miss_points=funnel,
                    true_gap_points=true_gap,
                    efl_band_seed_count=probe.efl_band_seed_count,
                    efl_band_min_fov_mismatch_deg=probe.efl_band_min_fov_mismatch_deg,
                    efl_band_min_fov_mismatch_case_id=probe.efl_band_min_fov_mismatch_case_id,
                )
            )
    return holes


# ---------------------------------------------------------------------------
# markdown 报告
# ---------------------------------------------------------------------------


def _render_scenario_section(
    scenario: Scenario,
    results: Sequence[MatchResult],
    pool_size: int,
    resolution: GridResolution,
) -> str:
    summary = summarize(results, scenario)
    bounds = SCENARIO_BOUNDS[scenario]
    holes = _cell_holes(results)

    lines = [
        f"## {scenario.value}",
        "",
        f"- 候选池（ZMX-backed）：{pool_size} 颗",
        (
            f"- 网格边界：EFL [{bounds.efl_mm_min}, {bounds.efl_mm_max}]mm × "
            f"F# [{bounds.f_number_min}, {bounds.f_number_max}] × "
            f"FOV [{bounds.fov_deg_min}, {bounds.fov_deg_max}]deg × "
            f"IMH [{bounds.image_height_mm_min}, {bounds.image_height_mm_max}]mm"
        ),
        (
            f"- 网格密度：{resolution.efl}×{resolution.fnum}×{resolution.fov}×{resolution.imh} = "
            f"{summary.total_points} 格点"
        ),
        "",
        "| 判据 | 格点数 | 占比 |",
        "|---|---:|---:|",
        f"| 甜区 ΔEFL∈[-15%,0]（主口径） | {summary.sweet_zone} | {summary.sweet_zone_pct:.1f}% |",
        f"| 宽松带或以上 ΔEFL∈[-35%,+10]（参考口径） | {summary.sweet_zone + summary.loose_band} | {summary.loose_band_or_better_pct:.1f}% |",
        f"| miss（超出宽松带） | {summary.miss} | {summary.miss_pct:.1f}% |",
        f"| 因缺维无法判断 | {summary.missing_dimension} | {summary.missing_dimension_pct:.1f}% |",
        f"| 池内无合法候选（no_seed_available） | {summary.no_seed_available} | {summary._pct(summary.no_seed_available):.1f}% |",
        f"| miss 中漏斗致 miss（严格：miss 且 EFL 维有原料） | {summary.funnel_caused_miss} | {summary._pct(summary.funnel_caused_miss):.1f}% |",
        f"| miss 中真空洞（EFL 存在性扫描无带内 seed） | {summary.true_gap} | {summary._pct(summary.true_gap):.1f}% |",
        "",
        "### 覆盖率热图（行=EFL, 列=FOV；格子=该切片 F#×IMH 子网格的甜区覆盖率）",
        "",
        render_heatmap_table(results),
        "",
    ]

    if holes:
        lines.append(
            f"### 空洞清单（{len(holes)} 个 (EFL,FOV) 切片甜区覆盖率=0%，"
            "与上方热图的 \"· 0%\" 格子逐一对应）"
        )
        lines.append("")
        lines.append(
            "| target EFL(mm) | target FOV(deg) | 格点数 | 最近 miss 距甜区边界 | "
            "平均 ΔEFL%(最佳匹配) | EFL带内seed数 | 带内seed最小\\|FOV失配\\|(deg) | "
            "漏斗致 miss(严格) | 真空洞 |"
        )
        lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for hole in sorted(holes, key=lambda h: (h.efl_mm, h.fov_deg)):
            avg_delta_str = (
                f"{hole.avg_delta_efl_pct:+.1f}%" if hole.avg_delta_efl_pct is not None else "N/A"
            )
            nearest_str = (
                f"{hole.nearest_miss_delta_efl_pct:.1f}pp"
                if hole.nearest_miss_delta_efl_pct is not None
                else "N/A"
            )
            mismatch_str = (
                f"{hole.efl_band_min_fov_mismatch_deg:.1f}"
                if hole.efl_band_min_fov_mismatch_deg is not None
                else "N/A"
            )
            lines.append(
                f"| {hole.efl_mm:.2f} | {hole.fov_deg:.1f} | {hole.total_points} | "
                f"{nearest_str} | {avg_delta_str} | "
                f"{hole.efl_band_seed_count} | {mismatch_str} | "
                f"{hole.funnel_caused_miss_points} | {hole.true_gap_points} |"
            )
        lines.append("")

        true_gap_holes = [h for h in holes if h.true_gap_points > 0]
        if true_gap_holes:
            true_gap_efls = sorted({h.efl_mm for h in true_gap_holes})
            efl_span = ", ".join(f"{efl:.2f}mm" for efl in true_gap_efls)
            lines.append(
                f"**EFL 维真空洞**：{scenario.value} 场景在 target EFL ≈ {efl_span} "
                f"（合计 {len(true_gap_holes)} 个 (EFL,FOV) 切片）附近，EFL 存在性"
                "扫描找不到 ΔEFL 落甜区的原生 seed——这是 EFL 维的真实原料空洞，"
                "建议 Phase 12 USPTO 补库优先定向这些 EFL 段（按上表平均 ΔEFL% "
                "的方向：负值=需要更长焦的 seed 补入，正值=需要更短焦的 seed "
                "补入）。"
            )
            lines.append("")

        # (c) 补库动机重写：EFL 维无真空洞时（或除真空洞外的切片），补库/调优
        # 的真输入是 FOV 匹配质量——按带内 seed 最小 |FOV 失配| 从大到小列出
        # 最差的切片（纯数据排序，不设阈值不加权）。
        fov_quality_holes = sorted(
            (h for h in holes if h.efl_band_min_fov_mismatch_deg is not None),
            key=lambda h: -(h.efl_band_min_fov_mismatch_deg or 0.0),
        )
        if fov_quality_holes:
            if not true_gap_holes:
                lines.append(
                    "**定向补库建议（FOV 匹配质量口径）**：EFL 维无真空洞——每个"
                    "空洞切片的 target EFL 在池内都有 ΔEFL∈[-15%,0] 的带内 seed"
                    "（存在性扫描）。但 EFL 有料 ≠ 可用原料：Mode3 现状只有 EFL "
                    "真收敛（CONVERGED_FIELDS={\"efl\"}），FOV 靠 seed 原生匹配，"
                    "带内 seed 的 FOV 失配直接决定候选的规格接近度。补库动机应改为"
                    "「改善 FOV 匹配质量」，按带内 seed 最小 |FOV 失配| 最大的切片"
                    "定向（同时这些切片也是漏斗调优铲——放宽 top_k / 复核 FOV 权重"
                    "——的选点依据）："
                )
            else:
                lines.append(
                    "**FOV 匹配质量（全部空洞切片）**：除上述 EFL 维真空洞外，"
                    "其余切片 EFL 维有原料但 FOV 失配如下（失配大的切片=补库改善 "
                    "FOV 匹配质量 / 漏斗调优的选点依据）："
                )
            for hole in fov_quality_holes[:5]:
                lines.append(
                    f"- EFL {hole.efl_mm:.2f}mm / FOV {hole.fov_deg:.1f}°：带内 "
                    f"{hole.efl_band_seed_count} 颗 seed，最小 |FOV 失配| = "
                    f"{hole.efl_band_min_fov_mismatch_deg:.1f}°"
                    f"（{hole.efl_band_min_fov_mismatch_case_id}）"
                )
        lines.append("")
    else:
        lines.append("### 空洞清单")
        lines.append("")
        lines.append("无——本场景网格采样下每个 (EFL,FOV) 切片至少有一个格点落甜区。")
        lines.append("")

    return "\n".join(lines)


def render_report(
    all_results: dict[Scenario, list[MatchResult]],
    pool_sizes: dict[Scenario, int],
    resolution: GridResolution,
    *,
    imh_completeness: dict[Scenario, tuple[int, int]],
) -> str:
    total_points = sum(len(r) for r in all_results.values())
    total_sweet = sum(
        summarize(results, scenario).sweet_zone for scenario, results in all_results.items()
    )

    lines = [
        "# 甜区覆盖率热图报告（Phase 11）",
        "",
        f"生成脚本：`scripts/sweet_zone_coverage.py`（确定性、无 CODE V 依赖，"
        f"共 {total_points} 格点；运行耗时打印在脚本 stdout，属非确定性字段，"
        "不入报告——报告 byte-for-byte 可再生）",
        "",
        "## 判据定义",
        "",
        "- **甜区（主口径）**：两段式匹配选出的库内最佳 seed，"
        f"ΔEFL%=(target-native)/native ∈ [{SWEET_ZONE_DELTA_EFL_PCT[0]:.0f}%, "
        f"{SWEET_ZONE_DELTA_EFL_PCT[1]:.0f}%]（真机 N=24 实锤：缩焦方向 12/12 "
        "全收敛，最深 -35.6% 仍收；本判据取更保守的 -15% 下界留安全边际）。",
        f"- **宽松带（参考口径）**：ΔEFL% ∈ [{LOOSE_BAND_DELTA_EFL_PCT[0]:.0f}%, "
        f"{LOOSE_BAND_DELTA_EFL_PCT[1]:.0f}%]，含拉焦方向真机实测的最后收敛点"
        "（+25.1% 起首次失败，此处 +10% 留安全边际）。",
        "- **两段式匹配**：镜像生产 Mode3 "
        "`TargetConvergedGenerator._rank_seeds_by_target_match`"
        "（`app/core/orchestration/generators.py`）——stage 1 "
        "`case_library.rank_seeds` 全维规格距离（FOV 权重 0.46 主导）收窄到 "
        f"top {FOV_PREFILTER_TOP_K} 颗近邻，stage 2 "
        "`seed_target_score.score_seed_target_match` 在邻域内按 EFL 收敛风险"
        " band 重排，取第一名为「库内最佳匹配」。这就是真实客户请求会被路由"
        "到的那颗 seed，不是理论最优 EFL 匹配。",
        "- **漏斗致 miss vs 真空洞（存在性扫描口径）**：对场景池每颗合法正 "
        "EFL seed 直接算 ΔEFL%，闭区间 [-15%, 0] 内存在任意一颗即「EFL 维有"
        "原料」（真存在性扫描，不是 band-rank 第一名判定——后者会让更近的轻微"
        "拉焦 seed 掩盖稍远的带内缩焦 seed）。**仅对 coverage=miss 的格点**"
        "判定：miss 且有原料 = `funnel_caused_miss`（排序/参数问题，两段式"
        "漏斗把带内 seed 挡在外面）；miss 且无原料 = 真空洞（需要补库的缺料）。"
        "loose_band 不计入漏斗口径。",
        "- **EFL 有料 ≠ 可用原料**：Mode3 现状只有 EFL 真收敛"
        "（`CONVERGED_FIELDS={\"efl\"}`），FOV 靠 seed 原生匹配——EFL 带内 "
        "seed 可能 FOV 差几十度，候选虽诚实但规格错配。因此空洞清单额外给出"
        "每个切片「EFL 带内 seed 的最小 |FOV 失配|」纯数据列（不设阈值、不加"
        "权），这是漏斗调优铲和补库决策的真输入。",
        "- **网格定义**：per-scenario 独立 EFL×F#×FOV×IMH 网格，边界取自 "
        "`app/core/parameter_guards.SCENARIO_BOUNDS`（非本脚本编造）。四维"
        "独立均匀取值，**不**做 IMH=EFL·tan(HFOV/2) 的近轴一致性推导——生产"
        "`rank_seeds`/`TargetSpec` 本身也不强制这条关系，这里如实复刻现状，"
        "不额外发明约束（已知限制，见文末）。",
        f"- **网格密度**：{resolution.efl}(EFL)×{resolution.fnum}(F#)×"
        f"{resolution.fov}(FOV)×{resolution.imh}(IMH) = "
        f"{resolution.efl * resolution.fnum * resolution.fov * resolution.imh} "
        "格点/场景。",
        "",
        "## 三场景覆盖率总览",
        "",
        "| 场景 | 候选池 | 格点数 | 甜区% | 宽松带或以上% | miss | 漏斗致 miss(严格) | 真空洞 | 缺维格点 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scenario in _SCENARIOS:
        results = all_results.get(scenario, [])
        summary = summarize(results, scenario)
        lines.append(
            f"| {scenario.value} | {pool_sizes.get(scenario, 0)} | {summary.total_points} | "
            f"{summary.sweet_zone_pct:.1f}% | {summary.loose_band_or_better_pct:.1f}% | "
            f"{summary.miss} | {summary.funnel_caused_miss} | {summary.true_gap} | "
            f"{summary.missing_dimension} |"
        )
    lines.append("")
    lines.append(
        f"良品率闸选题集（甜区覆盖点，见 `sweet-zone-topic-set.json`）共 {total_sweet} 条。"
    )
    lines.append("")

    lines.append("## 库数据完整性核验（IMH 维度）")
    lines.append("")
    lines.append(
        "`_case_image_height_mm`（`case_library.py`）在 metadata 直接字段缺失时会"
        "回落到 index.json 紧凑清单、再回落到 case_id 里的legacy `_IMH` token、"
        "最终回落到 0.0 sentinel（\"无数据\"标记，AGENTS.md 记录的已知问题）。"
        "本脚本对 ZMX-backed 候选池逐颗核验解析结果："
    )
    lines.append("")
    lines.append("| 场景 | 候选池 | 解析出真实 IMH(>0) | 回落到 0.0 sentinel |")
    lines.append("|---|---:|---:|---:|")
    for scenario in _SCENARIOS:
        real, total = imh_completeness.get(scenario, (0, 0))
        lines.append(f"| {scenario.value} | {total} | {real} | {total - real} |")
    lines.append("")

    for scenario in _SCENARIOS:
        results = all_results.get(scenario, [])
        lines.append(
            _render_scenario_section(
                scenario, results, pool_sizes.get(scenario, 0), resolution
            )
        )

    lines.append("## 已知限制")
    lines.append("")
    lines.append(
        "- 甜区判据只看 ΔEFL%（真机 N=24 数据唯一强证据的维度，见 "
        "`seed_target_score.py` docstring 的伪信号排雷清单）；F#/IMH/TTL 的"
        "收敛风险未被真机验证过，本报告的\"覆盖\"不代表 F#/IMH 也会真收敛"
        "——量产可用判定仍在 [EXPERT] 手里。"
    )
    lines.append(
        "- wide 与 ultrawide 共享同一个 302 颗候选池（`_candidate_scenarios` "
        "的 `_PHONE_SHORT_FOCUS` 家族分组，生产现状行为，非本脚本发明）——"
        "两个场景的覆盖率数字因此不是完全独立的两个样本。"
    )
    lines.append(
        "- EFL×F#×FOV×IMH 四维独立网格不强制近轴一致性（IMH 应约等于 "
        "EFL·tan(HFOV/2)），会包含一些物理上不典型的组合；这忠实复现了"
        "生产 `rank_seeds`/`TargetSpec` 本身对这四个字段的处理方式（同样"
        "不做一致性校验），未额外引入或修复这个既有限制。"
    )
    lines.append(
        "- 网格密度是覆盖率数字的采样分辨率，不是穷举；数字应读作\"在这个"
        "采样密度下观测到的覆盖率\"，边界附近的精确覆盖率会随密度提升而"
        "小幅浮动。"
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _imh_completeness_for_pool(pool: Sequence[OpticalSampleData]) -> tuple[int, int]:
    real = sum(1 for case in pool if _case_image_height_mm(case) > 0.0)
    return real, len(pool)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--efl-points", type=int, default=DEFAULT_GRID_RESOLUTION.efl)
    parser.add_argument("--fnum-points", type=int, default=DEFAULT_GRID_RESOLUTION.fnum)
    parser.add_argument("--fov-points", type=int, default=DEFAULT_GRID_RESOLUTION.fov)
    parser.add_argument("--imh-points", type=int, default=DEFAULT_GRID_RESOLUTION.imh)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--topic-set-path", type=Path, default=DEFAULT_TOPIC_SET_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    resolution = GridResolution(
        efl=args.efl_points, fnum=args.fnum_points, fov=args.fov_points, imh=args.imh_points
    )

    t_start = time.perf_counter()
    all_results: dict[Scenario, list[MatchResult]] = {}
    pool_sizes: dict[Scenario, int] = {}
    imh_completeness: dict[Scenario, tuple[int, int]] = {}
    all_topics: list[dict[str, object]] = []

    for scenario in _SCENARIOS:
        pool = _zmx_backed_pool(scenario)
        pool_sizes[scenario] = len(pool)
        imh_completeness[scenario] = _imh_completeness_for_pool(pool)
        grid = build_grid(scenario, resolution)
        results = [evaluate_grid_point(pool, gp) for gp in grid]
        all_results[scenario] = results
        all_topics.extend(build_topic_set(results))
        print(
            f"{scenario.value}: pool={len(pool)} grid_points={len(grid)}",
            file=sys.stderr,
        )

    elapsed = time.perf_counter() - t_start

    report_text = render_report(
        all_results,
        pool_sizes,
        resolution,
        imh_completeness=imh_completeness,
    )
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(report_text, encoding="utf-8")

    args.topic_set_path.parent.mkdir(parents=True, exist_ok=True)
    args.topic_set_path.write_text(
        json.dumps(all_topics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"report written: {args.report_path}")
    print(f"topic set written: {args.topic_set_path} ({len(all_topics)} sweet-zone topics)")
    print(f"elapsed: {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
