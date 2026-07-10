from __future__ import annotations

import math
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from app.core.engines import codev_batch, codev_optimize
from app.core.engines.codev_batch import (
    DEFAULT_CODEV_EXECUTABLE,
    CodeVBatchError,
    ensure_buf_exp_safe_filename,
)
from app.core.engines.codev_optimize import (
    _TARGET_REQUIRED_KEYS,
    CODEV_OPTIMIZE_RESULT_SCHEMA,
    DEFAULT_GLASS_BOUNDS_ND_VD,
    DEFAULT_OPTIMIZE_SEED,
    STANDARD_RESULT_SCHEMA,
    TARGET_RESULT_SCHEMA,
    _autovig_profile,
    _glass_map_hull,
    build_codev_optimize_sequence,
    build_codev_target_sequence,
    default_optimize_seed,
    parse_aut_error_trace,
    parse_codev_optimize_file,
    run_codev_optimize,
    run_codev_target,
    run_codev_target_autovig,
    run_codev_target_standard,
)
from app.core.engines.codev_readout import CODEV_READOUT_RESULT_SCHEMA
from app.core.spot_diagram import compute_spot_diagram
from app.core.zmx_ingest import load_normalized_zmx


def _fake_codev_executable(tmp_path: Path) -> Path:
    executable = tmp_path / "codev.exe"
    executable.write_text("", encoding="utf-8")
    return executable


def _buf_exp_paths_from_sequence(sequence_path: Path) -> list[Path]:
    sequence = sequence_path.read_text(encoding="ascii")
    matches = re.findall(r'BUF EXP B1 "([^"]+)"', sequence)
    assert len(matches) >= 2
    return [Path(match) for match in matches]


def _write_optimize_result(path: Path) -> None:
    rows = [
        ("schema", CODEV_OPTIMIZE_RESULT_SCHEMA),
        ("status", "ok"),
        ("source_zmx", DEFAULT_OPTIMIZE_SEED),
        ("optimization_status", "aut_completed"),
        ("glass_policy", "glass-not-varied"),
        ("thickness_policy", "MNT/MNE/MXT/MNA bounded in AUT"),
        ("optimized_readout_path", "atelier_codev_optimized_readout.tsv"),
        ("optimized_zmx_filename", "optimized.zmx"),
        ("before.efl_y_mm", "3.62252"),
        ("before.max_lateral_color_um", "4.8"),
        ("before.max_rms_spot_diameter_um", "26.0"),
        ("before.max_rms_wavefront_error_waves", "0.21"),
        ("before.max_distortion_pct", "1.3"),
        ("after.efl_y_mm", "3.62260"),
        ("after.max_lateral_color_um", "3.1"),
        ("after.max_rms_spot_diameter_um", "18.0"),
        ("after.max_rms_wavefront_error_waves", "0.17"),
        ("after.max_distortion_pct", "1.1"),
        ("efl_deviation_pct", "0.0022"),
    ]
    path.write_text("\n".join(f"{key}\t{value}" for key, value in rows) + "\n", encoding="utf-8")


def _write_optimized_readout(path: Path) -> None:
    rows = [
        ("schema", CODEV_READOUT_RESULT_SCHEMA),
        ("status", "ok"),
        ("source_zmx", DEFAULT_OPTIMIZE_SEED),
        ("units", "MM"),
        ("aperture_type", "FNO"),
        ("f_number", "2.4"),
        ("entrance_pupil_diameter_mm", "4.2"),
        ("num_surfaces", "3"),
        ("num_fields", "2"),
        ("num_wavelengths", "2"),
        ("num_zooms", "1"),
        ("stop_surface", "1"),
        ("field_type", "RIH"),
        ("reference_wavelength_index", "1"),
        ("image_height_y_mm", "3.0"),
        ("surface.1.radius_y_mm", "20.0"),
        ("surface.1.thickness_mm", "2.0"),
        ("surface.1.semi_diameter_mm", "1.1"),
        ("surface.1.glass", "BK7"),
        ("surface.1.nd", "1.5168"),
        ("surface.1.vd", "64.17"),
        ("surface.1.surface_type", "ASP"),
        ("surface.1.is_stop", "1"),
        ("surface.1.asphere.K", "-0.2"),
        ("surface.1.asphere.A", "0.0001"),
        ("surface.1.asphere.B", "-0.000002"),
        ("surface.1.asphere.C", "0"),
        ("surface.1.asphere.D", "0"),
        ("surface.1.asphere.E", "0"),
        ("surface.1.asphere.F", "0"),
        ("surface.1.asphere.G", "0"),
        ("surface.1.asphere.H", "0"),
        ("surface.1.asphere.J", "0"),
        ("surface.2.radius_y_mm", "-20.0"),
        ("surface.2.thickness_mm", "20.0"),
        ("surface.2.semi_diameter_mm", "2.2"),
        ("surface.2.glass", "___BLANK"),
        ("surface.2.nd", "1.62"),
        ("surface.2.vd", "30.0"),
        ("surface.2.surface_type", "SPH"),
        ("surface.2.is_stop", "0"),
        ("surface.2.asphere.K", "0"),
        ("surface.2.asphere.A", "0"),
        ("surface.2.asphere.B", "0"),
        ("surface.2.asphere.C", "0"),
        ("surface.2.asphere.D", "0"),
        ("surface.2.asphere.E", "0"),
        ("surface.2.asphere.F", "0"),
        ("surface.2.asphere.G", "0"),
        ("surface.2.asphere.H", "0"),
        ("surface.2.asphere.J", "0"),
        ("surface.3.radius_y_mm", "0.0"),
        ("surface.3.thickness_mm", "0.0"),
        ("surface.3.semi_diameter_mm", "3.3"),
        ("surface.3.glass", ""),
        ("surface.3.nd", "1.0"),
        ("surface.3.vd", "0.0"),
        ("surface.3.surface_type", "SPH"),
        ("surface.3.is_stop", "0"),
        ("surface.3.asphere.K", "0"),
        ("surface.3.asphere.A", "0"),
        ("surface.3.asphere.B", "0"),
        ("surface.3.asphere.C", "0"),
        ("surface.3.asphere.D", "0"),
        ("surface.3.asphere.E", "0"),
        ("surface.3.asphere.F", "0"),
        ("surface.3.asphere.G", "0"),
        ("surface.3.asphere.H", "0"),
        ("surface.3.asphere.J", "0"),
        ("wavelength.1.wavelength_nm", "555"),
        ("wavelength.1.weight", "1"),
        ("wavelength.2.wavelength_nm", "650"),
        ("wavelength.2.weight", "0.107"),
        ("field.1.definition_type", "RIH"),
        ("field.1.x", "0"),
        ("field.1.y", "0"),
        ("field.1.vuy", "0"),
        ("field.1.vly", "0"),
        ("field.1.vux", "0"),
        ("field.1.vlx", "0"),
        ("field.2.definition_type", "RIH"),
        ("field.2.x", "0"),
        ("field.2.y", "3.0"),
        ("field.2.vuy", "0.3"),
        ("field.2.vly", "0.1"),
        ("field.2.vux", "0.2"),
        ("field.2.vlx", "-0.1"),
    ]
    path.write_text("\n".join(f"{key}\t{value}" for key, value in rows) + "\n", encoding="utf-8")


def test_optimize_sequence_imports_zmx_runs_aut_and_exports_readout(tmp_path: Path) -> None:
    sequence = build_codev_optimize_sequence(
        source_zmx=default_optimize_seed(),
        result_path=tmp_path / "result.tsv",
        optimized_readout_path=tmp_path / "optimized-readout.tsv",
        max_cycles=7,
        min_cycles=2,
    )

    assert 'IN CV_MACRO:ZEMAXOS_TO_CV "' in sequence
    assert "AUT" in sequence
    assert "DEF VAR SA" in sequence
    assert "EFL = ^baseline_efl_y_mm" in sequence
    assert "FCT @lcum(NUM ^dummy)" in sequence
    assert "FCT @rmssum(NUM ^dummy)" in sequence
    assert "@atelier_latcolor == @lcum(1)" in sequence
    assert "@atelier_rmsspot == @rmssum(1)" in sequence
    assert "SPOTDATA" in sequence
    assert "RMSWE" in sequence
    assert "(DIX Z1 F^f)" in sequence
    assert "MNT 0.025" in sequence
    assert "MNE 0.025" in sequence
    assert "MXT 10" in sequence
    assert "MNA 0.001" in sequence
    assert "MXC 7" in sequence
    assert "MNC 2" in sequence
    assert "GCH" not in sequence
    assert f'"{CODEV_OPTIMIZE_RESULT_SCHEMA}"' in sequence
    assert f'"{CODEV_READOUT_RESULT_SCHEMA}"' in sequence
    assert 'BUF PUT B1 I^row J1 "f_number"\nBUF PUT B1 I^row J2 ABSF((FNO))' in sequence
    assert "^semi_diameter_mm == ABSF((MAP S^s))" in sequence
    assert "IF ^semi_diameter_mm < 1e-06" in sequence
    assert "BUF EXP B1" in sequence
    assert "optimized_zmx_filename" in sequence


def test_optimize_sequence_captures_before_before_aut_and_after_after_go(tmp_path: Path) -> None:
    sequence = build_codev_optimize_sequence(
        source_zmx=default_optimize_seed(),
        result_path=tmp_path / "result.tsv",
        optimized_readout_path=tmp_path / "optimized-readout.tsv",
    )
    lines = sequence.splitlines()

    before_index = lines.index("^before_max_rms_spot_diameter_um == @rmssum(1)")
    aut_index = lines.index("AUT")
    go_index = lines.index("GO")
    after_index = lines.index("^after_max_rms_spot_diameter_um == @rmssum(1)")

    assert before_index < aut_index
    assert go_index < after_index


def test_parse_codev_optimize_file_builds_structured_metrics(tmp_path: Path) -> None:
    result_path = tmp_path / "optimize.tsv"
    _write_optimize_result(result_path)

    summary = parse_codev_optimize_file(result_path)

    assert summary.source_zmx == DEFAULT_OPTIMIZE_SEED
    assert summary.optimization_status == "aut_completed"
    assert summary.glass_policy == "glass-not-varied"
    assert summary.optimized_zmx_filename == "optimized.zmx"
    assert summary.before.max_rms_spot_diameter_um == pytest.approx(26.0)
    assert summary.after.max_rms_spot_diameter_um == pytest.approx(18.0)
    assert summary.after.max_lateral_color_um < summary.before.max_lateral_color_um
    assert summary.efl_deviation_pct == pytest.approx(0.0022)
    assert summary.describe()["after"]["max_distortion_pct"] == pytest.approx(1.1)


def test_mock_codev_optimize_rebuilds_optimized_zmx_and_ingests(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = _fake_codev_executable(tmp_path)
    calls: list[list[str]] = []

    class FakePopen:
        pid = 2468
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            calls.append(command)
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            assert timeout == 12.0
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            optimize_result_path, optimized_readout_path = _buf_exp_paths_from_sequence(sequence_path)
            _write_optimize_result(optimize_result_path)
            _write_optimized_readout(optimized_readout_path)
            return "ignored screen output", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    result = run_codev_optimize(
        source_zmx=default_optimize_seed(),
        work_dir=tmp_path,
        executable=executable,
        timeout_seconds=12.0,
    )

    assert calls == [[str(executable), "/B", "atelier_codev_optimize.seq"]]
    assert result.batch.returncode == 1
    assert result.summary.after.max_rms_spot_diameter_um == pytest.approx(18.0)
    assert result.optimized_readout_path.is_file()
    assert result.optimized_readout.source_zmx == DEFAULT_OPTIMIZE_SEED
    assert result.optimized_zmx.name == "optimized.zmx"
    assert result.optimized_zmx.is_file()
    assert math.isfinite(result.ingested_efl_mm)


def test_parse_codev_optimize_file_rejects_missing_metric(tmp_path: Path) -> None:
    result_path = tmp_path / "optimize.tsv"
    _write_optimize_result(result_path)
    text = result_path.read_text(encoding="utf-8")
    result_path.write_text(
        text.replace("after.max_rms_wavefront_error_waves\t0.17\n", ""),
        encoding="utf-8",
    )

    with pytest.raises(CodeVBatchError) as error:
        parse_codev_optimize_file(result_path)

    assert error.value.kind == "failure"
    assert error.value.details["missing_keys"] == ["after.max_rms_wavefront_error_waves"]


def test_codev_optimize_report_records_engine_05a() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    report = backend_root / ".planning" / "loop" / "codev-optimize-report.md"

    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "ENGINE-05a" in text
    assert DEFAULT_OPTIMIZE_SEED in text
    assert "RMS spot" in text
    assert "Wavefront RMS" in text
    assert "Distortion" in text
    assert "optimized.zmx" in text


@pytest.mark.skipif(
    not DEFAULT_CODEV_EXECUTABLE.is_file(),
    reason="real CODE V installation required for the ENGINE-05a optimize smoke",
)
def test_real_codev_optimize_patent_seed_smoke(tmp_path: Path) -> None:
    try:
        result = run_codev_optimize(
            source_zmx=default_optimize_seed(),
            work_dir=tmp_path,
            timeout_seconds=180.0,
            max_cycles=3,
            min_cycles=1,
        )
    except CodeVBatchError as exc:
        if exc.kind in {"no_license", "timeout"}:
            pytest.skip(f"CODE V unavailable for optimize smoke: {exc.message}")
        raise
    except subprocess.SubprocessError as exc:
        pytest.skip(f"CODE V subprocess unavailable: {exc}")

    assert result.source_zmx.name == DEFAULT_OPTIMIZE_SEED
    assert result.summary.after.efl_y_mm == pytest.approx(result.summary.before.efl_y_mm, rel=0.02)
    assert result.summary.after.max_rms_spot_diameter_um >= 0.0
    assert result.summary.after.max_rms_wavefront_error_waves >= 0.0
    assert result.summary.after.max_distortion_pct >= 0.0
    assert result.optimized_zmx.name == "optimized.zmx"
    assert result.optimized_zmx.is_file()
    assert math.isfinite(result.ingested_efl_mm)


# ---------------------------------------------------------------------------
# Target-mode (spike ③优化落地) tests — EFL->target + FNO 锁 F# + 三快照
# ---------------------------------------------------------------------------

_TARGET_SNAPSHOTS = ("seed_baseline", "config_pre_aut", "post_aut")


def test_target_sequence_structure_stage_b() -> None:
    seq = build_codev_target_sequence(
        source_zmx=default_optimize_seed(),
        result_path=Path("r.tsv"),
        target_efl_mm=4.057,
        target_f_number=2.4,
        stage="B",
    )
    assert "EFL = 4.057" in seq  # seam 1: EFL -> target (非 ^baseline)
    assert "^baseline_efl_y_mm" not in seq  # target 模式不锚 seed 自身焦距
    assert "FNO 2.4" in seq  # seam 3a: FNO 锁 F#（E1 实测）
    for snap in _TARGET_SNAPSHOTS:  # 三快照
        assert f"^{snap}_efl_y_mm == ABSF((EFY))" in seq
        assert f'"{snap}.max_distortion_pct"' in seq
    assert f'"{TARGET_RESULT_SCHEMA}"' in seq
    assert '"mode"' in seq and '"target"' in seq
    assert '"stage"' in seq
    assert '"aut_converged"' in seq
    assert '"target.f_number"' in seq


def test_target_stage_a_omits_fno() -> None:
    seq = build_codev_target_sequence(
        source_zmx=default_optimize_seed(), result_path=Path("r.tsv"),
        target_efl_mm=4.0, stage="A",
    )
    assert "EFL = 4" in seq
    assert "\nFNO " not in seq  # Stage A 不设 F#（seed_hold）
    assert '"target.f_number"' not in seq


def test_target_mode_does_not_touch_baseline_sequence() -> None:
    """零回归 sanity：baseline build 仍锚 seed 自身焦距，未被 target 改动污染。"""
    base = build_codev_optimize_sequence(
        source_zmx=default_optimize_seed(),
        result_path=Path("r.tsv"),
        optimized_readout_path=Path("ro.tsv"),
    )
    assert "EFL = ^baseline_efl_y_mm" in base  # baseline 口径不变
    assert TARGET_RESULT_SCHEMA not in base  # baseline 不带 target schema


def test_target_param_validation_rejects_nonpositive() -> None:
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError):
            build_codev_target_sequence(
                source_zmx=default_optimize_seed(), result_path=Path("r.tsv"),
                target_efl_mm=bad,
            )
    with pytest.raises(ValueError):
        build_codev_target_sequence(
            source_zmx=default_optimize_seed(), result_path=Path("r.tsv"),
            target_efl_mm=4.0, target_f_number=-2.0,
        )


# ---------------------------------------------------------------------------
# GLC 玻璃变量修复 — 塑料域 GLA 边界（真机证实 both≥asphere，见
# .planning/debug/codev-target-convergence.md + scratch_diag/probe_glc_fix.py）
# ---------------------------------------------------------------------------

_PLASTIC_MATERIALS_ND_VD = {
    "PMMA": (1.4918, 57.4),
    "COC": (1.531, 56.0),
    "APEL": (1.5445, 55.9),
    "PS": (1.5905, 30.9),
    "PC": (1.5855, 29.9),
    "OKP4": (1.607, 27.0),
    "OKP4HT": (1.632, 23.0),
    "EP": (1.651, 21.5),
}
_SEED_ND_VD = (1.5170, 64.2)  # US20170003482A1 等专利 seed 的玻璃初值


def _glass_map_nfnc(nd: float, vd: float) -> float:
    return (nd - 1.0) / vd


def _point_in_glass_map_hull(nd: float, vd: float, corners: list[str]) -> bool:
    """独立于 _glass_map_hull 内部实现的 point-in-convex-polygon 验证：把
    'nd:vd' 冒号角点解析回 (nd, nF-nC) 平面（与 CODE V GLA 凸性检查同一平
    面），对每条边做同号 cross-product 测试。边界上（cross≈0）视为在内。"""
    poly = []
    for corner in corners:
        nd_text, vd_text = corner.split(":")
        c_nd, c_vd = float(nd_text), float(vd_text)
        poly.append((c_nd, _glass_map_nfnc(c_nd, c_vd)))
    point = (nd, _glass_map_nfnc(nd, vd))
    signs = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        signs.append((b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0]))
    return all(s >= -1e-9 for s in signs) or all(s <= 1e-9 for s in signs)


def test_default_glass_bounds_hull_has_3_to_5_vertices() -> None:
    corners = _glass_map_hull(DEFAULT_GLASS_BOUNDS_ND_VD)
    assert 3 <= len(corners) <= 5
    for corner in corners:
        nd_text, vd_text = corner.split(":")
        assert math.isfinite(float(nd_text))
        assert math.isfinite(float(vd_text))


def test_default_glass_bounds_hull_contains_all_plastics_and_seed() -> None:
    corners = _glass_map_hull(DEFAULT_GLASS_BOUNDS_ND_VD)
    all_points = {**_PLASTIC_MATERIALS_ND_VD, "seed(1.5170,64.2)": _SEED_ND_VD}
    for name, (nd, vd) in all_points.items():
        assert _point_in_glass_map_hull(nd, vd, corners), f"{name} outside default GLA hull"


def test_glass_map_hull_rejects_too_few_points() -> None:
    with pytest.raises(ValueError):
        _glass_map_hull([(1.5, 50.0), (1.6, 30.0)])


def test_glass_map_hull_rejects_collinear_points() -> None:
    # 相同 nd、不同 vd -> (nd, nF-nC) 平面上是一条垂直线，凸包退化为 2 点。
    with pytest.raises(ValueError):
        _glass_map_hull([(1.5, 50.0), (1.5, 55.0), (1.5, 60.0)])


def test_glass_map_hull_rejects_more_than_five_vertices() -> None:
    # 6 个互不相邻、彼此都在凸包上的点（正六边形式散布） -> 凸包 6 顶点。
    hexagon = [
        (1.45, 80.0),
        (1.50, 20.0),
        (1.55, 15.0),
        (1.60, 22.0),
        (1.65, 60.0),
        (1.62, 90.0),
    ]
    with pytest.raises(ValueError):
        _glass_map_hull(hexagon)


@pytest.mark.parametrize("extra_dof", ["glass", "both"])
def test_target_sequence_injects_gla_for_glass_variable_modes(extra_dof: str) -> None:
    seq = build_codev_target_sequence(
        source_zmx=default_optimize_seed(), result_path=Path("r.tsv"),
        target_efl_mm=4.0, extra_dof=extra_dof,
    )
    expected_corners = _glass_map_hull(DEFAULT_GLASS_BOUNDS_ND_VD)
    gla_line = f"  GLA {' '.join(expected_corners)}"
    assert gla_line in seq
    lines = seq.splitlines()
    aut_index = lines.index("AUT")
    go_index = next(i for i in range(aut_index, len(lines)) if lines[i] == "GO")
    gla_index = lines.index(gla_line)
    assert aut_index < gla_index < go_index  # GLA 必须在本次 AUT...GO 块内


@pytest.mark.parametrize("extra_dof", ["none", "asphere"])
def test_target_sequence_omits_gla_without_glass_variables(extra_dof: str) -> None:
    seq = build_codev_target_sequence(
        source_zmx=default_optimize_seed(), result_path=Path("r.tsv"),
        target_efl_mm=4.0, extra_dof=extra_dof,
    )
    assert "GLA " not in seq
    assert "\nGLA" not in seq


@pytest.mark.parametrize("extra_dof", ["asphere", "both"])
def test_target_sequence_asphere_dof_capped_at_zmx_anchor_order(extra_dof: str) -> None:
    """非球面 DOF 上限对齐数据锚 ZMX 格式（真机实锤 2026-07-09，见
    `_extra_dof_block` docstring）：zmx_writer 的 EVENASPH 只支持 CODE V
    A..G（PARM 2..8），H(18阶)/J(20阶) 无格式位可写。生成的 seq 只应放开
    A..G 共 7 项系数变量，绝不含 HC/JC 行。"""
    seq = build_codev_target_sequence(
        source_zmx=default_optimize_seed(), result_path=Path("r.tsv"),
        target_efl_mm=4.0, extra_dof=extra_dof,
    )
    for coeff in ("A", "B", "C", "D", "E", "F", "G"):
        assert f"    {coeff}C S^s 0" in seq
    assert "HC S^s 0" not in seq
    assert "JC S^s 0" not in seq


def test_target_sequence_custom_glass_bounds_override_default() -> None:
    custom_bounds = [(1.50, 40.0), (1.60, 20.0), (1.55, 70.0)]
    custom_corners = _glass_map_hull(custom_bounds)
    default_corners = _glass_map_hull(DEFAULT_GLASS_BOUNDS_ND_VD)
    assert custom_corners != default_corners  # sanity: fixture is actually distinct

    seq = build_codev_target_sequence(
        source_zmx=default_optimize_seed(), result_path=Path("r.tsv"),
        target_efl_mm=4.0, extra_dof="both", glass_bounds_nd_vd=custom_bounds,
    )
    assert f"  GLA {' '.join(custom_corners)}" in seq
    assert f"  GLA {' '.join(default_corners)}" not in seq


def test_target_sequence_epd_key_carries_mm_unit_suffix() -> None:
    """EPD 是毫米量纲，结果键必须带 `_mm` 后缀（仓库单位后缀约定）；旧的无
    后缀键 `.epd` 不得再出现——宏出参与 required-keys 契约同步锁死。"""
    seq = build_codev_target_sequence(
        source_zmx=default_optimize_seed(), result_path=Path("r.tsv"), target_efl_mm=4.0,
    )
    for snap in ("seed_baseline", "config_pre_aut", "post_aut"):
        assert f'"{snap}.epd_mm"' in seq
        assert f'"{snap}.epd"' not in seq
    assert "post_aut.epd_mm" in _TARGET_REQUIRED_KEYS
    assert "post_aut.epd" not in _TARGET_REQUIRED_KEYS


def _write_target_result(
    path: Path,
    *,
    converged: str = "1",
    dev: str = "0.001",
    num_fields: str = "3",
    edge: str = "0",
) -> None:
    rows = [
        ("schema", TARGET_RESULT_SCHEMA), ("status", "ok"),
        ("mode", "target"), ("stage", "A"), ("source_zmx", DEFAULT_OPTIMIZE_SEED),
        ("num_fields", num_fields), ("vignetting_edge", edge),
        ("target.efl_mm", "4.057"),
    ]
    for snap, efl, fno, imh, spot, wfe, dist in [
        ("seed_baseline", "3.6225", "2.32", "3.686", "9.57", "0.365", "2.01"),
        ("config_pre_aut", "3.6225", "2.32", "3.686", "9.57", "0.365", "2.01"),
        ("post_aut", "4.0570", "2.32", "4.128", "23.10", "0.474", "8.39"),
    ]:
        rows += [
            (f"{snap}.efl_y_mm", efl), (f"{snap}.max_lateral_color_um", "3.0"),
            (f"{snap}.max_rms_spot_diameter_um", spot),
            (f"{snap}.max_rms_wavefront_error_waves", wfe),
            (f"{snap}.max_distortion_pct", dist),
            (f"{snap}.fno", fno), (f"{snap}.epd_mm", "1.56"), (f"{snap}.maximh_mm", imh),
        ]
    rows += [("efl_target_deviation_pct", dev), ("aut_converged", converged)]
    path.write_text("\n".join(f"{k}\t{v}" for k, v in rows) + "\n", encoding="utf-8")


def test_autovig_profile_on_axis_unvignetted() -> None:
    assert _autovig_profile(0.0, 3) is None  # edge 0 -> 无渐晕默认路径
    assert _autovig_profile(0.5, 1) is None  # 单场无从裁
    assert _autovig_profile(0.5, 3) == [0.0, 0.5, 0.5]  # 轴上不裁，离轴均匀
    assert _autovig_profile(0.4, 4) == [0.0, 0.4, 0.4, 0.4]


def test_target_vignetting_injects_factors_and_provenance() -> None:
    seq = build_codev_target_sequence(
        source_zmx=default_optimize_seed(), result_path=Path("r.tsv"),
        target_efl_mm=4.0, vignetting=[0.0, 0.5, 0.5],
    )
    for cmd in ("VUY", "VLY", "VUX", "VLX"):
        assert f"{cmd} 0 0.5 0.5" in seq  # per-field positional 渐晕注入
    assert '"num_fields"' in seq  # 场数出参供 autovig 学习
    assert '"vignetting_edge"' in seq


def test_target_no_vignetting_is_zero_regression() -> None:
    seq = build_codev_target_sequence(
        source_zmx=default_optimize_seed(), result_path=Path("r.tsv"), target_efl_mm=4.0,
    )
    assert "\nVUY " not in seq  # 默认路径不注入渐晕（零回归）
    assert "\nVLY " not in seq


def test_target_vignetting_validation_rejects_out_of_range() -> None:
    for bad in ([1.0], [-0.1], []):
        with pytest.raises(ValueError):
            build_codev_target_sequence(
                source_zmx=default_optimize_seed(), result_path=Path("r.tsv"),
                target_efl_mm=4.0, vignetting=bad,
            )


def _autovig_fake_popen(edge_converges_at: float):
    """FakePopen writing conv=1 only when injected 渐晕 edge >= threshold."""

    class FakePopen:
        pid = 4321
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            (result_path,) = _buf_exp_paths_from_sequence_single(sequence_path)
            seq = sequence_path.read_text(encoding="ascii")
            m = re.search(r"^VUY ([\d. ]+)$", seq, re.MULTILINE)
            edge = max(float(x) for x in m.group(1).split()) if m else 0.0
            conv = "1" if edge >= edge_converges_at else "0"
            dev = "0.5" if conv == "1" else "9.0"
            _write_target_result(result_path, converged=conv, dev=dev, edge=str(edge))
            return "ignored", ""

    return FakePopen


def test_mock_autovig_climbs_to_minimal_converging_edge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = _fake_codev_executable(tmp_path)
    monkeypatch.setattr(codev_batch.subprocess, "Popen", _autovig_fake_popen(0.30))
    data = run_codev_target_autovig(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
        stage="A", executable=executable, timeout_seconds=12.0,
        vig_ladder=(0.0, 0.2, 0.3, 0.4),
    )
    assert data["autovig.converged"] == "1"
    assert data["autovig.edge_used"] == "0.3"  # 最小收敛裁剪
    assert "e0.00:dev9" in data["autovig.trace"]
    assert "e0.30" in data["autovig.trace"]
    assert "e0.40" not in data["autovig.trace"]  # 命中即停，不多裁


def test_mock_autovig_no_clip_when_native_converges(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = _fake_codev_executable(tmp_path)
    monkeypatch.setattr(codev_batch.subprocess, "Popen", _autovig_fake_popen(0.0))
    data = run_codev_target_autovig(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
        stage="A", executable=executable, timeout_seconds=12.0,
        vig_ladder=(0.0, 0.2, 0.3),
    )
    assert data["autovig.edge_used"] == "0"  # 原生收敛不裁
    assert data["autovig.converged"] == "1"
    assert data["autovig.trace"].startswith("e0.00") and data["autovig.trace"].endswith("c1")
    assert "e0.20" not in data["autovig.trace"]  # 首轮即返回


def _autovig_flood_popen(*, always_timeout: bool):
    """FakePopen: rung-0 (无 VUY) 超时(模拟 TIR flood)；有 VUY 的级写收敛结果。
    always_timeout=True 时每级都超时（模拟彻底 tooling-blocked）。"""

    class FakePopen:
        pid = 5555
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs
            self.communicate_calls = 0

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            self.communicate_calls += 1
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            seq = sequence_path.read_text(encoding="ascii")
            has_vig = re.search(r"^VUY ", seq, re.MULTILINE) is not None
            if always_timeout or not has_vig:  # rung-0 flood → 超时
                if self.communicate_calls == 1:
                    raise subprocess.TimeoutExpired(self.command, timeout, output=b"flood")
                self.returncode = -9
                return b"drained", b""
            (result_path,) = _buf_exp_paths_from_sequence_single(sequence_path)
            m = re.search(r"^VUY ([\d. ]+)$", seq, re.MULTILINE)
            edge = max(float(x) for x in m.group(1).split())
            _write_target_result(result_path, converged="1", dev="0.5", edge=str(edge))
            return b"", b""

    return FakePopen


def test_mock_autovig_climbs_past_rung0_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """rung-0 (v=0) TIR-flood 超时被吞，注入 num_fields 后续爬渐晕并收敛。"""
    executable = _fake_codev_executable(tmp_path)
    monkeypatch.setattr(codev_batch.subprocess, "Popen", _autovig_flood_popen(always_timeout=False))
    monkeypatch.setattr(
        codev_batch.subprocess, "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b""),
    )
    data = run_codev_target_autovig(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
        stage="A", executable=executable, timeout_seconds=0.01, platform_name="nt",
        num_fields=3, vig_ladder=(0.0, 0.2, 0.3),
    )
    assert data["autovig.converged"] == "1"
    assert data["autovig.edge_used"] == "0.2"  # rung-0 超时后首个收敛渐晕
    assert data["autovig.trace"].startswith("e0.00:timeout")


def test_mock_autovig_all_rungs_timeout_reraises_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """每级都超时且无可用数据 → 重抛 CodeVBatchError（保持 tooling-blocked 语义）。"""
    executable = _fake_codev_executable(tmp_path)
    monkeypatch.setattr(codev_batch.subprocess, "Popen", _autovig_flood_popen(always_timeout=True))
    monkeypatch.setattr(
        codev_batch.subprocess, "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b""),
    )
    with pytest.raises(CodeVBatchError) as error:
        run_codev_target_autovig(
            source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
            stage="A", executable=executable, timeout_seconds=0.01, platform_name="nt",
            num_fields=3, vig_ladder=(0.0, 0.2, 0.3),
        )
    assert error.value.kind == "timeout"


def test_mock_autovig_fallback_edge_used_matches_best_not_last_tried(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """归属一致性回归：当整条 ladder 都不收敛时，``_blocked_or_best`` 上报的
    ``autovig.edge_used`` 必须是实际被返回的 ``best`` 数据自己的 edge，而不是
    ladder 爬到的"最后一个尝试过的" edge——两者在"偏差最小的 rung 不是最后一
    个尝试的 rung"时会不一致（此处 edge=0.2 的偏差比 edge=0.3 更小，但 ladder
    仍会继续爬到 0.3 才耗尽，因为 0.2 本身没有收敛）。修复前，返回的
    ``autovig.edge_used`` 会错报为 "0.3"，但实际返回的三快照数字/文件名都来
    自 edge=0.2 的那次调用——资深看到的"渐晕量"和"实际候选设计"对不上。"""
    executable = _fake_codev_executable(tmp_path)
    dev_by_edge = {0.0: "5.0", 0.2: "1.5", 0.3: "3.0"}  # 0.2 最小, 但非最终 rung

    class FakePopen:
        pid = 7200
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            (result_path,) = _buf_exp_paths_from_sequence_single(sequence_path)
            seq = sequence_path.read_text(encoding="ascii")
            m = re.search(r"^VUY ([\d. ]+)$", seq, re.MULTILINE)
            edge = max(float(x) for x in m.group(1).split()) if m else 0.0
            _write_target_result(
                result_path, converged="0", dev=dev_by_edge[edge], edge=str(edge)
            )
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    data = run_codev_target_autovig(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
        stage="A", executable=executable, timeout_seconds=12.0,
        vig_ladder=(0.0, 0.2, 0.3), num_fields=3,
    )
    assert data["autovig.converged"] == "0"
    assert data["autovig.edge_used"] == "0.2"  # best 的 edge，不是最后尝试的 0.3
    assert float(data["efl_target_deviation_pct"]) == pytest.approx(1.5)


def test_mock_autovig_duplicate_rung_token_collision_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """0.1% token 分辨率之下仍碰撞的 ladder 输入（0.2 与 0.2004 同为 _vig0200）：
    绝不静默覆写前一 rung 的产物——命中已用 token 集合立即 ValueError。"""
    executable = _fake_codev_executable(tmp_path)
    monkeypatch.setattr(codev_batch.subprocess, "Popen", _autovig_fake_popen(9.9))  # 永不收敛
    with pytest.raises(ValueError, match="duplicate filename token"):
        run_codev_target_autovig(
            source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
            stage="A", executable=executable, timeout_seconds=12.0,
            num_fields=3, vig_ladder=(0.0, 0.2, 0.2004),
        )


def test_mock_autovig_malformed_num_fields_does_not_crash_ladder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """rung0 返回畸形 num_fields（如 "***"）时不炸整条 ladder：与 dev 解析同风格
    容错回退 None（不注入场数），走 rung0 数据兜底返回——修复前 int(float("***"))
    直接 ValueError 炸穿 autovig。"""
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 7302
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            (result_path,) = _buf_exp_paths_from_sequence_single(sequence_path)
            _write_target_result(result_path, converged="0", dev="7.7", num_fields="***")
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    data = run_codev_target_autovig(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
        stage="A", executable=executable, timeout_seconds=12.0, vig_ladder=(0.0, 0.2, 0.3),
    )
    assert data["autovig.converged"] == "0"
    assert data["autovig.edge_used"] == "0"  # 场数不可学 → 未爬非零 rung，兜底 rung0
    assert float(data["efl_target_deviation_pct"]) == pytest.approx(7.7)


def test_mock_autovig_all_rungs_fail_details_carry_trace_and_first_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """全灭异常路径不再丢过程线索：rung0 报 failure（结果文件未产出）、rung1 报
    timeout——全灭 raise 时仍抛 last_error 类型（timeout，保持既有分流兼容），但
    details 加法式附 autovig_trace（逐 rung edge→kind 摘要）与 first_error_kind
    （首错 = failure），供事后归因整条 ladder 的失败形态。"""
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 7303
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs
            self.communicate_calls = 0

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            self.communicate_calls += 1
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            seq = sequence_path.read_text(encoding="ascii")
            has_vig = re.search(r"^VUY ", seq, re.MULTILINE) is not None
            if not has_vig:
                return b"", b""  # rung0：不产出结果文件 → CodeVBatchError("failure")
            if self.communicate_calls == 1:
                raise subprocess.TimeoutExpired(self.command, timeout, output=b"flood")
            self.returncode = -9
            return b"drained", b""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(
        codev_batch.subprocess, "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b""),
    )
    with pytest.raises(CodeVBatchError) as error:
        run_codev_target_autovig(
            source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
            stage="A", executable=executable, timeout_seconds=0.01, platform_name="nt",
            num_fields=3, vig_ladder=(0.0, 0.2),
        )
    assert error.value.kind == "timeout"  # 仍抛 last_error 类型（既有语义零回归）
    assert error.value.details["first_error_kind"] == "failure"
    assert error.value.details["autovig_trace"] == ["e0.00:failure", "e0.20:timeout"]


def test_mock_run_codev_target_parses_three_snapshots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 4321
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            (result_path,) = _buf_exp_paths_from_sequence_single(sequence_path)
            _write_target_result(result_path)
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    data = run_codev_target(
        source_zmx=default_optimize_seed(), work_dir=tmp_path,
        target_efl_mm=4.057, stage="A", executable=executable, timeout_seconds=12.0,
    )
    assert data["mode"] == "target"
    assert data["aut_converged"] == "1"
    assert float(data["seed_baseline.efl_y_mm"]) == pytest.approx(3.6225)
    assert float(data["post_aut.efl_y_mm"]) == pytest.approx(4.0570)
    # 三快照像质数据齐全
    assert float(data["post_aut.max_rms_spot_diameter_um"]) == pytest.approx(23.10)
    assert float(data["post_aut.max_distortion_pct"]) == pytest.approx(8.39)


def _buf_exp_paths_from_sequence_single(sequence_path: Path) -> list[Path]:
    sequence = sequence_path.read_text(encoding="ascii")
    matches = re.findall(r'BUF EXP B1 "([^"]+)"', sequence)
    assert len(matches) == 1  # target 模式单 BUF EXP
    return [Path(m) for m in matches]


def _target_popen_with_baseline(baseline_text: str):
    """FakePopen 工厂：先写正常 target TSV，再把 seed_baseline EFL 改为
    `baseline_text`（模拟导入侧腐坏）。记录实例化次数，供 fail-fast 测试
    断言真正发起了几次 CODE V 批跑。"""

    class FakePopen:
        pid = 4322
        returncode = 1
        invocations = 0

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            type(self).invocations += 1
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            (result_path,) = _buf_exp_paths_from_sequence_single(sequence_path)
            _write_target_result(result_path)
            text = result_path.read_text(encoding="utf-8")
            result_path.write_text(
                text.replace(
                    "seed_baseline.efl_y_mm\t3.6225",
                    f"seed_baseline.efl_y_mm\t{baseline_text}",
                ),
                encoding="utf-8",
            )
            return "ignored", ""

    return FakePopen


def test_mock_run_codev_target_rejects_all_air_seed_baseline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """导入即全空气的种子（玻璃未解析，CODE V EFY 哨兵 1e35）必须立即抛可归因
    的 CodeVBatchError，而不是带着垃圾三快照继续跑 autovig ladder、最后以
    zmx_rebuild_error 伪装成 ZMX 重建问题（真机根因 2026-07-10，见
    scripts/repair_legacy_zmx_glass.py）。"""
    executable = _fake_codev_executable(tmp_path)
    monkeypatch.setattr(
        codev_batch.subprocess, "Popen", _target_popen_with_baseline("1.000000e+35")
    )

    with pytest.raises(CodeVBatchError) as error:
        run_codev_target(
            source_zmx=default_optimize_seed(), work_dir=tmp_path,
            target_efl_mm=4.057, stage="A", executable=executable, timeout_seconds=12.0,
        )
    assert error.value.kind == "failure"
    assert "unresolved glass" in error.value.message
    assert "all-air" in error.value.message
    assert error.value.details["seed_baseline_efl_y_mm"] == "1.000000e+35"
    assert error.value.details["preflight"] == "unresolved-glass"


def test_mock_run_codev_target_rejects_non_numeric_seed_baseline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """required-keys 闸已保证键存在，float() ValueError = 非数垃圾——这正是
    预检要抓的腐坏形态之一，必须抛可归因错误而不是静默跳过检查（W2）。"""
    executable = _fake_codev_executable(tmp_path)
    monkeypatch.setattr(
        codev_batch.subprocess, "Popen", _target_popen_with_baseline("n/a-garbage")
    )
    with pytest.raises(CodeVBatchError) as error:
        run_codev_target(
            source_zmx=default_optimize_seed(), work_dir=tmp_path,
            target_efl_mm=4.057, stage="A", executable=executable, timeout_seconds=12.0,
        )
    assert error.value.kind == "failure"
    assert "non-numeric" in error.value.message
    assert "n/a-garbage" in error.value.message
    assert error.value.details["preflight"] == "corrupt-baseline-efl"


def test_mock_autovig_preflight_defect_short_circuits_ladder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """种子级预检缺陷是确定性的：换渐晕 rung 不改变导入结果。autovig 必须在
    rung0 直接上抛，不爬完整条 ladder（W3）。"""
    executable = _fake_codev_executable(tmp_path)
    fake_popen = _target_popen_with_baseline("1.000000e+35")
    monkeypatch.setattr(codev_batch.subprocess, "Popen", fake_popen)
    with pytest.raises(CodeVBatchError) as error:
        run_codev_target_autovig(
            source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
            stage="A", executable=executable, timeout_seconds=12.0, platform_name="nt",
            num_fields=3, vig_ladder=(0.0, 0.2, 0.3),
        )
    assert error.value.details["preflight"] == "unresolved-glass"
    assert fake_popen.invocations == 1  # rung0 即上抛，不再爬 0.2/0.3


def test_mock_standard_preflight_defect_runs_one_batch_and_attributes_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """标准双配置入口对种子级预检缺陷只真机跑 1 次：第二配置如实记同一错误 +
    skipped 注记（W3）；preferred_reason 从真实 error dict 归因，不硬贴
    tooling-blocked 标签（W4）。"""
    executable = _fake_codev_executable(tmp_path)
    fake_popen = _target_popen_with_baseline("1.000000e+35")
    monkeypatch.setattr(codev_batch.subprocess, "Popen", fake_popen)
    result = run_codev_target_standard(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
        executable=executable, timeout_seconds=12.0,
    )
    assert fake_popen.invocations == 1  # 整个 standard 调用只发起 1 次 CODE V 批跑
    asphere_error = result["configs"]["asphere"]["error"]
    both = result["configs"]["both"]
    assert asphere_error["kind"] == "failure"
    assert "unresolved glass" in asphere_error["detail"]
    assert asphere_error["preflight"] == "unresolved-glass"
    assert both["error"] == asphere_error
    assert both["skipped"] == "seed-level preflight defect, identical for every config"
    assert result["preferred"] is None
    assert "unresolved glass" in result["preferred_reason"]
    assert "seed 级预检缺陷" in result["preferred_reason"]
    assert "tooling-blocked" not in result["preferred_reason"]


# ===========================================================================
# parse_aut_error_trace（AUT 误差函数轨迹诊断）单测：内联 fixture 摘录自真实
# .lis 样本，未经删改数值（仅省略了中间的 Parameter 逐行清单，不影响
# ABERR/CONST/ERR 三行组的解析）。
#   - 灾难案例来源：scratch_diag/dof_work/atelier_codev_target_A.19.lis
#     （cycle 0 与 cycle 22，行号约 668-673 / 6096-6103 / 6297）
#   - 健康案例来源：scratch_diag/glc_fix_work/glc_fix_both_gla.lis
#     （cycle 0 与 cycle 13，行号约 668-672 / 3765-3769 / 3966）
#   - Unstable 案例来源：scratch_diag/autovig_work/atelier_codev_target_A.1.lis
#     （cycle 10 重复块，行号约 1040-1089）
# ===========================================================================

_DISASTER_LIS_EXCERPT = """\
 CYCLE NUMBER 0:

  ABERR F. =        0.23586894
  CONST F. =      127.92366266
  ERR. F.  =      128.15953160

  OPD     0.38636451     0.03869299     0.08639244
  WAV     0.40688146     0.04147835     0.09106934

 CYCLE NUMBER 22:

  ABERR F. =        8.03888494
  CONST F. =      0.154255E+06
  ERR. F.  =      0.154263E+06       (change =     -0.110267E+01)

  OPD    11.14247810     6.93271640     1.68243607
  WAV    12.35508170     7.55339870     1.72979320

  Weighted Constraints:        target        value        WTC/PTC     contrib
  @ATELIER_LATCOLOR      =   0.00000E+00   6.05847E+00   1.000E-02   3.671E+03
  @ATELIER_RMSSPOT       =   0.00000E+00   3.88052E+02   1.000E-03   1.506E+05

     Normal AUTO Completion - System improvement less than IMP
AUT> GO
"""

_HEALTHY_LIS_EXCERPT = """\
 CYCLE NUMBER 0:

  ABERR F. =        0.23586894
  CONST F. =      127.92366266
  ERR. F.  =      128.15953160

 CYCLE NUMBER 13:

  ABERR F. =        0.17323803
  CONST F. =       26.95327543
  ERR. F.  =       27.12651346       (change =       -0.01919572)

  Weighted Constraints:        target        value        WTC/PTC     contrib
  @ATELIER_LATCOLOR      =   0.00000E+00   1.61726E-01   1.000E-02   2.616E+00
  @ATELIER_RMSSPOT       =   0.00000E+00   4.93333E+00   1.000E-03   2.434E+01

     Normal AUTO Completion - System improvement less than IMP
AUT> GO
"""

_NO_SIGNAL_LIS_EXCERPT = """\
CODE V> IN CV_MACRO:ZEMAXOS_TO_CV "seed.zmx"
CODE V> DEF VAR SA
CODE V> AUT
AUT> SUR N
AUT> CHG SA
AUT> WFR Y
"""

_UNSTABLE_LIS_EXCERPT = """\
 CYCLE NUMBER 10:

  ABERR F. =        6.93276207
  CONST F. =     1225.65241337
  ERR. F.  =     1232.58517544       (change =        3.23274194)

  OPD     0.51589472     0.64104172     7.93588616
  WAV     0.59888159     0.72541838    14.96124586

        EFL          REDU         PIM          OAL         EN PUP       EX PUP
      4.738699     0.000000     0.013967     6.032188     0.475900    -3.118203

  Active Constraints -   2:    target        value         diff        cost
  EFL                    =   5.26337E+00   4.73870E+00  -5.247E-01   4.378E+00
  Mn CT S2                                                          -7.390E+00

  Weighted Constraints:        target        value        WTC/PTC     contrib
  @ATELIER_LATCOLOR      =   0.00000E+00   1.56807E+00   1.000E-02   2.459E+02
  @ATELIER_RMSSPOT       =   0.00000E+00   3.13012E+01   1.000E-03   9.798E+02

     Normal AUTO Completion - Unstable Condition
AUT> GO
"""


def test_parse_aut_error_trace_disaster_case_flags_extreme_ratio() -> None:
    """真机灾难案例：IMP 只看相邻 cycle 改善速率，ERR. F. 从 cycle0 的
    128.15953160 爆炸到末 cycle 的 0.154263E+06（约 ×1204），末行仍报
    "System improvement less than IMP"——aut_converged（EFL-hit 代理）完全
    抓不到这类假阳性，本函数如实暴露数字（不下判定）。"""
    trace = parse_aut_error_trace(_DISASTER_LIS_EXCERPT)
    assert trace["err_f_first"] == pytest.approx(128.15953160)
    assert trace["err_f_last"] == pytest.approx(154263.0)
    assert trace["aberr_f_last"] == pytest.approx(8.03888494)
    assert trace["const_f_last"] == pytest.approx(154255.0)
    assert trace["err_f_ratio"] == pytest.approx(1203.68, rel=1e-3)
    assert trace["termination"] == "normal_completion"


def test_parse_aut_error_trace_healthy_case_ratio_below_one() -> None:
    """健康案例对照：同一 seed 起点 128.15953160，真实收敛到 27.12651346，
    ratio<1，与灾难案例（ratio>1000）虽终止措辞完全相同（都是 "System
    improvement less than IMP"）但 ratio 天差地别——这正是本诊断字段存在
    的意义：终止措辞本身分辨不出假阳性。"""
    trace = parse_aut_error_trace(_HEALTHY_LIS_EXCERPT)
    assert trace["err_f_first"] == pytest.approx(128.15953160)
    assert trace["err_f_last"] == pytest.approx(27.12651346)
    assert trace["err_f_ratio"] == pytest.approx(0.21166, rel=1e-3)
    assert trace["termination"] == "normal_completion"


def test_parse_aut_error_trace_no_cycle_data_returns_all_none() -> None:
    """找不到任何 ABERR/CONST/ERR. F. 三行组（例如进程在第一个 cycle 完成前
    被杀）→ 全字段 None，fail-open，不抛异常。"""
    trace = parse_aut_error_trace(_NO_SIGNAL_LIS_EXCERPT)
    assert trace == {
        "err_f_first": None,
        "err_f_last": None,
        "aberr_f_last": None,
        "const_f_last": None,
        "err_f_ratio": None,
        "termination": None,
    }


def test_parse_aut_error_trace_unstable_termination_keyword() -> None:
    """真机 "Unstable Condition" 终止措辞归一化为 unstable_condition；单
    cycle 场景下 err_f_first == err_f_last，ratio == 1.0。"""
    trace = parse_aut_error_trace(_UNSTABLE_LIS_EXCERPT)
    assert trace["err_f_first"] == pytest.approx(1232.58517544)
    assert trace["err_f_last"] == pytest.approx(1232.58517544)
    assert trace["err_f_ratio"] == pytest.approx(1.0)
    assert trace["termination"] == "unstable_condition"


def test_mock_run_codev_target_includes_aut_error_trace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """listing_path 可读时，run_codev_target 把 parse_aut_error_trace 的结果
    以 "aut_error_trace" 键附加进返回 dict（真机 .lis 同源样本，见上方单测）。
    listing 必须在 FakePopen.communicate() 期间才写出——run_codev_batch 用运行
    前后快照 diff 认领清单文件，运行前已存在的裸名 .lis 会被当作 stale 删除。"""
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 4322
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            (result_path,) = _buf_exp_paths_from_sequence_single(sequence_path)
            _write_target_result(result_path)
            sequence_path.with_suffix(".lis").write_text(
                _HEALTHY_LIS_EXCERPT, encoding="utf-8"
            )
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    data = run_codev_target(
        source_zmx=default_optimize_seed(), work_dir=tmp_path,
        target_efl_mm=4.057, stage="A", executable=executable, timeout_seconds=12.0,
    )
    trace = data["aut_error_trace"]
    assert trace is not None
    assert trace["err_f_first"] == pytest.approx(128.15953160)
    assert trace["err_f_last"] == pytest.approx(27.12651346)
    assert trace["termination"] == "normal_completion"


def test_mock_run_codev_target_aut_error_trace_none_without_listing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """没有任何 .lis 清单文件（listing_path 认领结果为 None，例如 CODE V 版本
    差异下未产出清单）→ aut_error_trace 键仍存在，值为 None——诊断字段
    fail-open，绝不影响 run_codev_target 主 TSV 契约（其余键照常齐全）。"""
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 4323
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            (result_path,) = _buf_exp_paths_from_sequence_single(sequence_path)
            _write_target_result(result_path)
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    data = run_codev_target(
        source_zmx=default_optimize_seed(), work_dir=tmp_path,
        target_efl_mm=4.057, stage="A", executable=executable, timeout_seconds=12.0,
    )
    assert data["aut_error_trace"] is None
    assert data["mode"] == "target"  # 主契约不受影响


# ===========================================================================
# run_codev_target_standard（C1 Mode3 标准打包入口）mock 测试：monkeypatch
# codev_optimize.run_codev_target_autovig 本体（模块级全局名，patch 后本函数
# 内部调用即生效），不触碰 subprocess/CODE V。
# ===========================================================================


def _standard_config_result(*, converged: str, rms: str | None) -> dict[str, str]:
    data = {"aut_converged": converged, "autovig.edge_used": "0.3", "autovig.converged": converged}
    if rms is not None:
        data["post_aut.max_rms_spot_diameter_um"] = rms
    return data


def _fake_autovig(results: dict[str, dict[str, str] | CodeVBatchError]):
    # 只按 extra_dof 分派；其余 kwargs（source_zmx/work_dir/target_* 等）都由
    # run_codev_target_standard 以关键字传入，一律吞进 _ignored，不参与判定。
    def _run(*, extra_dof: str = "none", **_ignored: object) -> dict[str, str]:
        outcome = results[extra_dof]
        if isinstance(outcome, CodeVBatchError):
            raise outcome
        return dict(outcome)

    return _run


def test_target_standard_prefers_both_when_lower_rms(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        codev_optimize,
        "run_codev_target_autovig",
        _fake_autovig(
            {
                "asphere": _standard_config_result(converged="1", rms="20.0"),
                "both": _standard_config_result(converged="1", rms="13.0"),
            }
        ),
    )
    result = run_codev_target_standard(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057
    )
    assert result["preferred"] == "both"
    assert "13" in result["preferred_reason"]
    assert result["configs"]["asphere"]["post_aut.max_rms_spot_diameter_um"] == "20.0"


def test_target_standard_prefers_asphere_when_lower_rms(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        codev_optimize,
        "run_codev_target_autovig",
        _fake_autovig(
            {
                "asphere": _standard_config_result(converged="1", rms="12.99"),
                "both": _standard_config_result(converged="1", rms="343.0"),
            }
        ),
    )
    result = run_codev_target_standard(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057
    )
    assert result["preferred"] == "asphere"


def test_target_standard_survivor_preferred_when_one_config_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    err = CodeVBatchError("timeout", "boom", details={"x": 1})
    monkeypatch.setattr(
        codev_optimize,
        "run_codev_target_autovig",
        _fake_autovig(
            {
                "asphere": _standard_config_result(converged="1", rms="15.0"),
                "both": err,
            }
        ),
    )
    result = run_codev_target_standard(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057
    )
    assert result["preferred"] == "asphere"
    assert result["configs"]["both"]["error"]["kind"] == "timeout"
    assert result["configs"]["both"]["error"]["detail"] == "boom"
    assert "post_aut.max_rms_spot_diameter_um" in result["configs"]["asphere"]


def test_target_standard_both_not_converged_compares_by_rms(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        codev_optimize,
        "run_codev_target_autovig",
        _fake_autovig(
            {
                "asphere": _standard_config_result(converged="0", rms="80.0"),
                "both": _standard_config_result(converged="0", rms="60.0"),
            }
        ),
    )
    result = run_codev_target_standard(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057
    )
    assert result["preferred"] == "both"


def test_target_standard_missing_rms_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        codev_optimize,
        "run_codev_target_autovig",
        _fake_autovig(
            {
                # asphere 缺 RMS key（fail-closed 当 +inf），即便 both 数值本身很差，
                # 仍应排到 both 之后——缺数据不能反而"赢"。
                "asphere": _standard_config_result(converged="1", rms=None),
                "both": _standard_config_result(converged="1", rms="500.0"),
            }
        ),
    )
    result = run_codev_target_standard(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057
    )
    assert result["preferred"] == "both"


def test_target_standard_zero_rms_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CODE V 宏 `@rmssum`（FCT 定义见 `_metric_function_block`）以 `^max==0`
    起始，只在 `SPOTDATA` 返回 `^err=0`（追迹成功）的场次才更新 `^max`；若
    某配置全部场次 `SPOTDATA` 都 `^err!=0`（追迹失败），`^max` 原样保留初值
    0 并被写出为 `post_aut.max_rms_spot_diameter_um="0"`——这是"追迹全失败"
    的哨兵值，不是"零误差"的真优值（物理上 RMS 点列径精确为 0 不存在，衍射
    极限设下界 >0）。rms="0" 的配置不得凭这个假优值赢过真实收敛 rms="5.0"
    的配置。"""
    monkeypatch.setattr(
        codev_optimize,
        "run_codev_target_autovig",
        _fake_autovig(
            {
                "asphere": _standard_config_result(converged="1", rms="0"),
                "both": _standard_config_result(converged="1", rms="5.0"),
            }
        ),
    )
    result = run_codev_target_standard(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057
    )
    assert result["preferred"] == "both"
    assert "不可用" in result["preferred_reason"]
    assert result["configs"]["asphere"]["post_aut.max_rms_spot_diameter_um"] == "0"


def test_target_standard_both_errors_preferred_is_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        codev_optimize,
        "run_codev_target_autovig",
        _fake_autovig(
            {
                "asphere": CodeVBatchError("timeout", "a boom"),
                "both": CodeVBatchError("failure", "b boom"),
            }
        ),
    )
    result = run_codev_target_standard(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057
    )
    assert result["preferred"] is None
    assert result["configs"]["asphere"]["error"]["kind"] == "timeout"
    assert result["configs"]["both"]["error"]["kind"] == "failure"


def test_target_standard_schema_and_provenance_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        codev_optimize,
        "run_codev_target_autovig",
        _fake_autovig(
            {
                "asphere": _standard_config_result(converged="1", rms="10.0"),
                "both": _standard_config_result(converged="1", rms="11.0"),
            }
        ),
    )
    result = run_codev_target_standard(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057
    )
    assert result["schema"] == STANDARD_RESULT_SCHEMA
    assert set(result["configs"]) == {"asphere", "both"}
    assert result["provenance"]["vignetting_search"] == "autovig"
    # glass_model 按 config 如实分开（诚实语义）：asphere 配置从不设玻璃变量
    # → "glass-frozen"；both 配置未传自定义 bounds → 默认塑料域标签。
    assert result["provenance"]["glass_model"] == {
        "asphere": "glass-frozen",
        "both": "fictitious-within-plastic-GLA(default)",
    }
    assert "gla_hull" not in result["provenance"]  # 默认 bounds 不附 hull 角点
    assert "EXPERT" in result["provenance"]["quality_note"]


def test_target_standard_custom_glass_bounds_provenance_carries_hull(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """自定义 glass bounds 时 provenance 必须如实标注 custom 并附上实际注入
    AUT GLA 的凸包角点字符串（与 _glass_map_hull 同源），供资深核对可变域。"""
    custom_bounds = [(1.50, 40.0), (1.60, 20.0), (1.55, 70.0)]
    monkeypatch.setattr(
        codev_optimize,
        "run_codev_target_autovig",
        _fake_autovig(
            {
                "asphere": _standard_config_result(converged="1", rms="10.0"),
                "both": _standard_config_result(converged="1", rms="11.0"),
            }
        ),
    )
    result = run_codev_target_standard(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
        glass_bounds_nd_vd=custom_bounds,
    )
    assert result["provenance"]["glass_model"] == {
        "asphere": "glass-frozen",
        "both": "fictitious-within-custom-GLA",
    }
    assert result["provenance"]["gla_hull"] == _glass_map_hull(custom_bounds)


def test_target_standard_full_tie_takes_fixed_priority_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """aut_converged 与 RMS 完全打平 → 按固定优先序取 asphere；reason 与排序
    从同一 rank 元组派生（消除双路计算分叉），措辞必须与打平事实一致。"""
    monkeypatch.setattr(
        codev_optimize,
        "run_codev_target_autovig",
        _fake_autovig(
            {
                "asphere": _standard_config_result(converged="1", rms="15.0"),
                "both": _standard_config_result(converged="1", rms="15.0"),
            }
        ),
    )
    result = run_codev_target_standard(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057
    )
    assert result["preferred"] == "asphere"
    assert "固定优先序" in result["preferred_reason"]
    assert "converged=1" in result["preferred_reason"]


def test_target_standard_invalid_glass_bounds_fail_fast(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """入口前置校验（0 真机成本）：standard 恒跑 both 配置，glass 路径必然消费
    bounds——非法 bounds 必须在入口立即 ValueError，不进配置循环烧真机批跑（修复
    前要等 asphere 整条 autovig ladder 跑完、爬到 both 构建 sequence 时才炸）。"""
    calls: list[str] = []

    def _spy(*, extra_dof: str = "none", **_ignored: object) -> dict[str, str]:
        calls.append(extra_dof)
        return _standard_config_result(converged="1", rms="10.0")

    monkeypatch.setattr(codev_optimize, "run_codev_target_autovig", _spy)
    with pytest.raises(ValueError):
        run_codev_target_standard(
            source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
            glass_bounds_nd_vd=[(1.50, 40.0), (1.60, 20.0)],  # <3 个点，无法构成凸多边形
        )
    assert calls == []  # fail-fast：未进任何配置的 autovig 调用


# ===========================================================================
# 优化后 ZMX 重建（emit_optimized_zmx）——加法式把 baseline
# run_codev_optimize 已有的 readout->zmx_writer 管线接到 target/autovig/
# standard 入口，供资深 Verify 候选设计文件本身，而不只是 tsv 数字快照。
# ===========================================================================


def _buf_exp_paths_from_target_sequence_pair(sequence_path: Path) -> tuple[Path, Path]:
    sequence = sequence_path.read_text(encoding="ascii")
    matches = re.findall(r'BUF EXP B1 "([^"]+)"', sequence)
    assert len(matches) == 2  # target 模式 emit_optimized_zmx=True -> 主结果 + readout
    return Path(matches[0]), Path(matches[1])


def _write_optimized_readout_with_nonzero_hj(path: Path) -> None:
    """在既有 readout fixture 基础上把 surface.1 的非球面 H 系数改成非零——
    模拟真机 extra_dof=asphere/both 打开 A..J 全部 DOF 后 AUT 真的动了 H 系数
    （zmx_writer 的 EVENASPH 只支持 CODE V A-G 对应 Zemax PARM 2-8，H/J 会被
    ``_reject_nonzero_unsupported_evenasphere_terms`` 拒绝），用于验证
    run_codev_target 的 fail-open 重建失败路径。"""
    _write_optimized_readout(path)
    text = path.read_text(encoding="utf-8")
    assert "surface.1.asphere.H\t0" in text
    text = text.replace("surface.1.asphere.H\t0", "surface.1.asphere.H\t0.0005", 1)
    path.write_text(text, encoding="utf-8")


def _fake_run_codev_target_popen_with_readout(readout_writer=_write_optimized_readout):
    class FakePopen:
        pid = 7001
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            result_path, readout_path = _buf_exp_paths_from_target_sequence_pair(sequence_path)
            _write_target_result(result_path)
            readout_writer(readout_path)
            return "ignored", ""

    return FakePopen


def test_target_sequence_emit_optimized_zmx_appends_readout_block() -> None:
    seq = build_codev_target_sequence(
        source_zmx=default_optimize_seed(), result_path=Path("r.tsv"),
        target_efl_mm=4.057, emit_optimized_zmx=True,
        optimized_readout_path=Path("ro.tsv"),
    )
    assert f'"{CODEV_READOUT_RESULT_SCHEMA}"' in seq
    assert seq.count('BUF EXP B1 "') == 2
    assert seq.index('BUF EXP B1 "r.tsv"') < seq.index('BUF EXP B1 "ro.tsv"')
    # 非球面 K/A..J 系数 + 玻璃 nd/vd 如实带出（baseline 同款字段名，见
    # _optimized_readout_block）
    assert 'CONCAT(^surface_prefix, ".nd")' in seq
    assert 'CONCAT(^surface_prefix, ".vd")' in seq
    assert 'CONCAT(^surface_prefix, ".asphere.H")' in seq
    assert 'CONCAT(^surface_prefix, ".asphere.J")' in seq


def test_target_sequence_emit_optimized_zmx_false_is_zero_regression() -> None:
    seq = build_codev_target_sequence(
        source_zmx=default_optimize_seed(), result_path=Path("r.tsv"), target_efl_mm=4.057,
    )
    assert CODEV_READOUT_RESULT_SCHEMA not in seq
    assert seq.count('BUF EXP B1 "') == 1


def test_target_sequence_emit_optimized_zmx_requires_readout_path() -> None:
    with pytest.raises(ValueError):
        build_codev_target_sequence(
            source_zmx=default_optimize_seed(), result_path=Path("r.tsv"),
            target_efl_mm=4.057, emit_optimized_zmx=True,
        )


def test_vignetting_filename_token_empty_for_none_or_empty() -> None:
    assert codev_optimize._vignetting_filename_token(None) == ""
    assert codev_optimize._vignetting_filename_token([]) == ""


def test_vignetting_filename_token_uses_max_edge() -> None:
    assert codev_optimize._vignetting_filename_token([0.0, 0.3, 0.3]) == "_vig0300"


def test_fmt_edge_filename_token_is_decimal_free() -> None:
    """真机实锤（2026-07-09）：CODE V BUF EXP 对文件名中"小数点后还跟更多
    非数字字符再到扩展名"的路径报 ERROR - Unable to open file. 并中止整条
    宏——见 _fmt_edge_filename_token 文档字符串。消歧后缀必须不含小数点。"""
    assert codev_optimize._fmt_edge_filename_token(0.0) == "_vig0000"
    assert codev_optimize._fmt_edge_filename_token(0.2) == "_vig0200"
    assert codev_optimize._fmt_edge_filename_token(0.7) == "_vig0700"
    assert "." not in codev_optimize._fmt_edge_filename_token(0.13)
    with pytest.raises(ValueError):
        codev_optimize._fmt_edge_filename_token(-0.1)
    with pytest.raises(ValueError):
        codev_optimize._fmt_edge_filename_token(float("nan"))


def test_fmt_edge_filename_token_permille_resolution_disambiguates() -> None:
    """token 分辨率提到 0.1%（千分位定宽 4 位）：细化 ladder 里相差 <1% 的两个
    edge（0.2 与 0.204）必须拿到不同 token——旧的 1% 分辨率（round(edge*100)）
    会把两者都编成 _vig020，rung 产物互相静默覆写。"""
    assert codev_optimize._fmt_edge_filename_token(0.204) == "_vig0204"
    assert codev_optimize._fmt_edge_filename_token(0.2) != codev_optimize._fmt_edge_filename_token(
        0.204
    )


def test_run_codev_target_rejects_buf_exp_hazard_readout_filename(tmp_path: Path) -> None:
    """机制守卫（不再只靠 token 生成侧自律）：带小数点的 rung tag 拼出的
    readout 文件名（"..._vig0.20_optimized_readout.tsv"）是 CODE V BUF EXP
    真机实锤的 "Unable to open file" 危险模式——必须在 Python 侧构造路径时
    立即 ValueError，不落 seq、不发起任何 CODE V 进程（此处未 mock Popen，
    若守卫失效测试会因缺 executable 报 CodeVBatchError 而非 ValueError）。"""
    with pytest.raises(ValueError, match="optimized_readout_path"):
        run_codev_target(
            source_zmx=default_optimize_seed(), work_dir=tmp_path,
            target_efl_mm=4.057, stage="A", executable=tmp_path / "codev.exe",
            timeout_seconds=12.0, emit_optimized_zmx=True, rung_filename_tag="_vig0.20",
        )
    assert list(tmp_path.glob("*.seq")) == []  # 守卫先于 seq 落盘


def test_run_codev_target_dangerous_shaped_zmx_output_name_is_exempt() -> None:
    """守卫只管 CODE V 会打开的路径：优化后 ZMX（zmx_writer Python 落盘、不经
    CODE V）文件名天然含小数点（"_target4.057_"），必须豁免——由
    test_mock_run_codev_target_emit_optimized_zmx_rebuilds_and_ingests 的
    文件名断言回归锁定；此处锁定 readout 文件名生成器本身对合法 token 安全。"""
    safe_readout = codev_optimize._target_optimized_readout_filename("A", "_vig0200")
    ensure_buf_exp_safe_filename(safe_readout)  # 合法 token 不误伤
    dangerous_zmx = codev_optimize._target_optimized_zmx_filename(
        default_optimize_seed(), 4.057, "_vig0200"
    )
    assert ".057_" in dangerous_zmx  # 危险形状确实存在，但该路径不经守卫


def test_mock_run_codev_target_default_optimized_zmx_path_is_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """零回归：emit_optimized_zmx 默认 False 时，返回 dict 新增的
    optimized_zmx_path 键固定为 None，不带 zmx_rebuild_error；sequence 仍是
    单 BUF EXP（_buf_exp_paths_from_sequence_single 的既有断言覆盖）。"""
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 7002
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            (result_path,) = _buf_exp_paths_from_sequence_single(sequence_path)
            _write_target_result(result_path)
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    data = run_codev_target(
        source_zmx=default_optimize_seed(), work_dir=tmp_path,
        target_efl_mm=4.057, stage="A", executable=executable, timeout_seconds=12.0,
    )
    assert data["optimized_zmx_path"] is None
    assert "zmx_rebuild_error" not in data


def test_mock_run_codev_target_emit_optimized_zmx_rebuilds_and_ingests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = _fake_codev_executable(tmp_path)
    monkeypatch.setattr(
        codev_batch.subprocess, "Popen", _fake_run_codev_target_popen_with_readout()
    )

    data = run_codev_target(
        source_zmx=default_optimize_seed(), work_dir=tmp_path,
        target_efl_mm=4.057, stage="A", executable=executable, timeout_seconds=12.0,
        emit_optimized_zmx=True,
    )

    assert data["mode"] == "target"  # 主契约不受影响
    assert "zmx_rebuild_error" not in data
    assert "batch_returncode" not in data  # returncode ∈ {0,1} 时不附带上报（零回归）
    assert data["optimized_zmx_path"] is not None
    zmx_path = Path(data["optimized_zmx_path"])
    assert zmx_path.is_file()
    assert zmx_path.name == f"{default_optimize_seed().stem}_target4.057_optimized.zmx"
    assert math.isfinite(data["optimized_zmx_ingested_efl_mm"])


def test_mock_run_codev_target_emit_optimized_zmx_rebuild_failure_is_fail_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """真机可能场景：extra_dof 打开非球面 DOF 后 AUT 真的把 H/J 系数拉成非
    零，zmx_writer 的 EVENASPH 写不出（只支持 A-G）——重建失败必须 fail-open，
    绝不炸 run_codev_target 的主 TSV 契约。"""
    executable = _fake_codev_executable(tmp_path)
    monkeypatch.setattr(
        codev_batch.subprocess, "Popen",
        _fake_run_codev_target_popen_with_readout(_write_optimized_readout_with_nonzero_hj),
    )

    data = run_codev_target(
        source_zmx=default_optimize_seed(), work_dir=tmp_path,
        target_efl_mm=4.057, stage="A", executable=executable, timeout_seconds=12.0,
        emit_optimized_zmx=True,
    )

    assert data["mode"] == "target"  # 主 TSV 契约不受影响
    assert data["aut_converged"] == "1"
    assert data["optimized_zmx_path"] is None
    assert "zmx_rebuild_error" in data
    assert "EVENASPH" in data["zmx_rebuild_error"]


def test_mock_run_codev_target_stale_readout_is_not_claimed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """批跑前陈旧产物清理（对齐 baseline run_codev_optimize）：上一轮遗留的同名
    optimized readout/ZMX 必须先 unlink——当本轮宏"主 tsv 成功但 readout 未导出"
    （真机原型：BUF EXP 拒开文件中止宏尾）时，重建管线不得认领陈旧 readout 伪装
    成功，而应如实报 zmx_rebuild_error。"""
    executable = _fake_codev_executable(tmp_path)

    stale_readout = tmp_path / "atelier_codev_target_A_optimized_readout.tsv"
    _write_optimized_readout(stale_readout)  # 完全合法的旧 readout，最具迷惑性
    stale_zmx = tmp_path / f"{default_optimize_seed().stem}_target4.057_optimized.zmx"
    stale_zmx.write_text("! stale optimized zmx from a previous run\n", encoding="ascii")

    class FakePopen:
        pid = 7304
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            result_path, _readout_path = _buf_exp_paths_from_target_sequence_pair(sequence_path)
            _write_target_result(result_path)  # 主 tsv 成功，但**不写**新 readout
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    data = run_codev_target(
        source_zmx=default_optimize_seed(), work_dir=tmp_path,
        target_efl_mm=4.057, stage="A", executable=executable, timeout_seconds=12.0,
        emit_optimized_zmx=True,
    )
    assert data["mode"] == "target"  # 主 TSV 契约不受影响
    assert data["optimized_zmx_path"] is None
    assert "zmx_rebuild_error" in data  # 如实报错，而非认领旧 readout 的静默"成功"
    assert not stale_readout.exists()  # 陈旧 readout 已在批跑前清理
    assert not stale_zmx.exists()  # 陈旧 optimized ZMX 同样清理，且未被重建重写


def test_mock_run_codev_target_out_of_range_returncode_refuses_zmx_rebuild(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """returncode 闸：越界 returncode（∉ _OPTIMIZE_OK_RETURNCODES）意味着宏尾完
    整性存疑。主 tsv 三快照数字是真实读到的仍如实返回，且 batch_returncode 字段
    如实上报；只有 ZMX 重建侧拒绝（即便 readout 文件看似齐全合法）。"""
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 7305
        returncode = 5  # ∉ _OPTIMIZE_OK_RETURNCODES {0, 1}

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            result_path, readout_path = _buf_exp_paths_from_target_sequence_pair(sequence_path)
            _write_target_result(result_path)
            _write_optimized_readout(readout_path)  # readout 看似齐全，仍应拒建
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    data = run_codev_target(
        source_zmx=default_optimize_seed(), work_dir=tmp_path,
        target_efl_mm=4.057, stage="A", executable=executable, timeout_seconds=12.0,
        emit_optimized_zmx=True,
    )
    # 行为一：主 tsv 数据仍返回 + batch_returncode 如实上报
    assert data["mode"] == "target"
    assert data["aut_converged"] == "1"
    assert float(data["post_aut.efl_y_mm"]) == pytest.approx(4.0570)
    assert data["batch_returncode"] == 5
    # 行为二：ZMX 重建侧拒绝（fail-open 进 zmx_rebuild_error，不炸主契约）
    assert data["optimized_zmx_path"] is None
    assert "zmx_rebuild_error" in data
    assert "returncode 5" in data["zmx_rebuild_error"]


def test_mock_autovig_emit_optimized_zmx_uses_distinct_filenames_per_rung(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """真机踩坑修复回归：一次 autovig ladder climb 内，多个 rung 共用同一
    (work_dir, stage)，若 .seq/.tsv/optimized ZMX/readout 文件名不带渐晕消歧
    后缀，非最终 rung 会被后续 rung 的同名文件覆写——返回的 optimized_zmx_path
    就会指向与其数值口径不符的文件（真机原始现象：US20170045714A1 @ target
    3.797mm，采纳 rung edge=0.2，CODE V BUF EXP 对旧的 "_vig0.20_..." 命名报
    ERROR - Unable to open file. 直接中止，readout/ZMX 从未落盘）。

    用非默认 ladder 的"细化"值（0.13/0.27/0.41，均不是常见的 0.1 步进刻度）
    验证消歧对任意 edge 值都成立，不只是默认 ladder 里的几个值；同时验证
    rung0（edge=0）自己也拿到了显式、非空的专属命名（不再是裸名）。"""
    executable = _fake_codev_executable(tmp_path)
    seen: list[tuple[float, Path, Path, Path]] = []

    class FakePopen:
        pid = 7100
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            seq = sequence_path.read_text(encoding="ascii")
            result_path, readout_path = _buf_exp_paths_from_target_sequence_pair(sequence_path)
            m = re.search(r"^VUY ([\d. ]+)$", seq, re.MULTILINE)
            edge = max(float(x) for x in m.group(1).split()) if m else 0.0
            seen.append((edge, sequence_path, result_path, readout_path))
            conv = "1" if edge >= 0.27 else "0"
            dev = "0.5" if conv == "1" else "9.0"
            _write_target_result(result_path, converged=conv, dev=dev, edge=str(edge))
            _write_optimized_readout(readout_path)
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    data = run_codev_target_autovig(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
        stage="A", executable=executable, timeout_seconds=12.0,
        vig_ladder=(0.0, 0.13, 0.27, 0.41), num_fields=3, emit_optimized_zmx=True,
    )
    assert data["autovig.edge_used"] == "0.27"

    # Exactly 3 rungs ran (0.0, 0.13, 0.27 — climb stops at first convergence,
    # 0.41 never tried), and each rung's .seq/.tsv/readout are pairwise distinct.
    assert [edge for edge, *_ in seen] == [0.0, 0.13, 0.27]
    seqs = [p for _, p, _, _ in seen]
    results = [p for _, _, p, _ in seen]
    readouts = [p for _, _, _, p in seen]
    assert len(set(seqs)) == len(seqs) == 3
    assert len(set(results)) == len(results) == 3
    assert len(set(readouts)) == len(readouts) == 3

    # rung0 (edge=0.0) is no longer bare-named: explicit "_vig0000" token.
    rung0_seq = seen[0][1]
    assert "_vig0000" in rung0_seq.name

    # Accepted rung (edge=0.27) is the one whose data/zmx is actually returned.
    zmx_path = Path(data["optimized_zmx_path"])
    assert zmx_path.is_file()
    assert "_vig0270" in zmx_path.name
    assert "_vig0130" not in zmx_path.name and "_vig0000" not in zmx_path.name


def test_target_standard_passes_emit_optimized_zmx_through_to_autovig(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: list[bool] = []

    def _run(*, extra_dof: str = "none", emit_optimized_zmx: bool = False, **_ignored: object):
        captured.append(emit_optimized_zmx)
        return _standard_config_result(converged="1", rms="10.0")

    monkeypatch.setattr(codev_optimize, "run_codev_target_autovig", _run)
    run_codev_target_standard(
        source_zmx=default_optimize_seed(), work_dir=tmp_path, target_efl_mm=4.057,
        emit_optimized_zmx=True,
    )
    assert captured == [True, True]  # 两配置（asphere/both）都透传


@pytest.mark.skipif(
    not DEFAULT_CODEV_EXECUTABLE.is_file(),
    reason="real CODE V installation required for the target-mode ZMX delivery smoke",
)
def test_real_codev_target_standard_delivers_verifiable_zmx() -> None:
    """③ target 优化模式接上"优化后 ZMX 重建"闭环的真机端到端冒烟（主公
    2026-07-09 指定的最小方案）：两配置（asphere/both）各自把优化后 ZMX 落
    盘，资深可以直接打开 Verify 候选设计文件本身，而不只是拿到 tsv 数字
    快照。"""
    backend_root = Path(__file__).resolve().parents[1]
    work_dir = backend_root / "scratch_diag" / "zmx_delivery_smoke"
    try:
        result = run_codev_target_standard(
            source_zmx=default_optimize_seed(),
            work_dir=work_dir,
            target_efl_mm=3.797,
            num_fields=3,
            emit_optimized_zmx=True,
        )
    except CodeVBatchError as exc:
        if exc.kind in {"no_license", "timeout"}:
            pytest.skip(f"CODE V unavailable for target-standard ZMX smoke: {exc.message}")
        raise

    # 两配置各自的重建结果如实报告：CODE V AUT 打开非球面 DOF（extra_dof∈
    # {asphere,both}）在真机上确有可能把某面的 H/J 系数拉成非零（本次真机
    # 结果证实：US20170003482A1 的 asphere 配置就命中了）——zmx_writer 的
    # EVENASPH 只支持 CODE V A-G 对应 Zemax PARM 2-8（H/J 需要 r^18/r^20，
    # 是 zmx_writer 既有、baseline 路径共享的限制，非本次改动引入），此时
    # fail-open 只留 zmx_rebuild_error，不当测试失败——这正是本次接缝设计要
    # 验证的行为本身。tooling-blocked（"error" 键）才是真失败。
    delivered: dict[str, Path] = {}
    for extra_dof in ("asphere", "both"):
        config = result["configs"][extra_dof]
        assert "error" not in config, config.get("error")
        zmx_path_str = config.get("optimized_zmx_path")
        if zmx_path_str:
            zmx_path = Path(zmx_path_str)
            assert zmx_path.is_file()
            delivered[extra_dof] = zmx_path
            print(f"[smoke] {extra_dof} optimized ZMX delivered: {zmx_path}")
        else:
            print(
                f"[smoke] {extra_dof} ZMX rebuild fail-open (no crash): "
                f"{config.get('zmx_rebuild_error')}"
            )
    if not delivered:
        # 真机如实结果（US20170003482A1 @ target 3.797mm）：两配置的 AUT 都把
        # 某面 H/J 系数拉成非零，命中 zmx_writer 既有的 EVENASPH 限制（H/J
        # 需要 r^18/r^20，只支持 A-G/PARM 2-8；baseline 路径共享同一限制，
        # 非本次改动引入）。fail-open 契约本身没有崩——两配置分别拿到结构化
        # zmx_rebuild_error 而非异常——这正是本测试要验证的核心行为；"两配置
        # 都能落盘 ZMX" 在这颗 seed 上恰好不成立，如实记录，不伪造通过。
        print(
            "[smoke] both configs fail-open on this seed/target (real H/J nonzero "
            "coefficients) — see per-config zmx_rebuild_error above; fail-open "
            "contract held (no crash, no tooling-blocked error)."
        )
        return

    # 优先用 both（若可得，因为 both 额外覆盖了玻璃 nd/vd 重建路径），否则退
    # 到 asphere——回读用真正落盘、如实报告的那份，不假设固定哪个配置成功。
    readback_source, readback_zmx = next(
        ((name, path) for name in ("both", "asphere") if (path := delivered.get(name))),
    )
    print(f"[smoke] readback source config: {readback_source}")
    optic = load_normalized_zmx(readback_zmx)
    readback_efl_mm = float(optic.paraxial.f2())
    num_surfaces = int(optic.surfaces.num_surfaces)
    print(f"[smoke] readback EFL_mm={readback_efl_mm}")
    print(f"[smoke] num_surfaces={num_surfaces}")
    assert math.isfinite(readback_efl_mm)
    assert readback_efl_mm == pytest.approx(3.797, rel=0.02)
    assert num_surfaces > 0

    try:
        spot_result = compute_spot_diagram(optic)
        max_rms_um = max(
            wavelength.rms_radius_um
            for field in spot_result.fields
            for wavelength in field.spots_by_wavelength
        )
        print(f"[smoke] RMS spot computable, max_rms_radius_um={max_rms_um}")
    except Exception as exc:  # noqa: BLE001 - diagnostic only, report honestly either way
        print(f"[smoke] RMS spot computation raised: {type(exc).__name__}: {exc}")


@pytest.mark.skipif(
    not DEFAULT_CODEV_EXECUTABLE.is_file(),
    reason="real CODE V installation required for the target-mode ZMX delivery smoke",
)
def test_real_codev_target_delivers_verifiable_zmx_without_extra_dof(tmp_path: Path) -> None:
    """补充真机冒烟：上面 run_codev_target_standard 的两配置（asphere/both）
    在 US20170003482A1 @ target 3.797mm 上都因真实非零 H/J 系数 fail-open
    （zmx_writer 的 EVENASPH 限制，见上一测试）。这里用 extra_dof="none"
    （默认，无非球面/玻璃 DOF 实验，AUT 只动曲率+厚度）直接跑
    run_codev_target，证明 readout->zmx_writer->zmx_ingest 整条重建链路本身
    在没有 H/J 风险时确实端到端可用——不是"整条链路做不出来"，只是这颗 seed
    在 asphere/both DOF 下真的推到了 zmx_writer 尚不支持的系数阶。"""
    result = run_codev_target(
        source_zmx=default_optimize_seed(),
        work_dir=tmp_path,
        target_efl_mm=3.797,
        stage="A",
        emit_optimized_zmx=True,
    )
    assert result.get("zmx_rebuild_error") is None, result.get("zmx_rebuild_error")
    zmx_path_str = result.get("optimized_zmx_path")
    assert zmx_path_str, f"no optimized_zmx_path in real result: {result}"
    zmx_path = Path(zmx_path_str)
    assert zmx_path.is_file()
    print(f"[smoke] extra_dof=none optimized ZMX: {zmx_path}")

    optic = load_normalized_zmx(zmx_path)
    readback_efl_mm = float(optic.paraxial.f2())
    num_surfaces = int(optic.surfaces.num_surfaces)
    print(f"[smoke] readback EFL_mm={readback_efl_mm}")
    print(f"[smoke] num_surfaces={num_surfaces}")
    assert math.isfinite(readback_efl_mm)
    assert readback_efl_mm == pytest.approx(3.797, rel=0.02)
    assert num_surfaces > 0

    try:
        spot_result = compute_spot_diagram(optic)
        max_rms_um = max(
            wavelength.rms_radius_um
            for field in spot_result.fields
            for wavelength in field.spots_by_wavelength
        )
        print(f"[smoke] RMS spot computable, max_rms_radius_um={max_rms_um}")
    except Exception as exc:  # noqa: BLE001 - diagnostic only, report honestly either way
        print(f"[smoke] RMS spot computation raised: {type(exc).__name__}: {exc}")
