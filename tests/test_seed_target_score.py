"""Seed-target EFL 距离打分 heuristic 单元测试。

锚点数据来自 `.planning/loop/seed-target-matching-report.md`（2026-07-09 真机
交叉矩阵）与 `scratch_diag/match_matrix_results.tsv` 的逐行实测，用于把公式
实现与真机观察到的收敛/失败边界对齐；公式本身的折点/斜率用合成数值精确
校验。
"""

from __future__ import annotations

import pytest

from app.core.engines.seed_target_score import (
    EVIDENCE_NOTE,
    SeedTargetScore,
    score_seed_target_match,
)

# ---------------------------------------------------------------------------
# 公式行为：折点、符号、无惩罚方向（合成数值，精确校验）
# ---------------------------------------------------------------------------


def test_no_offset_scores_zero() -> None:
    result = score_seed_target_match(seed_efl_mm=4.0, target_efl_mm=4.0)
    assert result.delta_efl_pct == pytest.approx(0.0)
    assert result.abs_delta_efl_pct == pytest.approx(0.0)
    assert result.score == pytest.approx(0.0)
    assert result.band == "lt5"


def test_pull_offset_exactly_at_threshold_has_no_penalty() -> None:
    # +20% 拉焦恰好在惩罚折点：max(0, 20-20)=0，score 应等于 abs_delta。
    result = score_seed_target_match(seed_efl_mm=10.0, target_efl_mm=12.0)
    assert result.delta_efl_pct == pytest.approx(20.0)
    assert result.abs_delta_efl_pct == pytest.approx(20.0)
    assert result.score == pytest.approx(20.0)
    assert result.band == "15to30"


def test_pull_offset_beyond_threshold_gets_linear_penalty() -> None:
    # +30% 拉焦：score = 30 + 1.0*(30-20) = 40。
    result = score_seed_target_match(seed_efl_mm=10.0, target_efl_mm=13.0)
    assert result.delta_efl_pct == pytest.approx(30.0)
    assert result.score == pytest.approx(40.0)
    assert result.band == "gt30"


def test_shrink_offset_never_penalized_even_at_large_magnitude() -> None:
    # -20%（缩焦）：与 +20% 同量级但方向相反，无惩罚，score 应等于 abs_delta，
    # 严格小于同量级拉焦一旦超过折点后的 score。
    shrink = score_seed_target_match(seed_efl_mm=10.0, target_efl_mm=8.0)
    assert shrink.delta_efl_pct == pytest.approx(-20.0)
    assert shrink.score == pytest.approx(20.0)
    assert shrink.band == "15to30"

    # -50%（深缩焦，量级远超 +20% 折点）依然无惩罚：score 恒等于 abs_delta。
    deep_shrink = score_seed_target_match(seed_efl_mm=10.0, target_efl_mm=5.0)
    assert deep_shrink.delta_efl_pct == pytest.approx(-50.0)
    assert deep_shrink.score == pytest.approx(deep_shrink.abs_delta_efl_pct)
    assert deep_shrink.score == pytest.approx(50.0)
    assert deep_shrink.band == "gt30"


# ---------------------------------------------------------------------------
# band 边界（score 决定，非 abs_delta_efl_pct）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seed_efl_mm", "target_efl_mm", "expected_band"),
    [
        (10.0, 10.049, "lt5"),  # score ~0.49 < 5
        (10.0, 10.5, "5to15"),  # score=5.0，左闭：5to15 下界
        (10.0, 11.499, "5to15"),  # score ~14.99 < 15
        (10.0, 11.5, "15to30"),  # score=15.0，左闭：15to30 下界
        (10.0, 8.5, "15to30"),  # -15% 缩焦，无惩罚，score=15.0 → 15to30 下界
        (10.0, 6.999, "gt30"),  # -30.01% 缩焦，无惩罚，score=30.01 → gt30
        (10.0, 7.0, "gt30"),  # -30% 缩焦，score=30.0 → gt30 下界
    ],
)
def test_band_boundaries(seed_efl_mm: float, target_efl_mm: float, expected_band: str) -> None:
    result = score_seed_target_match(seed_efl_mm=seed_efl_mm, target_efl_mm=target_efl_mm)
    assert result.band == expected_band


def test_pull_offset_29pct_lands_in_gt30_due_to_penalty() -> None:
    # +29.99% 拉焦：abs_delta 本身落在 15-30 区间，但惩罚把 score 推过 30，
    # 归入 gt30——这正是「按 score 定 band，不按 abs_delta 定」的设计意图。
    result = score_seed_target_match(seed_efl_mm=10.0, target_efl_mm=12.999)
    assert 15.0 <= result.abs_delta_efl_pct < 30.0
    assert result.score > 30.0
    assert result.band == "gt30"


# ---------------------------------------------------------------------------
# 输入校验
# ---------------------------------------------------------------------------


def test_zero_or_negative_seed_efl_raises() -> None:
    with pytest.raises(ValueError):
        score_seed_target_match(seed_efl_mm=0.0, target_efl_mm=4.0)
    with pytest.raises(ValueError):
        score_seed_target_match(seed_efl_mm=-1.0, target_efl_mm=4.0)


def test_zero_or_negative_target_efl_raises() -> None:
    with pytest.raises(ValueError):
        score_seed_target_match(seed_efl_mm=4.0, target_efl_mm=0.0)
    with pytest.raises(ValueError):
        score_seed_target_match(seed_efl_mm=4.0, target_efl_mm=-1.0)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_seed_efl_raises(bad: float) -> None:
    # NaN 在 `<= 0` 比较下恒 False、+inf > 0——单靠符号校验会静默穿透，
    # 污染 delta/score/band；非有限值必须与非正值一样在入口 ValueError。
    with pytest.raises(ValueError):
        score_seed_target_match(seed_efl_mm=bad, target_efl_mm=4.0)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_target_efl_raises(bad: float) -> None:
    with pytest.raises(ValueError):
        score_seed_target_match(seed_efl_mm=4.0, target_efl_mm=bad)


# ---------------------------------------------------------------------------
# evidence_note
# ---------------------------------------------------------------------------


def test_evidence_note_present_and_cites_source() -> None:
    result = score_seed_target_match(seed_efl_mm=4.0, target_efl_mm=4.0)
    assert result.evidence_note == EVIDENCE_NOTE
    assert "seed-target-matching-report.md" in result.evidence_note
    assert "N=24" in result.evidence_note
    assert "[EXPERT]" in result.evidence_note


def test_describe_round_trips_all_fields() -> None:
    result = score_seed_target_match(seed_efl_mm=4.0, target_efl_mm=5.0)
    described = result.describe()
    assert described == {
        "delta_efl_pct": result.delta_efl_pct,
        "abs_delta_efl_pct": result.abs_delta_efl_pct,
        "score": result.score,
        "band": result.band,
        "evidence_note": result.evidence_note,
    }


# ---------------------------------------------------------------------------
# 真机矩阵已知点抽查（.planning/loop/seed-target-matching-report.md §4）
# ---------------------------------------------------------------------------


def test_anchor_near_zero_offset_us9651759b2_t1() -> None:
    # US9651759B2 -> T1: 报告 ΔEFL%=-1.8346（round-trip 精度容差见下），band 应为 lt5。
    result = score_seed_target_match(seed_efl_mm=3.2781, target_efl_mm=3.2180)
    assert result.abs_delta_efl_pct == pytest.approx(1.8346, abs=0.01)
    assert result.band == "lt5"


def test_anchor_pull_25pct_us9239447b1_t2_lands_in_gt30() -> None:
    # US9239447B1 -> T2: 报告 ΔEFL%=+25.0811，真机在此偏移首次收敛失败
    # （<=+20% 全收敛，+25.1% 起见失败）。score 应因惩罚被推入 gt30，
    # 与真机"此偏移量级开始不可靠"的判断一致。
    result = score_seed_target_match(seed_efl_mm=3.0356, target_efl_mm=3.7970)
    assert result.delta_efl_pct == pytest.approx(25.08, abs=0.05)
    assert result.band == "gt30"


def test_anchor_deep_shrink_us9810880b2_t1_still_converges_but_scores_high() -> None:
    # US9810880B2 -> T1: 报告 ΔEFL%=-35.5763（缩焦方向最深偏移，真机仍 100% 收敛），
    # 无惩罚，score 应恰好等于 abs_delta（不因方向对称套用拉焦惩罚）。
    result = score_seed_target_match(seed_efl_mm=4.9951, target_efl_mm=3.2180)
    assert result.delta_efl_pct == pytest.approx(-35.58, abs=0.05)
    assert result.score == pytest.approx(result.abs_delta_efl_pct)
    assert result.band == "gt30"


def test_result_is_frozen_dataclass_instance() -> None:
    result = score_seed_target_match(seed_efl_mm=4.0, target_efl_mm=4.0)
    assert isinstance(result, SeedTargetScore)
    with pytest.raises(AttributeError):
        result.score = 999.0  # type: ignore[misc]
