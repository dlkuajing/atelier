"""Shared display formatting for every candidate-set surface (P17 对抗审 M3).

单一真相源：候选集页面（`app/main.py` 的 `_candidate_*_context`）、xlsx 导出
（`export.py`）、离线 MD 报告（`scripts/c1_orchestrate.py`）都从这里取格式化
函数——同一 payload 经同一格式化器产出同一字符串，"页面数字 = 带走物数字"
才字面成立（对抗审 M3 指出此前 xlsx 写原始 float、页面写三位小数字符串，
同源对象成立但显示口径不一致）。

**假零守卫（诚实红线）**：非零值绝不因显示精度塌缩成 "0.000"/"0.0%" 假零
（对抗审 M3：`0 < RI < 0.0005` 曾显示 "0.000"，资深会合理读成真实零照度）。
小于最小显示刻度的非零值显示为 `<0.001`（负值 `>-0.001`）；**真零仍显示
"0.000"**——真零是合法测量结果（如 Mode3 满口径边缘场 pass-fraction 精确
为 0），不能反向伪装成小量。
"""

from __future__ import annotations

from app.core.orchestration.candidate import MetricValue


def fmt_float(value: float, *, precision: int = 3) -> str:
    """`f"{value:.{precision}f}"` + 假零守卫：非零但四舍五入后为零的值显示
    `<最小刻度`（负值 `>-最小刻度`），真零照常显示。"""
    formatted = f"{value:.{precision}f}"
    if value != 0.0 and float(formatted) == 0.0:
        tick = 10.0 ** -precision
        if value > 0:
            return f"<{tick:.{precision}f}"
        return f">-{tick:.{precision}f}"
    return formatted


def fmt_pct(value: float, *, precision: int = 1) -> str:
    """百分比口径的 `fmt_float`：同样的假零守卫（`0 < x < 最小百分比刻度`
    显示 `<0.1%` 而不是 `0.0%`）。"""
    formatted = f"{value:.{precision}%}"
    if value != 0.0 and float(formatted.rstrip("%")) == 0.0:
        tick = 10.0 ** -precision
        if value > 0:
            return f"<{tick:.{precision}f}%"
        return f">-{tick:.{precision}f}%"
    return formatted


def fmt_metric(metric: MetricValue, *, precision: int = 3) -> str:
    """`MetricValue` → 显示字符串；unavailable 恒 "N/A"（fail-closed 的显示面）。"""
    if metric.status == "unavailable" or metric.value is None:
        return "N/A"
    return fmt_float(metric.value, precision=precision)


def fmt_optional_target(value: float | None, *, precision: int = 3) -> str:
    """target 数值（None = unconstrained）的统一口径。"""
    return "(unconstrained)" if value is None else fmt_float(float(value), precision=precision)


def fmt_optional_int(value: int | None) -> str:
    return "(unconstrained)" if value is None else str(value)


def fmt_rel_violation(rel: float | None) -> str:
    """相对偏差：页面与导出物统一为 1 位小数百分比（此前 xlsx 落 0..1 原始
    比率、页面显示百分比——同一数字两种单位表达，对抗审 M3 指名）。"""
    return "N/A" if rel is None else fmt_pct(rel, precision=1)


def fmt_yes_no(flag: bool) -> str:
    return "Yes" if flag else "No"
