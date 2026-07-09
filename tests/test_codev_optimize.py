from __future__ import annotations

import math
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from app.core.engines import codev_batch
from app.core.engines.codev_batch import DEFAULT_CODEV_EXECUTABLE, CodeVBatchError
from app.core.engines.codev_optimize import (
    CODEV_OPTIMIZE_RESULT_SCHEMA,
    DEFAULT_GLASS_BOUNDS_ND_VD,
    DEFAULT_OPTIMIZE_SEED,
    TARGET_RESULT_SCHEMA,
    _autovig_profile,
    _glass_map_hull,
    build_codev_optimize_sequence,
    build_codev_target_sequence,
    default_optimize_seed,
    parse_codev_optimize_file,
    run_codev_optimize,
    run_codev_target,
    run_codev_target_autovig,
)
from app.core.engines.codev_readout import CODEV_READOUT_RESULT_SCHEMA


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
            (f"{snap}.fno", fno), (f"{snap}.epd", "1.56"), (f"{snap}.maximh_mm", imh),
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
