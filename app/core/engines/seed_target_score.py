"""Seed-target EFL 距离打分 heuristic（几何距离代理，非良品判定）。

数据出处
--------
`.planning/loop/seed-target-matching-report.md`（2026-07-09，工作树
`spike/codev-target-convergence`）；8 seed x 3 target = 24 组合真机交叉矩阵，
CODE V `run_codev_target_autovig`（stage="A"，仅拉 EFL，extra_dof="asphere"）
产出的收敛/RMS 实测数据，逐行数据见同目录 `scratch_diag/match_matrix_results.tsv`。

公式依据
--------
``score = |ΔEFL%| + 1.0 * max(0, ΔEFL% - 20)``

- 第 1 项 |ΔEFL%|：报告 §5.1 显示对收敛内 post RMS 的 Spearman rho=+0.744
  （p<0.001，N=19），也是对收敛与否本身最强的单一预测子（对 conv 的
  rho=-0.645，p=0.001）——是本 heuristic 唯一的核心项。
- 第 2 项：报告 §5.3 揭示方向不对称——缩焦（target < seed EFL，带符号
  ΔEFL%<0）12/12 全收敛，最深达 -35.6% 仍收敛；拉焦（ΔEFL%>0）在 +25.1%
  起首次收敛失败，>+35% 全灭。因此仅对拉焦方向、且超过 +20%（在实测失败
  下界 +25.1% 之下留出安全边际）的部分线性加罚，斜率 1.0 是最保守的一档
  等权处理，不是拟合值。
- 分桶边界（<5 / 5-15 / 15-30 / >30）对应报告 §5.2 的 |ΔEFL%| 经验分桶，
  各桶收敛率与 post RMS 中位数见报告原表；**分桶判定用 score（含惩罚后），
  不是 abs_delta_efl_pct**——这样 +25.1% 这类"名义上刚过 25%"但已跨越实测
  失败边界的组合，会被推进最危险的分桶，语义与真机一致。

明确声明
--------
本模块输出的 `score`/`band` 是"收敛/质量风险的几何距离代理"，**不是**合格/
良品判定——量产可用与否的最终判断权与 [EXPERT] 背书始终在资深光学设计师
手里（见 AGENTS.md 北极星条款），任何调用方不得把 band 当作合格/优良/可用
的自动裁决。

伪信号清单（刻意未采用，勿加）
--------
报告 §5.1 排雷结果：
- **原生 EFL（seed 自身 EFL 绝对值）**：与带符号偏移强共线（target 取自池
  分布绝对值，长焦 seed 天然落负偏移侧），rho=+0.694 是共线伪信号，非独立
  信号。
- **baseline RMS（优化前 RMS）**：收敛内对 post RMS 无信号（rho=+0.117，
  p=0.63）；与 conv 的相关同样是共线伪影（差 baseline 的恰是长焦组）。
- **ZMX 面数**：弱信号且仅在 RMS 放大倍数一侧勉强过 0.05（p=0.040，N=19，
  样本太小不押注）。
- **原生 F#**：对 conv/post RMS 均不显著（p=0.60 / p=0.15）。

接入意图
--------
供 C1 Mode3（③优化落地）编排在候选 seed 排序/预警时调用；**本模块不接
`case_library` 现有路由**——那是 C1 实施阶段的整合工作，本文件只是独立可
测的打分单元。

限制（继承自源报告 §7）：N=24（收敛内 N=19），单一数据集自证；系数/阈值
精度不超过 ±1 分桶带宽；仅覆盖 EFL 一个距离维度（F#/IMH/TTL 未测）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

#: 分桶枚举——纯几何距离语义，不使用"优/良/可/险"等品质词，避免越过
#: [EXPERT] 合格判定红线。
SeedTargetBand = Literal["lt5", "5to15", "15to30", "gt30"]

EVIDENCE_NOTE = (
    "数据出处: .planning/loop/seed-target-matching-report.md "
    "(2026-07-09, N=24 真机交叉矩阵, 8 seed x 3 target, "
    "CODE V run_codev_target_autovig stage=A EFL-only, extra_dof=asphere). "
    "方向不对称: 缩焦(带符号ΔEFL%<0)N=12 全收敛(最深-35.6%); "
    "拉焦(ΔEFL%>0)自+25.1%起首次收敛失败, >+35%全灭。"
    "分桶按 score(含拉焦惩罚)判定, 非 abs_delta_efl_pct 判定。"
    "精度: 系数/阈值取整于分桶带宽, 误差不超过±1桶(N=24, 收敛内N=19, 单数据集自证)。"
    "非良品判定: score/band 是收敛/质量风险的几何距离代理, "
    "合格判定权在[EXPERT]资深评审, 本模块不代判。"
)

_PULL_PENALTY_THRESHOLD_PCT = 20.0
_PULL_PENALTY_SLOPE = 1.0

_BAND_LT5_UPPER = 5.0
_BAND_5TO15_UPPER = 15.0
_BAND_15TO30_UPPER = 30.0


@dataclass(frozen=True)
class SeedTargetScore:
    """一次 seed-target EFL 距离打分结果。"""

    delta_efl_pct: float
    abs_delta_efl_pct: float
    score: float
    band: SeedTargetBand
    evidence_note: str = EVIDENCE_NOTE

    def describe(self) -> dict[str, object]:
        return {
            "delta_efl_pct": self.delta_efl_pct,
            "abs_delta_efl_pct": self.abs_delta_efl_pct,
            "score": self.score,
            "band": self.band,
            "evidence_note": self.evidence_note,
        }


def score_seed_target_match(seed_efl_mm: float, target_efl_mm: float) -> SeedTargetScore:
    """按 seed 原生 EFL 与 target EFL 的距离打分（heuristic，非良品判定）。

    Args:
        seed_efl_mm: seed 原生（优化前）EFL，单位 mm，须为有限正数。
        target_efl_mm: 目标 EFL，单位 mm，须为有限正数。

    Returns:
        SeedTargetScore，含带符号/绝对偏移百分比、heuristic 分数与机器分桶。

    Raises:
        ValueError: seed_efl_mm 或 target_efl_mm 非有限（NaN/±inf）或 <= 0。
    """
    # NaN/inf 在 `<= 0` 比较下会静默穿透（NaN 所有比较均 False；+inf > 0），
    # 一路污染 delta/score/band——非有限值必须与非正值一样在入口就炸。
    if not math.isfinite(seed_efl_mm) or seed_efl_mm <= 0:
        raise ValueError(f"seed_efl_mm must be finite and > 0, got {seed_efl_mm}")
    if not math.isfinite(target_efl_mm) or target_efl_mm <= 0:
        raise ValueError(f"target_efl_mm must be finite and > 0, got {target_efl_mm}")

    delta_efl_pct = (target_efl_mm - seed_efl_mm) / seed_efl_mm * 100.0
    abs_delta_efl_pct = abs(delta_efl_pct)
    pull_penalty = _PULL_PENALTY_SLOPE * max(0.0, delta_efl_pct - _PULL_PENALTY_THRESHOLD_PCT)
    score = abs_delta_efl_pct + pull_penalty
    band = _band_for_score(score)

    return SeedTargetScore(
        delta_efl_pct=delta_efl_pct,
        abs_delta_efl_pct=abs_delta_efl_pct,
        score=score,
        band=band,
    )


def _band_for_score(score: float) -> SeedTargetBand:
    """按 score（非 abs_delta_efl_pct）划分机器分桶，见模块 docstring 公式依据。"""
    if score < _BAND_LT5_UPPER:
        return "lt5"
    if score < _BAND_5TO15_UPPER:
        return "5to15"
    if score < _BAND_15TO30_UPPER:
        return "15to30"
    return "gt30"
