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
  `num_fields=3` 是 generators.py `_candidate_for_seed` 当前硬编码值（未来若
  可配，需要 codev_post_aut 补一个字段才能精确复现，见 module docstring 尾注）。
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.core.engines.codev_optimize import _autovig_profile, build_codev_target_sequence
from app.core.orchestration.candidate import (
    CandidateSet,
    GenerationMode,
    ManufacturabilityProxy,
    MetricValue,
    ScoredCandidate,
    TargetDeviation,
    TargetSpec,
)
from app.core.zmx_ingest import ZMX_AMMO_DIR

_NON_PASS_FAIL_BANNER = (
    "本表仅量化数据，不代为判定——量产可用性判断权与 [EXPERT] 背书"
    "始终在资深设计师手里（AGENTS.md 北极星条款）。"
)

# Fixed Mode3 constant this module's .seq reconstruction relies on — mirrors
# `generators.py::TargetConvergedGenerator._candidate_for_seed`'s hardcoded
# `run_codev_target_standard(..., num_fields=3)` call. If that call site ever
# starts varying `num_fields` per seed, a real field count needs to be added
# to `OpticalExtras.codev_post_aut` before this constant can be retired.
_MODE3_NUM_FIELDS = 3


def _metric_cell(metric: MetricValue) -> float | str:
    return metric.value if metric.status == "available" and metric.value is not None else "N/A"


def _optional_cell(value: float | int | None) -> float | int | str:
    return "(unconstrained)" if value is None else value


# ---------------------------------------------------------------------------
# ① xlsx workbook
# ---------------------------------------------------------------------------

_TARGET_ROWS: tuple[tuple[str, str], ...] = (
    ("Scenario", "scenario"),
    ("EFL (mm)", "efl_mm"),
    ("FOV (deg)", "fov_deg"),
    ("F-number", "fnum"),
    ("Image height (mm)", "image_height_mm"),
    ("Max total track (mm)", "max_total_track_mm"),
    ("Element count", "n_elements"),
)

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


def _write_summary_sheet(
    ws: Worksheet, candidate_set: CandidateSet, *, job_id: str, requirement: str | None
) -> None:
    ws.title = "Summary"
    ws.append(["Atelier C1 candidate set — spec sheet export"])
    ws.append(["Generated (UTC)", datetime.now(UTC).isoformat(timespec="seconds")])
    ws.append(["Job ID", job_id])
    ws.append(["Requirement", requirement or "(none)"])
    ws.append([])
    if candidate_set.honesty_banner:
        ws.append(["Honesty notice", candidate_set.honesty_banner])
        ws.append([])
    ws.append(["Target spec"])
    target = candidate_set.target
    for label, attr in _TARGET_ROWS:
        value = target.scenario.value if attr == "scenario" else getattr(target, attr)
        ws.append([label, _optional_cell(value)])
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
    return [
        mfg.total_track_mm,
        mfg.n_pieces,
        "Yes" if mfg.has_special_glass else "No",
        _metric_cell(mfg.aspheric_term_count),
        _metric_cell(mfg.aspheric_surface_count),
        _metric_cell(mfg.chief_ray_angle_deg),
    ]


def _write_candidates_sheet(ws: Worksheet, candidate_set: CandidateSet) -> None:
    ws.title = "Candidates"
    header = ["candidate_id", "mode", "source_case_id", "rank_status", "rank_score", "coverage_pct", "missing_metrics"]
    for field in _DEVIATION_FIELDS:
        header += [f"{field}_target", f"{field}_achieved", f"{field}_rel_violation", f"{field}_converged"]
    header += [label for label, _ in _IMAGE_QUALITY_COLUMNS]
    header += ["ttl_mm", "n_pieces", "has_special_glass", "aspheric_term_count", "aspheric_surface_count", "chief_ray_angle_deg"]
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
            row.rank.score if row.rank.score is not None else "N/A",
            row.rank.coverage_pct,
            ", ".join(row.rank.missing_metrics) or "(none)",
        ]
        for field in _DEVIATION_FIELDS:
            dev = by_field.get(field)
            if dev is None:
                line += ["(n/a)", "(n/a)", "(n/a)", "(n/a)"]
            else:
                line += [
                    _optional_cell(dev.target),
                    dev.achieved,
                    dev.rel_violation if dev.rel_violation is not None else "N/A",
                    "Yes" if dev.converged_toward_target else "No",
                ]
        for _, attr in _IMAGE_QUALITY_COLUMNS:
            line.append(_metric_cell(getattr(row.image_quality, attr)))
        line += _manufacturability_row(row.manufacturability)
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


def _reproduction_seq_text(sc: ScoredCandidate, target: TargetSpec) -> str | None:
    """Best-effort deterministic reconstruction of a CODE V macro that would
    reproduce (not byte-for-byte replay — a fresh, equivalent recipe) this
    Mode3 candidate's optimization. `None` (fail closed) whenever any input
    it needs isn't available — never fabricates a partial/misleading macro.
    See module docstring for the exact provenance chain."""
    if sc.mode is not GenerationMode.TARGET_CONVERGED:
        return None
    if target.efl_mm is None:
        return None
    seed_zmx = _resolve_seed_zmx_path(sc)
    if seed_zmx is None:
        return None
    preferred = _mode3_preferred_config(sc.scorecard.candidate_id)
    if preferred is None:
        return None
    post_aut = sc.generated.optical_extras.codev_post_aut
    edge_used = post_aut.get("autovig.edge_used") if post_aut else None
    vignetting = None
    if isinstance(edge_used, int | float):
        vignetting = _autovig_profile(float(edge_used), _MODE3_NUM_FIELDS)
    try:
        return build_codev_target_sequence(
            source_zmx=seed_zmx,
            result_path="atelier_reproduction_result.tsv",
            target_efl_mm=target.efl_mm,
            extra_dof=preferred,
            vignetting=vignetting,
            emit_optimized_zmx=True,
            optimized_readout_path="atelier_reproduction_optimized_readout.txt",
        )
    except Exception:  # noqa: BLE001 - reconstruction is best-effort; any failure fails closed (no .seq in the bundle), never raises into the export route
        return None


def _bundle_readme(
    sc: ScoredCandidate,
    *,
    zmx_path,
    seq_text: str | None,
) -> str:
    row = sc.scorecard
    gen = sc.generated
    lines = [
        "Atelier C1 candidate bundle — provenance & non-verdict notice",
        "=" * 66,
        "",
        f"candidate_id: {row.candidate_id}",
        f"mode: {row.mode.value}",
        f"source_case_id: {gen.source_case_id or '(none)'}",
        f"rank: status={row.rank.status}, score={row.rank.score}, "
        f"coverage_pct={row.rank.coverage_pct:.0%}",
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
            "cleaned-up temp directory as the optimized ZMX above). Re-running it",
            "against the seed ZMX is expected to reproduce an equivalent optimization",
            "to the one that produced this candidate, not necessarily bit-identical",
            f"results. Assumes num_fields={_MODE3_NUM_FIELDS} (the current fixed",
            "Mode3 constant) since the actual per-run field count isn't persisted.",
        ]
    elif row.mode is GenerationMode.TARGET_CONVERGED:
        lines += [
            "reproduction.seq: NOT included — this Mode3 candidate is missing one of",
            "the provenance fields the reconstruction needs (target EFL, preferred",
            "config, autovig edge_used, or the seed's own ZMX under data/zmx/).",
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
    reproduction `.seq` (Mode3, when reconstructible) + README. Always
    returns a valid, non-empty zip — even when neither artifact is available,
    the README honestly explains why (fail closed, never a broken zip)."""
    zmx_path = _resolve_candidate_zmx_path(sc)
    seq_text = _reproduction_seq_text(sc, target)
    readme = _bundle_readme(sc, zmx_path=zmx_path, seq_text=seq_text)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme)
        if zmx_path is not None:
            zf.write(zmx_path, arcname="candidate.zmx")
        if seq_text is not None:
            zf.writestr("reproduction.seq", seq_text)
    return buffer.getvalue()
