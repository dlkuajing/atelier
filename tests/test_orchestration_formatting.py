"""Tests for `app.core.orchestration.formatting` — P17 对抗审 M3 的单一格式化
真相源：页面 / xlsx / MD 报告共用，含"非零小值绝不显示 0.000 假零"守卫。
"""

from __future__ import annotations

from app.core.orchestration.candidate import MetricValue
from app.core.orchestration.formatting import (
    fmt_float,
    fmt_metric,
    fmt_optional_int,
    fmt_optional_target,
    fmt_pct,
    fmt_rel_violation,
    fmt_yes_no,
)

# ---------------------------------------------------------------------------
# 假零守卫（对抗审 M3 核心：0 < RI < 0.0005 曾显示 "0.000"）
# ---------------------------------------------------------------------------


def test_fmt_float_tiny_positive_never_renders_as_zero():
    assert fmt_float(0.0004) == "<0.001"
    assert fmt_float(0.0004999) == "<0.001"
    assert fmt_float(1e-12) == "<0.001"


def test_fmt_float_tiny_negative_never_renders_as_zero():
    assert fmt_float(-0.0004) == ">-0.001"


def test_fmt_float_true_zero_still_renders_as_zero():
    """真零是合法测量结果（如 Mode3 满口径边缘场 pass-fraction 精确为 0），
    必须照常显示 0.000——假零守卫不得反向把真零伪装成小量。"""
    assert fmt_float(0.0) == "0.000"


def test_fmt_float_normal_values_unchanged():
    assert fmt_float(0.812) == "0.812"
    assert fmt_float(3.8) == "3.800"
    assert fmt_float(0.001) == "0.001"  # exactly at the tick: representable, not fake zero
    assert fmt_float(12.6, precision=1) == "12.6"


def test_fmt_pct_tiny_positive_never_renders_as_zero_percent():
    assert fmt_pct(0.0004) == "<0.1%"
    assert fmt_pct(0.004, precision=0) == "<1%"


def test_fmt_pct_true_zero_and_normal_values():
    assert fmt_pct(0.0) == "0.0%"
    assert fmt_pct(0.007) == "0.7%"
    assert fmt_pct(1.0, precision=0) == "100%"


# ---------------------------------------------------------------------------
# MetricValue / optional / misc wrappers
# ---------------------------------------------------------------------------


def test_fmt_metric_unavailable_is_na():
    assert fmt_metric(MetricValue(value=None, status="unavailable")) == "N/A"


def test_fmt_metric_available_uses_fake_zero_guard():
    assert fmt_metric(MetricValue(value=0.0004, status="available")) == "<0.001"
    assert fmt_metric(MetricValue(value=0.32, status="available")) == "0.320"


def test_fmt_optional_target_none_is_unconstrained():
    assert fmt_optional_target(None) == "(unconstrained)"
    assert fmt_optional_target(4.35) == "4.350"
    assert fmt_optional_target(78.0, precision=1) == "78.0"


def test_fmt_optional_int():
    assert fmt_optional_int(None) == "(unconstrained)"
    assert fmt_optional_int(6) == "6"


def test_fmt_rel_violation():
    assert fmt_rel_violation(None) == "N/A"
    assert fmt_rel_violation(0.0066) == "0.7%"
    assert fmt_rel_violation(0.0004) == "<0.1%"  # fake-zero guard applies to percents too


def test_fmt_yes_no():
    assert fmt_yes_no(True) == "Yes"
    assert fmt_yes_no(False) == "No"
