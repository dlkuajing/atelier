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

Mode3 优化 ZMX 由 generator 持久化并通过 `optimized_zmx_path` 解析；复制失败
仍 fail-closed 不导出。Stage B 复现 `.seq` 只从 closed FNO-ladder evidence
重建 accepted_final 的实际配置（target EFL/F-number、stage、extra_dof、
num_fields、effective_edge_used）。证据缺失、未达标或与批 target 不一致时不
导出 `.seq`；绝不退回旧 post-AUT 裸字典或猜 native/no-clip 配置。
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.core.case_library import load_case_library
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

_FNUM_EVIDENCE_COLUMNS: tuple[str, ...] = (
    "fnum_ladder_target_achieved",
    "fnum_accepted_measured_fnum",
    "fnum_accepted_effective_edge_used",
    "fnum_accepted_ray_grid",
    "fnum_accepted_quality_note",
)

_STAGEC_EVIDENCE_COLUMNS: tuple[str, ...] = (
    "stagec_machine_execution_status",
    "stagec_reconstruction_status",
    "stagec_imh_source",
    "stagec_imh_achieved",
    "stagec_fov_source",
    "stagec_fov_deg",
    "stagec_real_chief_ray_status",
    "stagec_rsi_status",
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
    header += list(_FNUM_EVIDENCE_COLUMNS)
    header += list(_STAGEC_EVIDENCE_COLUMNS)
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
        evidence = gen.fnum_ladder_evidence
        accepted = evidence.accepted_final if evidence is not None else None
        line += [
            evidence.target_achieved if evidence is not None else None,
            fmt_float(accepted.measured_fnum) if accepted is not None else "N/A",
            fmt_float(accepted.effective_edge_used) if accepted is not None else "N/A",
            json.dumps(
                accepted.ray_grid.model_dump(), ensure_ascii=False, sort_keys=True
            )
            if accepted is not None
            else "N/A",
            accepted.quality_note if accepted is not None else "N/A",
        ]
        stagec = gen.stagec_field_evidence
        line += [
            stagec.machine_execution_status if stagec is not None else "N/A",
            stagec.reconstruction_status if stagec is not None else "N/A",
            stagec.imh_source if stagec is not None else "N/A",
            stagec.image_height_achieved if stagec is not None else None,
            stagec.fov_source if stagec is not None else "N/A",
            (
                fmt_float(
                    stagec.measured_full_fov_deg
                    if stagec.measured_full_fov_deg is not None
                    else stagec.derived_full_fov_deg
                )
                if stagec is not None
                and (
                    stagec.measured_full_fov_deg is not None
                    or stagec.derived_full_fov_deg is not None
                )
                else "N/A"
            ),
            stagec.real_chief_ray_status if stagec is not None else "N/A",
            stagec.rsi_status if stagec is not None else "N/A",
        ]
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
    reconstruction = sc.generated.stagec_field_reconstruction
    if reconstruction is not None:
        evidence = sc.generated.stagec_field_evidence
        if reconstruction.status != "constructed" or reconstruction.output_path is None:
            return None
        if evidence is None or evidence.image_height_achieved or (
            evidence.target_image_height_mm != reconstruction.target_image_height_mm
            or evidence.nominal_image_height_mm != reconstruction.target_image_height_mm
        ):
            return None
        if reconstruction.num_fields is None or (
            len(reconstruction.normalized_fractions) != reconstruction.num_fields
            or not reconstruction.normalized_fractions
            or not math.isclose(
                max(abs(value) for value in reconstruction.normalized_fractions),
                1.0,
                rel_tol=0.0,
                abs_tol=1e-15,
            )
        ):
            return None
        source = Path(reconstruction.source_path)
        if not source.is_file() or (
            hashlib.sha256(source.read_bytes()).hexdigest()
            != reconstruction.source_sha256_before
        ):
            return None
        path = Path(reconstruction.output_path)
        if not path.is_file() or reconstruction.output_sha256 is None:
            return None
        if hashlib.sha256(path.read_bytes()).hexdigest() != reconstruction.output_sha256:
            return None
        optimized_path = sc.generated.optimized_zmx_path
        if optimized_path is None or Path(optimized_path).resolve() != path.resolve():
            return None
        metadata = sc.generated.payload.metadata
        if metadata is None or metadata.image_height_mm != reconstruction.target_image_height_mm:
            return None
        expected_fov = 2 * math.degrees(
            math.atan(
                reconstruction.target_image_height_mm
                / sc.generated.payload.paraxial.effective_focal_length_mm
            )
        )
        if evidence.derived_full_fov_deg is None or not math.isclose(
            evidence.derived_full_fov_deg, expected_fov, rel_tol=1e-12, abs_tol=1e-12
        ) or not math.isclose(metadata.fov_deg, expected_fov, rel_tol=1e-12, abs_tol=1e-12):
            return None
        return path
    optimized_path = sc.generated.optimized_zmx_path
    if optimized_path:
        path = Path(optimized_path)
        return path if path.is_file() else None
    metadata = sc.generated.payload.metadata
    if metadata is None or not metadata.source_zmx:
        return None
    path = ZMX_AMMO_DIR / metadata.source_zmx
    return path if path.is_file() else None


def _candidate_zmx_unavailable_reason(sc: ScoredCandidate) -> str:
    if sc.generated.stagec_field_reconstruction is not None:
        return (
            "Stage C source/output hash, target/profile, or candidate payload path is missing "
            "or inconsistent; candidate.zmx withheld"
        )
    return (
        "this candidate's ZMX is not resolvable on disk; persistence failure is recorded "
        "and export fails closed"
    )


def _resolve_seed_zmx_path(sc: ScoredCandidate):
    """Resolve the *original seed's* ZMX (not the Mode3 optimized result) —
    used as the reproduction `.seq`'s `source_zmx` input.

    **Exact-case contract（CI 红修根因，2026-07-11）**：不得从 `case_id` 合成
    文件名（旧实现 `f"{case_id}.zmx"` 硬编码小写扩展名——`data/zmx/` 实际是
    混合大小写：5 颗 `.ZMX` / 437 颗 `.zmx`。Windows 文件系统大小写不敏感把
    这个 bug 完全掩蔽，Ubuntu CI 大小写敏感立即 miss）。唯一可靠的精确文件
    名是 seed case 自己的 `metadata.source_zmx`（全库 442/442 与磁盘逐字符
    一致，本地审计核验）——按 `source_case_id` 回查 case library 取它。
    `load_case_library` 是 LRU 缓存，线性扫一遍是内存操作。"""
    case_id = sc.generated.source_case_id
    if not case_id:
        return None
    for case in load_case_library():
        if case.metadata is not None and case.metadata.case_id == case_id:
            path = ZMX_AMMO_DIR / case.metadata.source_zmx
            return path if path.is_file() else None
    return None  # seed not in the library -> fail closed, never guess a filename


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
    if sc.generated.stagec_field_reconstruction is not None:
        reconstruction = sc.generated.stagec_field_reconstruction
        if reconstruction.status != "constructed":
            return None, "Stage C field reconstruction is not complete"
        # The existing sequence builder does not encode FTYP3/YFLN, and the
        # CODE V ANG->IMG/RSI syntax is intentionally not guessed.  Shipping a
        # Stage-B-only macro for a Stage-C candidate would be false replay.
        return None, (
            "Stage C CODE V field syntax and real chief-ray/RSI replay are pending machine "
            "verification; Stage-B-only sequence withheld"
        )
    evidence = sc.generated.fnum_ladder_evidence
    if evidence is None:
        return None, "validated Stage B FNO-ladder evidence missing"
    if not evidence.target_achieved or evidence.accepted_final is None:
        return None, "Stage B FNO ladder did not produce an accepted_final rung"
    if target.efl_mm is None:
        return None, "target EFL missing from the batch's TargetSpec"
    if not math.isclose(target.efl_mm, evidence.target_efl_mm, rel_tol=1e-12):
        return None, "batch target EFL does not match the accepted ladder recipe"
    if not math.isclose(target.fnum, evidence.fnum_target, rel_tol=1e-12):
        return None, "batch target F-number does not match the accepted ladder recipe"
    seed_zmx = _resolve_seed_zmx_path(sc)
    if seed_zmx is None:
        return None, "seed ZMX not resolvable under data/zmx/"
    accepted = evidence.accepted_final
    if not math.isfinite(accepted.effective_edge_used):
        return None, "accepted effective_edge_used is non-finite"
    vignetting = _autovig_profile(accepted.effective_edge_used, evidence.num_fields)
    try:
        return (
            build_codev_target_sequence(
                source_zmx=seed_zmx,
                result_path="atelier_reproduction_result.tsv",
                target_efl_mm=evidence.target_efl_mm,
                target_f_number=evidence.fnum_target,
                stage=evidence.stage,
                extra_dof=evidence.extra_dof,
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
    evidence = gen.fnum_ladder_evidence
    stagec = gen.stagec_field_evidence
    accepted = evidence.accepted_final if evidence is not None else None
    lines += [
        f"fnum_ladder.target_achieved: {evidence.target_achieved if evidence else 'unavailable'}",
        f"accepted_final.measured_fnum: {fmt_float(accepted.measured_fnum) if accepted else 'N/A'}",
        "accepted_final.effective_edge_used: "
        f"{fmt_float(accepted.effective_edge_used) if accepted else 'N/A'}",
        "accepted_final.ray_grid: "
        + (
            json.dumps(
                accepted.ray_grid.model_dump(), ensure_ascii=False, sort_keys=True
            )
            if accepted
            else "N/A"
        ),
        f"accepted_final.quality_note: {accepted.quality_note if accepted else 'N/A'}",
        "",
    ]
    if stagec is not None:
        lines += [
            "stagec.field_evidence: "
            + json.dumps(stagec.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            "stagec.FOV: derived/measured only; never optimized/converged",
            "stagec.[EXPERT]: no production-readiness verdict is supplied",
            "",
        ]
    if zmx_path is not None:
        lines += [
            f"candidate.zmx: included ({zmx_path.name}), delivered-payload prescription.",
        ]
    else:
        lines += [
            "candidate.zmx: NOT included — " + _candidate_zmx_unavailable_reason(sc),
        ]
    lines.append("")
    if seq_text is not None:
        lines += [
            "reproduction.seq: included — a deterministically RECONSTRUCTED CODE V",
            "macro (not the literal historical .seq). Rebuilt from the",
            "candidate's validated Stage B ladder evidence (target EFL/F-number,",
            "stage, extra_dof, and accepted effective_edge_used pupil-clip). Re-running it against the seed",
            "ZMX is expected to reproduce an equivalent optimization to the one that",
            "produced this candidate, not necessarily bit-identical results.",
            f"Uses persisted num_fields={evidence.num_fields if evidence else 'N/A'};",
            "the accepted ray-retry/autovig pupil configuration is not guessed.",
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
