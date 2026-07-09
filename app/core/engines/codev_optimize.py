"""CODE V AUT optimization batch adapter for imported ZMX seeds."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.core.engines.codev_batch import (
    DEFAULT_CODEV_EXECUTABLE,
    CodeVBatchError,
    CodeVBatchResult,
    parse_codev_result_file,
    run_codev_batch,
)
from app.core.engines.codev_readout import (
    CODEV_READOUT_RESULT_SCHEMA,
    CodeVReadout,
    parse_codev_readout_file,
)
from app.core.engines.codev_roundtrip import DEFAULT_PATENT_ROUNDTRIP_SEED
from app.core.engines.zmx_writer import write_zmx_from_codev_readout
from app.core.zmx_ingest import ZMX_AMMO_DIR, load_normalized_zmx

CODEV_OPTIMIZE_RESULT_SCHEMA = "atelier-codev-optimize-v1"
DEFAULT_OPTIMIZE_SEED = DEFAULT_PATENT_ROUNDTRIP_SEED

_OPTIMIZE_SEQUENCE_NAME = "atelier_codev_optimize.seq"
_OPTIMIZE_RESULT_NAME = "atelier_codev_optimize.tsv"
_OPTIMIZED_READOUT_NAME = "atelier_codev_optimized_readout.tsv"
_OPTIMIZED_ZMX_NAME = "optimized.zmx"
_OPTIMIZE_OK_RETURNCODES = {0, 1}
_DEFAULT_TOLERANCE_TOP_N = 5
_DEFAULT_TOLERANCE_MTF_FREQUENCY_LPMM = 100.0
_DEFAULT_TOLERANCE_RADIUS_DELTA_FRACTION = 0.005
_DEFAULT_TOLERANCE_THICKNESS_DELTA_MM = 0.005
_DEFAULT_TOLERANCE_NRD = 32
_OPTIMIZE_REQUIRED_KEYS = (
    "schema",
    "status",
    "source_zmx",
    "optimization_status",
    "glass_policy",
    "thickness_policy",
    "optimized_readout_path",
    "optimized_zmx_filename",
    "before.efl_y_mm",
    "before.max_lateral_color_um",
    "before.max_rms_spot_diameter_um",
    "before.max_rms_wavefront_error_waves",
    "before.max_distortion_pct",
    "after.efl_y_mm",
    "after.max_lateral_color_um",
    "after.max_rms_spot_diameter_um",
    "after.max_rms_wavefront_error_waves",
    "after.max_distortion_pct",
    "efl_deviation_pct",
)
_ASPHERE_COEFFICIENT_LABELS = ("K", "A", "B", "C", "D", "E", "F", "G", "H", "J")


@dataclass(frozen=True)
class CodeVOptimizationMetrics:
    """Metrics explicitly emitted by the CODE V optimization macro."""

    efl_y_mm: float
    max_lateral_color_um: float
    max_rms_spot_diameter_um: float
    max_rms_wavefront_error_waves: float
    max_distortion_pct: float

    def describe(self) -> dict[str, float]:
        return {
            "efl_y_mm": self.efl_y_mm,
            "max_lateral_color_um": self.max_lateral_color_um,
            "max_rms_spot_diameter_um": self.max_rms_spot_diameter_um,
            "max_rms_wavefront_error_waves": self.max_rms_wavefront_error_waves,
            "max_distortion_pct": self.max_distortion_pct,
        }


@dataclass(frozen=True)
class CodeVToleranceSensitivity:
    """One CODE V perturbation replay row emitted by the sensitivity block."""

    rank: int
    parameter_name: str
    perturbation: str
    mtf_drop: float
    nominal_mtf: float | None = None
    perturbed_mtf: float | None = None
    provenance: str = "codev-run"

    def describe(self) -> dict[str, object]:
        return {
            "rank": self.rank,
            "parameter_name": self.parameter_name,
            "perturbation": self.perturbation,
            "mtf_drop": self.mtf_drop,
            "nominal_mtf": self.nominal_mtf,
            "perturbed_mtf": self.perturbed_mtf,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class CodeVOptimizeSummary:
    """Structured metrics and policy flags parsed from the AUT result TSV."""

    source_zmx: str
    optimization_status: str
    glass_policy: str
    thickness_policy: str
    optimized_readout_path: str
    optimized_zmx_filename: str
    before: CodeVOptimizationMetrics
    after: CodeVOptimizationMetrics
    efl_deviation_pct: float
    tolerance_sensitivity: tuple[CodeVToleranceSensitivity, ...] = ()
    tolerance_metric: str = "CODE V perturbation replay MTF drop"
    tolerance_provenance: str = "codev-run"

    def describe(self) -> dict[str, object]:
        return {
            "source_zmx": self.source_zmx,
            "optimization_status": self.optimization_status,
            "glass_policy": self.glass_policy,
            "thickness_policy": self.thickness_policy,
            "optimized_readout_path": self.optimized_readout_path,
            "optimized_zmx_filename": self.optimized_zmx_filename,
            "before": self.before.describe(),
            "after": self.after.describe(),
            "efl_deviation_pct": self.efl_deviation_pct,
            "tolerance_metric": self.tolerance_metric,
            "tolerance_provenance": self.tolerance_provenance,
            "tolerance_sensitivity_top_n": [
                item.describe() for item in self.tolerance_sensitivity
            ],
        }


@dataclass(frozen=True)
class CodeVOptimizeResult:
    """Completed CODE V AUT run, reconstructed ZMX, and ingest confirmation."""

    batch: CodeVBatchResult
    source_zmx: Path
    summary: CodeVOptimizeSummary
    optimized_readout_path: Path
    optimized_readout: CodeVReadout
    optimized_zmx: Path
    ingested_efl_mm: float

    @property
    def data(self) -> dict[str, str]:
        return self.batch.data

    def describe(self) -> dict[str, object]:
        return {
            "batch": self.batch.describe(),
            "source_zmx": str(self.source_zmx),
            "summary": self.summary.describe(),
            "optimized_readout_path": str(self.optimized_readout_path),
            "optimized_readout": self.optimized_readout.describe(),
            "optimized_zmx": str(self.optimized_zmx),
            "ingested_efl_mm": self.ingested_efl_mm,
        }


def default_optimize_seed() -> Path:
    """Return the selected patent seed for ENGINE-05a."""

    return ZMX_AMMO_DIR / DEFAULT_OPTIMIZE_SEED


def build_codev_optimize_sequence(
    *,
    source_zmx: Path | str,
    result_path: Path | str,
    optimized_readout_path: Path | str,
    optimized_zmx_filename: str = _OPTIMIZED_ZMX_NAME,
    max_cycles: int = 25,
    min_cycles: int = 3,
    min_center_thickness_mm: float = 0.025,
    min_edge_thickness_mm: float = 0.025,
    max_center_thickness_mm: float = 10.0,
    min_air_gap_mm: float = 0.001,
    lateral_color_weight: float = 0.01,
    rms_spot_weight: float = 0.001,
    tolerance_top_n: int = _DEFAULT_TOLERANCE_TOP_N,
    tolerance_mtf_frequency_lpmm: float = _DEFAULT_TOLERANCE_MTF_FREQUENCY_LPMM,
    tolerance_radius_delta_fraction: float = _DEFAULT_TOLERANCE_RADIUS_DELTA_FRACTION,
    tolerance_thickness_delta_mm: float = _DEFAULT_TOLERANCE_THICKNESS_DELTA_MM,
    tolerance_nrd: int = _DEFAULT_TOLERANCE_NRD,
) -> str:
    """Build a CODE V sequence that imports a ZMX, runs AUT, and exports TSVs."""

    _validate_positive_int(max_cycles, "max_cycles")
    _validate_positive_int(min_cycles, "min_cycles")
    _validate_nonnegative(min_center_thickness_mm, "min_center_thickness_mm")
    _validate_nonnegative(min_edge_thickness_mm, "min_edge_thickness_mm")
    _validate_positive(max_center_thickness_mm, "max_center_thickness_mm")
    _validate_nonnegative(min_air_gap_mm, "min_air_gap_mm")
    _validate_positive(lateral_color_weight, "lateral_color_weight")
    _validate_positive(rms_spot_weight, "rms_spot_weight")
    _validate_positive_int(tolerance_top_n, "tolerance_top_n")
    _validate_positive(tolerance_mtf_frequency_lpmm, "tolerance_mtf_frequency_lpmm")
    _validate_positive(tolerance_radius_delta_fraction, "tolerance_radius_delta_fraction")
    _validate_positive(tolerance_thickness_delta_mm, "tolerance_thickness_delta_mm")
    _validate_positive_int(tolerance_nrd, "tolerance_nrd")

    source_zmx = Path(source_zmx)
    result_path = Path(result_path)
    optimized_readout_path = Path(optimized_readout_path)
    lines: list[str] = [
        "! Generated by app.core.engines.codev_optimize.",
        *(_metric_function_block()),
        "OUT NO",
        f"IN CV_MACRO:ZEMAXOS_TO_CV {_quote_codev_path(source_zmx)}",
        "DEF VAR SA",
        "^baseline_efl_y_mm == ABSF((EFY))",
        *_capture_metric_variables("before"),
        "AUT",
        "  SUR N",
        "  CHG SA",
        "  WFR Y",
        "  WTF FA 10",
        "  EFL = ^baseline_efl_y_mm",
        "  @atelier_latcolor == @lcum(1)",
        "  @atelier_latcolor = 0",
        f"  WTC {_fmt_number(lateral_color_weight)}",
        "  @atelier_rmsspot == @rmssum(1)",
        "  @atelier_rmsspot = 0",
        f"  WTC {_fmt_number(rms_spot_weight)}",
        f"  MNT {_fmt_number(min_center_thickness_mm)}",
        f"  MNE {_fmt_number(min_edge_thickness_mm)}",
        f"  MXT {_fmt_number(max_center_thickness_mm)}",
        f"  MNA {_fmt_number(min_air_gap_mm)}",
        f"  MXC {max_cycles}",
        f"  MNC {min_cycles}",
        "  IMP 0.001",
        "GO",
        *_capture_metric_variables("after"),
        "^efl_deviation_pct == 0",
        "IF ABSF(^before_efl_y_mm) > 1.0E-12",
        "  ^efl_deviation_pct == "
        "ABSF((^after_efl_y_mm-^before_efl_y_mm)/^before_efl_y_mm)*100",
        "END IF",
        "^row == 1",
    ]
    _append_put_row(lines, '"schema"', f'"{CODEV_OPTIMIZE_RESULT_SCHEMA}"')
    _append_put_row(lines, '"status"', '"ok"')
    _append_put_row(lines, '"source_zmx"', f'"{source_zmx.name}"')
    _append_put_row(lines, '"optimization_status"', '"aut_completed"')
    _append_put_row(lines, '"glass_policy"', '"glass-not-varied"')
    _append_put_row(
        lines,
        '"thickness_policy"',
        '"MNT/MNE/MXT/MNA bounded in AUT"',
    )
    _append_put_row(lines, '"optimized_readout_path"', f'"{optimized_readout_path.name}"')
    _append_put_row(lines, '"optimized_zmx_filename"', f'"{optimized_zmx_filename}"')
    for prefix in ("before", "after"):
        _append_metric_rows(lines, prefix)
    _append_put_row(lines, '"efl_deviation_pct"', "^efl_deviation_pct")
    _append_tolerance_sensitivity_rows(
        lines,
        top_n=tolerance_top_n,
        mtf_frequency_lpmm=tolerance_mtf_frequency_lpmm,
        radius_delta_fraction=tolerance_radius_delta_fraction,
        thickness_delta_mm=tolerance_thickness_delta_mm,
        nrd=tolerance_nrd,
    )
    lines.extend(
        [
            f"BUF EXP B1 {_quote_codev_path(result_path)}",
            "BUF DEL B1",
            *_optimized_readout_block(source_name=source_zmx.name),
            f"BUF EXP B1 {_quote_codev_path(optimized_readout_path)}",
            "BUF DEL B1",
            "OUT YES",
            "EXI YES",
            "",
        ]
    )
    return "\n".join(lines)


def write_codev_optimize_sequence(
    *,
    sequence_path: Path | str,
    source_zmx: Path | str,
    result_path: Path | str,
    optimized_readout_path: Path | str,
    optimized_zmx_filename: str = _OPTIMIZED_ZMX_NAME,
    **kwargs: object,
) -> Path:
    """Write the CODE V AUT optimization sequence and return the path."""

    sequence_path = Path(sequence_path)
    sequence_path.parent.mkdir(parents=True, exist_ok=True)
    sequence_path.write_text(
        build_codev_optimize_sequence(
            source_zmx=source_zmx,
            result_path=result_path,
            optimized_readout_path=optimized_readout_path,
            optimized_zmx_filename=optimized_zmx_filename,
            **kwargs,
        ),
        encoding="ascii",
    )
    return sequence_path


def run_codev_optimize(
    *,
    source_zmx: Path | str | None = None,
    work_dir: Path | str,
    executable: Path | str | os.PathLike[str] = DEFAULT_CODEV_EXECUTABLE,
    timeout_seconds: float = 180.0,
    optimized_zmx_filename: str = _OPTIMIZED_ZMX_NAME,
    platform_name: str = os.name,
    **sequence_options: object,
) -> CodeVOptimizeResult:
    """Run CODE V AUT optimization and ingest the rebuilt optimized ZMX."""

    source_zmx = default_optimize_seed() if source_zmx is None else Path(source_zmx)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    sequence_path = work_dir / _OPTIMIZE_SEQUENCE_NAME
    result_path = work_dir / _OPTIMIZE_RESULT_NAME
    optimized_readout_path = work_dir / _OPTIMIZED_READOUT_NAME
    optimized_zmx_path = work_dir / optimized_zmx_filename
    for stale in (optimized_readout_path, optimized_zmx_path):
        if stale.exists():
            stale.unlink()

    write_codev_optimize_sequence(
        sequence_path=sequence_path,
        source_zmx=source_zmx,
        result_path=result_path,
        optimized_readout_path=optimized_readout_path,
        optimized_zmx_filename=optimized_zmx_filename,
        **sequence_options,
    )
    batch = run_codev_batch(
        sequence_path=sequence_path,
        result_path=result_path,
        executable=executable,
        work_dir=work_dir,
        timeout_seconds=timeout_seconds,
        platform_name=platform_name,
        expected_schema=CODEV_OPTIMIZE_RESULT_SCHEMA,
        required_keys=_OPTIMIZE_REQUIRED_KEYS,
        allow_nonzero_ok_result=True,
    )
    if batch.returncode not in _OPTIMIZE_OK_RETURNCODES:
        raise CodeVBatchError(
            "failure",
            "CODE V optimization exited with an unsupported returncode despite an ok result file",
            details={
                "returncode": batch.returncode,
                "allowed_returncodes": sorted(_OPTIMIZE_OK_RETURNCODES),
                "data": batch.data,
                "result_path": str(batch.result_path),
            },
        )

    summary = parse_codev_optimize_data(batch.data)
    readout_path = work_dir / summary.optimized_readout_path
    optimized_readout = parse_codev_readout_file(readout_path)
    optimized_zmx = write_zmx_from_codev_readout(
        optimized_readout,
        optimized_zmx_path,
        name=f"{source_zmx.stem}-optimized",
    )
    optic = load_normalized_zmx(optimized_zmx)
    ingested_efl_mm = float(optic.paraxial.f2())
    if not math.isfinite(ingested_efl_mm):
        raise CodeVBatchError(
            "failure",
            "optimized.zmx was rebuilt but zmx_ingest returned a non-finite EFL",
            details={"optimized_zmx": str(optimized_zmx), "ingested_efl_mm": ingested_efl_mm},
        )
    return CodeVOptimizeResult(
        batch=batch,
        source_zmx=source_zmx,
        summary=summary,
        optimized_readout_path=readout_path,
        optimized_readout=optimized_readout,
        optimized_zmx=optimized_zmx,
        ingested_efl_mm=ingested_efl_mm,
    )


# ===========================================================================
# Target-mode (spike ③优化落地): EFL->客户 target + FNO 锁 F#(E1 实测) + 三快照
# 加法式：全新函数，不触碰 baseline build_codev_optimize_sequence（零回归）。
# spec: docs/superpowers/specs/2026-07-08-codev-target-convergence-spike-design.md
# ===========================================================================

TARGET_RESULT_SCHEMA = "atelier-codev-target-v1"
_TARGET_SNAPSHOTS = ("seed_baseline", "config_pre_aut", "post_aut")


def _capture_target_snapshot(prefix: str) -> list[str]:
    """Capture efl + 4 像质度量 + fno/epd/maximh for one snapshot."""
    lines = list(_capture_metric_variables(prefix))  # efl + lat/spot/wfe/dist
    lines += [
        f"^{prefix}_fno == ABSF((FNO))",
        f"^{prefix}_epd == ABSF((EPD))",
        f"^{prefix}_ftyp == (TYP FLD)",
        f"^{prefix}_maximh == 0",
        "FOR ^f 1 (NUM F)",
        "  ^yh == (YRI F^f Z1)",
        f'  IF ^{prefix}_ftyp = "ANG"',
        f"    ^yh == ^{prefix}_efl_y_mm * TANF((YAN F^f Z1)*4*ATANF(1)/180)",
        f'  ELS IF ^{prefix}_ftyp = "IMG"',
        "    ^yh == (YIM F^f Z1)",
        "  END IF",
        f"  IF ABSF(^yh) > ^{prefix}_maximh",
        f"    ^{prefix}_maximh == ABSF(^yh)",
        "  END IF",
        "END FOR",
    ]
    return lines


def _append_target_snapshot_rows(lines: list[str], prefix: str) -> None:
    _append_metric_rows(lines, prefix)  # efl + 4 metrics
    _append_put_row(lines, f'"{prefix}.fno"', f"^{prefix}_fno")
    _append_put_row(lines, f'"{prefix}.epd"', f"^{prefix}_epd")
    _append_put_row(lines, f'"{prefix}.maximh_mm"', f"^{prefix}_maximh")


def _extra_dof_block(extra_dof: str) -> list[str]:
    """加优化变量（DOF 实验 · 主公授权解锁接缝2/非球面）：
    extra_dof ∈ none|asphere|glass|both。非球面系数 AC..JC(4-20阶) / 玻璃 GLC，
    per-surface 循环设变量（CODE V 语法：`<X>C S^s 0` 非球面、`GLC S^s 0` 玻璃）。"""
    if extra_dof not in ("none", "asphere", "glass", "both"):
        raise ValueError(f"extra_dof must be none|asphere|glass|both: {extra_dof!r}")
    if extra_dof == "none":
        return []
    lines = ["FOR ^s 1 (NUM S)"]
    if extra_dof in ("asphere", "both"):
        lines.append('  IF (TYP SUR S^s) = "ASP"')
        lines += [f"    {c}C S^s 0" for c in ("A", "B", "C", "D", "E", "F", "G", "H", "J")]
        lines.append("  END IF")
    if extra_dof in ("glass", "both"):
        lines += [
            "  ^probe_nd == ABSF((IND S^s W1))",
            "  IF ^probe_nd > 1.05",  # 真玻璃（非空气 nd≈1）才设玻璃变量
            "    GLC S^s 0",
            "  END IF",
        ]
    lines.append("END FOR")
    return lines


def _validate_vignetting(vignetting: list[float] | None) -> None:
    if vignetting is None:
        return
    if not vignetting:
        raise ValueError("vignetting must be a non-empty list or None")
    for v in vignetting:
        numeric = float(v)
        if not math.isfinite(numeric) or numeric < 0 or numeric >= 1:
            raise ValueError(f"vignetting fraction must be in [0,1): {v!r}")


def _vignetting_edge(vignetting: list[float] | None) -> float:
    """Representative edge (max) vignetting fraction for provenance; 0 if none."""
    return max(vignetting) if vignetting else 0.0


def _vignetting_block(vignetting: list[float]) -> list[str]:
    """Set per-field 渐晕 factors (VUY/VLY/VUX/VLX), positional over fields F1..Fn.
    Clips the outer entrance-pupil fraction so TIR-ing marginal rays leave the
    optimization ray grid. Does NOT change F# (defined by the stop aperture)."""
    values = " ".join(_fmt_number(v) for v in vignetting)
    return [f"{cmd} {values}" for cmd in ("VUY", "VLY", "VUX", "VLX")]


def build_codev_target_sequence(
    *,
    source_zmx: Path | str,
    result_path: Path | str,
    target_efl_mm: float,
    target_f_number: float | None = None,
    target_imh_mm: float | None = None,
    stage: str = "A",
    extra_dof: str = "none",
    vignetting: list[float] | None = None,
    max_cycles: int = 25,
    min_cycles: int = 3,
    lateral_color_weight: float = 0.01,
    rms_spot_weight: float = 0.001,
    min_center_thickness_mm: float = 0.025,
    min_edge_thickness_mm: float = 0.025,
    max_center_thickness_mm: float = 10.0,
    min_air_gap_mm: float = 0.001,
) -> str:
    """Build target-mode sequence: import seed, capture 3 snapshots, pull EFL to
    客户 target (seam 1), lock F# via FNO mode (seam 3a, E1 实测锁), keep merit
    (lat color + RMS spot). Stage A=EFL only; B=+F#; C(IMH 场重建)另做。

    vignetting: 可选 per-field 渐晕裁剪 fraction（0≤v<1，clip 掉的入瞳半径比例）。
    ZMX->CV 导入丢弃 ray-aiming/渐晕 → 宽+快种子离轴边缘光线 TIR 毒化优化光栅；
    渐晕裁掉这些光线让 AUT 光栅可追迹（**不改 F#**，F# 由光阑定）。由
    run_codev_target_autovig 自动搜最小收敛渐晕。诊断见 .planning/debug/codev-target-convergence.md。"""

    _validate_positive(target_efl_mm, "target_efl_mm")
    if target_f_number is not None:
        _validate_positive(target_f_number, "target_f_number")
    if target_imh_mm is not None:
        _validate_positive(target_imh_mm, "target_imh_mm")
    _validate_vignetting(vignetting)
    _validate_positive_int(max_cycles, "max_cycles")
    _validate_positive_int(min_cycles, "min_cycles")

    source_zmx = Path(source_zmx)
    result_path = Path(result_path)

    lines: list[str] = [
        "! target-mode: EFL->target + FNO-lock F# + 3 snapshots. codev_optimize.",
        *_metric_function_block(),
        "OUT NO",
        f"IN CV_MACRO:ZEMAXOS_TO_CV {_quote_codev_path(source_zmx)}",
        "DEF VAR SA",  # 默认变量集=曲率+厚度（非球面/玻璃冻结）
        # 加 DOF 实验（接缝2 玻璃可变 / 非球面系数放开 · 主公授权）
        *_extra_dof_block(extra_dof),
        # 快照1 seed_baseline（配置前，仅对照）
        *_capture_target_snapshot("seed_baseline"),
    ]
    # seam 3a: F# 走 FNO 模式（E1 实测：AUT 每轮重解 EPD 锁 F#）
    if target_f_number is not None:
        lines.append(f"FNO {_fmt_number(target_f_number)}")
    # ray setup fix: 渐晕裁剪优化光栅（导入后丢 ray-aiming 致离轴 TIR 的修复）
    if vignetting is not None:
        lines += _vignetting_block(vignetting)
    # 快照2 config_pre_aut（客户配置后、优化前——含 F#/渐晕 setup）
    lines += _capture_target_snapshot("config_pre_aut")
    # AUT: seam 1 EFL->target + 既有 merit（横向色差 + RMS 点列）
    lines += [
        "AUT",
        "  SUR N",
        "  CHG SA",
        "  WFR Y",
        "  WTF FA 10",
        f"  EFL = {_fmt_number(target_efl_mm)}",
        "  @atelier_latcolor == @lcum(1)",
        "  @atelier_latcolor = 0",
        f"  WTC {_fmt_number(lateral_color_weight)}",
        "  @atelier_rmsspot == @rmssum(1)",
        "  @atelier_rmsspot = 0",
        f"  WTC {_fmt_number(rms_spot_weight)}",
        f"  MNT {_fmt_number(min_center_thickness_mm)}",
        f"  MNE {_fmt_number(min_edge_thickness_mm)}",
        f"  MXT {_fmt_number(max_center_thickness_mm)}",
        f"  MNA {_fmt_number(min_air_gap_mm)}",
        f"  MXC {max_cycles}",
        f"  MNC {min_cycles}",
        "  IMP 0.001",
        "GO",
    ]
    # 快照3 post_aut（优化后）
    lines += _capture_target_snapshot("post_aut")
    # EFL 达成偏差 + aut_converged 代理（E6：无显式收敛码→EFL-hit）
    lines += [
        f"^target_efl == {_fmt_number(target_efl_mm)}",
        "^efl_target_dev_pct == 0",
        "IF ABSF(^target_efl) > 1.0E-12",
        "  ^efl_target_dev_pct == ABSF((^post_aut_efl_y_mm-^target_efl)/^target_efl)*100",
        "END IF",
        "^aut_converged == 0",
        "IF ^efl_target_dev_pct < 2.0",
        "  ^aut_converged == 1",
        "END IF",
        "^numf_out == (NUM F)",
        "^row == 1",
    ]
    _append_put_row(lines, '"schema"', f'"{TARGET_RESULT_SCHEMA}"')
    _append_put_row(lines, '"status"', '"ok"')
    _append_put_row(lines, '"mode"', '"target"')
    _append_put_row(lines, '"stage"', f'"{stage}"')
    _append_put_row(lines, '"source_zmx"', f'"{source_zmx.name}"')
    _append_put_row(lines, '"num_fields"', "^numf_out")
    _append_put_row(lines, '"vignetting_edge"', _fmt_number(_vignetting_edge(vignetting)))
    _append_put_row(lines, '"target.efl_mm"', "^target_efl")
    if target_f_number is not None:
        _append_put_row(lines, '"target.f_number"', _fmt_number(target_f_number))
    if target_imh_mm is not None:
        _append_put_row(lines, '"target.imh_mm"', _fmt_number(target_imh_mm))
    for snap in _TARGET_SNAPSHOTS:
        _append_target_snapshot_rows(lines, snap)
    _append_put_row(lines, '"efl_target_deviation_pct"', "^efl_target_dev_pct")
    _append_put_row(lines, '"aut_converged"', "^aut_converged")
    lines += [
        f"BUF EXP B1 {_quote_codev_path(result_path)}",
        "BUF DEL B1",
        "OUT YES",
        "EXI YES",
        "",
    ]
    return "\n".join(lines)


_TARGET_REQUIRED_KEYS = (
    "schema", "status", "mode", "stage", "target.efl_mm",
    "seed_baseline.efl_y_mm", "seed_baseline.fno", "seed_baseline.maximh_mm",
    "config_pre_aut.efl_y_mm", "config_pre_aut.fno", "config_pre_aut.maximh_mm",
    "post_aut.efl_y_mm", "post_aut.fno", "post_aut.epd", "post_aut.maximh_mm",
    "post_aut.max_rms_spot_diameter_um", "post_aut.max_rms_wavefront_error_waves",
    "post_aut.max_distortion_pct",
    "efl_target_deviation_pct", "aut_converged",
)


def run_codev_target(
    *,
    source_zmx: Path | str,
    work_dir: Path | str,
    target_efl_mm: float,
    target_f_number: float | None = None,
    target_imh_mm: float | None = None,
    stage: str = "A",
    executable: Path | str | os.PathLike[str] = DEFAULT_CODEV_EXECUTABLE,
    timeout_seconds: float = 180.0,
    platform_name: str = os.name,
    **sequence_options: object,
) -> dict[str, str]:
    """Run one target-mode AUT and return the parsed three-snapshot data dict."""

    source_zmx = Path(source_zmx)
    work_dir = Path(work_dir).resolve()  # 绝对路径：CODE V BUF EXP 相对路径会二次拼接失败
    work_dir.mkdir(parents=True, exist_ok=True)
    seq = work_dir / f"atelier_codev_target_{stage}.seq"
    res = work_dir / f"atelier_codev_target_{stage}.tsv"
    seq.write_text(
        build_codev_target_sequence(
            source_zmx=source_zmx, result_path=res, target_efl_mm=target_efl_mm,
            target_f_number=target_f_number, target_imh_mm=target_imh_mm, stage=stage,
            **sequence_options,
        ),
        encoding="ascii",
    )
    batch = run_codev_batch(
        sequence_path=seq, result_path=res, executable=executable, work_dir=work_dir,
        timeout_seconds=timeout_seconds, platform_name=platform_name,
        expected_schema=TARGET_RESULT_SCHEMA, required_keys=_TARGET_REQUIRED_KEYS,
        allow_nonzero_ok_result=True,
    )
    return dict(batch.data)


# 自动渐晕搜索（主公 2026-07-09 ratify 的 ray-setup 方案）：宽+快种子导入丢
# ray-aiming → 离轴边缘 TIR 毒化优化光栅。搜最小离轴渐晕让 AUT 收敛，保 native F#。
# edge_used 作为质量 provenance 上报（渐晕越大=越多边缘光被弃=收敛越"取巧"，供资深判）。
_DEFAULT_VIG_LADDER: tuple[float, ...] = (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7)


def _autovig_profile(edge: float, num_fields: int) -> list[float] | None:
    """On-axis 场不裁（居中系统轴上不渐晕），离轴场均匀裁 `edge`。edge==0 或单场
    → None（走默认零渐晕路径）。TIR 是离轴宽角光线，probe_field 已证离轴-only 即收敛。"""
    if edge <= 0 or num_fields <= 1:
        return None
    return [0.0] + [float(edge)] * (num_fields - 1)


def run_codev_target_autovig(
    *,
    source_zmx: Path | str,
    work_dir: Path | str,
    target_efl_mm: float,
    target_f_number: float | None = None,
    target_imh_mm: float | None = None,
    stage: str = "A",
    vig_ladder: tuple[float, ...] = _DEFAULT_VIG_LADDER,
    num_fields: int | None = None,
    executable: Path | str | os.PathLike[str] = DEFAULT_CODEV_EXECUTABLE,
    timeout_seconds: float = 180.0,
    platform_name: str = os.name,
    **sequence_options: object,
) -> dict[str, str]:
    """Climb `vig_ladder` from 0, return the FIRST target run whose AUT converges
    (EFL dev<2%) — i.e. the minimal off-axis 渐晕 needed — preserving F#. Annotates
    the returned dict with autovig.edge_used / autovig.converged / autovig.trace so
    资深 sees how much aperture was clipped to converge. If none converge, returns the
    min-deviation trial.

    Resilient to per-rung timeout/failure: a rung that errors (e.g. rung-0 v=0 flooding
    TIR → hard timeout) is recorded and the search keeps climbing (higher 渐晕 clips the
    TIR → the rung runs fast). num_fields is learned from the rung-0 run, or injected
    (needed to keep climbing when rung-0 itself times out). Only re-raises (tooling-
    blocked) when EVERY rung fails to produce parseable data."""

    trace: list[str] = []
    best: dict[str, str] | None = None
    best_dev = float("inf")
    last_error: CodeVBatchError | None = None

    def _trial(edge: float, vig: list[float] | None) -> tuple[dict[str, str] | None, bool]:
        nonlocal best, best_dev, last_error
        try:
            data = run_codev_target(
                source_zmx=source_zmx, work_dir=work_dir, target_efl_mm=target_efl_mm,
                target_f_number=target_f_number, target_imh_mm=target_imh_mm, stage=stage,
                executable=executable, timeout_seconds=timeout_seconds,
                platform_name=platform_name, vignetting=vig, **sequence_options,
            )
        except CodeVBatchError as exc:
            last_error = exc
            trace.append(f"e{edge:.2f}:{exc.kind}")
            return None, False
        try:
            dev = float(data.get("efl_target_deviation_pct", "nan"))
        except ValueError:
            dev = float("nan")
        conv = str(data.get("aut_converged")) == "1"
        trace.append(f"e{edge:.2f}:dev{dev:.3g}:c{int(conv)}")
        if not math.isnan(dev) and dev < best_dev:
            best_dev, best = dev, data
        return data, conv

    def _annotate(data: dict[str, str], edge: float, converged: bool) -> dict[str, str]:
        return {**data, "autovig.edge_used": _fmt_number(edge),
                "autovig.converged": "1" if converged else "0",
                "autovig.trace": " ".join(trace)}

    def _blocked_or_best(edge: float) -> dict[str, str]:
        if best is None and last_error is not None:
            raise last_error  # 全无可用数据 → tooling-blocked（保持既有语义）
        return _annotate(dict(best) if best is not None else {}, edge, False)

    # Rung 0 (always first): no 渐晕 — native-convergence check + learns field count.
    data, conv = _trial(0.0, None)
    if conv and data is not None:
        return _annotate(data, 0.0, True)
    nf = num_fields
    if nf is None and data is not None:
        nf = int(float(data.get("num_fields", "0") or "0"))
    if not nf or nf <= 1:
        return _blocked_or_best(0.0)  # rung0 超时/失败且未注入 nf，或单场种子
    # Climb the nonzero rungs; return the minimal 渐晕 that converges. 每级超时/失败即续爬。
    last_edge = 0.0
    for edge in (e for e in vig_ladder if e > 0):
        vig = _autovig_profile(edge, nf)
        if vig is None:
            break  # 单场种子：离轴裁剪无从帮忙（TIR 若在轴上）
        last_edge = edge
        data, conv = _trial(edge, vig)
        if conv and data is not None:
            return _annotate(data, edge, True)
    return _blocked_or_best(last_edge)


def parse_codev_optimize_file(result_path: Path | str) -> CodeVOptimizeSummary:
    """Parse an AUT optimization TSV exported by ``BUF EXP``."""

    data = parse_codev_result_file(
        result_path,
        expected_schema=CODEV_OPTIMIZE_RESULT_SCHEMA,
        required_keys=_OPTIMIZE_REQUIRED_KEYS,
    )
    return parse_codev_optimize_data(data)


def parse_codev_optimize_data(data: Mapping[str, str]) -> CodeVOptimizeSummary:
    """Convert flat optimization TSV data into structured metrics."""

    if data.get("schema") != CODEV_OPTIMIZE_RESULT_SCHEMA:
        raise CodeVBatchError(
            "failure",
            "CODE V optimize data has an unexpected schema",
            details={
                "expected_schema": CODEV_OPTIMIZE_RESULT_SCHEMA,
                "actual_schema": data.get("schema"),
            },
        )
    if data.get("status") != "ok":
        raise CodeVBatchError(
            "failure",
            "CODE V optimize data reported a non-ok status",
            details={"status": data.get("status")},
        )
    return CodeVOptimizeSummary(
        source_zmx=_required_text(data, "source_zmx"),
        optimization_status=_required_text(data, "optimization_status"),
        glass_policy=_required_text(data, "glass_policy"),
        thickness_policy=_required_text(data, "thickness_policy"),
        optimized_readout_path=_required_text(data, "optimized_readout_path"),
        optimized_zmx_filename=_required_text(data, "optimized_zmx_filename"),
        before=_parse_metrics(data, "before"),
        after=_parse_metrics(data, "after"),
        efl_deviation_pct=_required_float(data, "efl_deviation_pct"),
        tolerance_sensitivity=_parse_tolerance_sensitivity(data),
        tolerance_metric=data.get(
            "tolerance.metric",
            "CODE V perturbation replay MTF drop",
        ),
        tolerance_provenance=data.get("tolerance.provenance", "codev-run"),
    )


def _parse_tolerance_sensitivity(
    data: Mapping[str, str],
) -> tuple[CodeVToleranceSensitivity, ...]:
    count_text = data.get("tolerance.count", "").strip()
    if not count_text:
        return ()
    try:
        count = int(float(count_text))
    except ValueError as exc:
        raise CodeVBatchError(
            "failure",
            "CODE V tolerance data contains a non-integer count",
            details={"key": "tolerance.count", "value": count_text},
        ) from exc
    if count <= 0:
        return ()

    top_n = _optional_positive_int(data, "tolerance.top_n") or _DEFAULT_TOLERANCE_TOP_N
    items: list[CodeVToleranceSensitivity] = []
    for index in range(1, count + 1):
        prefix = f"tolerance.{index}"
        parameter_name = _required_text(data, f"{prefix}.parameter_name")
        perturbation = _required_text(data, f"{prefix}.perturbation")
        mtf_drop = _required_float(data, f"{prefix}.mtf_drop")
        if mtf_drop < 0:
            raise CodeVBatchError(
                "failure",
                "CODE V tolerance data contains a negative MTF drop",
                details={"key": f"{prefix}.mtf_drop", "value": mtf_drop},
            )
        items.append(
            CodeVToleranceSensitivity(
                rank=index,
                parameter_name=parameter_name,
                perturbation=perturbation,
                mtf_drop=mtf_drop,
                nominal_mtf=_optional_float(data, f"{prefix}.nominal_mtf"),
                perturbed_mtf=_optional_float(data, f"{prefix}.perturbed_mtf"),
                provenance=data.get("tolerance.provenance", "codev-run"),
            )
        )

    ranked = sorted(items, key=lambda item: (-item.mtf_drop, item.parameter_name))
    return tuple(
        CodeVToleranceSensitivity(
            rank=rank,
            parameter_name=item.parameter_name,
            perturbation=item.perturbation,
            mtf_drop=item.mtf_drop,
            nominal_mtf=item.nominal_mtf,
            perturbed_mtf=item.perturbed_mtf,
            provenance=item.provenance,
        )
        for rank, item in enumerate(ranked[:top_n], start=1)
    )


def _parse_metrics(data: Mapping[str, str], prefix: str) -> CodeVOptimizationMetrics:
    return CodeVOptimizationMetrics(
        efl_y_mm=_required_float(data, f"{prefix}.efl_y_mm"),
        max_lateral_color_um=_required_float(data, f"{prefix}.max_lateral_color_um"),
        max_rms_spot_diameter_um=_required_float(data, f"{prefix}.max_rms_spot_diameter_um"),
        max_rms_wavefront_error_waves=_required_float(
            data,
            f"{prefix}.max_rms_wavefront_error_waves",
        ),
        max_distortion_pct=_required_float(data, f"{prefix}.max_distortion_pct"),
    )


def _metric_function_block() -> list[str]:
    return [
        "FCT @lcum(NUM ^dummy)",
        "LCL NUM ^dummy ^f ^wshort ^wlong ^x1 ^x2 ^y1 ^y2 ^value ^max",
        "^max == 0",
        "^wshort == 1",
        "^wlong == (NUM W)",
        "FOR ^f 1 (NUM F)",
        "  ^x1 == (X F^f Z1 R1 W^wshort SI)",
        "  ^y1 == (Y F^f Z1 R1 W^wshort SI)",
        "  ^x2 == (X F^f Z1 R1 W^wlong SI)",
        "  ^y2 == (Y F^f Z1 R1 W^wlong SI)",
        "  ^value == SQRTF((^x1-^x2)**2 + (^y1-^y2)**2)*1000",
        "  IF ^value > ^max",
        "    ^max == ^value",
        "  END IF",
        "END FOR",
        "END FCT ^max",
        "FCT @rmssum(NUM ^dummy)",
        "LCL NUM ^dummy ^f ^spot(10) ^err ^value ^max",
        "^max == 0",
        "FOR ^f 1 (NUM F)",
        "  ^err == SPOTDATA(1,^f,1,0.01,'CEN',0,0,^spot)",
        "  IF ^err = 0",
        "    ^value == ^spot(1)*1000",
        "    IF ^value > ^max",
        "      ^max == ^value",
        "    END IF",
        "  END IF",
        "END FOR",
        "END FCT ^max",
        "FCT @mtfmin(NUM ^freq, NUM ^nrd)",
        "LCL NUM ^freq ^nrd ^f ^xout(6) ^yout(6) ^xmtf ^ymtf ^value ^min",
        "^min == 1",
        "FOR ^f 1 (NUM F)",
        "  ^xmtf == MTF_1FLD(1,^f,^freq,0,^nrd,^xout,'DIF','SIN')",
        "  ^ymtf == MTF_1FLD(1,^f,^freq,90,^nrd,^yout,'DIF','SIN')",
        "  IF ^xmtf >= 0 and ^ymtf >= 0",
        "    ^value == (^xmtf+^ymtf)/2",
        "    IF ^value < ^min",
        "      ^min == ^value",
        "    END IF",
        "  END IF",
        "END FOR",
        "END FCT ^min",
        "FCT @wfewav(NUM ^dummy)",
        "LCL NUM ^dummy ^f ^ok ^rwe(10,26) ^value ^max",
        "^max == 0",
        "^ok == RMSWE(1,0,60,^rwe,'NOM')",
        "IF ^ok >= 0",
        "  FOR ^f 1 (NUM F)",
        "    ^value == ABSF(^rwe(1,^f))",
        "    IF ^value > ^max",
        "      ^max == ^value",
        "    END IF",
        "  END FOR",
        "END IF",
        "END FCT ^max",
        "FCT @dstpct(NUM ^dummy)",
        "LCL NUM ^dummy ^f ^dx ^dy ^value ^max",
        "^max == 0",
        "FOR ^f 1 (NUM F)",
        "  ^dx == (DIX Z1 F^f)",
        "  ^dy == (DIY Z1 F^f)",
        "  ^value == SQRTF(^dx*^dx + ^dy*^dy)*100",
        "  IF ^value > ^max",
        "    ^max == ^value",
        "  END IF",
        "END FOR",
        "END FCT ^max",
    ]


def _capture_metric_variables(prefix: str) -> list[str]:
    return [
        f"^{prefix}_efl_y_mm == ABSF((EFY))",
        f"^{prefix}_max_lateral_color_um == @lcum(1)",
        f"^{prefix}_max_rms_spot_diameter_um == @rmssum(1)",
        f"^{prefix}_max_rms_wavefront_error_waves == @wfewav(1)",
        f"^{prefix}_max_distortion_pct == @dstpct(1)",
    ]


def _append_metric_rows(lines: list[str], prefix: str) -> None:
    _append_put_row(lines, f'"{prefix}.efl_y_mm"', f"^{prefix}_efl_y_mm")
    _append_put_row(
        lines,
        f'"{prefix}.max_lateral_color_um"',
        f"^{prefix}_max_lateral_color_um",
    )
    _append_put_row(
        lines,
        f'"{prefix}.max_rms_spot_diameter_um"',
        f"^{prefix}_max_rms_spot_diameter_um",
    )
    _append_put_row(
        lines,
        f'"{prefix}.max_rms_wavefront_error_waves"',
        f"^{prefix}_max_rms_wavefront_error_waves",
    )
    _append_put_row(lines, f'"{prefix}.max_distortion_pct"', f"^{prefix}_max_distortion_pct")


def _append_tolerance_sensitivity_rows(
    lines: list[str],
    *,
    top_n: int,
    mtf_frequency_lpmm: float,
    radius_delta_fraction: float,
    thickness_delta_mm: float,
    nrd: int,
) -> None:
    _append_put_row(lines, '"tolerance.schema"', '"atelier-codev-tolerance-v1"')
    _append_put_row(
        lines,
        '"tolerance.metric"',
        '"CODE V perturbation replay MTF drop"',
    )
    _append_put_row(lines, '"tolerance.provenance"', '"codev-run"')
    _append_put_row(lines, '"tolerance.top_n"', str(top_n))
    _append_put_row(
        lines,
        '"tolerance.mtf_frequency_lpmm"',
        _fmt_number(mtf_frequency_lpmm),
    )
    lines.extend(
        [
            "^tolerance_count == 0",
            f"^tol_freq == {_fmt_number(mtf_frequency_lpmm)}",
            f"^tol_radius_fraction == {_fmt_number(radius_delta_fraction)}",
            f"^tol_thickness_delta == {_fmt_number(thickness_delta_mm)}",
            f"^tol_nrd == {nrd}",
            "^tol_nominal_mtf == @mtfmin(^tol_freq,^tol_nrd)",
            "^tol_stop == (STO)",
            "^tol_nsurf == (NUM S)",
            "FOR ^s 1 ^tol_nsurf",
            "  ^tol_surface_type == (TYP SUR S^s)",
            "  ^tol_candidate_surface == 1",
            "  IF ^s = ^tol_stop",
            "    ^tol_candidate_surface == 0",
            "  END IF",
            "  IF ^s = ^tol_nsurf",
            "    ^tol_candidate_surface == 0",
            "  END IF",
            '  IF ^tol_surface_type = "DUM"',
            "    ^tol_candidate_surface == 0",
            "  END IF",
            "  ^radius_nominal == (RDY S^s)",
            "  IF ^tol_candidate_surface = 1 and ABSF(^radius_nominal) > 1.0E-9 and ABSF(^radius_nominal) < 1.0E9",
            "    ^tol_delta == ABSF(^radius_nominal)*^tol_radius_fraction",
            "    IF ^tol_delta < 1.0E-6",
            "      ^tol_delta == 1.0E-6",
            "    END IF",
            "    ^perturbed_value == ^radius_nominal + ^tol_delta",
            "    RDY S^s ^perturbed_value",
            "    ^tol_perturbed_mtf == @mtfmin(^tol_freq,^tol_nrd)",
            "    RDY S^s ^radius_nominal",
            "    ^tol_drop == ^tol_nominal_mtf - ^tol_perturbed_mtf",
            "    IF ^tol_drop < 0",
            "      ^tol_drop == 0",
            "    END IF",
            '    ^parameter_name == "surface."',
            "    ^parameter_name == CONCAT(^parameter_name, NUM_TO_STR(^s))",
            '    ^parameter_name == CONCAT(^parameter_name, ".radius_y_mm")',
            "    ^perturbation == NUM_TO_STR(^tol_delta)",
            '    ^perturbation == CONCAT("+", ^perturbation)',
            '    ^perturbation == CONCAT(^perturbation, " mm")',
        ]
    )
    _append_dynamic_tolerance_candidate(lines)
    lines.extend(
        [
            "  END IF",
            "  ^thickness_nominal == (THI S^s)",
            "  IF ^tol_candidate_surface = 1 and ^thickness_nominal > 1.0E-9",
            "    ^tol_delta == ^tol_thickness_delta",
            "    ^perturbed_value == ^thickness_nominal + ^tol_delta",
            "    THI S^s ^perturbed_value",
            "    ^tol_perturbed_mtf == @mtfmin(^tol_freq,^tol_nrd)",
            "    THI S^s ^thickness_nominal",
            "    ^tol_drop == ^tol_nominal_mtf - ^tol_perturbed_mtf",
            "    IF ^tol_drop < 0",
            "      ^tol_drop == 0",
            "    END IF",
            '    ^parameter_name == "surface."',
            "    ^parameter_name == CONCAT(^parameter_name, NUM_TO_STR(^s))",
            '    ^parameter_name == CONCAT(^parameter_name, ".thickness_mm")',
            "    ^perturbation == NUM_TO_STR(^tol_delta)",
            '    ^perturbation == CONCAT("+", ^perturbation)',
            '    ^perturbation == CONCAT(^perturbation, " mm")',
        ]
    )
    _append_dynamic_tolerance_candidate(lines)
    lines.extend(
        [
            "  END IF",
            "END FOR",
        ]
    )
    _append_put_row(lines, '"tolerance.count"', "^tolerance_count")


def _append_dynamic_tolerance_candidate(lines: list[str]) -> None:
    lines.extend(
        [
            "    ^tolerance_count == ^tolerance_count+1",
            '    ^tolerance_prefix == "tolerance."',
            "    ^tolerance_prefix == CONCAT(^tolerance_prefix, NUM_TO_STR(^tolerance_count))",
            "    ^key == CONCAT(^tolerance_prefix, \".parameter_name\")",
            "    BUF PUT B1 I^row J1 ^key",
            "    BUF PUT B1 I^row J2 ^parameter_name",
            "    ^row == ^row+1",
            "    ^key == CONCAT(^tolerance_prefix, \".perturbation\")",
            "    BUF PUT B1 I^row J1 ^key",
            "    BUF PUT B1 I^row J2 ^perturbation",
            "    ^row == ^row+1",
            "    ^key == CONCAT(^tolerance_prefix, \".mtf_drop\")",
            "    BUF PUT B1 I^row J1 ^key",
            "    BUF PUT B1 I^row J2 ^tol_drop",
            "    ^row == ^row+1",
            "    ^key == CONCAT(^tolerance_prefix, \".nominal_mtf\")",
            "    BUF PUT B1 I^row J1 ^key",
            "    BUF PUT B1 I^row J2 ^tol_nominal_mtf",
            "    ^row == ^row+1",
            "    ^key == CONCAT(^tolerance_prefix, \".perturbed_mtf\")",
            "    BUF PUT B1 I^row J1 ^key",
            "    BUF PUT B1 I^row J2 ^tol_perturbed_mtf",
            "    ^row == ^row+1",
        ]
    )


def _optimized_readout_block(*, source_name: str) -> list[str]:
    lines = [
        "^row == 1",
        "^refw == (REF)",
        "^numsur == (NUM S)",
        "^numfld == (NUM F)",
        "^numwav == (NUM W)",
        "^numz == (NUM Z)",
        "^stop == (STO)",
        "^units == (DIM)",
        "^apetype == (TYP APE)",
        "^field_type == (TYP FLD)",
        "^maximh == 0",
        "^pi == 4*ATANF(1)",
        "^deg_to_rad == ^pi/180",
        "^efy == ABSF((EFY))",
        "FOR ^f 1 ^numfld",
        "  ^yh == (YRI F^f Z1)",
        '  IF ^field_type = "ANG"',
        "    ^field_angle_y == (YAN F^f Z1)",
        "    ^field_angle_y_rad == ^field_angle_y * ^deg_to_rad",
        "    ^yh == ^efy * TANF(^field_angle_y_rad)",
        '  ELS IF ^field_type = "IMG"',
        "    ^yh == (YIM F^f Z1)",
        "  END IF",
        "  IF ABSF(^yh) > ^maximh",
        "    ^maximh == ABSF(^yh)",
        "  END IF",
        "END FOR",
    ]
    _append_put_row(lines, '"schema"', f'"{CODEV_READOUT_RESULT_SCHEMA}"')
    _append_put_row(lines, '"status"', '"ok"')
    _append_put_row(lines, '"source_zmx"', f'"{source_name}"')
    _append_put_row(lines, '"units"', "^units")
    _append_put_row(lines, '"aperture_type"', "^apetype")
    _append_put_row(lines, '"f_number"', "ABSF((FNO))")
    _append_put_row(lines, '"entrance_pupil_diameter_mm"', "ABSF((EPD))")
    _append_put_row(lines, '"num_surfaces"', "^numsur")
    _append_put_row(lines, '"num_fields"', "^numfld")
    _append_put_row(lines, '"num_wavelengths"', "^numwav")
    _append_put_row(lines, '"num_zooms"', "^numz")
    _append_put_row(lines, '"stop_surface"', "^stop")
    _append_put_row(lines, '"field_type"', "^field_type")
    _append_put_row(lines, '"reference_wavelength_index"', "^refw")
    _append_put_row(lines, '"image_height_y_mm"', "^maximh")
    lines.extend(
        [
            "FOR ^s 1 ^numsur",
            '  ^surface_prefix == "surface."',
            "  ^surface_prefix == CONCAT(^surface_prefix, NUM_TO_STR(^s))",
            "  ^surf_type == (TYP SUR S^s)",
            "  ^glass == (GLA S^s)",
            "  ^nd == ABSF((IND S^s W^refw))",
            "  ^vd == 0",
            "  IF (NUM W) >= 3",
            "    ^n1 == ABSF((IND S^s W1))",
            "    ^nl == ABSF((IND S^s WL))",
            "    ^diffn == ^nl - ^n1",
            "    IF ABSF(^diffn) > 1.0E-12",
            "      ^vd == (^nd - 1) / ^diffn",
            "    END IF",
            "  END IF",
            "  ^isstop == 0",
            "  IF ^s = ^stop",
            "    ^isstop == 1",
            "  END IF",
            "  ^coefK == 0",
            "  ^coefA == 0",
            "  ^coefB == 0",
            "  ^coefC == 0",
            "  ^coefD == 0",
            "  ^coefE == 0",
            "  ^coefF == 0",
            "  ^coefG == 0",
            "  ^coefH == 0",
            "  ^coefJ == 0",
            '  IF ^surf_type = "ASP"',
            "    ^coefK == (K S^s)",
            "    ^coefA == (A S^s)",
            "    ^coefB == (B S^s)",
            "    ^coefC == (C S^s)",
            "    ^coefD == (D S^s)",
            "    ^coefE == (E S^s)",
            "    ^coefF == (F S^s)",
            "    ^coefG == (G S^s)",
            "    ^coefH == (H S^s)",
            "    ^coefJ == (J S^s)",
            '  ELS IF ^surf_type = "CON"',
            "    ^coefK == (K S^s)",
            "  END IF",
        ]
    )
    _append_dynamic_surface_row(lines, ".radius_y_mm", "(RDY S^s)")
    _append_dynamic_surface_row(lines, ".thickness_mm", "(THI S^s)")
    _append_dynamic_surface_positive_row(
        lines,
        ".semi_diameter_mm",
        "(MAP S^s)",
        variable_name="semi_diameter_mm",
    )
    _append_dynamic_surface_row(lines, ".glass", "^glass")
    _append_dynamic_surface_row(lines, ".nd", "^nd")
    _append_dynamic_surface_row(lines, ".vd", "^vd")
    _append_dynamic_surface_row(lines, ".surface_type", "^surf_type")
    _append_dynamic_surface_row(lines, ".is_stop", "^isstop")
    for label in _ASPHERE_COEFFICIENT_LABELS:
        _append_dynamic_surface_row(lines, f".asphere.{label}", f"^coef{label}")
    lines.append("END FOR")
    lines.extend(
        [
            "FOR ^w 1 ^numwav",
            '  ^wavelength_prefix == "wavelength."',
            "  ^wavelength_prefix == CONCAT(^wavelength_prefix, NUM_TO_STR(^w))",
        ]
    )
    _append_dynamic_wavelength_row(lines, ".wavelength_nm", "(WL W^w)")
    _append_dynamic_wavelength_row(lines, ".weight", "(WTW Z1 W^w)")
    lines.append("END FOR")
    lines.extend(
        [
            "FOR ^f 1 ^numfld",
            '  ^field_prefix == "field."',
            "  ^field_prefix == CONCAT(^field_prefix, NUM_TO_STR(^f))",
            "  ^field_x == 0",
            "  ^field_y == 0",
            '  IF ^field_type = "OBJ"',
            "    ^field_x == (XOB F^f Z1)",
            "    ^field_y == (YOB F^f Z1)",
            '  ELS IF ^field_type = "IMG"',
            "    ^field_x == (XIM F^f Z1)",
            "    ^field_y == (YIM F^f Z1)",
            '  ELS IF ^field_type = "ANG"',
            "    ^field_x == (XAN F^f Z1)",
            "    ^field_y == (YAN F^f Z1)",
            "  ELS",
            "    ^field_x == (XRI F^f Z1)",
            "    ^field_y == (YRI F^f Z1)",
            "  END IF",
        ]
    )
    _append_dynamic_field_row(lines, ".definition_type", "^field_type")
    _append_dynamic_field_row(lines, ".x", "^field_x")
    _append_dynamic_field_row(lines, ".y", "^field_y")
    _append_dynamic_field_row(lines, ".vuy", "(VUY F^f Z1)")
    _append_dynamic_field_row(lines, ".vly", "(VLY F^f Z1)")
    _append_dynamic_field_row(lines, ".vux", "(VUX F^f Z1)")
    _append_dynamic_field_row(lines, ".vlx", "(VLX F^f Z1)")
    lines.append("END FOR")
    return lines


def _append_put_row(lines: list[str], key: str, value: str) -> None:
    lines.append(f"BUF PUT B1 I^row J1 {key}")
    lines.append(f"BUF PUT B1 I^row J2 {value}")
    lines.append("^row == ^row+1")


def _append_dynamic_surface_row(lines: list[str], suffix: str, value: str) -> None:
    lines.append(f'  ^key == CONCAT(^surface_prefix, "{suffix}")')
    lines.append("  BUF PUT B1 I^row J1 ^key")
    lines.append(f"  BUF PUT B1 I^row J2 {value}")
    lines.append("  ^row == ^row+1")


def _append_dynamic_surface_positive_row(
    lines: list[str],
    suffix: str,
    value: str,
    *,
    variable_name: str,
    floor: float = 1.0e-6,
) -> None:
    lines.append(f"  ^{variable_name} == ABSF({value})")
    lines.append(f"  IF ^{variable_name} < {_fmt_number(floor)}")
    lines.append(f"    ^{variable_name} == {_fmt_number(floor)}")
    lines.append("  END IF")
    _append_dynamic_surface_row(lines, suffix, f"^{variable_name}")


def _append_dynamic_field_row(lines: list[str], suffix: str, value: str) -> None:
    lines.append(f'  ^key == CONCAT(^field_prefix, "{suffix}")')
    lines.append("  BUF PUT B1 I^row J1 ^key")
    lines.append(f"  BUF PUT B1 I^row J2 {value}")
    lines.append("  ^row == ^row+1")


def _append_dynamic_wavelength_row(lines: list[str], suffix: str, value: str) -> None:
    lines.append(f'  ^key == CONCAT(^wavelength_prefix, "{suffix}")')
    lines.append("  BUF PUT B1 I^row J1 ^key")
    lines.append(f"  BUF PUT B1 I^row J2 {value}")
    lines.append("  ^row == ^row+1")


def _required_text(data: Mapping[str, str], key: str) -> str:
    value = data.get(key, "").strip()
    if not value:
        _raise_missing_key(key)
    return value


def _required_float(data: Mapping[str, str], key: str) -> float:
    value = data.get(key, "").strip()
    if not value:
        _raise_missing_key(key)
    try:
        numeric = float(value)
    except ValueError as exc:
        raise CodeVBatchError(
            "failure",
            "CODE V optimize data contains a non-numeric value",
            details={"key": key, "value": value},
        ) from exc
    if not math.isfinite(numeric):
        raise CodeVBatchError(
            "failure",
            "CODE V optimize data contains a non-finite value",
            details={"key": key, "value": value},
        )
    return numeric


def _optional_float(data: Mapping[str, str], key: str) -> float | None:
    value = data.get(key, "").strip()
    if not value:
        return None
    try:
        numeric = float(value)
    except ValueError as exc:
        raise CodeVBatchError(
            "failure",
            "CODE V optimize data contains a non-numeric value",
            details={"key": key, "value": value},
        ) from exc
    if not math.isfinite(numeric):
        raise CodeVBatchError(
            "failure",
            "CODE V optimize data contains a non-finite value",
            details={"key": key, "value": value},
        )
    return numeric


def _optional_positive_int(data: Mapping[str, str], key: str) -> int | None:
    value = data.get(key, "").strip()
    if not value:
        return None
    try:
        numeric = int(float(value))
    except ValueError as exc:
        raise CodeVBatchError(
            "failure",
            "CODE V optimize data contains a non-integer value",
            details={"key": key, "value": value},
        ) from exc
    if numeric < 1:
        raise CodeVBatchError(
            "failure",
            "CODE V optimize data contains a non-positive integer value",
            details={"key": key, "value": value},
        )
    return numeric


def _raise_missing_key(key: str) -> None:
    raise CodeVBatchError(
        "failure",
        "CODE V optimize data is missing a required field",
        details={"missing_key": key},
    )


def _validate_positive_int(value: int, name: str) -> None:
    if value < 1:
        raise ValueError(f"{name} must be positive: {value!r}")


def _validate_positive(value: float, name: str) -> None:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{name} must be positive and finite: {value!r}")


def _validate_nonnegative(value: float, name: str) -> None:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"{name} must be non-negative and finite: {value!r}")


def _fmt_number(value: float) -> str:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"CODE V numeric value must be finite: {value!r}")
    if abs(numeric) < 1e-15:
        numeric = 0.0
    return f"{numeric:.15g}"


def _quote_codev_path(path: Path) -> str:
    value = str(path)
    if any(char in value for char in ('"', "\r", "\n")):
        raise ValueError(f"CODE V path cannot contain quotes or newlines: {value!r}")
    return f'"{value}"'
