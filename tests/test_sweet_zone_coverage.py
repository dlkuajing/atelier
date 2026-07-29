"""Tests for `scripts/sweet_zone_coverage.py` — Phase 11 甜区覆盖率热图。

覆盖：
1. 网格构造（`_linspace` / `build_grid`）——格点数、边界内、单点退化为中点。
2. 两段式匹配（`_rank_pool_by_target`）——镜像
   `TargetConvergedGenerator._rank_seeds_by_target_match`（generators.py）的
   stage 1（`rank_seeds` FOV/IMH 近邻预筛）+ stage 2（`score_seed_target_match`
   EFL band 排序）两步顺序，用真实库数据的 FOV 窄/宽变体对复现同一个真机
   实锤最小案例（narrow FOV vs wide FOV 打平在 stage 2、只有 stage 1 能分辨）。
3. 覆盖判定（`evaluate_grid_point`）——甜区/宽松带/miss 边界、空池
   no_seed_available、缺 IMH 维 fail-closed 降级、漏斗致 miss 标记。
4. 聚合/报告/选题集辅助函数——纯函数，合成 `MatchResult` 输入。
"""

from __future__ import annotations

import pytest

from app.core.case_library import _candidate_scenarios, load_case_library
from app.core.lens_system import Scenario
from app.core.optical_sample import OpticalSampleData
from app.core.zmx_ingest import ZMX_AMMO_DIR
from scripts.sweet_zone_coverage import (
    LOOSE_BAND_DELTA_EFL_PCT,
    SWEET_ZONE_DELTA_EFL_PCT,
    GridPoint,
    GridResolution,
    MatchResult,
    ScenarioSummary,
    _efl_band_material,
    _linspace,
    _rank_pool_by_target,
    _zmx_backed_pool,
    build_grid,
    build_topic_set,
    evaluate_grid_point,
    render_heatmap_table,
    summarize,
)

# ---------------------------------------------------------------------------
# 真实库 fixtures（同 tests/test_orchestration_generators.py 的风格：真 case
# `model_copy(deep=True)` 后微调字段，不从零手搓 OpticalSampleData）
# ---------------------------------------------------------------------------


def _real_case_with_zmx() -> OpticalSampleData:
    for case in load_case_library():
        if case.metadata is not None and (ZMX_AMMO_DIR / case.metadata.source_zmx).is_file():
            return case
    raise AssertionError("case library has no case with an on-disk source ZMX")


def _cases_for(scenario: Scenario) -> list[OpticalSampleData]:
    allowed = _candidate_scenarios(scenario)
    return [
        c for c in load_case_library() if c.metadata is not None and c.metadata.scenario in allowed
    ]


def _fov_variant_pair() -> tuple[OpticalSampleData, OpticalSampleData]:
    """narrow(36deg) / wide(78deg) FOV 变体对，EFL/F#/IMH 全同——同
    test_orchestration_generators.py::_fov_variant_pair 的真机实锤最小案例。"""
    base = _real_case_with_zmx()
    assert base.metadata is not None

    narrow = base.model_copy(deep=True)
    assert narrow.metadata is not None
    narrow.metadata.case_id = f"{base.metadata.case_id}-swz-narrow"
    narrow.metadata.fov_deg = 36.0

    wide = base.model_copy(deep=True)
    assert wide.metadata is not None
    wide.metadata.case_id = f"{base.metadata.case_id}-swz-wide"
    wide.metadata.fov_deg = 78.0

    return narrow, wide


def _missing_imh_variant() -> OpticalSampleData:
    """一个 metadata.image_height_mm=None、case_id/source_zmx 均不含 `_IMH`
    token、也不在 index.json 里的合成 case——`_case_image_height_mm` 的所有
    解析分支全部落空，回落到 0.0 sentinel（真实"缺维"场景，非本脚本编造）。
    `source_zmx` 必须一并改掉，否则会通过原 case 的索引清单条目意外解析出
    真值，掩盖这个测试想复现的缺维场景。"""
    base = _real_case_with_zmx()
    assert base.metadata is not None
    variant = base.model_copy(deep=True)
    assert variant.metadata is not None
    variant.metadata.case_id = "SWZ-SYNTHETIC-NOIMH-0001"
    variant.metadata.source_zmx = "SWZ-SYNTHETIC-NOIMH-0001.zmx"
    variant.metadata.image_height_mm = None
    return variant


# ---------------------------------------------------------------------------
# `_linspace` / `build_grid`
# ---------------------------------------------------------------------------


def test_linspace_single_point_returns_midpoint():
    assert _linspace(2.0, 6.0, 1) == pytest.approx([4.0])


def test_linspace_multiple_points_evenly_spaced_inclusive():
    assert _linspace(0.0, 10.0, 5) == pytest.approx([0.0, 2.5, 5.0, 7.5, 10.0])


def test_linspace_rejects_nonpositive_point_count():
    with pytest.raises(ValueError):
        _linspace(0.0, 1.0, 0)


def test_build_grid_point_count_matches_resolution_product():
    resolution = GridResolution(efl=2, fnum=2, fov=2, imh=2)
    grid = build_grid(Scenario.SMARTPHONE_WIDE, resolution)
    assert len(grid) == 16


def test_build_grid_values_within_scenario_bounds():
    from app.core.parameter_guards import SCENARIO_BOUNDS

    resolution = GridResolution(efl=3, fnum=2, fov=3, imh=2)
    scenario = Scenario.SMARTPHONE_TELEPHOTO
    bounds = SCENARIO_BOUNDS[scenario]
    grid = build_grid(scenario, resolution)
    assert len(grid) == 3 * 2 * 3 * 2
    for gp in grid:
        assert bounds.efl_mm_min <= gp.efl_mm <= bounds.efl_mm_max
        assert bounds.f_number_min <= gp.fnum <= bounds.f_number_max
        assert bounds.fov_deg_min <= gp.fov_deg <= bounds.fov_deg_max
        assert bounds.image_height_mm_min <= gp.image_height_mm <= bounds.image_height_mm_max
        assert gp.scenario == scenario


# ---------------------------------------------------------------------------
# 两段式匹配 — 镜像 generators.py 的 stage1/stage2 顺序
# ---------------------------------------------------------------------------


def test_rank_pool_by_target_prefers_fov_near_seed_when_narrowed():
    narrow_fov, wide_fov = _fov_variant_pair()
    assert narrow_fov.metadata is not None and wide_fov.metadata is not None
    pool = [narrow_fov, wide_fov]
    grid_point = GridPoint(
        scenario=Scenario.SMARTPHONE_WIDE,
        efl_mm=narrow_fov.paraxial.effective_focal_length_mm,
        fnum=narrow_fov.paraxial.f_number,
        fov_deg=78.0,
        image_height_mm=None,
    )
    scored = _rank_pool_by_target(pool, grid_point, top_k=10)
    assert scored[0][0].metadata.case_id == wide_fov.metadata.case_id


def test_rank_pool_by_target_empty_pool_returns_empty_list():
    grid_point = GridPoint(
        scenario=Scenario.SMARTPHONE_WIDE,
        efl_mm=4.0,
        fnum=2.0,
        fov_deg=78.0,
        image_height_mm=3.3,
    )
    assert _rank_pool_by_target([], grid_point, top_k=10) == []


def test_rank_pool_by_target_top_k_narrows_stage1_candidates():
    """top_k=1 时 stage 1 只留最近邻一颗——用来在下面的漏斗测试里制造
    "整池有更好 EFL 匹配，但被 stage1 过滤掉" 的确定性场景。"""
    narrow_fov, wide_fov = _fov_variant_pair()
    pool = [narrow_fov, wide_fov]
    grid_point = GridPoint(
        scenario=Scenario.SMARTPHONE_WIDE,
        efl_mm=narrow_fov.paraxial.effective_focal_length_mm,
        fnum=narrow_fov.paraxial.f_number,
        fov_deg=78.0,
        image_height_mm=None,
    )
    scored = _rank_pool_by_target(pool, grid_point, top_k=1)
    assert len(scored) == 1
    assert scored[0][0].metadata.case_id == wide_fov.metadata.case_id


# ---------------------------------------------------------------------------
# `evaluate_grid_point` — 覆盖判定 + fail-closed 降级
# ---------------------------------------------------------------------------


def test_evaluate_grid_point_sweet_zone_when_delta_within_band():
    base = _real_case_with_zmx()
    assert base.metadata is not None
    seed_efl = base.paraxial.effective_focal_length_mm
    # target 略低于 seed 原生 EFL（缩焦 10% -> ΔEFL%=-10%，落在 [-15,0]）
    target_efl = seed_efl * 0.90
    grid_point = GridPoint(
        scenario=base.metadata.scenario,
        efl_mm=target_efl,
        fnum=base.paraxial.f_number,
        fov_deg=base.metadata.fov_deg,
        image_height_mm=None,
    )
    result = evaluate_grid_point([base], grid_point, top_k=10)
    assert result.coverage == "sweet_zone"
    assert result.delta_efl_pct == pytest.approx(-10.0, abs=0.05)
    assert result.seed_case_id == base.metadata.case_id


def test_evaluate_grid_point_loose_band_when_outside_sweet_but_inside_loose():
    base = _real_case_with_zmx()
    assert base.metadata is not None
    seed_efl = base.paraxial.effective_focal_length_mm
    # +8% 拉焦：不在[-15,0]甜区，仍在[-35,+10]宽松带
    target_efl = seed_efl * 1.08
    grid_point = GridPoint(
        scenario=base.metadata.scenario,
        efl_mm=target_efl,
        fnum=base.paraxial.f_number,
        fov_deg=base.metadata.fov_deg,
        image_height_mm=None,
    )
    result = evaluate_grid_point([base], grid_point, top_k=10)
    assert result.coverage == "loose_band"


def test_evaluate_grid_point_miss_when_outside_loose_band():
    base = _real_case_with_zmx()
    assert base.metadata is not None
    seed_efl = base.paraxial.effective_focal_length_mm
    target_efl = seed_efl * 2.0  # +100% 拉焦，远超宽松带上界 +10%
    grid_point = GridPoint(
        scenario=base.metadata.scenario,
        efl_mm=target_efl,
        fnum=base.paraxial.f_number,
        fov_deg=base.metadata.fov_deg,
        image_height_mm=None,
    )
    result = evaluate_grid_point([base], grid_point, top_k=10)
    assert result.coverage == "miss"


@pytest.mark.parametrize(
    "multiplier",
    [
        1.0 + SWEET_ZONE_DELTA_EFL_PCT[0] / 100.0,  # 恰好甜区下界 -15%
        1.0 + SWEET_ZONE_DELTA_EFL_PCT[1] / 100.0,  # 恰好甜区上界 0%
    ],
)
def test_evaluate_grid_point_sweet_zone_boundary_inclusive(multiplier: float):
    base = _real_case_with_zmx()
    assert base.metadata is not None
    seed_efl = base.paraxial.effective_focal_length_mm
    grid_point = GridPoint(
        scenario=base.metadata.scenario,
        efl_mm=seed_efl * multiplier,
        fnum=base.paraxial.f_number,
        fov_deg=base.metadata.fov_deg,
        image_height_mm=None,
    )
    result = evaluate_grid_point([base], grid_point, top_k=10)
    assert result.coverage == "sweet_zone"


def test_evaluate_grid_point_no_seed_available_for_empty_pool():
    grid_point = GridPoint(
        scenario=Scenario.SMARTPHONE_WIDE, efl_mm=4.0, fnum=2.0, fov_deg=78.0, image_height_mm=3.3
    )
    result = evaluate_grid_point([], grid_point, top_k=10)
    assert result.coverage == "no_seed_available"
    assert result.seed_case_id is None


def test_evaluate_grid_point_flags_missing_dimension_when_imh_unreal():
    seed = _missing_imh_variant()
    assert seed.metadata is not None
    seed_efl = seed.paraxial.effective_focal_length_mm
    grid_point = GridPoint(
        scenario=seed.metadata.scenario,
        efl_mm=seed_efl,  # ΔEFL=0%，若非缺维会落甜区——验证缺维判定优先生效
        fnum=seed.paraxial.f_number,
        fov_deg=seed.metadata.fov_deg,
        image_height_mm=None,
    )
    result = evaluate_grid_point([seed], grid_point, top_k=10)
    assert result.coverage == "missing_dimension"
    assert result.imh_data_real is False


def test_evaluate_grid_point_efl_material_exists_but_not_selected_flag():
    """top_k=1 时 stage1 只留 narrow_fov（EFL 远，miss），但池内 wide_fov
    其实有个甜区带内的 EFL 匹配（存在性扫描可见）——必须标
    efl_material_exists_but_not_selected=True，不能把"没选它"和"库真没有"
    混为一谈（中性命名，对抗审 MINOR：不断言"应由放宽漏斗恢复"）。stage 1b
    的席位锚 cap 在此场景为 0（席位=narrow_fov 自身，FOV 失配 0），
    wide_fov（失配 42°）不会被补齐——如实保持 miss。"""
    narrow_fov, wide_fov = _fov_variant_pair()
    assert narrow_fov.metadata is not None and wide_fov.metadata is not None
    wide_fov.metadata.computed_efl_mm = narrow_fov.metadata.computed_efl_mm
    wide_fov.paraxial.effective_focal_length_mm = narrow_fov.paraxial.effective_focal_length_mm

    # target FOV=36 + top_k=1 迫使 narrow_fov 独占 stage1 top1；同时把
    # narrow_fov 的 EFL 拉远（×2.5 → ΔEFL=-60%，超出宽松带 = miss）、
    # wide_fov 的 EFL 恰好命中 target（ΔEFL=0%，带内）——构造"池内有带内
    # seed 但漏斗未选中"的确定性反例。
    narrow_fov.metadata.computed_efl_mm *= 2.5
    narrow_fov.paraxial.effective_focal_length_mm *= 2.5

    pool = [narrow_fov, wide_fov]
    grid_point = GridPoint(
        scenario=narrow_fov.metadata.scenario,
        efl_mm=wide_fov.paraxial.effective_focal_length_mm,  # 恰好命中 wide_fov 原生 EFL
        fnum=narrow_fov.paraxial.f_number,
        fov_deg=36.0,  # 更接近 narrow_fov 原生 FOV -> stage1 top_k=1 选中 narrow_fov
        image_height_mm=None,
    )
    result = evaluate_grid_point(pool, grid_point, top_k=1)
    assert result.coverage == "miss"
    assert result.efl_material_exists_but_not_selected is True
    # 存在性扫描字段：带内只有 wide_fov 一颗（narrow_fov ΔEFL=-60% 不在带内），
    # 最小 |FOV 失配| = |78 - 36| = 42。
    assert result.efl_band_seed_count == 1
    assert result.efl_band_min_fov_mismatch_case_id == wide_fov.metadata.case_id
    assert result.efl_band_min_fov_mismatch_deg == pytest.approx(42.0)


def test_efl_material_flag_false_for_loose_band_even_with_in_band_material():
    """PR#60 对抗审 BLOCKER 2 回归锚：efl_material_exists_but_not_selected
    仅在 coverage=="miss" 时成立。构造 top pick 落 loose_band（ΔEFL=+8%）而
    池内另有带内 seed（ΔEFL≈-2.9%）未被选中的情形——旧实现
    （`coverage not in ("sweet_zone",)`）会把这种 loose_band 也计入，
    污染严格 miss 子集口径。"""
    narrow_fov, wide_fov = _fov_variant_pair()
    assert narrow_fov.metadata is not None and wide_fov.metadata is not None

    target_efl = narrow_fov.paraxial.effective_focal_length_mm
    # narrow_fov：native = target/1.08 → ΔEFL = +8%（loose_band，非 miss）
    narrow_native = target_efl / 1.08
    narrow_fov.paraxial.effective_focal_length_mm = narrow_native
    narrow_fov.metadata.computed_efl_mm = narrow_native
    # wide_fov：native = target/0.97 → ΔEFL ≈ -2.91%（甜区带内）
    wide_native = target_efl / 0.97
    wide_fov.paraxial.effective_focal_length_mm = wide_native
    wide_fov.metadata.computed_efl_mm = wide_native

    pool = [narrow_fov, wide_fov]
    grid_point = GridPoint(
        scenario=narrow_fov.metadata.scenario,
        efl_mm=target_efl,
        fnum=narrow_fov.paraxial.f_number,
        fov_deg=36.0,  # 迫使 stage1 top_k=1 选中 narrow_fov（loose_band 那颗）
        image_height_mm=None,
    )
    result = evaluate_grid_point(pool, grid_point, top_k=1)
    assert result.coverage == "loose_band"
    assert result.efl_band_seed_count == 1  # 带内原料确实存在（wide_fov）
    assert result.efl_material_exists_but_not_selected is False  # loose_band 不计入


# ---------------------------------------------------------------------------
# `_efl_band_material` — EFL 维原料存在性扫描（对抗审 BLOCKER 1 回归锚）
# ---------------------------------------------------------------------------


def test_efl_band_material_finds_in_band_seed_behind_closer_positive_delta():
    """对抗审 BLOCKER 1 描述的确切反例形状：池里同时有"更近的轻微拉焦
    seed"（ΔEFL=+0.38%，band-rank 第一）和"稍远的带内缩焦 seed"
    （ΔEFL≈-3.06%）。band-rank 第一名判定会被前者掩盖判成无原料；存在性
    扫描必须报告带内原料存在。"""
    base = _real_case_with_zmx()
    assert base.metadata is not None
    target_efl = 5.2

    near_pull = base.model_copy(deep=True)
    assert near_pull.metadata is not None
    near_pull.metadata.case_id = "SWZ-NEAR-PULL"
    near_pull_native = target_efl / 1.0038  # ΔEFL ≈ +0.38%（带外，正向）
    near_pull.paraxial.effective_focal_length_mm = near_pull_native
    near_pull.metadata.computed_efl_mm = near_pull_native

    in_band = base.model_copy(deep=True)
    assert in_band.metadata is not None
    in_band.metadata.case_id = "SWZ-IN-BAND"
    in_band_native = target_efl / 0.9694  # ΔEFL ≈ -3.06%（带内）
    in_band.paraxial.effective_focal_length_mm = in_band_native
    in_band.metadata.computed_efl_mm = in_band_native
    in_band.metadata.fov_deg = 60.0

    material = _efl_band_material([near_pull, in_band], target_efl, 75.0)
    assert material.in_band_count == 1
    assert material.min_fov_mismatch_case_id == "SWZ-IN-BAND"
    assert material.min_fov_mismatch_deg == pytest.approx(15.0)


def test_efl_band_material_empty_pool_reports_no_material():
    material = _efl_band_material([], 4.0, 75.0)
    assert material.in_band_count == 0
    assert material.min_fov_mismatch_deg is None
    assert material.min_fov_mismatch_case_id is None


@pytest.mark.parametrize(
    ("scenario", "target_efl_mm", "anchor_case_id", "anchor_delta_pct"),
    [
        # 对抗审报告给出的三个真库反例（band-rank 第一名判定漏判、存在性扫描
        # 应报有原料的格点），作回归锚：
        (Scenario.SMARTPHONE_WIDE, 5.2, "US-11719917-B2-e6", -3.0577),
        (Scenario.SMARTPHONE_TELEPHOTO, 11.5, "US-20210364737-A1-e8", -4.2596),
        (Scenario.SMARTPHONE_ULTRAWIDE, 3.2, "US-12210213-B2-e3", -1.6911),
    ],
)
def test_efl_band_material_real_library_counterexample_anchors(
    scenario: Scenario, target_efl_mm: float, anchor_case_id: str, anchor_delta_pct: float
):
    pool = _zmx_backed_pool(scenario)
    anchor = next(
        (c for c in pool if c.metadata is not None and c.metadata.case_id == anchor_case_id),
        None,
    )
    assert anchor is not None, f"anchor seed {anchor_case_id} missing from {scenario} pool"
    native = anchor.paraxial.effective_focal_length_mm
    delta = (target_efl_mm - native) / native * 100.0
    assert delta == pytest.approx(anchor_delta_pct, abs=0.01)
    assert SWEET_ZONE_DELTA_EFL_PCT[0] <= delta <= SWEET_ZONE_DELTA_EFL_PCT[1]

    material = _efl_band_material(pool, target_efl_mm, 75.0)
    assert material.in_band_count >= 1  # 存在性扫描必须看见带内原料


# ---------------------------------------------------------------------------
# `_zmx_backed_pool` — 只读复用 cases_for_scenario + 磁盘 ZMX 存在性过滤
# ---------------------------------------------------------------------------


def test_zmx_backed_pool_matches_known_routable_seed_counts():
    # 家族分组：wide 请求池与 ultrawide 请求池是同一个合并池，见
    # `_candidate_scenarios` 的 `_PHONE_SHORT_FOCUS` 分组——这里锁的是"至少
    # 不比已知真值小"而非精确家族数字，避免和未来入库新 seed 打架。
    #
    # 2026-07-29 `fov_deg` 重锚后实测 wide 332 / tele 110 / ultrawide 332
    # （旧下限 224 / 134 / 78）。**tele 少了 24 颗不是能力变少，是分桶纠正**：
    # 那些 case 存的是半视场，一颗 72° 的镜头被读成 36°、从 45° 长焦上限底下
    # 溜了进去。上限一个字没动，动的是喂给它的数的单位。
    # 真正该守的性质是**没有 case 掉出可路由**，所以下面额外锁住三池并集 == 全库。
    wide_pool = _zmx_backed_pool(Scenario.SMARTPHONE_WIDE)
    tele_pool = _zmx_backed_pool(Scenario.SMARTPHONE_TELEPHOTO)
    ultrawide_pool = _zmx_backed_pool(Scenario.SMARTPHONE_ULTRAWIDE)
    assert len(wide_pool) >= 332
    assert len(tele_pool) >= 110
    assert len(ultrawide_pool) >= 332
    routable = {
        case.metadata.case_id
        for case in wide_pool + tele_pool + ultrawide_pool
        if case.metadata is not None
    }
    assert len(routable) == 442
    for case in wide_pool + tele_pool + ultrawide_pool:
        assert case.metadata is not None
        assert (ZMX_AMMO_DIR / case.metadata.source_zmx).is_file()


# ---------------------------------------------------------------------------
# 聚合 / 报告 / 选题集辅助函数（合成 MatchResult，不依赖真实库）
# ---------------------------------------------------------------------------


def _gp(efl: float = 4.0, fnum: float = 2.0, fov: float = 75.0, imh: float = 3.5) -> GridPoint:
    return GridPoint(
        scenario=Scenario.SMARTPHONE_WIDE, efl_mm=efl, fnum=fnum, fov_deg=fov, image_height_mm=imh
    )


def test_summarize_counts_and_percentages():
    results = [
        MatchResult(grid_point=_gp(), coverage="sweet_zone"),
        MatchResult(grid_point=_gp(), coverage="sweet_zone"),
        MatchResult(grid_point=_gp(), coverage="loose_band"),
        # miss + 带内原料 = EFL 有料未选中（严格 miss 子集口径）
        MatchResult(
            grid_point=_gp(),
            coverage="miss",
            efl_band_seed_count=3,
            efl_material_exists_but_not_selected=True,
        ),
        # miss + 无带内原料 = 真空洞
        MatchResult(grid_point=_gp(), coverage="miss", efl_band_seed_count=0),
        MatchResult(grid_point=_gp(), coverage="missing_dimension"),
        MatchResult(grid_point=_gp(), coverage="no_seed_available"),
    ]
    summary = summarize(results, Scenario.SMARTPHONE_WIDE)
    assert isinstance(summary, ScenarioSummary)
    assert summary.total_points == 7
    assert summary.sweet_zone == 2
    assert summary.loose_band == 1
    assert summary.miss == 2
    assert summary.missing_dimension == 1
    assert summary.no_seed_available == 1
    assert summary.efl_material_exists_but_not_selected == 1
    assert summary.true_gap == 1
    assert summary.sweet_zone_pct == pytest.approx(2 / 7 * 100.0)


def test_summarize_empty_results_does_not_divide_by_zero():
    summary = summarize([], Scenario.SMARTPHONE_WIDE)
    assert summary.total_points == 0
    assert summary.sweet_zone_pct == 0.0


def test_build_topic_set_only_includes_sweet_zone_entries():
    covered = MatchResult(
        grid_point=_gp(efl=4.0, fnum=2.0, fov=75.0, imh=3.5),
        coverage="sweet_zone",
        seed_case_id="US1234567B1",
        seed_native_efl_mm=4.3,
        delta_efl_pct=-6.98,
        band="5to15",
    )
    missed = MatchResult(grid_point=_gp(efl=9.0), coverage="miss")
    topics = build_topic_set([covered, missed])
    assert len(topics) == 1
    topic = topics[0]
    assert topic["scenario"] == Scenario.SMARTPHONE_WIDE.value
    assert topic["seed_case_id"] == "US1234567B1"
    assert topic["efl_mm"] == pytest.approx(4.0)
    assert topic["delta_efl_pct"] == pytest.approx(-6.98)
    assert topic["band"] == "5to15"


def test_render_heatmap_table_contains_axis_values_and_percentages():
    results = [
        MatchResult(grid_point=_gp(efl=4.0, fov=70.0), coverage="sweet_zone"),
        MatchResult(grid_point=_gp(efl=4.0, fov=70.0), coverage="miss"),
        MatchResult(grid_point=_gp(efl=5.0, fov=80.0), coverage="miss"),
    ]
    table = render_heatmap_table(results)
    assert "70.0" in table
    assert "80.0" in table
    assert "4.00" in table
    assert "5.00" in table
    assert "50%" in table  # efl=4/fov=70 cell: 1 of 2 sweet_zone
    assert "0%" in table  # efl=5/fov=80 cell: 0 of 1 sweet_zone


def test_loose_band_bounds_are_superset_of_sweet_zone_bounds():
    sweet_lo, sweet_hi = SWEET_ZONE_DELTA_EFL_PCT
    loose_lo, loose_hi = LOOSE_BAND_DELTA_EFL_PCT
    assert loose_lo <= sweet_lo
    assert loose_hi >= sweet_hi


# ---------------------------------------------------------------------------
# 生产等价校验（对抗审 MAJOR"镜像循环论证"修复）：本脚本的两段式本地重实现
# 必须与生产 `TargetConvergedGenerator._rank_seeds_by_target_match` 在真实
# 库数据 + 场景边界网格抽样（3 场景 × 18 = 54 格点 ≥ 50）上逐格点、逐名次
# 完全一致——镜像 drift（cap 语义/排序键/过滤条件任一处不同步）会被立即
# 抓住，覆盖率报告的数字才有资格代表生产行为。
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario",
    [Scenario.SMARTPHONE_WIDE, Scenario.SMARTPHONE_TELEPHOTO, Scenario.SMARTPHONE_ULTRAWIDE],
)
def test_rank_pool_by_target_matches_production_rank_seeds_by_target_match(scenario: Scenario):
    from app.core.orchestration.candidate import TargetSpec
    from app.core.orchestration.generators import TargetConvergedGenerator

    pool = _zmx_backed_pool(scenario)
    assert pool, f"{scenario} ZMX-backed pool unexpectedly empty"
    grid = build_grid(scenario, GridResolution(efl=3, fnum=2, fov=3, imh=1))
    assert len(grid) == 18  # 3 场景合计 54 格点 >= 50（对抗审要求的抽样规模）

    for gp in grid:
        script_scored = _rank_pool_by_target(pool, gp)
        spec = TargetSpec(
            scenario=scenario,
            efl_mm=gp.efl_mm,
            fov_deg=gp.fov_deg,
            fnum=gp.fnum,
            image_height_mm=gp.image_height_mm,
        )
        production_scored = TargetConvergedGenerator._rank_seeds_by_target_match(spec)
        script_readout = [
            (case.metadata.case_id, match.band, match.score)
            for case, match in script_scored
            if case.metadata is not None
        ]
        production_readout = [
            (case.metadata.case_id, match.band, match.score)
            for case, match in production_scored
            if case.metadata is not None
        ]
        assert script_readout == production_readout, (
            f"mirror drift at grid point {gp}: script={script_readout[:3]}... "
            f"production={production_readout[:3]}..."
        )
