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
    DEFAULT_OPTIMIZE_SEED,
    TARGET_RESULT_SCHEMA,
    build_codev_optimize_sequence,
    build_codev_target_sequence,
    default_optimize_seed,
    parse_codev_optimize_file,
    run_codev_optimize,
    run_codev_target,
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


def _write_target_result(path: Path) -> None:
    rows = [
        ("schema", TARGET_RESULT_SCHEMA), ("status", "ok"),
        ("mode", "target"), ("stage", "A"), ("source_zmx", DEFAULT_OPTIMIZE_SEED),
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
    rows += [("efl_target_deviation_pct", "0.001"), ("aut_converged", "1")]
    path.write_text("\n".join(f"{k}\t{v}" for k, v in rows) + "\n", encoding="utf-8")


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
