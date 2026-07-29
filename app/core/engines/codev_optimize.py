"""CODE V AUT optimization batch adapter for imported ZMX seeds."""

from __future__ import annotations

import math
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.core.engines.codev_batch import (
    DEFAULT_CODEV_EXECUTABLE,
    CodeVBatchError,
    CodeVBatchResult,
    ensure_buf_exp_safe_filename,
    ensure_codev_safe_input_path,
    parse_codev_result_file,
    run_codev_batch,
)
from app.core.engines.codev_readout import (
    ASPHERE_EXPORT_SCALE,
    CODEV_READOUT_RESULT_SCHEMA,
    CodeVReadout,
    _append_odd_asphere_block,
    parse_codev_readout_file,
)
from app.core.engines.codev_roundtrip import DEFAULT_PATENT_ROUNDTRIP_SEED
from app.core.engines.zmx_import_prep import stage_zmx_for_codev
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
    # Every ``None`` below means "not measurable for this run" (see
    # _parse_metrics). None is NEVER interchangeable with a numeric value:
    # 0.0 lateral color means "measured, and achromatic", 0.0 RMS spot would
    # mean "measured as a perfect point", and both are what the CODE V macros
    # emit when nothing traced at all.
    max_lateral_color_um: float | None
    max_rms_spot_diameter_um: float | None
    max_rms_wavefront_error_waves: float | None
    max_distortion_pct: float | None
    # Wavelength count CODE V actually had. ``None`` for legacy result files
    # written before the macro emitted it -- unknown, not "verified fine".
    wavelength_count: int | None = None
    # True when no field produced a traceable ray, so every ray-derived metric
    # above is the macro's initial value rather than a measurement.
    ray_trace_degenerate: bool = False

    def describe(self) -> dict[str, float | bool | None]:
        return {
            "efl_y_mm": self.efl_y_mm,
            "max_lateral_color_um": self.max_lateral_color_um,
            "max_rms_spot_diameter_um": self.max_rms_spot_diameter_um,
            "max_rms_wavefront_error_waves": self.max_rms_wavefront_error_waves,
            "max_distortion_pct": self.max_distortion_pct,
            "wavelength_count": self.wavelength_count,
            "ray_trace_degenerate": self.ray_trace_degenerate,
        }


@dataclass(frozen=True)
class CodeVToleranceSensitivity:
    """One CODE V perturbation replay row emitted by the sensitivity block.

    ``mtf_drop`` is ``None`` when the macro's own subtraction
    (``^tol_drop == ^tol_nominal_mtf - ^tol_perturbed_mtf``) was fed a degenerate
    endpoint, because the difference of an unmeasured value is not a measurement.
    See ``_parse_tolerance_sensitivity`` for why that matters more here than for
    the endpoints themselves.
    """

    rank: int
    parameter_name: str
    perturbation: str
    mtf_drop: float | None
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
    ensure_codev_safe_input_path(source_zmx, role="source_zmx")
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
    idle_timeout_seconds: float | None = None,
    optimized_zmx_filename: str = _OPTIMIZED_ZMX_NAME,
    platform_name: str = os.name,
    **sequence_options: object,
) -> CodeVOptimizeResult:
    """Run CODE V AUT optimization and ingest the rebuilt optimized ZMX."""

    source_zmx = default_optimize_seed() if source_zmx is None else Path(source_zmx)
    # Absolute before ANY path is derived from it: run_codev_batch hands
    # ``work_dir`` to CODE V as the process cwd, so every relative path embedded
    # in the macro (the ZMX import, and both ``BUF EXP`` targets) would be
    # resolved against it a second time and land in ``work_dir/work_dir/...``.
    # run_codev_target and codev_tolerance already resolve for this reason.
    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    # Import through a wavelength-normalized copy; ``source_zmx`` stays the
    # original so provenance and derived filenames are unaffected.
    import_zmx = stage_zmx_for_codev(source_zmx, work_dir)
    sequence_path = work_dir / _OPTIMIZE_SEQUENCE_NAME
    result_path = work_dir / _OPTIMIZE_RESULT_NAME
    optimized_readout_path = work_dir / _OPTIMIZED_READOUT_NAME
    optimized_zmx_path = work_dir / optimized_zmx_filename
    for stale in (optimized_readout_path, optimized_zmx_path):
        if stale.exists():
            stale.unlink()

    write_codev_optimize_sequence(
        sequence_path=sequence_path,
        source_zmx=import_zmx,
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
        idle_timeout_seconds=idle_timeout_seconds,
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
EFL_TARGET_TOLERANCE_PCT = 2.0
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
    _append_put_row(lines, f'"{prefix}.epd_mm"', f"^{prefix}_epd")
    _append_put_row(lines, f'"{prefix}.maximh_mm"', f"^{prefix}_maximh")


def _extra_dof_block(extra_dof: str) -> list[str]:
    """加优化变量（DOF 实验 · 主公授权解锁接缝2/非球面）：
    extra_dof ∈ none|asphere|glass|both。非球面系数 AC..GC(4-16阶) / 玻璃 GLC，
    per-surface 循环设变量（CODE V 语法：`<X>C S^s 0` 非球面、`GLC S^s 0` 玻璃）。

    非球面系数上限对齐数据锚 ZMX 格式（真机实锤 2026-07-09）：数据锚
    zmx_writer 的 EVENASPH 只保留 PARM 1 + PARM 2..8 对应 CODE V A..G
    （4-16 阶），H(18阶)/J(20阶) 无格式位可写。原先 DOF 放到 A..J 全部 9 项，
    真机跑 US20170003482A1 asphere/both 后 H/J 系数被 AUT 拉成非零
    （~1e-6 量级），触发 zmx_writer 的
    `_reject_nonzero_unsupported_evenasphere_terms` fail-open——候选设计
    ZMX 重建直接拿不到文件。收紧到 A..G 让优化产物天然落在锚格式可表达域
    内；H/J 对应的 18/20 阶项对手机镜头这类小视场系统像差贡献本就极小，
    收紧不改变可达的优化空间上限。"""
    if extra_dof not in ("none", "asphere", "glass", "both"):
        raise ValueError(f"extra_dof must be none|asphere|glass|both: {extra_dof!r}")
    if extra_dof == "none":
        return []
    lines = ["FOR ^s 1 (NUM S)"]
    if extra_dof in ("asphere", "both"):
        lines.append('  IF (TYP SUR S^s) = "ASP"')
        lines += [f"    {c}C S^s 0" for c in ("A", "B", "C", "D", "E", "F", "G")]
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


# ---------------------------------------------------------------------------
# 玻璃可变域修复（GLC 负杠杆 → 正杠杆，真机证实，见 .planning/debug/
# codev-target-convergence.md「下一杠杆」章节 + scratch_diag/probe_glc_fix.py）：
# `GLC S^s 0` 只声明"该面玻璃可变"，CODE V AUT 默认套的可变域是内置 Schott
# 矿物玻璃四角 NFK5/NSK16/NLAF2/SF4——手机镜头是塑料镜片，AUT 把玻璃拉出该
# 矿物域外的不可实现区，误差函数爆炸（US20170003482A1 both 模式 RMS 343µm 灾
# 难案例）。修复：在 AUT 块内注入自定义塑料域 GLA 边界，把玻璃变量约束在
# 可注塑折射率/色散范围内。
#
# ★ 凸性陷阱（真机踩坑）★：CODE V 的 GLA 角点凸性检查不在 (nd, vd) 笛卡尔平
# 面做，而在玻璃图标准平面 (nd, nF-nC) 做，其中 nF-nC = (nd-1)/vd 是非线性变
# 换。一个在 (nd, vd) 里凸的四边形，变换后完全可能不凸（某点落入其余三点凸
# 包内部），导致 CODE V 报 "ERROR - Corner points must form a convex
# polygon."。所以角点必须先做 (nd, nF-nC) 变换、在该平面算凸包、按凸序排列，
# Python 侧排好凸序即语法在 CODE V 侧永不炸。
# ---------------------------------------------------------------------------

# 常见光学塑料 (nd, vd) 锚点 + 专利 seed 初值锚点 + 两个探边余量角点（低折射高
# 阿贝 / 高折射低阿贝），凸包顶点数经验证恰为 5（PMMA 类角点 tuple 顺序无关，
# _glass_map_hull 会重新按凸序排列）。任何改动都必须重跑
# `_glass_map_hull(DEFAULT_GLASS_BOUNDS_ND_VD)` 确认顶点数仍在 3-5 且仍覆盖
# 全部材料点（test_codev_optimize.py 有回归测试）。
DEFAULT_GLASS_BOUNDS_ND_VD: tuple[tuple[float, float], ...] = (
    (1.4918, 57.4),  # PMMA
    (1.531, 56.0),  # COC
    (1.5445, 55.9),  # APEL
    (1.5905, 30.9),  # PS
    (1.5855, 29.9),  # PC
    (1.607, 27.0),  # OKP4
    (1.632, 23.0),  # OKP4HT
    (1.651, 21.5),  # EP（高折射光学塑料）
    (1.5170, 64.2),  # 专利 seed（US20170003482A1 等）玻璃初值锚点，必须落在域内
    (1.42, 68.0),  # 探边余量：低折射/高阿贝角（比现有塑料更宽松）
    (1.69, 18.0),  # 探边余量：高折射/低阿贝角（比现有塑料更宽松）
)


def _glass_map_hull(bounds_nd_vd: Sequence[tuple[float, float]]) -> list[str]:
    """把 (nd,vd) 点集变换到 CODE V GLA 实际做凸性检查的 (nd, nF-nC) 玻璃图
    平面（nF-nC=(nd-1)/vd），算 2D 凸包（自实现 cross-product 单调链，不引入
    scipy——保持本模块轻依赖），返回按凸序排列的 GLA 冒号格式角点字符串
    （`f"{nd:.4f}:{vd:.2f}"`，用原始 (nd,vd) 而非变换后坐标，因凸包顶点本就
    是输入点子集，逐点变换可逆）。

    CODE V GLA 接受 3-5 个角点；凸包顶点数不在该范围视为不可用配置直接报错
    （宁可 Python 侧提前炸，也不要把非法角点数丢给 CODE V 猜）。<3 点或点集
    在该平面内共线（凸包退化为一条线段）同样 ValueError。"""

    points: list[tuple[float, float, float]] = []  # (x=nd, y=nF-nC, vd_orig)
    seen: set[tuple[float, float]] = set()
    for nd, vd in bounds_nd_vd:
        nd = float(nd)
        vd = float(vd)
        if not math.isfinite(nd) or nd <= 1.0:
            raise ValueError(f"glass bound nd must be finite and > 1.0: {nd!r}")
        if not math.isfinite(vd) or vd <= 0:
            raise ValueError(f"glass bound vd must be finite and positive: {vd!r}")
        key = (nd, vd)
        if key in seen:
            continue
        seen.add(key)
        points.append((nd, (nd - 1.0) / vd, vd))
    if len(points) < 3:
        raise ValueError(
            f"glass bounds need at least 3 distinct (nd,vd) points, got {len(points)}"
        )

    # 2D 叉积只读 (x=nd, y=nF-nC) 两维；点为 3-tuple（末位 vd 仅供输出），
    # 用 Sequence[float] 直收整点，省去每次调用的 [:2] 切片。
    def _cross(o: Sequence[float], a: Sequence[float], b: Sequence[float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    points.sort(key=lambda p: (p[0], p[1]))
    lower: list[tuple[float, float, float]] = []
    for p in points:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float, float]] = []
    for p in reversed(points):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]

    if len(hull) < 3:
        raise ValueError(
            "glass bounds are collinear in the (nd, nF-nC) glass-map plane; "
            "no convex polygon can be formed"
        )
    if len(hull) > 5:
        raise ValueError(
            f"glass bounds convex hull has {len(hull)} vertices; "
            "CODE V GLA accepts at most 5 corner points"
        )
    return [f"{nd:.4f}:{vd:.2f}" for nd, _y, vd in hull]


# Import-time sanity check: 默认边界必须直接可用（凸包顶点数 3-5），改动
# DEFAULT_GLASS_BOUNDS_ND_VD 时若破坏这个断言，模块加载即炸，而不是等到某次
# CODE V 批跑才发现。
assert 3 <= len(_glass_map_hull(DEFAULT_GLASS_BOUNDS_ND_VD)) <= 5, (
    "DEFAULT_GLASS_BOUNDS_ND_VD convex hull must have 3-5 vertices for CODE V GLA"
)


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


#: Constrain distortion to the seed's own measured value rather than a fixed
#: percentage. Non-circular by construction: the seed is where optimisation
#: *starts*, not what the candidate is judged against, so nothing about the
#: control leaks into how the candidate is built (NORTH-STAR 6 lists that leak
#: as an open circularity problem, and this avoids it).
#:
#: MEASURED, and it is not the better default. Real machine, six trials'
#: converging rungs (2026-07-30), seed-baseline vs a fixed `< 3`:
#:
#:   bound respected     2/4  vs  3/4
#:   EFL still converged 2/4  vs  2/4
#:   best-case RMS spot  445  vs  70 um   (US-20240201471-A1-e4)
#:
#: CODE V's AUT constraints are not hard guarantees: when a constraint is
#: infeasible against the others it is simply left active and violated rather
#: than raising. A tighter bound therefore conflicts with the EFL constraint
#: more often, and both end up unsatisfied -- US-12210142-B2-e1 overshot its
#: 1.119% seed value by 2x, US-20250370227-A1-e12 by 4x.
#:
#: Neither bound unlocks P2. The optimiser spends whatever allowance it is
#: given (`< 3` lands on exactly 3.00, `< 10` on exactly 10.00), so a fixed 3%
#: parks candidates at 3% while the controls measure 0.28-1.98% and the
#: distortion criterion is lost anyway. Hence: both modes ship, neither is a
#: default, and the bound stays a per-run parameter until evidence shows a
#: value that actually wins.
SEED_BASELINE_DISTORTION = -1.0


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
    glass_bounds_nd_vd: Sequence[tuple[float, float]] | None = None,
    max_cycles: int = 25,
    min_cycles: int = 3,
    lateral_color_weight: float = 0.01,
    rms_spot_weight: float = 0.001,
    distortion_weight: float | None = None,
    distortion_constraint_pct: float | None = None,
    min_center_thickness_mm: float = 0.025,
    min_edge_thickness_mm: float = 0.025,
    max_center_thickness_mm: float = 10.0,
    min_air_gap_mm: float = 0.001,
    emit_optimized_zmx: bool = False,
    optimized_readout_path: Path | str | None = None,
) -> str:
    """Build target-mode sequence: import seed, capture 3 snapshots, pull EFL to
    客户 target (seam 1), lock F# via FNO mode (seam 3a, E1 实测锁), keep merit
    (lat color + RMS spot). Stage A=EFL only; B=+F#; C(IMH 场重建)另做。

    vignetting: 可选 per-field 渐晕裁剪 fraction（0≤v<1，clip 掉的入瞳半径比例）。
    ZMX->CV 导入丢弃 ray-aiming/渐晕 → 宽+快种子离轴边缘光线 TIR 毒化优化光栅；
    渐晕裁掉这些光线让 AUT 光栅可追迹（**不改 F#**，F# 由光阑定）。由
    run_codev_target_autovig 自动搜最小收敛渐晕。诊断见 .planning/debug/codev-target-convergence.md。

    glass_bounds_nd_vd: extra_dof∈{glass,both} 时，AUT 块内 GLA 塑料可变域边界
    的 (nd,vd) 点集（None 用 DEFAULT_GLASS_BOUNDS_ND_VD）。真机证实 CODE V AUT
    对 `GLC S^s 0` 声明的玻璃变量默认套内置 Schott 矿物玻璃四角
    （NFK5/NSK16/NLAF2/SF4），不适配塑料手机镜头，会把玻璃拉到不可实现区致
    误差函数爆炸（US20170003482A1 both 模式 RMS 343µm 灾难案例）；注入塑料域
    GLA 边界后同 seed RMS 收敛到 12.99µm（追平纯非球面 13.0µm）。extra_dof∈
    {none,asphere} 时不注入（没有玻璃变量，GLA 无意义）。角点凸性检查见
    _glass_map_hull 文档字符串（(nd, nF-nC) 平面陷阱）。

    emit_optimized_zmx: 加法式接缝（③ 优化落地"资深可 Verify"闭环，见
    run_codev_target 文档字符串）——为 True 时宏尾在主结果 BUF EXP 之后追加
    baseline `run_codev_optimize` 同款 `_optimized_readout_block`（本文件内
    定义，DB 读数直出：非球面 K/A..J 系数、玻璃 nd/vd、渐晕等如实带出，无论
    extra_dof 动了什么），导出到 optimized_readout_path 的第二个 BUF EXP。
    False（默认）时宏尾与改动前逐字节一致——零回归。optimized_readout_path
    在 emit_optimized_zmx=True 时必填（否则 ValueError）。"""

    _validate_positive(target_efl_mm, "target_efl_mm")
    if target_f_number is not None:
        _validate_positive(target_f_number, "target_f_number")
    if target_imh_mm is not None:
        _validate_positive(target_imh_mm, "target_imh_mm")
    _validate_vignetting(vignetting)
    _validate_positive_int(max_cycles, "max_cycles")
    _validate_positive_int(min_cycles, "min_cycles")
    if distortion_weight is not None:
        # A zero or negative weight would silently neuter the operand rather
        # than disable it -- if you mean off, pass None.
        _validate_positive(distortion_weight, "distortion_weight")
    if distortion_constraint_pct is not None and distortion_constraint_pct != SEED_BASELINE_DISTORTION:
        _validate_positive(distortion_constraint_pct, "distortion_constraint_pct")
    if distortion_weight is not None and distortion_constraint_pct is not None:
        # Both forms declare the same operand name. The manual warns that giving
        # more than one form does not cancel the others -- the tolerance is
        # entered twice, "which may not be physically correct".
        raise ValueError(
            "distortion_weight and distortion_constraint_pct are alternative forms "
            "of the same operand; pass at most one"
        )
    if emit_optimized_zmx and optimized_readout_path is None:
        raise ValueError("optimized_readout_path is required when emit_optimized_zmx=True")

    source_zmx = Path(source_zmx)
    ensure_codev_safe_input_path(source_zmx, role="source_zmx")
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
    aut_lines = [
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
    ]
    if distortion_constraint_pct is not None:
        # A *constraint*, not a weight. The CODE V Optimization manual states the
        # two are different mechanisms for the same user-defined quantity:
        #
        #     Constrained with:                @xxx >  =  < constraint_tar
        #     Included in the error function:  @xxx = constraint_tar / WTC wt
        #
        # The weight form below was tried first and refuted on the real machine
        # (PR #110). That refutation does **not** carry over to this form.
        #
        # Real-machine A/B, six trials' converging rungs (2026-07-29), unconstrained
        # vs `< 3`:
        #   * bound held in 17/18 arms
        #   * US-20240201471-A1-e4: EFL deviation 0.91% -> 0.00%, distortion
        #     24.06% -> 3.00%, RMS spot 318 -> 70um  (better on every axis)
        #   * US-12210142-B2-e1:    deviation 0.00% -> 0.00%, distortion 24.30% -> 3.00%
        #   * two other converged seeds LOST EFL convergence (1.35% -> 34.5%,
        #     0.00% -> 19.1%), so this is seed-dependent, not free
        #
        # Note the optimiser spends the full allowance: `< 3` lands on exactly
        # 3.00 and `< 10` on exactly 10.00, so the bound *is* the output.
        #
        # Default stays None: it changes what AUT converges to.
        bound = (
            f"{_fmt_number(distortion_constraint_pct)}"
            if distortion_constraint_pct != SEED_BASELINE_DISTORTION
            else "^seed_baseline_max_distortion_pct"
        )
        aut_lines += [
            "  @atelier_distortion == @dstpct(1)",
            f"  @atelier_distortion < {bound}",
        ]
    elif distortion_weight is not None:
        # Distortion is one of the three metrics P2 judges (NORTH-STAR §1.1) and
        # was the only one with no operand here, so the optimiser has been free
        # to trade it away. Measured cost, 2026-07-29 pilot (12 judged trials):
        # distortion is a losing metric in 8, and in **3 it is the only loss** --
        # US-12124006-B2-e3 (1.7x the control), US-12571987-B2-e1 (5.3x), and
        # US-20240176104-A1-e2 (14.5x, while beating its control 3.2x on RMS and
        # 2.2x on MTF). Matching distortion on those three alone would move par
        # from 2/12 to 5/12.
        #
        # Default stays None: this changes what AUT converges to, so it is opt-in
        # until a real-machine A/B shows what it costs the other two metrics.
        aut_lines += [
            "  @atelier_distortion == @dstpct(1)",
            "  @atelier_distortion = 0",
            f"  WTC {_fmt_number(distortion_weight)}",
        ]
    aut_lines += [
        f"  MNT {_fmt_number(min_center_thickness_mm)}",
        f"  MNE {_fmt_number(min_edge_thickness_mm)}",
        f"  MXT {_fmt_number(max_center_thickness_mm)}",
        f"  MNA {_fmt_number(min_air_gap_mm)}",
        f"  MXC {max_cycles}",
        f"  MNC {min_cycles}",
        "  IMP 0.001",
    ]
    if extra_dof in ("glass", "both"):
        # GLC 玻璃变量修复（真机证实）：塑料域 GLA 边界替换 CODE V 默认矿物
        # 玻璃四角，见模块顶部「玻璃可变域修复」章节。
        bounds = DEFAULT_GLASS_BOUNDS_ND_VD if glass_bounds_nd_vd is None else glass_bounds_nd_vd
        aut_lines.append(f"  GLA {' '.join(_glass_map_hull(bounds))}")
    aut_lines.append("GO")
    lines += aut_lines
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
        f"IF ^efl_target_dev_pct < {EFL_TARGET_TOLERANCE_PCT:.1f}",
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
    ]
    if emit_optimized_zmx:
        # 加法式：读数块/第二 BUF EXP 只在 emit_optimized_zmx=True 时出现，
        # 默认路径（False）宏尾与改动前逐字节一致。
        lines += [
            *_optimized_readout_block(source_name=source_zmx.name),
            f"BUF EXP B1 {_quote_codev_path(Path(optimized_readout_path))}",  # type: ignore[arg-type]
            "BUF DEL B1",
        ]
    lines += [
        "OUT YES",
        "EXI YES",
        "",
    ]
    return "\n".join(lines)


_TARGET_REQUIRED_KEYS = (
    "schema", "status", "mode", "stage", "target.efl_mm",
    "seed_baseline.efl_y_mm", "seed_baseline.fno", "seed_baseline.maximh_mm",
    "config_pre_aut.efl_y_mm", "config_pre_aut.fno", "config_pre_aut.maximh_mm",
    "post_aut.efl_y_mm", "post_aut.fno", "post_aut.epd_mm", "post_aut.maximh_mm",
    "post_aut.max_rms_spot_diameter_um", "post_aut.max_rms_wavefront_error_waves",
    "post_aut.max_distortion_pct",
    "efl_target_deviation_pct", "aut_converged",
)


# ---------------------------------------------------------------------------
# AUT 误差函数轨迹诊断（诚实性修复 · 灾难案例实锤）：CODE V AUT 的 IMP 终止判
# 据只看相邻两 cycle 的改善速率，不看绝对量级——真机灾难案例
# （scratch_diag/dof_work/atelier_codev_target_A.19.lis）cycle0 ERR. F. =
# 128.15953160，一路爆炸到末 cycle ERR. F. = 0.154263E+06（×1204），末行仍报
# "Normal AUTO Completion - System improvement less than IMP"；现有
# aut_converged（EFL-hit 代理）完全抓不到这类假阳性。本节把 .lis 里逐 cycle
# 的 ERR. F./ABERR F./CONST F. 与终止行原文如实解析出来，供 scorecard/资深
# 看——只出数字，绝不下"假阳性/良品"判定（[EXPERT] 红线，见 AGENTS.md 北极星
# 条款）。纯读文本、fail-open：解析失败不能反过来炸掉 run_codev_target 的主
# 流程（TSV 数值契约才是主线，.lis 只是诊断性 side-channel）。
# ---------------------------------------------------------------------------

_AUT_CYCLE_BLOCK_RE = re.compile(
    r"ABERR\s+F\.\s*=\s*(?P<aberr>[-+0-9.EeDd]+)\s*\r?\n"
    r"\s*CONST\s+F\.\s*=\s*(?P<const>[-+0-9.EeDd]+)\s*\r?\n"
    r"\s*ERR\.\s*F\.\s*=\s*(?P<err>[-+0-9.EeDd]+)"
)

# (原文短语, 归一化关键词) —— 短语原文照抄 CODE V 输出（含大小写/标点），来自
# scratch_diag/ 下真实 .lis 样本穷举（多颗 seed、多种 extra_dof 配置）。找不
# 到匹配的终止措辞 → termination=None（未知/新措辞不硬猜）。
_AUT_TERMINATION_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("Normal AUTO Completion - System improvement less than IMP", "normal_completion"),
    ("Normal AUTO Completion - Unstable Condition", "unstable_condition"),
    ("Normal AUTO Completion - Maximum cycle limit reached", "max_cycle_limit"),
    ("Abnormal AUTO Completion - Irrecoverable Condition", "irrecoverable_condition"),
    (
        "Abnormal AUTO Completion - Unable to scale up Pupil and Field specifications",
        "unable_to_scale_pupil_field",
    ),
    # P15 Stage 2 真机回填（2026-07-11 采证矩阵 corpus，42 格）：aperture/pupil
    # 缩放失败家族的两个新措辞——"Scaled down SPC data" 13 次 / "Scaled down
    # nominal system cannot be traced" 6 次（.planning/loop/p15-stageb-evidence/
    # summary.md §6）。此前未登记时 fail-open 返回 termination=None（无害但不可
    # 观测）。
    ("Abnormal AUTO Completion - Scaled down SPC data", "scaled_down_spc_data"),
    (
        "Abnormal AUTO Completion - Scaled down nominal system cannot be traced",
        "scaled_down_nominal_cannot_be_traced",
    ),
)
_AUT_TERMINATION_RE = re.compile(
    "|".join(re.escape(phrase) for phrase, _keyword in _AUT_TERMINATION_KEYWORDS)
)
_AUT_TERMINATION_LOOKUP: dict[str, str] = dict(_AUT_TERMINATION_KEYWORDS)

_AUT_ERROR_TRACE_EMPTY: dict[str, float | str | None] = {
    "err_f_first": None,
    "err_f_last": None,
    "aberr_f_last": None,
    "const_f_last": None,
    "err_f_ratio": None,
    "termination": None,
}


def _parse_aut_float(token: str) -> float | None:
    """CODE V 一般用 E 记号；容错接受 Fortran D 记号。转换失败 → None（单个
    token 解析失败不该炸掉整条诊断轨迹）。"""
    try:
        return float(token.replace("D", "E").replace("d", "e"))
    except ValueError:
        return None


def parse_aut_error_trace(listing_text: str) -> dict[str, float | str | None]:
    """从 CODE V AUT ``.lis`` 清单文本解析逐 cycle 误差函数轨迹（纯诊断字段，
    不做良品/假阳性判定——判断权在资深设计师，见 AGENTS.md 北极星 [EXPERT] 红
    线）。

    Returns a dict with:
      - err_f_first: cycle 0 的 ``ERR. F.``
      - err_f_last: 最后一个 cycle 的 ``ERR. F.``
      - aberr_f_last / const_f_last: 最后一个 cycle 的 ``ABERR F.`` / ``CONST F.``
      - err_f_ratio: ``err_f_last / err_f_first``（``err_f_first`` 为 0 或缺失
        → None）
      - termination: 终止行关键词（见 ``_AUT_TERMINATION_KEYWORDS``），文本里
        一个都没识别到 → None

    找不到任何 ``ABERR F./CONST F./ERR. F.`` 三行组 → 全字段 None（fail-open：
    诊断性质，找不到不代表调用方数据有误，不抛异常）。
    """

    blocks = list(_AUT_CYCLE_BLOCK_RE.finditer(listing_text))
    if not blocks:
        return dict(_AUT_ERROR_TRACE_EMPTY)

    first_block, last_block = blocks[0], blocks[-1]
    err_f_first = _parse_aut_float(first_block.group("err"))
    err_f_last = _parse_aut_float(last_block.group("err"))
    aberr_f_last = _parse_aut_float(last_block.group("aberr"))
    const_f_last = _parse_aut_float(last_block.group("const"))

    err_f_ratio: float | None = None
    if err_f_first is not None and err_f_last is not None and err_f_first != 0:
        err_f_ratio = err_f_last / err_f_first

    term_matches = _AUT_TERMINATION_RE.findall(listing_text)
    termination = _AUT_TERMINATION_LOOKUP.get(term_matches[-1]) if term_matches else None

    return {
        "err_f_first": err_f_first,
        "err_f_last": err_f_last,
        "aberr_f_last": aberr_f_last,
        "const_f_last": const_f_last,
        "err_f_ratio": err_f_ratio,
        "termination": termination,
    }


def _safe_aut_error_trace(listing_path: Path | None) -> dict[str, float | str | None] | None:
    """读 + 解析 ``.lis`` 的 fail-open 包装：读不到文件/解析抛任何异常 → None
    （诊断字段绝不影响 ``run_codev_target`` 的主 TSV 契约）。"""
    if listing_path is None:
        return None
    try:
        listing_text = listing_path.read_text(encoding="utf-8", errors="replace")
        return parse_aut_error_trace(listing_text)
    except Exception:  # noqa: BLE001 - 诊断 side-channel，任何异常都不外泄给主流程
        return None


def _safe_ray_grid_classification(listing_path: Path | None) -> dict[str, object] | None:
    """光栅健康度分类（对抗审查 BLOCKER-1 修复 2026-07-11）：对同一 ``.lis``
    清单跑 ``fno_probe.classify_fno_listing``（TIR / chief-ray-missing /
    aperture-conflict / ok / other，ok 需正面证据 fail-closed），返回
    ``describe()`` dict。P15 Stage 2 采证矩阵（42 格真机）证明
    ``aut_converged=1 + post_aut.fno==target`` 是双重假阳性达标信号——F# 系
    统参数达值与光线可追迹性是两个完全分离的维度，光栅健康度必须独立可观
    测（.planning/loop/p15-stageb-evidence/summary.md §0）。

    与 ``_safe_aut_error_trace`` 同款 fail-open：读不到/解析抛异常 → None，
    绝不影响主 TSV 契约。延迟导入 ``fno_probe``：该模块顶层 import 本模块
    （``build_codev_target_sequence``/``run_codev_target``），模块级互导会
    循环。"""
    if listing_path is None:
        return None
    try:
        from app.core.engines.fno_probe import classify_fno_listing

        listing_text = listing_path.read_text(encoding="utf-8", errors="replace")
        return classify_fno_listing(listing_text).describe()
    except Exception:  # noqa: BLE001 - 诊断 side-channel，任何异常都不外泄给主流程
        return None


# ---------------------------------------------------------------------------
# 优化后 ZMX 重建（③ target 模式接上"资深可 Verify"闭环）：把 baseline
# run_codev_optimize 已有的 readout→zmx_writer 重建管线加法式移植到 target
# 模式。target 模式没有单一"before/after"——它有 seed_baseline/config_pre_aut/
# post_aut 三快照 + autovig 多 rung 重跑，因此文件名需要跨 rung 消歧（同一
# work_dir/stage 在一次 ladder climb 内会被 run_codev_target 反复调用，只有
# vignetting 逐级改变）：见 run_codev_target_autovig 文档字符串。
# ---------------------------------------------------------------------------


def _fmt_edge_filename_token(edge: float) -> str:
    """渐晕 edge 的**不含小数点**文件名消歧后缀，如 edge=0.2 -> ``"_vig0200"``。

    真机实锤（2026-07-09 隔离探针，见 .planning/debug 与本次修复的诊断记
    录）：CODE V ``BUF EXP`` 对形如 ``"..._vig0.20_optimized_readout.tsv"``
    这类"文件名中段小数点后还跟着更多非数字字符、再到扩展名"的路径会报
    ``ERROR - Unable to open file.`` 并中止整条宏（``WARNING - Sequence
    aborted``）——真实产线案例 US20170045714A1 @ target 3.797mm、edge=0.2 收
    敛命中：readout 导出整段失败，下游 ``parse_codev_readout_file`` 找不到
    文件，fail-open 吞掉异常，最终该 rung 的 optimized ZMX **完全没有落
    盘**（不是"被覆写"，是从未被导出）。隔离对照实验（同一 seed，仅改文件
    名）证实：``"...v0.20.tsv"``（小数点后到扩展名之间只剩纯数字）不报错，
    ``"...vig0.20_readout.tsv"``（小数点后还有字母/下划线）必报错；纯数字
    的 ``"...vig020_readout.tsv"`` 同样不报错。这与 ``codev_batch.
    run_codev_batch`` 文档字符串里已有的".seq 文件名 stem 不要以 .<数字> 结
    尾"警告是同一个 CODE V 文件名解析怪癖的更普遍情形（不止 .seq stem，任何
    经 BUF EXP 打开的路径都会中招）。因此渐晕 edge 一律编码成不含小数点、定
    宽 4 位的千分位整数（0.1% 分辨率，如 0.2 -> ``0200``、0.204 -> ``0204``），
    从根上规避这个怪癖，而不是逐个文件名踩坑。0.1% 分辨率之下仍碰撞的输入
    （如 0.2 与 0.2004）由 ``run_codev_target_autovig`` 的已用 token 集合兜底
    （重复即 ValueError，绝不静默覆写前一 rung 的产物）。"""
    edge = float(edge)
    if not math.isfinite(edge) or edge < 0:
        raise ValueError(f"edge must be finite and non-negative: {edge!r}")
    return f"_vig{round(edge * 1000):04d}"


def _vignetting_filename_token(vignetting: object) -> str:
    """从 ``vignetting`` 派生消歧后缀（见 ``_fmt_edge_filename_token`` 的 CODE
    V BUF EXP 怪癖说明）。``None``/空列表 -> ``""``（保持零回归：未经
    autovig、不带渐晕的普通 ``run_codev_target`` 调用文件名不变）。autovig 的
    每个 rung（含 edge=0）改走 ``run_codev_target`` 的 ``rung_filename_tag``
    参数显式指定，不再依赖本函数对 ``vignetting=None`` 的处理——那条路径本
    身的光学行为（是否发 VUY/VLY/VUX/VLX 命令）不因文件名消歧而改变。"""
    if not vignetting:
        return ""
    try:
        edge = max(float(v) for v in vignetting)  # type: ignore[union-attr]
    except (TypeError, ValueError):
        return ""
    return _fmt_edge_filename_token(edge)


def _target_optimized_readout_filename(stage: str, vignetting_token: str) -> str:
    return f"atelier_codev_target_{stage}{vignetting_token}_optimized_readout.tsv"


def _fmt_efl_filename_token(target_efl_mm: float) -> str:
    """目标 EFL 的**不含小数点**文件名消歧后缀，如 5.680244mm -> ``"_target005680"``。

    与 ``_fmt_edge_filename_token`` 同一个 CODE V 文件名怪癖，但这里踩的是
    **重新导入**而不是 BUF EXP 导出。原实现用 ``f"{efl:.6g}"`` 拼出
    ``"..._target5.68024_vig0600_optimized.zmx"``，正是 ``_BUF_EXP_HAZARD_RE``
    描述的危险形状（小数点后跟数字、同一点分段内还有非数字内容）。

    此前刻意不守卫，理由是"该文件由 zmx_writer Python 侧落盘、不经 CODE V
    打开"——**该前提已不成立**。北极星四件套要求候选处方 ZMX 可被第三方导入
    CODE V/Zemax 独立复核（P4），P2 异源打平率也必须重新导入候选才能量它。

    真机单变量 A/B（2026-07-28，同一份字节、同一文件名长度、只把 stem 里的
    ``.`` 换成 ``x``）：``..._target5.68024_vig0600_optimized.zmx`` 报
    ``ERROR - Zemax File ...`` 后导入一个空系统（EFL 1e+35 / NUM W=1 /
    NUM F=1 / 全零度量）；``..._target5x68024_vig0600_optimized.zmx`` 正常导入
    （NUM W=3 / NUM F=2 / EFL 4.507）。即**此前每一颗交付出去的候选 ZMX，
    文件名本身就挡住了独立复核**。

    编码沿用渐晕 token 的约定：微米分辨率的定宽整数（0.001mm，手机镜头 EFL
    量级 1-30mm，六位可覆盖到 999.999mm）。
    """
    efl = float(target_efl_mm)
    if not math.isfinite(efl) or efl <= 0:
        raise ValueError(f"target_efl_mm must be finite and positive: {target_efl_mm!r}")
    return f"_target{round(efl * 1000):06d}"


def _target_optimized_zmx_filename(
    source_zmx: Path, target_efl_mm: float, vignetting_token: str
) -> str:
    efl_token = _fmt_efl_filename_token(target_efl_mm)
    return f"{source_zmx.stem}{efl_token}{vignetting_token}_optimized.zmx"


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
    idle_timeout_seconds: float | None = None,
    platform_name: str = os.name,
    emit_optimized_zmx: bool = False,
    rung_filename_tag: str | None = None,
    **sequence_options: object,
) -> dict[str, object]:
    """Run one target-mode AUT and return the parsed three-snapshot data dict.

    ``"aut_error_trace"`` is an additive diagnostic key (see
    ``parse_aut_error_trace``): the raw AUT cycle-by-cycle ERR. F. progression
    read from the run's ``.lis`` listing, exposed alongside the TSV-derived
    fields. It never affects the TSV-based contract above it — a missing or
    unparseable listing just yields ``None``.

    ``"ray_grid"`` is a second additive diagnostic key (see
    ``_safe_ray_grid_classification``, BLOCKER-1 修复): the same listing's
    ray-grid health classification (``fno_probe.classify_fno_listing``
    describe() dict — TIR / chief-ray-missing / aperture-conflict / ok /
    other). Same fail-open semantics: missing listing yields ``None``.

    ``rung_filename_tag`` (加法式，默认 ``None``)：显式指定本次调用产出的
    ``.seq``/``.tsv``/readout/optimized ZMX 的消歧后缀，覆盖从
    ``sequence_options["vignetting"]`` 派生的默认值（见
    ``_vignetting_filename_token``）。``run_codev_target_autovig`` 用它给
    **每个** rung（含 edge=0）都传一个显式、不含小数点的 tag（见
    ``_fmt_edge_filename_token``），使同一 ``(work_dir, stage)`` 下的多次
    ladder-climb 调用互不覆写、rung 归属可确认——这只影响文件名，不改变
    ``vignetting`` kwarg 本身传给 ``build_codev_target_sequence`` 的光学行为
    （edge=0 的 rung 仍是 ``vignetting=None``，不发 VUY/VLY/VUX/VLX 命令，
    数值零回归）。未传（``None``）时保持原有行为：不带渐晕的普通调用文件名
    不变，带渐晕的调用退回 ``_vignetting_filename_token`` 派生的后缀。

    ``emit_optimized_zmx`` (加法式接缝，默认 False=零回归)：为 True 时追加
    baseline 同款 readout 块（本文件 ``_optimized_readout_block``，DB 读数
    直出——非球面 K/A..J 系数、玻璃 nd/vd 如实带出，无论 extra_dof 动了什么
    自由度）、解析、经 ``zmx_writer.write_zmx_from_codev_readout`` 重建 ZMX 落
    盘 ``work_dir``，再用 ``zmx_ingest.load_normalized_zmx`` 回读验证 EFL 有
    限。任一环节失败（最典型：extra_dof 打开非球面 DOF 后 AUT 把 H/J 系数拉
    成非零——``zmx_writer`` 的 EVENASPH 只支持 CODE V A-G 对应 Zemax
    PARM 2-8，见其 ``_reject_nonzero_unsupported_evenasphere_terms``，H/J 需要
    r^18/r^20 不受支持；或 CODE V BUF EXP 因文件名含小数点拒开文件，见
    ``_fmt_edge_filename_token``）都 fail-open：只把 ``"zmx_rebuild_error"``
    字符串塞进返回 dict，绝不炸这里的主 TSV 契约。成功时返回 dict 含
    ``"optimized_zmx_path"``（绝对路径字符串）与
    ``"optimized_zmx_ingested_efl_mm"``；未启用/失败时前者为 ``None``。
    """

    source_zmx = Path(source_zmx)
    work_dir = Path(work_dir).resolve()  # 绝对路径：CODE V BUF EXP 相对路径会二次拼接失败
    work_dir.mkdir(parents=True, exist_ok=True)
    # 导入走波长归一化副本；``source_zmx`` 保持原件，产物命名与溯源不受影响。
    import_zmx = stage_zmx_for_codev(source_zmx, work_dir)
    filename_token = (
        rung_filename_tag
        if rung_filename_tag is not None
        else _vignetting_filename_token(sequence_options.get("vignetting"))
    )
    seq = work_dir / f"atelier_codev_target_{stage}{filename_token}.seq"
    res = work_dir / f"atelier_codev_target_{stage}{filename_token}.tsv"
    optimized_readout_path: Path | None = None
    optimized_zmx_out: Path | None = None
    if emit_optimized_zmx:
        optimized_readout_path = work_dir / _target_optimized_readout_filename(
            stage, filename_token
        )
        # 机制守卫：readout 是宏尾第二个 BUF EXP 打开的路径，但不经
        # run_codev_batch（那里只守卫 seq/主 TSV）——危险文件名（如带小数点的
        # stage/rung tag 拼出 "..._vig0.20_optimized_readout.tsv"）必须在这里
        # 提前 ValueError，否则 CODE V 真机上静默中止宏尾、readout 永不落盘
        # （fail-open 只留 zmx_rebuild_error，病灶极难归因）。
        ensure_buf_exp_safe_filename(
            optimized_readout_path, role="optimized_readout_path"
        )
        optimized_zmx_out = work_dir / _target_optimized_zmx_filename(
            source_zmx, target_efl_mm, filename_token
        )
        # 候选 ZMX 同样守卫。它由 zmx_writer Python 侧落盘不假，但它是**交付
        # 物**：北极星四件套要求第三方能把它导进 CODE V/Zemax 独立复核，P2 异
        # 源打平率也要重新导入它才能量。真机 A/B 已证实带小数点的名字会让
        # ZEMAXOS_TO_CV 报错并导入一个空系统（见 _fmt_efl_filename_token）。
        ensure_buf_exp_safe_filename(optimized_zmx_out, role="optimized_zmx_path")
        # 批跑前清理同名陈旧产物（对齐 baseline run_codev_optimize 的清理模式）：
        # 本轮宏尾 readout 导出若失败（如 BUF EXP 拒开文件中止宏），fail-open 的
        # 重建管线绝不能认领上一轮遗留的 readout/ZMX 伪装"成功"——宁可如实报
        # zmx_rebuild_error。
        for stale in (optimized_readout_path, optimized_zmx_out):
            if stale.exists():
                stale.unlink()
    seq.write_text(
        build_codev_target_sequence(
            source_zmx=import_zmx, result_path=res, target_efl_mm=target_efl_mm,
            target_f_number=target_f_number, target_imh_mm=target_imh_mm, stage=stage,
            emit_optimized_zmx=emit_optimized_zmx,
            optimized_readout_path=optimized_readout_path,
            **sequence_options,
        ),
        encoding="ascii",
    )
    batch = run_codev_batch(
        sequence_path=seq, result_path=res, executable=executable, work_dir=work_dir,
        timeout_seconds=timeout_seconds, idle_timeout_seconds=idle_timeout_seconds,
        platform_name=platform_name,
        expected_schema=TARGET_RESULT_SCHEMA, required_keys=_TARGET_REQUIRED_KEYS,
        allow_nonzero_ok_result=True,
    )
    data: dict[str, object] = dict(batch.data)
    # Fail-fast 预检（数据病灶防线，真机实锤 2026-07-10）：seed_baseline 是导入
    # 后、任何配置/AUT 之前的 CODE V 直读快照。EFL 非有限或 |EFL| >= 1e30
    # （CODE V 垃圾哨兵——全空气系统实测 EFY=1e35）说明种子进 CODE V 时玻璃根本
    # 没解析（GLAS 名不在目录且非 model glass，ZEMAXOS_TO_CV 静默置为空气）。
    # 立即抛可归因错误，而不是让 AUT 在零光焦度系统上跑完整条 autovig ladder、
    # 最后以 "zmx_rebuild_error: non-finite EFL: -inf" 伪装成重建问题（根因诊断
    # 见 tests/test_zmx_glass_resolvability.py 与 scripts/repair_legacy_zmx_glass.py）。
    baseline_efl_text = str(data.get("seed_baseline.efl_y_mm", ""))
    try:
        baseline_efl_mm = float(baseline_efl_text)
    except ValueError:
        # required-keys 闸已保证该键存在——解析失败即非数垃圾，正是预检要抓的
        # 腐坏形态之一，绝不吞掉（fail-fast，与哨兵路径同款可归因错误）。
        raise CodeVBatchError(
            "failure",
            "seed baseline EFL readout is non-numeric garbage: "
            f"{baseline_efl_text!r}; the CODE V import/readout is corrupt for "
            "this seed (see scripts/repair_legacy_zmx_glass.py for the known "
            "unresolved-glass defect family)",
            details={
                "source_zmx": str(source_zmx),
                "seed_baseline_efl_y_mm": baseline_efl_text,
                "preflight": "corrupt-baseline-efl",
            },
        ) from None
    if not math.isfinite(baseline_efl_mm) or abs(baseline_efl_mm) >= 1e30:
        raise CodeVBatchError(
            "failure",
            "seed imported into CODE V with unresolved glass (all-air system): "
            f"baseline EFL {baseline_efl_text!r}; check the source ZMX GLAS lines "
            "carry explicit model-glass nd/vd or CODE-V-resolvable catalog names "
            "(see scripts/repair_legacy_zmx_glass.py)",
            details={
                "source_zmx": str(source_zmx),
                "seed_baseline_efl_y_mm": baseline_efl_text,
                "sentinel_threshold": 1e30,
                "preflight": "unresolved-glass",
            },
        )
    data["aut_error_trace"] = _safe_aut_error_trace(batch.listing_path)
    # 加法式诊断键（BLOCKER-1）：同一 .lis 的光栅健康度分类，供 FNO ladder /
    # scorecard 把「参数达值」与「光线可追迹」两维分开上报。fail-open，缺清单
    # → None。
    data["ray_grid"] = _safe_ray_grid_classification(batch.listing_path)
    data["optimized_zmx_path"] = None
    returncode_ok = batch.returncode in _OPTIMIZE_OK_RETURNCODES
    if not returncode_ok:
        # 如实上报（诚实不变量）：主 TSV 三快照数字是真实读到的，仍然返回；
        # 但越界 returncode 意味着宏尾完整性存疑，把真实 returncode 附带上报。
        data["batch_returncode"] = batch.returncode
    if emit_optimized_zmx:
        assert optimized_readout_path is not None and optimized_zmx_out is not None
        if not returncode_ok:
            # ZMX 重建侧拒绝（fail-open，不炸主 TSV 契约）：越界 returncode 下
            # 宏尾第二个 BUF EXP（readout 导出）是否完整执行不可信，拒绝据其
            # 重建 optimized ZMX。
            data["zmx_rebuild_error"] = (
                f"batch returncode {batch.returncode} outside allowed "
                f"{sorted(_OPTIMIZE_OK_RETURNCODES)}; macro-tail integrity uncertain, "
                "refusing to rebuild optimized ZMX from the readout"
            )
            return data
        try:
            optimized_readout = parse_codev_readout_file(optimized_readout_path)
            optimized_zmx_path = write_zmx_from_codev_readout(
                optimized_readout,
                optimized_zmx_out,
                name=f"{source_zmx.stem}-target-{stage}-optimized",
            )
            optic = load_normalized_zmx(optimized_zmx_path)
            ingested_efl_mm = float(optic.paraxial.f2())
            if not math.isfinite(ingested_efl_mm):
                raise ValueError(
                    "optimized ZMX was rebuilt but zmx_ingest returned a "
                    f"non-finite EFL: {ingested_efl_mm!r}"
                )
            data["optimized_zmx_path"] = str(optimized_zmx_path)
            data["optimized_zmx_ingested_efl_mm"] = ingested_efl_mm
        except Exception as exc:  # noqa: BLE001 - rebuild is additive/fail-open, must never break the TSV contract
            data["zmx_rebuild_error"] = f"{type(exc).__name__}: {exc}"
    return data


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
    idle_timeout_seconds: float | None = None,
    platform_name: str = os.name,
    emit_optimized_zmx: bool = False,
    **sequence_options: object,
) -> dict[str, object]:
    """Climb `vig_ladder` from 0, return the FIRST target run whose AUT converges
    (EFL dev<2%) — i.e. the minimal off-axis 渐晕 needed — preserving F#. Annotates
    the returned dict with autovig.edge_used / autovig.converged / autovig.trace so
    资深 sees how much aperture was clipped to converge. If none converge, returns the
    min-deviation trial.

    Resilient to per-rung timeout/failure: a rung that errors (e.g. rung-0 v=0 flooding
    TIR → hard timeout) is recorded and the search keeps climbing (higher 渐晕 clips the
    TIR → the rung runs fast). num_fields is learned from the rung-0 run, or injected
    (needed to keep climbing when rung-0 itself times out). Only re-raises (tooling-
    blocked) when EVERY rung fails to produce parseable data.

    ``emit_optimized_zmx`` (加法式，默认 False)：透传给 **每个** rung 的
    ``run_codev_target`` 调用，而非只在最终采纳的 rung 上启用——取舍原因：
    readout/ZMX 重建只是同一次 CODE V 批跑宏尾多几行 ``BUF PUT``/``BUF EXP``，
    不是额外的进程发起（真正昂贵的是 `/B` 子进程启动+ZMX 导入+AUT，readout
    在同一进程内几乎零成本）；若只想给"最终采纳"那个 rung 重建，需要在判定
    收敛后对同一配置重新跑一次 CODE V（多一次进程调用，真实变慢），得不偿
    失。每个 rung（**含 edge=0**）都经 ``rung_filename_tag=_fmt_edge_filename_
    token(edge)`` 拿到显式、不含小数点的专属文件名（``.seq``/``.tsv``/
    readout/ZMX 全部消歧，见 ``_fmt_edge_filename_token`` 的 CODE V BUF EXP
    "Unable to open file" 怪癖说明），同一 ``(work_dir, stage)`` 内多个 rung
    之间不再互相覆写；返回 dict 里的 ``optimized_zmx_path`` 只对应最终被
    ``_annotate``/``_blocked_or_best`` 采纳的那次 rung 自己的文件。"""

    trace: list[str] = []
    best: dict[str, object] | None = None
    best_dev = float("inf")
    best_edge = 0.0
    first_error: CodeVBatchError | None = None
    last_error: CodeVBatchError | None = None
    used_rung_tokens: set[str] = set()

    def _trial(edge: float, vig: list[float] | None) -> tuple[dict[str, object] | None, bool]:
        nonlocal best, best_dev, best_edge, first_error, last_error
        rung_token = _fmt_edge_filename_token(edge)
        if rung_token in used_rung_tokens:
            # 0.1% token 分辨率之下仍碰撞的 ladder 输入：静默覆写会让 rung 产物
            # 归属混叠（真机踩坑同源病灶），直接拒绝。
            raise ValueError(
                f"vig_ladder produces duplicate filename token {rung_token!r} at "
                f"edge={edge!r}; rungs would silently overwrite each other's files"
            )
        used_rung_tokens.add(rung_token)
        try:
            data = run_codev_target(
                source_zmx=source_zmx, work_dir=work_dir, target_efl_mm=target_efl_mm,
                target_f_number=target_f_number, target_imh_mm=target_imh_mm, stage=stage,
                executable=executable, timeout_seconds=timeout_seconds,
                idle_timeout_seconds=idle_timeout_seconds,
                platform_name=platform_name, vignetting=vig,
                rung_filename_tag=rung_token,
                emit_optimized_zmx=emit_optimized_zmx, **sequence_options,
            )
        except CodeVBatchError as exc:
            if exc.details.get("preflight"):
                # 种子级预检缺陷（如导入即全空气/基线读数腐坏）：换渐晕 rung
                # 不可能改变导入结果，爬完整条 ladder 只是把同一错误重打 N 次
                # CODE V——直接上抛，保留可归因 details。
                raise
            if first_error is None:
                first_error = exc
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
            best_dev, best, best_edge = dev, data, edge
        return data, conv

    def _annotate(data: dict[str, object], edge: float, converged: bool) -> dict[str, object]:
        return {**data, "autovig.edge_used": _fmt_number(edge),
                "autovig.converged": "1" if converged else "0",
                "autovig.trace": " ".join(trace)}

    def _blocked_or_best(edge: float) -> dict[str, object]:
        if best is None:
            if last_error is not None:
                # 全无可用数据 → tooling-blocked（保持既有语义：仍抛 last_error
                # 本体/类型，调用方按 kind 分流不受影响）；details 加法式附上
                # 逐 rung trace（edge→kind/dev 摘要）与首个 rung 错误的 kind，
                # 异常路径不再丢失整条 ladder 的过程线索。
                last_error.details["autovig_trace"] = list(trace)
                last_error.details["first_error_kind"] = (
                    first_error.kind if first_error is not None else None
                )
                raise last_error  # 全无可用数据 → tooling-blocked（保持既有语义）
            # 所有 rung 都返回了数据但 dev 全 NaN（never < best_dev）：无可归属的
            # best，退回末次尝试的 edge。
            return _annotate({}, edge, False)
        # 归属一致性：非收敛兜底路径上报 best 数据自己的 edge（best_edge），而
        # 不是 ladder 爬到的"最后一个尝试过的" edge——否则 autovig.edge_used 会
        # 和实际返回的 optimized_zmx_path/三快照数字对不上（best 可能来自更早、
        # 偏差更小的某个 rung，ladder 之后仍继续爬到了更高、更差的 edge 才耗尽）。
        return _annotate(dict(best), best_edge, False)

    # Rung 0 (always first): no 渐晕 — native-convergence check + learns field count.
    data, conv = _trial(0.0, None)
    if conv and data is not None:
        return _annotate(data, 0.0, True)
    nf = num_fields
    if nf is None and data is not None:
        try:
            nf = int(float(data.get("num_fields", "0") or "0"))
        except (TypeError, ValueError):
            # 畸形 num_fields（与上方 dev 解析同风格容错）：回退 None——不注入
            # 场数，无法构造离轴渐晕 profile 时走下方兜底返回，不炸整条 ladder。
            nf = None
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


# ===========================================================================
# 标准打包入口（C1 Mode3 接入锚 · spec §10 六接缝之 1/2/3a）：asphere/both 双
# 配置全跑（串行）+ 数值排序取 preferred，双份数据全保留。加法式：全新函数，
# 不动上面任何既有函数（零回归）。
# ===========================================================================

STANDARD_RESULT_SCHEMA = "atelier-codev-target-standard-v1"
_STANDARD_EXTRA_DOF_CONFIGS: tuple[str, ...] = ("asphere", "both")


def _standard_config_converged(result: Mapping[str, object]) -> int:
    """Fail-closed：aut_converged 缺失/非法值一律当 0（不给"已收敛"背书）。"""
    raw = result.get("aut_converged")
    if raw is None:
        return 0
    try:
        return 1 if int(float(str(raw))) == 1 else 0
    except (TypeError, ValueError):
        return 0


def _standard_config_rms(result: Mapping[str, object]) -> float:
    """Fail-closed：post_aut RMS 点列缺失/非数/非有限/非正一律当 +inf（排到
    最后，不当"更优"——缺数据不能反而赢）。

    非正（``<= 0.0``）同样 fail-closed，不只是缺失/非数/非有限：CODE V 宏
    ``@rmssum``（见本文件 ``_metric_function_block`` 的 ``FCT @rmssum``
    定义）以 ``^max == 0`` 起始，只在 ``SPOTDATA`` 返回 ``^err = 0``（追迹
    成功）的场次才更新 ``^max``；若某配置全部场次 ``SPOTDATA`` 都返回
    ``^err != 0``（追迹失败），``^max`` 原样保留初值 0 并被当作
    ``post_aut.max_rms_spot_diameter_um=0.0`` 写出——这是"追迹全失败"的
    哨兵值，不是"零误差"的真优值。物理上 RMS 点列径精确为 0（或负）不存
    在（衍射极限设下界 >0），必须当缺失处理，否则追迹失败的配置会顶着假
    的完美 RMS 赢过真正收敛的配置。"""
    raw = result.get("post_aut.max_rms_spot_diameter_um")
    if raw is None:
        return float("inf")
    try:
        value = float(str(raw))
    except (TypeError, ValueError):
        return float("inf")
    if not math.isfinite(value) or value <= 0.0:
        return float("inf")
    return value


def _standard_config_rank(result: Mapping[str, object]) -> tuple[int, int, float]:
    """越小越优：(是否报错, 是否未收敛, RMS)。报错的配置永远排最后；同为
    未报错时按 aut_converged 分层，同层再比 RMS。"""
    if "error" in result:
        return (1, 1, float("inf"))
    return (0, 0 if _standard_config_converged(result) else 1, _standard_config_rms(result))


def _rms_display(rms: float) -> str:
    """reason 文案用：`_standard_config_rms` fail-closed 出的 `+inf` 哨兵
    不能原样格式成 `infµm`——那会让读者误以为 CODE V 真的测出了无穷大
    RMS，而实情是"RMS 不可用（缺失/非数/非有限/非正），fail-closed 落后"。
    如实转述二者之一。"""
    return "不可用（缺失/非法/非正，fail-closed 落后）" if math.isinf(rms) else f"{rms:.4g}µm"


def _error_summary(result: Mapping[str, object]) -> str:
    """reason 文案用：从配置结果里的 error dict 如实摘要 kind + detail 片段。
    绝不把数据缺陷（如 unresolved-glass 预检）硬贴 tooling 标签。"""
    error = result.get("error")
    if not isinstance(error, Mapping):
        return "kind=unknown"
    kind = error.get("kind", "unknown")
    detail = str(error.get("detail", "") or "")
    if len(detail) > 100:
        detail = detail[:97] + "..."
    return f"kind={kind}: {detail}" if detail else f"kind={kind}"


def _config_is_preflight(result: Mapping[str, object]) -> bool:
    error = result.get("error")
    return isinstance(error, Mapping) and bool(error.get("preflight"))


def _select_preferred(
    configs: Mapping[str, Mapping[str, object]],
) -> tuple[str | None, str]:
    """两配置按 `_standard_config_rank` 排序取 preferred；两配置都报错时
    返回 (None, 原因)。判定规则见 `run_codev_target_standard` docstring。

    rank 元组每配置只计算一次，排序与 reason 措辞都从同一元组派生——排序
    走一套计算、reason 再独立重算一套的双路结构，一旦两路对 fail-closed 边界
    的处理有丝毫不一致，reason 就会与实际排序矛盾（说谎的 provenance），
    故此处刻意收敛为单一数据源。"""

    ranks = {
        name: _standard_config_rank(configs[name]) for name in _STANDARD_EXTRA_DOF_CONFIGS
    }
    ranked = sorted(_STANDARD_EXTRA_DOF_CONFIGS, key=ranks.__getitem__)
    best, second = ranked[0], ranked[1]
    best_errored, best_not_conv, best_rms = ranks[best]
    second_errored, second_not_conv, second_rms = ranks[second]
    if best_errored:
        # 如实归因（W4）：从各配置真实 error dict 摘要 kind + detail，只在
        # 没有种子级预检缺陷标记时才称 tooling-blocked——数据缺陷（如
        # unresolved-glass）不是工具链问题，误贴标签会把修数据的工单派去修工具。
        summaries = "; ".join(
            f'"{name}" {_error_summary(configs[name])}'
            for name in _STANDARD_EXTRA_DOF_CONFIGS
        )
        label = (
            "seed 级预检缺陷"
            if any(_config_is_preflight(configs[name]) for name in _STANDARD_EXTRA_DOF_CONFIGS)
            else "tooling-blocked"
        )
        return None, f"两配置均报 CodeVBatchError（{label}；{summaries}），无可用结果"
    if second_errored:
        return best, (
            f'"{second}" 配置报 CodeVBatchError（{_error_summary(configs[second])}），'
            f'"{best}" 为唯一可用结果'
        )
    best_conv = 1 - best_not_conv
    second_conv = 1 - second_not_conv
    if best_conv != second_conv:
        return best, (
            f'"{best}" aut_converged={best_conv} 优于 "{second}" aut_converged={second_conv}'
        )
    if best_rms != second_rms:
        return best, (
            f'"{best}" post_aut.max_rms_spot_diameter_um={_rms_display(best_rms)} 优于 '
            f'"{second}" 的 {_rms_display(second_rms)}'
        )
    return best, (
        f"aut_converged 与 post_aut RMS spot 均打平（converged={best_conv}, "
        f'rms={_rms_display(best_rms)}），按固定优先序取 "{best}"'
    )


def run_codev_target_standard(
    *,
    source_zmx: Path | str,
    work_dir: Path | str,
    target_efl_mm: float,
    target_f_number: float | None = None,
    target_imh_mm: float | None = None,
    executable: Path | str | os.PathLike[str] = DEFAULT_CODEV_EXECUTABLE,
    timeout_seconds: float = 180.0,
    idle_timeout_seconds: float | None = None,
    num_fields: int | None = None,
    vig_ladder: tuple[float, ...] = _DEFAULT_VIG_LADDER,
    glass_bounds_nd_vd: Sequence[tuple[float, float]] | None = None,
    emit_optimized_zmx: bool = False,
) -> dict[str, object]:
    """C1 Mode3（TargetConvergedGenerator）③ 优化标准打包入口。

    spec 锚：docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration
    -design.md §10「Mode3 接口锚（③ 六接缝）」。Mode3 优化维 =
    {EFL, F#, IMH, FOV}（spec §10 顶部按语；TTL 不在优化维，见 spec §5.2
    `CONVERGED_FIELDS`）。本函数落地六接缝中的：

      - 接缝1 EFL 解锁朝 target：`build_codev_target_sequence` 内
        `EFL = {target_efl_mm}`（真机 E1 验证）。
      - 接缝2 玻璃可变：`extra_dof="both"` 走塑料域 GLA 边界（见模块「玻璃
        可变域修复」章节；凸性陷阱已修，commit 7b504c6）。
      - 接缝3a F# 锁：FNO 模式（真机 E1 实测锁）。

    未落地：IMH/FOV（Stage C 场重建；`target_imh_mm` 目前仅透传进三快照
    读数，AUT merit 未加 IMH/FOV 操作数）。接缝4-6（applied_to_payload 真
    置 True / verification checklist 自动 apply / payload delivery 落地）
    不属本函数，分别在 `local_optimizer.py` / `case_library.py` 侧。

    真机结论（主公 2026-07-09 attended 验证）：`extra_dof` ∈ {asphere,both}
    互有胜负（both 在 5 颗 seed 中 3 胜 2 负），无法静态判定哪个配置更优。
    因此标准配置 = 双配置全跑（串行；asphere=纯非球面 DOF；both=非球面+塑料域
    玻璃 DOF），按数值指标排序取 preferred，**双份数据全部保留**——不丢弃
    "输"的那份，资深设计师可能仍要看两份对比。

    preferred 判定规则（纯数值排序，非良品判定，写死不可绕过）：
      1. 任一配置抛 `CodeVBatchError`（tooling-blocked）排最后；两配置都
         抛错 → `preferred=None`。
      2. 比较 `aut_converged`（EFL 达成 target 偏差<2%，"1">"0"）；缺失/
         非法值 fail-closed 当 0（不给"已收敛"背书）。
      3. `aut_converged` 打平则比 `post_aut.max_rms_spot_diameter_um`，小
         者优；缺失/NaN/非有限 fail-closed 当 +inf（排到最后，不当
         "更优"）。
      4. 仍打平（如两者 RMS 都缺失）→ 固定优先序取 "asphere"（更简单、无
         玻璃可变风险的配置）。

    返回值不是"良品/合格"判定——量产可用性判断权与 [EXPERT] 背书始终在资
    深设计师手里（AGENTS.md 北极星条款），本函数只做数值排序。

    emit_optimized_zmx（加法式，默认 False=零回归）：为 True 时两配置
    （asphere/both，各自独立 work_dir/extra_dof 子目录，互不覆写）各自透传
    进 `run_codev_target_autovig`，各自把优化后 ZMX 重建落盘——preferred 与
    "输"的一份都各自拿到自己的 `optimized_zmx_path`，资深两份都能 Verify。
    重建失败 fail-open（见 run_codev_target 文档字符串），只在该配置的
    `configs[...]["zmx_rebuild_error"]` 留痕，不影响 preferred 排序。

    Returns:
        {"schema": STANDARD_RESULT_SCHEMA,
         "configs": {"asphere": {...}, "both": {...}},  # 各为
             run_codev_target_autovig 的原始返回 dict（emit_optimized_zmx=True
             时含 optimized_zmx_path / 可能的 zmx_rebuild_error），或
             {"error": {"kind": ..., "detail": ...}}（该配置报错时）
         "preferred": "asphere" | "both" | None,
         "preferred_reason": str,
         "provenance": {"vignetting_search": "autovig",
                        "glass_model": {"asphere": "glass-frozen",  # 从不设玻璃变量
                                        "both": "fictitious-within-plastic-GLA(default)"
                                                | "fictitious-within-custom-GLA"},
                        "gla_hull": [...],  # 仅自定义 bounds 时出现：实际注入
                                            # AUT GLA 的凸包角点字符串列表
                        "quality_note": "..."}}
    """

    work_dir = Path(work_dir)
    # Fail-fast 前置校验（0 真机成本）：standard 恒跑 "both" 配置，glass 路径必然
    # 消费 bounds——非法 bounds 与其等整条 asphere autovig ladder 真机批跑完、爬到
    # both 配置构建 sequence 时才炸，不如入口立即 ValueError，不进配置循环。
    # 凸包角点同时供 provenance.gla_hull 使用（与实际注入 AUT GLA 的角点同源）。
    gla_hull = _glass_map_hull(
        DEFAULT_GLASS_BOUNDS_ND_VD if glass_bounds_nd_vd is None else glass_bounds_nd_vd
    )
    configs: dict[str, dict[str, object]] = {}
    # 串行——CODE V 单实例/单 license seat 硬约束，勿并行化。
    preflight_error: dict[str, object] | None = None
    for extra_dof in _STANDARD_EXTRA_DOF_CONFIGS:
        if preflight_error is not None:
            # 种子级预检缺陷（导入即坏，与 extra_dof 配置无关）：第二配置
            # 不再真机重跑同一必然失败，如实记同一错误 + skipped 注记。
            configs[extra_dof] = {
                "error": dict(preflight_error),
                "skipped": "seed-level preflight defect, identical for every config",
            }
            continue
        try:
            data = run_codev_target_autovig(
                source_zmx=source_zmx,
                work_dir=work_dir / extra_dof,
                target_efl_mm=target_efl_mm,
                target_f_number=target_f_number,
                target_imh_mm=target_imh_mm,
                vig_ladder=vig_ladder,
                num_fields=num_fields,
                executable=executable,
                timeout_seconds=timeout_seconds,
                idle_timeout_seconds=idle_timeout_seconds,
                extra_dof=extra_dof,
                glass_bounds_nd_vd=glass_bounds_nd_vd,
                emit_optimized_zmx=emit_optimized_zmx,
            )
            configs[extra_dof] = dict(data)
        except CodeVBatchError as exc:
            error: dict[str, object] = {"kind": exc.kind, "detail": exc.message}
            if exc.details.get("preflight"):
                error["preflight"] = exc.details["preflight"]
                preflight_error = error
            configs[extra_dof] = {"error": error}

    preferred, preferred_reason = _select_preferred(configs)
    # provenance 按 config 如实生成（诚实语义：标签必须与该配置实际跑法一致）：
    # asphere 配置全程不设玻璃变量（无 GLC/GLA）→ "glass-frozen"；both 配置的
    # 玻璃模型标签从实际生效的 bounds 派生，且自定义 bounds 时附上实际注入
    # AUT GLA 的凸包角点字符串（gla_hull），供资深核对可变域本身。顶层只留
    # vignetting_search/quality_note 这两个对两配置同真的共性字段。
    both_glass_model = (
        "fictitious-within-plastic-GLA(default)"
        if glass_bounds_nd_vd is None
        else "fictitious-within-custom-GLA"
    )
    provenance: dict[str, object] = {
        "vignetting_search": "autovig",
        "glass_model": {"asphere": "glass-frozen", "both": both_glass_model},
        "quality_note": (
            "RMS measured on vignetted pupil (edge_used); preferred is numeric "
            "ordering, NOT a yield/quality judgment (EXPERT red line)"
        ),
    }
    if glass_bounds_nd_vd is not None:
        provenance["gla_hull"] = gla_hull
    return {
        "schema": STANDARD_RESULT_SCHEMA,
        "configs": configs,
        "preferred": preferred,
        "preferred_reason": preferred_reason,
        "provenance": provenance,
    }


# ===========================================================================
# FNO 阶梯引擎（Phase 15 Stage 3 · P15-c 交付）：从真机实测 native F# 分级逼近
# 客户 fnum_target（几何级距），每级复用 run_codev_target_autovig（渐晕/
# ray-setup 按该级目标 F# 重新爬梯，短 AUT，EFL 约束保持不变）。见
# .planning/loop/opt3-final-handoff-2026-07-09.md 限制#1（显式 FNO 命令致宽
# 视场主光线追迹失败）与 app/core/engines/fno_probe.py（Stage A/B 失败模式采
# 证 harness，同一根因的姊妹交付）。
#
# 纯加法式新函数——不修改上面任何既有函数的签名/行为，零回归由"新增代码路
# 径与已有测试路径互不相交"保证，不依赖某个"参数为 None 时退化到旧行为"的分
# 支（本文件既有的 target-mode / 标准打包入口都是同一模式，见各自 section
# banner）。
#
# ★ 未接入 C1（run_codev_target_standard）★：本函数刻意不修改任何既有函数、
# 不出现在 CONVERGED_FIELDS（现={"efl"}）——AGENTS.md 北极星条款要求
# CONVERGED_FIELDS 扩 fnum 需真机证据支撑，本阶段（Phase 15 Stage 3）只建
# 引擎 + mock 测试；真机验证 + ≥8 seed 收敛矩阵是下一真机窗（orchestrator
# 续派）。
# ===========================================================================

FNO_LADDER_RESULT_SCHEMA = "atelier-p15-fno-ladder-v1"


def _geometric_fnum_ladder(
    *, native_fnum: float, fnum_target: float, rung_count: int
) -> list[float]:
    """从 ``native_fnum`` 到 ``fnum_target`` 的几何级距序列（不含 native 本
    身，含末级）。末级强制精确等于 ``fnum_target``（浮点几何插值的舍入残差
    在最后一步被清零，不留"差一点点没到 target"的假象）。"""
    if rung_count < 1:
        raise ValueError(f"rung_count must be >= 1: {rung_count!r}")
    _validate_positive(native_fnum, "native_fnum")
    _validate_positive(fnum_target, "fnum_target")
    if math.isclose(native_fnum, fnum_target, rel_tol=1e-9):
        return [fnum_target]
    ratio = fnum_target / native_fnum
    rungs = [native_fnum * (ratio ** (k / rung_count)) for k in range(1, rung_count + 1)]
    rungs[-1] = fnum_target
    return rungs


def _fmt_fnum_ladder_token(value: float) -> str:
    """Dot-free filename token for an F# ladder rung (same CODE V ``BUF EXP``
    filename hazard as ``_fmt_edge_filename_token``, but F# values are not
    bounded to ``[0,1)`` like vignetting edges — dedicated helper at 0.01
    resolution, not a reuse of the vignetting-specific one)."""
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"value must be finite and non-negative: {value!r}")
    return f"fno{round(numeric * 100):04d}"


def _measured_fnum(data: Mapping[str, object]) -> float | None:
    """F# 实测口径（opt3 轮2-3 教训："F# 构造即达≈0" 是一阶物理错，AUT 拉
    EFL/改渐晕时 F# 会漂）：``post_aut.efl_y_mm / post_aut.epd_mm`` 活算，绝
    不信任何构造值。任一字段缺失/非数/非有限，或 EPD≈0（除零风险）→ None
    （fail-closed，宁缺不估算）。"""
    try:
        efl = float(str(data.get("post_aut.efl_y_mm", "")))
        epd = float(str(data.get("post_aut.epd_mm", "")))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(efl) or not math.isfinite(epd) or abs(epd) < 1e-9:
        return None
    return abs(efl / epd)


def _optional_finite_float(data: Mapping[str, object], key: str) -> float | None:
    try:
        value = float(str(data.get(key, "")))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


# F# 达值几何容差默认 8%：spike 设计 spec §6 预设几何容差（F# 8% / IMH 2%，
# 主公 ratify，见 .planning/debug/codev-target-convergence.md「已定决策」1）。
_DEFAULT_FNUM_TOLERANCE_PCT = 8.0

# ray-aware 渐晕重试的建议阶梯（调用方**显式**选用；ladder 参数默认 None=
# 不启用=零回归）：opt3 真机杠杆实证（.planning/debug/codev-target-
# convergence.md 诊断 v2）——显式 VUY/VLY 0.40 全场 → conv✅；0 0.50 0.50 仅
# 离轴 → conv✅；0.30 离轴 / 0.20 全场 → 不足。故从 0.2 爬到 0.5。死路（勿
# 改走）：SET VIG/SET VIY 对零渐晕 seed 是 no-op；SET APE/CAP 的孔径由已失败
# reference ray 派生=循环。
RAY_RETRY_VIG_LADDER: tuple[float, ...] = (0.2, 0.3, 0.4, 0.5)


def _ray_traceable(ray_grid: object) -> bool | None:
    """光线可追迹维（BLOCKER-1）：从 ``run_codev_target`` 的 ``ray_grid`` 诊
    断键（``fno_probe.classify_fno_listing`` describe() dict）派生三值判定——
    ``True`` 仅当分类为 ``"ok"``（正面证据 fail-closed，见 fno_probe）；分类
    为任何失败类 → ``False``；无 ``ray_grid`` 证据（缺清单）→ ``None``（不可
    知≠可追迹，``target_achieved`` 对 None 同样不放行）。"""
    if not isinstance(ray_grid, Mapping):
        return None
    return ray_grid.get("category") == "ok"


def _fno_ladder_rung_from_data(
    *,
    rung_index: int,
    target_fnum: float | None,
    data: Mapping[str, object],
    fnum_tolerance_pct: float,
) -> dict[str, object]:
    """构造一个成功产出数据的 rung 记录。fail-closed：``measured_fnum`` 为
    ``None`` 时该 rung ``status="non-finite"``（快照字段非有限/缺失），否则
    ``"measured"``——绝不用估算填充任何字段。

    ``status="measured"`` 只表示「数据层可解析」（EFL_real/EPD_real 活算出
    了有限值），**不是成功判定**（对抗审查 BLOCKER-1：旧名 "ok" 会被下游读
    成成功）。成功与否拆成两个独立维度分开上报：

      - ``fno_param_achieved``：F# **系统参数达值**维——实测 F# 落在本 rung
        目标的 ``fnum_tolerance_pct`` 几何容差内（rung 0 无目标 → None）。
      - ``ray_traceable``：**光线可追迹**维——``ray_grid`` 分类为 "ok"（正
        面证据）才 True；TIR/MISS/aperture-conflict/other → False；无清单证
        据 → None。

    P15 Stage 2 采证矩阵（42 格真机）证明两维完全分离：40/40 非超时格参数
    逐位达值、但仅 7/42 光栅 clean——单看任何一维都是假阳性。"""
    measured = _measured_fnum(data)
    fnum_target_deviation_pct: float | None = None
    fno_param_achieved: bool | None = None
    if measured is not None and target_fnum is not None and target_fnum > 1e-12:
        fnum_target_deviation_pct = abs(measured - target_fnum) / target_fnum * 100
        fno_param_achieved = fnum_target_deviation_pct <= fnum_tolerance_pct

    aut_error_trace = data.get("aut_error_trace")
    err_f_ratio = (
        aut_error_trace.get("err_f_ratio") if isinstance(aut_error_trace, Mapping) else None
    )
    ray_grid = data.get("ray_grid")
    return {
        "rung_index": rung_index,
        "target_fnum": target_fnum,
        "status": "measured" if measured is not None else "non-finite",
        "measured_fnum": measured,
        "fnum_target_deviation_pct": fnum_target_deviation_pct,
        "fno_param_achieved": fno_param_achieved,
        "ray_traceable": _ray_traceable(ray_grid),
        "ray_grid": dict(ray_grid) if isinstance(ray_grid, Mapping) else None,
        "efl_target_deviation_pct": _optional_finite_float(data, "efl_target_deviation_pct"),
        "post_aut.max_rms_spot_diameter_um": _optional_finite_float(
            data, "post_aut.max_rms_spot_diameter_um"
        ),
        "post_aut.max_rms_wavefront_error_waves": _optional_finite_float(
            data, "post_aut.max_rms_wavefront_error_waves"
        ),
        "err_f_ratio": err_f_ratio,
        "aut_termination": (
            aut_error_trace.get("termination")
            if isinstance(aut_error_trace, Mapping)
            else None
        ),
        "aut_converged": str(data.get("aut_converged")) == "1",
        "autovig.edge_used": data.get("autovig.edge_used"),
        "autovig.converged": data.get("autovig.converged"),
        # Additive schema 演化（对抗审查 MAJOR 裁决，沿仓库 additive 先例）：
        # effective_edge_used / ray_retry 两字段**无条件恒在**（含 ray-retry
        # 未启用的默认路径）——旧键与旧值不变，新键 additive，见
        # test_fno_ladder_rung_schema_is_additive_over_pilot_contract。刻意不
        # 做"条件出现"（条件字段更伤消费者）。
        # effective_edge_used = 渐晕 provenance 单一读取点：未经 ray-retry 时
        # = autovig.edge_used 原值；ray-retry 采纳后 = 重试的显式渐晕 edge
        # （见 _ray_aware_retry）。资深读 RMS/WFE 必须连同此列（RMS 在裁瞳上
        # 测=偏乐观）。
        "effective_edge_used": data.get("autovig.edge_used"),
        "quality_note": (
            "RMS/WFE measured on the accepted autovig pupil; read together with "
            "effective_edge_used"
        ),
        "optimized_zmx_path": data.get("optimized_zmx_path"),
        "ray_retry": None,
        "error": None,
    }


def _fno_ladder_error_rung(
    *, rung_index: int, target_fnum: float | None, exc: CodeVBatchError
) -> dict[str, object]:
    return {
        "rung_index": rung_index,
        "target_fnum": target_fnum,
        "status": "error",
        "measured_fnum": None,
        "fnum_target_deviation_pct": None,
        "fno_param_achieved": None,
        "ray_traceable": None,
        "ray_grid": None,
        "efl_target_deviation_pct": None,
        "post_aut.max_rms_spot_diameter_um": None,
        "post_aut.max_rms_wavefront_error_waves": None,
        "err_f_ratio": None,
        "aut_termination": None,
        "aut_converged": False,
        "autovig.edge_used": None,
        "autovig.converged": None,
        "effective_edge_used": None,
        "quality_note": "rung has no measured accepted optical quality",
        "optimized_zmx_path": None,
        "ray_retry": None,
        "error": {"kind": exc.kind, "detail": exc.message},
    }


def _ray_aware_retry(
    *,
    rung: dict[str, object],
    rung_index: int,
    target_fnum: float | None,
    num_fields: int | None,
    retry_vig_ladder: tuple[float, ...],
    retry_work_dir: Path,
    fnum_tolerance_pct: float,
    run_kwargs: Mapping[str, object],
) -> dict[str, object]:
    """Ray-aware 渐晕重试（P15 阶梯试点实锤的引擎缺口修复，加法式）：

    背景（ladder-pilot-2026-07-11 真机证据）：autovig 只在 EFL 不收敛时爬渐
    晕；一个 EFL 已收敛但光栅带伤（如 chief-ray-missing）的 rung 永远拿不到
    渐晕清理——而渐晕（显式 VUY/VLY/VUX/VLX 因子裁优化光栅，opt3 已验证杠
    杆，F# 不变）恰是裁掉病灶光线的工具。本函数对这样的 rung 按
    ``retry_vig_ladder`` 逐级用显式离轴渐晕（``_autovig_profile``：轴上不
    裁、离轴均匀裁）重跑 ``run_codev_target``，**接受判据 = EFL-hit AND
    ray-clean**（``aut_converged=1`` 且 ``ray_grid.category=="ok"``），命中
    即停。

    诚实口径：
      - 采纳重试后，rung 本体数据（measured_fnum/RMS/WFE/ray_grid 等）全部
        来自重试那次 run；``autovig.edge_used``/``autovig.converged`` 保留
        autovig 阶段的原值（那是 autovig 真实跑出的），采纳数据的真实渐晕
        写在 ``effective_edge_used``（渐晕 provenance 单一读取点）。
      - ``ray_retry.quality_note`` 如实标注：RMS/WFE 在裁瞳光栅上测=较全瞳
        偏乐观，资深必须连渐晕列读。
      - 单次重试报 ``CodeVBatchError``（如 timeout）→ 记录该 attempt 续爬
        下一级（吞并续爬纪律）；爬满仍不满足 → 保留原始（autovig 阶段）
        rung 数据 + ``ray_retry.accepted_edge=None``，rung 如实不被接受
        （``ray_traceable`` 维持 False，``target_achieved`` 不放行）。
    """
    # ray_retry 记录在三个出口分支（采纳 / 耗尽 / 无法尝试）保持同一键集
    # {triggered, accepted_edge, attempts, quality_note, skip_reason}（对抗审
    # 查 MINOR 修复）：quality_note 三分支恒在（消费者无需按分支猜键）；
    # skip_reason 仅在"根本没尝试"时非 None——与"尝试了但耗尽"稳定区分。
    attempts: list[dict[str, object]] = []
    if not num_fields or num_fields <= 1:
        # 无场数（rung 数据里学不到）或单场种子：离轴渐晕 profile 无从构造，
        # 不烧真机盲试——如实记录后返回原 rung（fail-closed，不接受）。
        out = dict(rung)
        out["ray_retry"] = {
            "triggered": True,
            "accepted_edge": None,
            "attempts": attempts,
            "quality_note": (
                "retry not attempted; rung not accepted, original autovig-stage data kept"
            ),
            "skip_reason": (
                "num_fields unavailable or single-field seed; cannot build off-axis profile"
            ),
        }
        return out
    for edge in retry_vig_ladder:
        vig = _autovig_profile(edge, num_fields)
        if vig is None:
            continue  # edge<=0：无渐晕重试无意义（等同原 rung），跳过
        try:
            data2 = run_codev_target(
                work_dir=retry_work_dir,
                vignetting=vig,
                rung_filename_tag=_fmt_edge_filename_token(edge),
                **run_kwargs,
            )
        except CodeVBatchError as exc:
            attempts.append(
                {"edge": edge, "aut_converged": None, "ray_category": None, "error": exc.kind}
            )
            continue
        conv = str(data2.get("aut_converged")) == "1"
        ray_grid = data2.get("ray_grid")
        category = ray_grid.get("category") if isinstance(ray_grid, Mapping) else None
        attempts.append(
            {"edge": edge, "aut_converged": conv, "ray_category": category, "error": None}
        )
        if conv and category == "ok":
            accepted = _fno_ladder_rung_from_data(
                rung_index=rung_index,
                target_fnum=target_fnum,
                data=data2,
                fnum_tolerance_pct=fnum_tolerance_pct,
            )
            # autovig.* 保留 autovig 阶段原值（诚实：重试不是 autovig 跑的）；
            # 采纳数据的真实渐晕走 effective_edge_used。
            accepted["autovig.edge_used"] = rung.get("autovig.edge_used")
            accepted["autovig.converged"] = rung.get("autovig.converged")
            accepted["effective_edge_used"] = _fmt_number(edge)
            accepted["quality_note"] = (
                "RMS/WFE measured on the retry's vignetted pupil "
                f"(off-axis edge={edge:g}) — optimistic vs full pupil; "
                "read together with effective_edge_used"
            )
            accepted["ray_retry"] = {
                "triggered": True,
                "accepted_edge": edge,
                "attempts": attempts,
                "quality_note": (
                    "RMS/WFE measured on the retry's vignetted pupil "
                    f"(off-axis edge={edge:g}) — optimistic vs full pupil; "
                    "read together with effective_edge_used"
                ),
                "skip_reason": None,
            }
            return accepted
    out = dict(rung)
    out["ray_retry"] = {
        "triggered": True,
        "accepted_edge": None,
        "attempts": attempts,
        "quality_note": (
            "exhausted retry ladder without an EFL-hit AND ray-clean edge; "
            "rung not accepted, original autovig-stage data kept"
        ),
        "skip_reason": None,
    }
    return out


def run_codev_target_fno_ladder(
    *,
    source_zmx: Path | str,
    work_dir: Path | str,
    target_efl_mm: float,
    fnum_target: float,
    target_imh_mm: float | None = None,
    stage: str = "A",
    rung_count: int = 3,
    fnum_tolerance_pct: float = _DEFAULT_FNUM_TOLERANCE_PCT,
    vig_ladder: tuple[float, ...] = _DEFAULT_VIG_LADDER,
    ray_retry_vig_ladder: tuple[float, ...] | None = None,
    num_fields: int | None = None,
    extra_dof: str = "none",
    glass_bounds_nd_vd: Sequence[tuple[float, float]] | None = None,
    executable: Path | str | os.PathLike[str] = DEFAULT_CODEV_EXECUTABLE,
    timeout_seconds: float = 180.0,
    idle_timeout_seconds: float | None = None,
    platform_name: str = os.name,
    emit_optimized_zmx: bool = False,
) -> dict[str, object]:
    """从 seed 实测 native F# 分级逼近 ``fnum_target``（几何级距，rung_count
    级 + rung 0 = native），每级独立调用 ``run_codev_target_autovig``（该级
    目标 F# 下重新爬渐晕/ray-setup 梯，短 AUT，EFL 约束保持不变）。

    Rung 0（native）：``target_f_number=None``（不设 FNO，即现有已验证的
    Stage A/autovig 路径）——用它的 ``post_aut`` 快照实测 native F#
    （``EFL_real/EPD_real`` 活算，见 ``_measured_fnum``），而不是信任调用方
    传入或 index.json 里的标称值（opt3 轮2-3 教训：F# 会随 AUT/渐晕漂移，构
    造值不可信）。Rung 1..``rung_count``：目标 F# 按
    ``_geometric_fnum_ladder`` 几何插值，末级强制精确等于 ``fnum_target``。

    每级独立、串行调用 ``run_codev_target_autovig``；该级若报
    ``CodeVBatchError`` 且非 seed 级预检缺陷 → 记为该 rung
    ``status="error"``，**吞并续爬**下一级（先例：``US20180143405A1``
    recovery，见 ``run_codev_target_autovig`` 文档字符串）。Seed 级预检缺陷
    （如导入即全空气）→ 换 F# 不会改变导入结果，立即整条 ladder 短路上抛
    （与 ``run_codev_target_autovig``/``run_codev_target_standard`` 同款
    fail-fast 语义）。若 rung 0 本身就短路/未拿到可用 native 实测，几何级
    距无基点可算——如实只保留 rung 0 的记录，不猜测续爬（fail-closed，宁缺
    不估算）。

    fail-closed（AGENTS.md 诚实红线）：任一 rung 的 ``post_aut`` 关键快照字
    段非有限/缺失 → 该 rung ``status="non-finite"``，对应字段一律 ``None``，
    绝不用估算填充。``measured_fnum`` 是本函数的核心诚实性字段：F# 达成与否
    只信 ``post_aut.efl_y_mm``/``post_aut.epd_mm`` 活算之比，不信 ``FNO``
    命令本身"构造设定"了什么。

    双维达标判定（对抗审查 BLOCKER-1/-2 修复 2026-07-11）：P15 Stage 2 采证
    矩阵（42 格真机）证明「FNO 系统参数达值」与「光线可追迹性」完全分离
    （40/40 参数逐位达值 vs 仅 7/42 光栅 clean）——``aut_converged=1 +
    post_aut.fno==target`` 是双重假阳性。因此：

      - 每 rung 记录 ``fno_param_achieved``（实测 F# 落 ``fnum_tolerance_pct``
        几何容差内，默认 8% = spike spec §6 主公 ratify 容差）与
        ``ray_traceable``（``ray_grid`` 分类为 "ok" 的正面证据）两个独立维度。
      - 顶层 ``target_achieved`` 仅当**目标 rung**（target_fnum ==
        fnum_target 的那一级）同时满足四条：status="measured" AND
        fno_param_achieved AND aut_converged（EFL 约束保持）AND
        ray_traceable——任何一维缺证据（None）都不放行（fail-closed）。
      - ``last_measured_rung`` 只回答「爬到哪」（最后一个可解析 rung），与
        「到没到 target」（``accepted_final``，仅 ``target_achieved`` 时非
        None）是两个不同的问题，刻意分开命名。

    每个 rung 独立子目录（``work_dir/rung{k}_...``），互不覆写——内部
    autovig 爬梯已用 ``_fmt_edge_filename_token`` 消歧同一 rung 内的渐晕级，
    F#-rung 之间的消歧则由子目录边界保证，不需要改动
    ``run_codev_target_autovig`` 本体。

    ``ray_retry_vig_ladder``（默认 ``None`` = 不启用）：ray-aware 渐晕重试
    （真机试点 ladder-pilot-2026-07-11 实锤的引擎缺口——autovig 只治"EFL 不
    收敛"，不治"EFL 收敛但光栅带伤"，全部试点 rung edge=0 即证）。

    兼容性声明（对抗审查 MAJOR 裁决，沿仓库 additive-schema 先例）：默认
    ``None`` 时为**行为零回归**（不发起任何重试 CODE V 调用、既有键值全部
    不变），但 rung 记录 schema 为 **additive 演化**——新增
    ``effective_edge_used``（默认路径下恒等于 ``autovig.edge_used``）与
    ``ray_retry``（默认路径下恒为 ``None``）两个**无条件恒在**的字段，刻意
    不做条件出现（条件字段更伤消费者）。旧消费者按旧键读取不受影响，见
    ``test_fno_ladder_rung_schema_is_additive_over_pilot_contract``。

    启用后，任一 rung 满足 **EFL-hit（aut_converged）AND
    ray_traceable is False**（光栅有确证病灶；``None``=无证据不烧真机盲试）
    时，按该阶梯逐级用显式离轴渐晕因子（``_autovig_profile``，opt3 验证杠杆
    VUY/VLY/VUX/VLX，F# 不变）重跑该 rung，接受判据 = **EFL-hit AND
    ray-clean**，命中即停；爬满不中则保留原数据、rung 如实不被接受。建议值
    ``RAY_RETRY_VIG_LADDER``（0.2→0.5，opt3 实测有效带）。重试证据全部进
    rung 记录的 ``ray_retry`` dict（统一键集 triggered/attempts/
    accepted_edge/quality_note/skip_reason，三出口分支同构），采纳数据的真
    实渐晕在 ``effective_edge_used``（渐晕 provenance 单一读取点；RMS 在裁
    瞳上测=偏乐观，资深连列读）。

    Returns:
        {"schema": FNO_LADDER_RESULT_SCHEMA, "source_zmx": ..., "stage": ...,
         "target_efl_mm": ..., "fnum_target": ..., "rung_count": ...,
         "fnum_tolerance_pct": float,
         "native_fnum_measured": float | None,
         "rungs": [rung0_dict, rung1_dict, ...],  # 见
             _fno_ladder_rung_from_data / _fno_ladder_error_rung；每 rung 含
             effective_edge_used（渐晕 provenance）与 ray_retry（None=未触发）
         "last_measured_rung_index": int | None,  # 最后一个可解析 rung（爬到哪）
         "last_measured_rung": dict | None,       # 该 rung 记录浅拷贝；None=全灭
         "target_achieved": bool,   # 四条件达标（见上），fail-closed
         "accepted_final": dict | None,  # 达标时=目标 rung 记录；未达标=None
         "blocked": bool}  # True 当且仅当没有任何一级产出可解析数据
    """

    work_dir = Path(work_dir)
    rungs: list[dict[str, object]] = []

    def _run_rung(*, rung_index: int, target_fnum: float | None, tag: str) -> dict[str, object]:
        try:
            data = run_codev_target_autovig(
                source_zmx=source_zmx,
                work_dir=work_dir / tag,
                target_efl_mm=target_efl_mm,
                target_f_number=target_fnum,
                target_imh_mm=target_imh_mm,
                stage=stage,
                vig_ladder=vig_ladder,
                num_fields=num_fields,
                executable=executable,
                timeout_seconds=timeout_seconds,
                idle_timeout_seconds=idle_timeout_seconds,
                platform_name=platform_name,
                extra_dof=extra_dof,
                glass_bounds_nd_vd=glass_bounds_nd_vd,
                emit_optimized_zmx=emit_optimized_zmx,
            )
        except CodeVBatchError as exc:
            if exc.details.get("preflight"):
                raise
            return _fno_ladder_error_rung(rung_index=rung_index, target_fnum=target_fnum, exc=exc)
        rung = _fno_ladder_rung_from_data(
            rung_index=rung_index,
            target_fnum=target_fnum,
            data=data,
            fnum_tolerance_pct=fnum_tolerance_pct,
        )
        if (
            ray_retry_vig_ladder
            and rung["status"] == "measured"
            and rung["aut_converged"] is True
            and rung["ray_traceable"] is False
        ):
            # 场数：优先调用方注入，否则从本 rung 数据学（autovig 出参 TSV 键）。
            nf = num_fields
            if nf is None:
                try:
                    nf = int(float(str(data.get("num_fields", "0") or "0")))
                except (TypeError, ValueError):
                    nf = None
            rung = _ray_aware_retry(
                rung=rung,
                rung_index=rung_index,
                target_fnum=target_fnum,
                num_fields=nf,
                retry_vig_ladder=ray_retry_vig_ladder,
                retry_work_dir=work_dir / tag / "ray_retry",
                fnum_tolerance_pct=fnum_tolerance_pct,
                run_kwargs={
                    "source_zmx": source_zmx,
                    "target_efl_mm": target_efl_mm,
                    "target_f_number": target_fnum,
                    "target_imh_mm": target_imh_mm,
                    "stage": stage,
                    "executable": executable,
                    "timeout_seconds": timeout_seconds,
                    "platform_name": platform_name,
                    "extra_dof": extra_dof,
                    "glass_bounds_nd_vd": glass_bounds_nd_vd,
                    "emit_optimized_zmx": emit_optimized_zmx,
                },
            )
        return rung

    rung0 = _run_rung(rung_index=0, target_fnum=None, tag="rung0_native")
    rungs.append(rung0)
    native_measured = rung0["measured_fnum"] if rung0["status"] == "measured" else None

    if native_measured is not None:
        ladder = _geometric_fnum_ladder(
            native_fnum=native_measured, fnum_target=fnum_target, rung_count=rung_count
        )
        for k, rung_target in enumerate(ladder, start=1):
            token = _fmt_fnum_ladder_token(rung_target)
            rungs.append(
                _run_rung(rung_index=k, target_fnum=rung_target, tag=f"rung{k}_{token}")
            )
    # else: rung0 未拿到可用 native 实测（error/non-finite）——几何级距无基点
    # 可算，不猜测续爬，如实只留 rung0 的记录（fail-closed，宁缺不估算）。

    measured_rungs = [r for r in rungs if r["status"] == "measured"]
    last_measured = dict(measured_rungs[-1]) if measured_rungs else None

    # target_achieved 四条件（BLOCKER-2，fail-closed：布尔维度的 None 不放行）：
    # 目标 rung 存在且可解析 + F# 参数达值（容差内）+ EFL 约束保持 + 光栅可追
    # 迹（正面证据）。目标 rung 按 target_fnum == fnum_target 认定（末级由
    # _geometric_fnum_ladder 强制精确等于 target；native≈target 时唯一级即目标级）。
    target_rungs = [
        r
        for r in rungs
        if r["target_fnum"] is not None
        and math.isclose(float(r["target_fnum"]), fnum_target, rel_tol=1e-9)
    ]
    accepted_final: dict[str, object] | None = None
    if target_rungs:
        candidate = target_rungs[-1]
        if (
            candidate["status"] == "measured"
            and candidate["fno_param_achieved"] is True
            and candidate["aut_converged"] is True
            and candidate["ray_traceable"] is True
        ):
            accepted_final = dict(candidate)
    return {
        "schema": FNO_LADDER_RESULT_SCHEMA,
        "source_zmx": Path(source_zmx).name,
        "stage": stage,
        "target_efl_mm": target_efl_mm,
        "fnum_target": fnum_target,
        "rung_count": rung_count,
        "fnum_tolerance_pct": fnum_tolerance_pct,
        "vig_ladder": list(vig_ladder),
        "ray_retry_vig_ladder": list(ray_retry_vig_ladder or ()),
        "num_fields": num_fields,
        "extra_dof": extra_dof,
        "native_fnum_measured": native_measured,
        "rungs": rungs,
        "last_measured_rung_index": (
            last_measured["rung_index"] if last_measured is not None else None
        ),
        "last_measured_rung": last_measured,
        "target_achieved": accepted_final is not None,
        "accepted_final": accepted_final,
        "blocked": last_measured is None,
    }


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
    """Parse the perturbation replay rows, withholding drops built on seed values.

    ``mtf_drop`` is not an independent reading: the macro computes it as
    ``^tol_nominal_mtf - ^tol_perturbed_mtf`` and clamps a negative result to 0.
    Both endpoints pass through ``_measured_mtf_or_none``, so a degenerate
    ``@mtfmin`` seed of 1.0 is already withheld there -- but the *difference*
    was still reported, and it is the sort key, so a degenerate endpoint does
    more damage than a degenerate endpoint reading:

    * degenerate nominal (1.0) minus a real perturbed value yields the largest
      possible drop, which sorts the row to **rank 1** -- the run's headline
      "most sensitive parameter" becomes the one that produced no data at all;
    * degenerate perturbed value yields a negative difference that the macro
      clamps to ``0`` -- "perfectly insensitive to this perturbation", which is
      the recurring trap of a degenerate value landing exactly on the ideal
      reading.

    A drop therefore counts as measured only when both endpoints are present and
    inside the measurable band. Rows whose drop is withheld are still reported
    (the perturbation was run) but sort **after** every measured row, so an
    unmeasured row can never occupy the top of the ranking.
    """
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
        # 1.0 是 @mtfmin 的"无一视场出数"种子值，不是"完美 MTF"。
        nominal_mtf = _measured_mtf_or_none(_optional_float(data, f"{prefix}.nominal_mtf"))
        perturbed_mtf = _measured_mtf_or_none(_optional_float(data, f"{prefix}.perturbed_mtf"))
        items.append(
            CodeVToleranceSensitivity(
                rank=index,
                parameter_name=parameter_name,
                perturbation=perturbation,
                mtf_drop=(
                    mtf_drop if nominal_mtf is not None and perturbed_mtf is not None else None
                ),
                nominal_mtf=nominal_mtf,
                perturbed_mtf=perturbed_mtf,
                provenance=data.get("tolerance.provenance", "codev-run"),
            )
        )

    # Unmeasured drops sort last, never into the headline slot.
    ranked = sorted(
        items,
        key=lambda item: (
            item.mtf_drop is None,
            -(item.mtf_drop if item.mtf_drop is not None else 0.0),
            item.parameter_name,
        ),
    )
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


def _parse_wavelength_count(data: Mapping[str, str], prefix: str) -> int | None:
    """Wavelength count CODE V actually ran with, or None on legacy result files."""

    raw = data.get(f"{prefix}.num_wavelengths")
    if raw is None:
        return None
    try:
        value = int(float(str(raw)))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _parse_metrics(data: Mapping[str, str], prefix: str) -> CodeVOptimizationMetrics:
    wavelength_count = _parse_wavelength_count(data, prefix)
    lateral_color: float | None = _required_float(data, f"{prefix}.max_lateral_color_um")
    # Fail-closed on un-measurable lateral color.
    #
    # ``@lcum`` (see _metric_function_block) measures the image-point separation
    # between the shortest and longest wavelength: ^wshort == 1, ^wlong == (NUM W).
    # When CODE V ends up with a single wavelength both indices point at the SAME
    # wavelength, so the distance is identically 0 and the macro reports perfect
    # achromatism for a system whose chromatic behaviour was never evaluated.
    # It also silently neuters the ``@atelier_latcolor = 0`` optimization target.
    #
    # This is not hypothetical: 403 of 442 library seeds (91%) carry the 3-row
    # WAVM header, and a 2026-07-27 real-machine probe collapsed 6/6 of them to
    # NUM W == 1 on import (the 24-row, CODE-V-round-tripped seeds kept 5).
    #
    # Unlike @rmssum -- where any value <= 0 is impossible and thus self-marking
    # (see _standard_config_rms) -- 0.0 is a PHYSICALLY LEGITIMATE lateral color.
    # The degenerate case is therefore indistinguishable from a real result by
    # value alone, and the wavelength count is the only sound discriminator.
    if wavelength_count is not None and wavelength_count < 3:
        lateral_color = None

    # Second, independent degeneracy: NO field traced at all.
    #
    # Every metric FCT in _metric_function_block seeds an accumulator and only
    # updates it for fields whose query succeeds, so a system where every field
    # fails returns the seed value -- and each seed value is the *ideal* reading:
    # @rmssum/@wfewav/@dstpct start at ``^max == 0`` and @mtfmin at ``^min == 1``.
    # Real-machine evidence (2026-07-27, 8 corpus seeds x 2 arms): 4 of the 8
    # returned exactly rms=0 / wfe=0 / distortion=0 / lat=0 / mtf=1 while their
    # EFL computed normally, and their listings carry 99x "Total reflection at
    # surface 12", "Ray missed surface", "Unable to find chief ray" -- CODE V
    # even printed "distortion calculations may be in error." 16 times.
    #
    # RMS spot diameter and RMS wavefront error are positive-definite, so <= 0
    # is self-marking for those two. Distortion and lateral color have legitimate
    # 0.0 readings and cannot be judged by value -- the collapse of BOTH
    # positive-definite metrics is what tells us nothing was traced.
    #
    # This guard is what keeps the multi-wavelength import fix from *opening* a
    # hole: once a trace-failed seed reports NUM W = 3, the wavelength test above
    # no longer fires, and its 0.0 lateral color would read as "measured, and
    # perfectly achromatic".
    rms_spot = _positive_metric_or_none(_required_float(data, f"{prefix}.max_rms_spot_diameter_um"))
    wavefront_error = _positive_metric_or_none(
        _required_float(data, f"{prefix}.max_rms_wavefront_error_waves")
    )
    distortion: float | None = _required_float(data, f"{prefix}.max_distortion_pct")
    ray_trace_degenerate = rms_spot is None and wavefront_error is None
    if ray_trace_degenerate:
        distortion = None
        lateral_color = None

    return CodeVOptimizationMetrics(
        efl_y_mm=_required_float(data, f"{prefix}.efl_y_mm"),
        max_lateral_color_um=lateral_color,
        max_rms_spot_diameter_um=rms_spot,
        max_rms_wavefront_error_waves=wavefront_error,
        max_distortion_pct=distortion,
        wavelength_count=wavelength_count,
        ray_trace_degenerate=ray_trace_degenerate,
    )


def _positive_metric_or_none(value: float | None) -> float | None:
    """Return a positive-definite metric, or ``None`` when it cannot be one.

    RMS spot diameter and RMS wavefront error are strictly positive for any real
    system (diffraction sets a floor above zero), so ``<= 0`` can only be the
    "nothing traced" accumulator seed described in :func:`_parse_metrics`, and a
    non-finite value can only be a broken export.
    """

    if value is None or not math.isfinite(value) or value <= 0.0:
        return None
    return value


def _measured_mtf_or_none(value: float | None) -> float | None:
    """Return a measured MTF, or ``None`` when the reading is the ``@mtfmin`` seed.

    ``@mtfmin`` starts at ``^min == 1`` and only ever decreases, so 1.0 survives
    exactly when no field produced a modulation value. Callers always evaluate at
    a strictly positive frequency (``_validate_positive`` on
    ``tolerance_mtf_frequency_lpmm``), where diffraction bounds MTF strictly below
    1 -- so ``>= 1.0`` is self-marking, and ``<= 0`` is likewise unphysical.
    """

    if value is None or not math.isfinite(value):
        return None
    if value <= 0.0 or value >= 1.0:
        return None
    return value


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
        # Emitted so the reader can tell "achromatic" from "never measured":
        # @lcum spans W1..W(NUM W) and degenerates to a constant 0 at NUM W < 3.
        f"^{prefix}_num_wavelengths == (NUM W)",
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
    _append_put_row(lines, f'"{prefix}.num_wavelengths"', f"^{prefix}_num_wavelengths")


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
    # This emitter and codev_readout's write result files that the same parser
    # reads, so every surface-level block has to exist in both. PR #107 added
    # the SPS ODD block to codev_readout only, and the consequence was silent
    # and expensive: run_codev_readout round-tripped aspheres correctly while
    # the *candidate-producing* path still refused every SPS ODD seed
    # (7 of 14 trials `candidate_zmx_missing` in the 2026-07-29 pilot re-run).
    _append_odd_asphere_block(lines)
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
        # Must stay in lockstep with codev_readout's emitter: both write result
        # files that the same parser reads. See ASPHERE_EXPORT_SCALE.
        _append_dynamic_surface_row(
            lines,
            f".asphere_scaled.{label}",
            f"^coef{label}*{ASPHERE_EXPORT_SCALE:.0f}",
        )
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
