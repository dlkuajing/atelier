"""C1 候选集规格书级导出（Phase 17 子项2）。

两个导出物，均从**同一份已验证 `CandidateSet`**（`app.main._candidate_set_context`
读 `record.result["candidate_set"]`、`CandidateSet.model_validate` 一次后同时喂给
HTML 渲染与本模块）取数——不重新触碰 optic/ZMX、不二次计算，与页面同源
（北极星"诚实红线"：导出物数值必须与页面同源）。[EXPERT] 栅格在导出物中同样
留白（不写任何 合格/良品/pass/fail 字样）。

① `build_candidate_set_workbook`：xlsx 工作簿——Summary 页（需求回显 + 批次
摘要 + honesty banner）+ Candidates 页（每候选一行：5 维偏差 + 像质摘要 +
可制造性 proxy + 排序结果）。
② `build_candidate_bundle_zip`：单候选 ZMX + 复现 .seq + README 下载包。

**已知限制（如实记录，非本铲修复范围）**：Mode3（`TargetConvergedGenerator`，
`app/core/orchestration/generators.py`）优化后的 ZMX 落在一次性
`tempfile.TemporaryDirectory` 里，任务结束即清理——`generators.py` 是另一在飞
PR（`feat/mode3-funnel-tuning`，#63）的文件面，本铲铁律不碰。因此：
- ZMX 下载对**任意** mode 都走同一条路径解析（`ZMX_AMMO_DIR /
  payload.metadata.source_zmx`）——Mode1（检索，零优化）今天就能下载真实文件；
  Mode3 的优化 ZMX 今天解析不到（fail closed，README 如实说明），一旦
  generators.py 侧把优化 ZMX 落进持久化目录（或把路径接进这里），这条路径
  自动生效，不需要再改本模块。
- 复现 `.seq`：Mode3 专属，用 `codev_optimize.build_codev_target_sequence`
  （纯字符串生成，见其 docstring）从候选留存的 provenance（target EFL、
  candidate_id 编码的 preferred 配置、`codev_post_aut["autovig.edge_used"]`）
  重建一份"配方"宏——不是历史上真正跑过的那份 `.seq`字节（那份也在同一个
  已清理的临时目录里），是可重新提交给 CODE V、预期产出等价优化的复现脚本。
  **上列三件 provenance 缺任何一件即 fail-closed 不交付 .seq**（P17 对抗审
  M2：缺 `edge_used` 曾退化成 native/no-clip 宏仍冒充"复现"——渐晕/裁瞳
  配置是复现语义的一部分，缺件重建=另一个配置，README 会写明缺哪件；
  `edge_used=0.0` 是合法完整值=零裁瞳，不算缺件）。`num_fields=3` 是
  generators.py `_candidate_for_seed` 当前硬编码值（未来若可配，需要
  codev_post_aut 补一个字段才能精确复现）。
"""

from __future__ import annotations

import io
import math
import zipfile
from datetime import UTC, datetime

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.core.engines.codev_optimize import _autovig_profile, build_codev_target_sequence
from app.core.orchestration.candidate import (
    CandidateSet,
    GenerationMode,
    ManufacturabilityProxy,
    RepeatabilityMetrics,
    ScoredCandidate,
    TargetDeviation,
    TargetSpec,
)
from app.core.orchestration.formatting import (
    fmt_float,
    fmt_metric,
    fmt_optional_int,
    fmt_optional_target,
    fmt_pct,
    fmt_rel_violation,
    fmt_yes_no,
)
from app.core.zmx_ingest import ZMX_AMMO_DIR

_NON_PASS_FAIL_BANNER = (
    "本表仅量化数据，不代为判定——量产可用性判断权与 [EXPERT] 背书"
    "始终在资深设计师手里（AGENTS.md 北极星条款）。"
)

# P17 对抗审 M3：xlsx 单元格与候选集页面共用 `orchestration.formatting` 的
# 同一套格式化函数（同一 payload → 同一字符串，含"非零小值不落 0.000 假零"
# 守卫）。代价是 xlsx 携带的是显示口径字符串而非原始 float——全精度原值以
# job result JSON（`CandidateSet.model_dump`）为机读真相源，Summary 页有
# 显式说明行。
_PRECISION_NOTE = (
    "数值口径：与候选集页面同一格式化器（三位小数 / 1 位小数百分比；"
    "非零小值显示为 <最小刻度，绝不显示假零 0.000）。全精度原始数据以"
    " job result JSON（CandidateSet.model_dump）为准。"
)

# Fixed Mode3 constant this module's .seq reconstruction relies on — mirrors
# `generators.py::TargetConvergedGenerator._candidate_for_seed`'s hardcoded
# `run_codev_target_standard(..., num_fields=3)` call. If that call site ever
# starts varying `num_fields` per seed, a real field count needs to be added
# to `OpticalExtras.codev_post_aut` before this constant can be retired.
_MODE3_NUM_FIELDS = 3


# ---------------------------------------------------------------------------
# ① xlsx workbook
# ---------------------------------------------------------------------------

_DEVIATION_FIELDS: tuple[str, ...] = ("efl", "fov", "fnum", "imh", "ttl")

_IMAGE_QUALITY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("MTF sag", "mtf_sag"),
    ("MTF tan", "mtf_tan"),
    ("Diffraction cutoff (lp/mm)", "diffraction_cutoff_lp_per_mm"),
    ("RMS spot radius max (um)", "rms_spot_radius_max_um"),
    ("RMS spot radius mean (um)", "rms_spot_radius_mean_um"),
    ("Min Strehl ratio", "min_strehl_ratio"),
    ("RMS wavefront error (waves)", "rms_wavefront_error_waves"),
    ("Field curvature tan delta (mm)", "field_curvature_tangential_delta_mm"),
    ("Field curvature sag delta (mm)", "field_curvature_sagittal_delta_mm"),
    ("Max distortion (%)", "max_distortion_pct"),
    ("Relative illumination (worst field)", "relative_illumination"),
)


def _target_spec_rows(target: TargetSpec) -> list[tuple[str, str]]:
    """Target-spec echo rows — identical strings to the page's
    `_candidate_requirement_rows` (`app/main.py`), including the page's
    per-field precisions (FOV = 1 decimal)."""
    return [
        ("Scenario", target.scenario.value),
        ("EFL (mm)", fmt_optional_target(target.efl_mm)),
        ("FOV (deg)", fmt_optional_target(target.fov_deg, precision=1)),
        ("F-number", fmt_float(target.fnum)),
        ("Image height (mm)", fmt_optional_target(target.image_height_mm)),
        ("Max total track (mm)", fmt_optional_target(target.max_total_track_mm)),
        ("Element count", fmt_optional_int(target.n_elements)),
    ]


def _write_summary_sheet(
    ws: Worksheet, candidate_set: CandidateSet, *, job_id: str, requirement: str | None
) -> None:
    ws.title = "Summary"
    ws.append(["Atelier C1 candidate set — spec sheet export"])
    ws.append(["Generated (UTC)", datetime.now(UTC).isoformat(timespec="seconds")])
    ws.append(["Job ID", job_id])
    ws.append(["Requirement", requirement or "(none)"])
    ws.append([_PRECISION_NOTE])
    ws.append([])
    if candidate_set.honesty_banner:
        ws.append(["Honesty notice", candidate_set.honesty_banner])
        ws.append([])
    ws.append(["Target spec"])
    for label, value in _target_spec_rows(candidate_set.target):
        ws.append([label, value])
    ws.append([])
    summary = candidate_set.summary
    ws.append(["Batch summary"])
    ws.append(["Candidate count", summary.candidate_count])
    ws.append(["Ranked", summary.ranked_count])
    ws.append(["Withheld", summary.withheld_count])
    ws.append(["RI missing", summary.ri_missing_count])
    for mode, count in summary.mode_counts.items():
        ws.append([f"mode={mode.value}", count])
    for note in summary.notes:
        ws.append(["Note", note])
    ws.append([])
    ws.append([_NON_PASS_FAIL_BANNER])


def _deviation_by_field(deviations: list[TargetDeviation]) -> dict[str, TargetDeviation]:
    return {dev.field: dev for dev in deviations}


def _manufacturability_row(mfg: ManufacturabilityProxy) -> list[object]:
    # Same strings/precisions as the page's `_candidate_manufacturability_context`.
    return [
        fmt_float(mfg.total_track_mm),
        mfg.n_pieces,
        fmt_yes_no(mfg.has_special_glass),
        fmt_metric(mfg.aspheric_term_count, precision=0),
        fmt_metric(mfg.aspheric_surface_count, precision=0),
        fmt_metric(mfg.chief_ray_angle_deg),
    ]


_REPEATABILITY_COLUMNS: tuple[str, ...] = (
    "repeatability_run_count",
    "repeatability_status",
    "repeatability_rms_um_min",
    "repeatability_rms_um_max",
    "repeatability_rms_um_spread",
    "repeatability_wfe_waves_min",
    "repeatability_wfe_waves_max",
    "repeatability_wfe_waves_spread",
    "repeatability_note",
)


def _repeatability_row(rep: RepeatabilityMetrics) -> list[object]:
    # Same strings as the page's `_candidate_repeatability_context`.
    return [
        rep.run_count,
        rep.status,
        fmt_metric(rep.rms_spot_radius_um_min),
        fmt_metric(rep.rms_spot_radius_um_max),
        fmt_metric(rep.rms_spot_radius_um_spread),
        fmt_metric(rep.wfe_waves_min),
        fmt_metric(rep.wfe_waves_max),
        fmt_metric(rep.wfe_waves_spread),
        rep.note,
    ]


def _write_candidates_sheet(ws: Worksheet, candidate_set: CandidateSet) -> None:
    ws.title = "Candidates"
    header = ["candidate_id", "mode", "source_case_id", "rank_status", "rank_score", "coverage_pct", "missing_metrics"]
    for field in _DEVIATION_FIELDS:
        header += [
            f"{field}_target",
            f"{field}_achieved",
            f"{field}_violation",
            f"{field}_rel_violation",
            f"{field}_converged",
        ]
    header += [label for label, _ in _IMAGE_QUALITY_COLUMNS]
    header += ["ttl_mm", "n_pieces", "has_special_glass", "aspheric_term_count", "aspheric_surface_count", "chief_ray_angle_deg"]
    header += list(_REPEATABILITY_COLUMNS)
    ws.append(header)

    for sc in candidate_set.candidates:
        row = sc.scorecard
        gen = sc.generated
        by_field = _deviation_by_field(row.target_deviations)
        line: list[object] = [
            row.candidate_id,
            row.mode.value,
            gen.source_case_id or "(none)",
            row.rank.status,
            fmt_float(row.rank.score) if row.rank.score is not None else "N/A",
            fmt_pct(row.rank.coverage_pct, precision=0),
            ", ".join(row.rank.missing_metrics) or "(none)",
        ]
        for field in _DEVIATION_FIELDS:
            dev = by_field.get(field)
            if dev is None:
                line += ["(n/a)", "(n/a)", "(n/a)", "(n/a)", "(n/a)"]
            else:
                # Same strings as the page's `_candidate_deviation_row`.
                line += [
                    fmt_optional_target(dev.target),
                    fmt_float(dev.achieved),
                    fmt_float(dev.violation),
                    fmt_rel_violation(dev.rel_violation),
                    fmt_yes_no(dev.converged_toward_target),
                ]
        for _, attr in _IMAGE_QUALITY_COLUMNS:
            line.append(fmt_metric(getattr(row.image_quality, attr)))
        line += _manufacturability_row(row.manufacturability)
        line += _repeatability_row(row.repeatability)
        ws.append(line)


def build_candidate_set_workbook(
    candidate_set: CandidateSet, *, job_id: str, requirement: str | None
) -> bytes:
    """Render one xlsx workbook (bytes) for the whole candidate set. Pure
    function of `candidate_set` — the same validated object the candidate-set
    page renders (`app.main._candidate_set_context`), so every number here is
    the identical value shown on the page (no second computation)."""
    wb = Workbook()
    summary_ws = wb.active
    assert summary_ws is not None
    _write_summary_sheet(summary_ws, candidate_set, job_id=job_id, requirement=requirement)
    candidates_ws = wb.create_sheet("Candidates")
    _write_candidates_sheet(candidates_ws, candidate_set)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# ② per-candidate ZMX + reproduction .seq + README zip
# ---------------------------------------------------------------------------


def _resolve_candidate_zmx_path(sc: ScoredCandidate):
    """Resolve the candidate's own delivered-payload ZMX under the
    persistent `ZMX_AMMO_DIR` — mode-agnostic by design (see module
    docstring "已知限制"): real today for `RETRIEVED` candidates, will start
    resolving for `TARGET_CONVERGED` candidates automatically once the
    generators.py-side persistence gap is closed, with zero changes needed
    here. `None` when the metadata is missing or the file isn't actually
    there (fail closed, never fabricates a path)."""
    metadata = sc.generated.payload.metadata
    if metadata is None or not metadata.source_zmx:
        return None
    path = ZMX_AMMO_DIR / metadata.source_zmx
    return path if path.is_file() else None


def _resolve_seed_zmx_path(sc: ScoredCandidate):
    """Resolve the *original seed's* ZMX (not the Mode3 optimized result) —
    `case_id` is derived as `source_zmx.rsplit(".", 1)[0]` everywhere in this
    codebase (`case_library.build_sample_from_optic`), so this reconstruction
    is exact, not a guess. Used as the reproduction `.seq`'s `source_zmx`
    input."""
    case_id = sc.generated.source_case_id
    if not case_id:
        return None
    path = ZMX_AMMO_DIR / f"{case_id}.zmx"
    return path if path.is_file() else None


def _mode3_preferred_config(candidate_id: str) -> str | None:
    """Parse the `preferred` extra_dof config name out of a Mode3 candidate
    id, which `generators.py` encodes as
    `f"{case_id}::target-converged-{preferred}"` (structural, not a guess —
    the only place that string is built)."""
    marker = "::target-converged-"
    if marker not in candidate_id:
        return None
    return candidate_id.rsplit(marker, 1)[-1] or None


def _reproduction_seq_text(
    sc: ScoredCandidate, target: TargetSpec
) -> tuple[str | None, str | None]:
    """Deterministic reconstruction of a CODE V macro that would reproduce
    (not byte-for-byte replay — a fresh, equivalent recipe) this Mode3
    candidate's optimization. Returns `(seq_text, unavailable_reason)` —
    exactly one is non-None.

    **Fail closed on ANY missing provenance input** (P17 对抗审 M2)：包括
    `autovig.edge_used`——它决定复现宏的渐晕/裁瞳配置，缺了它重建出的宏会
    退化成 native/no-clip、与实际跑次的 pupil 配置不同，那不是"复现"而是
    另一个配置冒充复现。宁缺毋假：缺件时不交付 `.seq`，README 写明缺哪件。
    注意 `edge_used == 0.0` 是**合法完整**的 provenance（实际跑次就是零裁
    瞳，`_autovig_profile(0, ...)` 正确产出 `None` 渐晕 = 忠实复现），与
    "缺失"严格区分。"""
    if sc.mode is not GenerationMode.TARGET_CONVERGED:
        return None, "not applicable (Mode1, zero optimization ran)"
    if target.efl_mm is None:
        return None, "target EFL missing from the batch's TargetSpec"
    seed_zmx = _resolve_seed_zmx_path(sc)
    if seed_zmx is None:
        return None, "seed ZMX not resolvable under data/zmx/"
    preferred = _mode3_preferred_config(sc.scorecard.candidate_id)
    if preferred is None:
        return None, "preferred extra_dof config not parseable from candidate_id"
    post_aut = sc.generated.optical_extras.codev_post_aut
    edge_used = post_aut.get("autovig.edge_used") if post_aut else None
    if not isinstance(edge_used, int | float) or not math.isfinite(float(edge_used)):
        return None, (
            "autovig edge_used missing from provenance — the actual run's "
            "vignetting/pupil-clip configuration cannot be reconstructed, and a "
            "macro with a guessed (native/no-clip) pupil would NOT reproduce this "
            "candidate (复现宏不可用：缺 autovig edge_used)"
        )
    vignetting = _autovig_profile(float(edge_used), _MODE3_NUM_FIELDS)
    try:
        return (
            build_codev_target_sequence(
                source_zmx=seed_zmx,
                result_path="atelier_reproduction_result.tsv",
                target_efl_mm=target.efl_mm,
                extra_dof=preferred,
                vignetting=vignetting,
                emit_optimized_zmx=True,
                optimized_readout_path="atelier_reproduction_optimized_readout.txt",
            ),
            None,
        )
    except Exception as exc:  # noqa: BLE001 - reconstruction fails closed (no .seq in the bundle), never raises into the export route
        return None, f"sequence build failed: {type(exc).__name__}"


def _bundle_readme(
    sc: ScoredCandidate,
    *,
    zmx_path,
    seq_text: str | None,
    seq_unavailable_reason: str | None,
) -> str:
    row = sc.scorecard
    gen = sc.generated
    rank_score_str = (
        fmt_float(row.rank.score) if row.rank.score is not None else "N/A"
    )
    lines = [
        "Atelier C1 candidate bundle — provenance & non-verdict notice",
        "=" * 66,
        "",
        f"candidate_id: {row.candidate_id}",
        f"mode: {row.mode.value}",
        f"source_case_id: {gen.source_case_id or '(none)'}",
        f"rank: status={row.rank.status}, score={rank_score_str}, "
        f"coverage_pct={fmt_pct(row.rank.coverage_pct, precision=0)}",
        "",
        "NOT A PRODUCTION-READINESS VERDICT: this bundle carries quantitative",
        "data only. 量产可用性判断权与 [EXPERT] 背书始终在资深设计师手里——本包",
        "不代为判定，[EXPERT] 一栏在候选集页面上保持留白。",
        "",
    ]
    if zmx_path is not None:
        lines += [
            f"candidate.zmx: included ({zmx_path.name}), delivered-payload prescription.",
        ]
    else:
        lines += [
            "candidate.zmx: NOT included — this candidate's ZMX is not resolvable on",
            "disk today. Known limitation: Mode3 (target-converged) optimized ZMX",
            "files are written to a per-job temporary directory that is cleaned up",
            "when the job finishes (app/core/orchestration/generators.py, out of",
            "scope for this fix — see that module's TargetConvergedGenerator",
            "docstring). Mode1 (retrieved) candidates always resolve here.",
        ]
    lines.append("")
    if seq_text is not None:
        lines += [
            "reproduction.seq: included — a deterministically RECONSTRUCTED CODE V",
            "macro (not the literal historical .seq, which lived in the same",
            "cleaned-up temp directory as the optimized ZMX above). Rebuilt from the",
            "candidate's full stored provenance (target EFL, preferred extra_dof",
            "config, autovig edge_used pupil-clip). Re-running it against the seed",
            "ZMX is expected to reproduce an equivalent optimization to the one that",
            "produced this candidate, not necessarily bit-identical results.",
            f"Assumes num_fields={_MODE3_NUM_FIELDS} (the current fixed Mode3",
            "constant) since the actual per-run field count isn't persisted.",
        ]
    elif row.mode is GenerationMode.TARGET_CONVERGED:
        lines += [
            "reproduction.seq: NOT included (fail closed — a macro missing part of",
            "the actual run's configuration would not be a reproduction). Reason:",
            f"  {seq_unavailable_reason or '(unknown)'}",
        ]
    else:
        lines += [
            "reproduction.seq: not applicable — this is a Mode1 (retrieved) candidate,",
            "zero optimization ran, there is nothing to reproduce.",
        ]
    lines.append("")
    return "\n".join(lines) + "\n"


def build_candidate_bundle_zip(sc: ScoredCandidate, *, target: TargetSpec) -> bytes:
    """Zip bundle (bytes) for one candidate: ZMX (when resolvable) +
    reproduction `.seq` (Mode3, when reconstructible from complete provenance)
    + README. Always returns a valid, non-empty zip — even when neither
    artifact is available, the README honestly explains why (fail closed,
    never a broken zip, never a partial artifact passing itself off as
    complete)."""
    zmx_path = _resolve_candidate_zmx_path(sc)
    seq_text, seq_unavailable_reason = _reproduction_seq_text(sc, target)
    readme = _bundle_readme(
        sc,
        zmx_path=zmx_path,
        seq_text=seq_text,
        seq_unavailable_reason=seq_unavailable_reason,
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme)
        if zmx_path is not None:
            zf.write(zmx_path, arcname="candidate.zmx")
        if seq_text is not None:
            zf.writestr("reproduction.seq", seq_text)
    return buffer.getvalue()
