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


def test_evaluate_grid_point_funnel_caused_miss_flag():
    """top_k=1 时 stage1 只留 narrow_fov（EFL 远，miss），但整池（wide_fov）
    其实有个甜区内的 EFL 匹配——必须标 funnel_caused_miss=True，不能把"漏斗
    窄"和"库真没有"混为一谈。"""
    narrow_fov, wide_fov = _fov_variant_pair()
    assert narrow_fov.metadata is not None and wide_fov.metadata is not None
    wide_fov.metadata.computed_efl_mm = narrow_fov.metadata.computed_efl_mm
    wide_fov.paraxial.effective_focal_length_mm = narrow_fov.paraxial.effective_focal_length_mm

    # narrow_fov 保持原生 EFL；target 定在离 narrow_fov 很远（miss）但离
    # wide_fov（EFL 现在同 narrow_fov，所以其实两者 EFL 相同——改用 F# 来分
    # 出 stage1 排序即可，这里简化：直接把 target FOV 设为 78，使 stage1
    # top_k=1 只留 wide_fov（FOV 更近），narrow_fov 被踢出；反向验证「stage1
    # 收窄不会误伤」不是本测试目的，故改用 top_k=1 + target fov=36 迫使
    # narrow_fov 独占 top1，同时把 narrow_fov 的 EFL 错配、wide_fov 的 EFL
    # 甜区匹配，构造"whole-pool 有解但漏斗未选中"的确定性反例。
    narrow_fov.metadata.computed_efl_mm *= 2.5  # 远离 target -> narrow_fov 会 miss
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
    assert result.coverage != "sweet_zone"
    assert result.funnel_caused_miss is True
    assert result.whole_pool_best_case_id == wide_fov.metadata.case_id


# ---------------------------------------------------------------------------
# `_zmx_backed_pool` — 只读复用 cases_for_scenario + 磁盘 ZMX 存在性过滤
# ---------------------------------------------------------------------------


def test_zmx_backed_pool_matches_known_routable_seed_counts():
    # AGENTS.md / MEMORY 记录的可路由底库：wide 224 / tele 134 / ultrawide 78
    # （家族分组：wide 请求池与 ultrawide 请求池是同一个 302 颗合并池，见
    # `_candidate_scenarios` 的 `_PHONE_SHORT_FOCUS` 分组——这里锁的是"至少
    # 不比已知真值小"而非精确家族数字，避免和未来入库新 seed 打架）。
    wide_pool = _zmx_backed_pool(Scenario.SMARTPHONE_WIDE)
    tele_pool = _zmx_backed_pool(Scenario.SMARTPHONE_TELEPHOTO)
    ultrawide_pool = _zmx_backed_pool(Scenario.SMARTPHONE_ULTRAWIDE)
    assert len(wide_pool) >= 224
    assert len(tele_pool) >= 134
    assert len(ultrawide_pool) >= 78
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
        MatchResult(grid_point=_gp(), coverage="miss"),
        MatchResult(grid_point=_gp(), coverage="missing_dimension"),
        MatchResult(grid_point=_gp(), coverage="no_seed_available"),
    ]
    summary = summarize(results, Scenario.SMARTPHONE_WIDE)
    assert isinstance(summary, ScenarioSummary)
    assert summary.total_points == 6
    assert summary.sweet_zone == 2
    assert summary.loose_band == 1
    assert summary.miss == 1
    assert summary.missing_dimension == 1
    assert summary.no_seed_available == 1
    assert summary.sweet_zone_pct == pytest.approx(2 / 6 * 100.0)


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
