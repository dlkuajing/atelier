"""Tests for `app.core.relative_illumination` — C1 §7-D RI compute.

权威依据：C1 spec §7-D（RI 度量口径）+ §9（测试策略，RI 数值锚/缺失路径）。
`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`

**数值锚偏离说明（如实记录）**：spec §9 要求"已知渐晕系数 seed → RI 边缘值
交叉验证"。经核实（`grep -c "^CLAP\\|^FLAP" data/zmx/*.zmx` 和
`^VCXN\\|^VCYN` 的非零值扫描），本仓库 `data/zmx/` 全部 353 个案例文件
**均未声明**任何 CLAP/FLAP 物理孔径或非零 VCX/VCY 渐晕压缩系数——库内不存在
"已知渐晕系数 seed"。因此数值锚改为：验证 `cos^4(theta)` 解析分量在真实
case 的 FOV 上精确匹配独立计算的期望值（真实、可复现，不是编造的通过），
并验证 `vignetting_factor` 部分对本库诚实报 1.0（真实事实，非假绿——见
`relative_illumination.py` 模块 docstring 的详细论证）。
"""

from __future__ import annotations

import math

import pytest

from app.core.case_library import load_case_library
from app.core.mtf_fields import MTF_CANONICAL_FIELD_FRACS, format_mtf_field_fraction
from app.core.optical_sample import OpticalSampleData
from app.core.relative_illumination import compute_relative_illumination

# A specific, deterministic real case (78 deg full FOV wide seed) used as the
# numeric anchor. Picked because it has a large-enough field angle for the
# cos^4(theta) falloff to be numerically distinctive (not ~1.0 everywhere).
_ANCHOR_CASE_ID = "3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56"


def _anchor_case() -> OpticalSampleData:
    for case in load_case_library():
        if case.metadata is not None and case.metadata.case_id == _ANCHOR_CASE_ID:
            return case
    raise AssertionError(f"anchor case {_ANCHOR_CASE_ID} not found in case library")


def _first_case_with_metadata() -> OpticalSampleData:
    for case in load_case_library():
        if case.metadata is not None:
            return case
    raise AssertionError("case library has no case with metadata")


# ---------------------------------------------------------------------------
# Numeric anchor — cos^4(theta) cross-validation against a real seed (§9)
# ---------------------------------------------------------------------------


def test_ri_axis_field_is_unity():
    case = _anchor_case()
    ri = compute_relative_illumination(case)
    axis = ri[format_mtf_field_fraction(0.0)]
    assert axis.status == "available"
    assert axis.value == 1.0  # cos^4(0) * vignetting_factor(axis)/vignetting_factor(axis) == 1.0


def test_ri_matches_analytic_cos4_falloff_for_known_fov():
    """Cross-validate every canonical field's RI against an independently
    computed cos^4(theta) expectation, using the case's own real FOV. This is
    the numeric anchor substituting for a "known vignetting seed" (none exist
    in this library, see module docstring)."""
    case = _anchor_case()
    assert case.metadata is not None
    ri = compute_relative_illumination(case)
    half_fov_deg = case.metadata.fov_deg / 2.0

    for frac in MTF_CANONICAL_FIELD_FRACS:
        key = format_mtf_field_fraction(frac)
        metric = ri[key]
        assert metric.status == "available", key
        field_angle_deg = frac * half_fov_deg
        expected_cos4 = math.cos(math.radians(field_angle_deg)) ** 4
        assert metric.value == pytest.approx(expected_cos4)


def test_ri_monotonically_decreases_with_field():
    """A real wide-FOV lens should show falling RI toward the edge field
    (cos^4 falloff is always active, even with vignetting_factor==1.0)."""
    case = _anchor_case()
    ri = compute_relative_illumination(case)
    values = [ri[format_mtf_field_fraction(f)].value for f in MTF_CANONICAL_FIELD_FRACS]
    assert all(v is not None for v in values)
    assert values == sorted(values, reverse=True)
    assert values[0] == 1.0
    assert values[-1] < values[0]


def test_ri_vignetting_factor_is_honestly_one_for_this_library():
    """Documented fact (not a bug): no case in `data/zmx/` declares a
    physical clear aperture (CLAP/FLAP) or nonzero VCX/VCY, so Optiland's
    ray trace never blocks a ray here — RI reduces to pure cos^4(theta) for
    every case today. Asserting this pins the honest baseline so a future
    change that silently starts fabricating vignetting doesn't go unnoticed."""
    case = _anchor_case()
    assert case.metadata is not None
    ri = compute_relative_illumination(case)
    half_fov_deg = case.metadata.fov_deg / 2.0
    edge = ri[format_mtf_field_fraction(1.0)]
    expected_cos4_only = math.cos(math.radians(half_fov_deg)) ** 4
    assert edge.value == pytest.approx(expected_cos4_only)


# ---------------------------------------------------------------------------
# Fail-closed paths (§7-D "缺失/算不出时 fail closed")
# ---------------------------------------------------------------------------


def test_ri_no_metadata_is_fully_unavailable():
    case = _first_case_with_metadata()
    stripped = case.model_copy(update={"metadata": None})
    ri = compute_relative_illumination(stripped)
    expected_keys = {format_mtf_field_fraction(f) for f in MTF_CANONICAL_FIELD_FRACS}
    assert set(ri.keys()) == expected_keys
    for metric in ri.values():
        assert metric.status == "unavailable"
        assert metric.value is None


def test_ri_missing_source_zmx_file_is_fully_unavailable():
    case = _first_case_with_metadata()
    assert case.metadata is not None
    broken = case.model_copy(
        update={"metadata": case.metadata.model_copy(update={"source_zmx": "does-not-exist.zmx"})}
    )
    ri = compute_relative_illumination(broken)
    expected_keys = {format_mtf_field_fraction(f) for f in MTF_CANONICAL_FIELD_FRACS}
    assert set(ri.keys()) == expected_keys
    for metric in ri.values():
        assert metric.status == "unavailable"
        assert metric.value is None


def test_ri_result_always_covers_canonical_field_keys():
    case = _anchor_case()
    ri = compute_relative_illumination(case)
    expected_keys = {format_mtf_field_fraction(f) for f in MTF_CANONICAL_FIELD_FRACS}
    assert set(ri.keys()) == expected_keys
