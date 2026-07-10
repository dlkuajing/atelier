"""Tests for `app.core.orchestration.export` — P17 sub-item 2 spec-sheet
export (xlsx workbook + per-candidate ZMX/.seq bundle zip).

Covers: workbook has the two expected sheets with values sourced from the
same `CandidateSet` the page renders (no verdict wording anywhere); the zip
bundle resolves a real ZMX for a retrieved (Mode1) candidate and fails
closed with an honest README when the payload's ZMX isn't on disk (the
known Mode3 temp-directory gap); the Mode3 reproduction `.seq` reconstructs
when provenance is complete and fails closed otherwise.
"""

from __future__ import annotations

import io
import zipfile

import openpyxl

from app.core.case_library import load_case_library
from app.core.optical_sample import OpticalSampleData
from app.core.orchestration.candidate import (
    CandidateSet,
    CandidateSetSummary,
    GeneratedCandidate,
    GenerationMode,
    ImageQualityMetrics,
    ManufacturabilityProxy,
    MetricValue,
    OpticalExtras,
    RankResult,
    ScorecardRow,
    ScoredCandidate,
    TargetDeviation,
    TargetSpec,
)
from app.core.orchestration.export import (
    build_candidate_bundle_zip,
    build_candidate_set_workbook,
)
from app.core.zmx_ingest import ZMX_AMMO_DIR

# ---------------------------------------------------------------------------
# Fixtures / helpers (mirrors tests/test_orchestration_candidate.py)
# ---------------------------------------------------------------------------


def _first_case_with_metadata() -> OpticalSampleData:
    for case in load_case_library():
        if case.metadata is not None:
            return case
    raise AssertionError("case library has no case with metadata")


_CASE = _first_case_with_metadata()


def _metric(value: float | None = None) -> MetricValue:
    if value is None:
        return MetricValue(value=None, status="unavailable")
    return MetricValue(value=value, status="available")


def _image_quality() -> ImageQualityMetrics:
    return ImageQualityMetrics(
        mtf_sag=_metric(0.62),
        mtf_tan=_metric(0.58),
        diffraction_cutoff_lp_per_mm=_metric(810.0),
        rms_spot_radius_max_um=_metric(3.1),
        rms_spot_radius_mean_um=_metric(1.9),
        min_strehl_ratio=_metric(0.71),
        rms_wavefront_error_waves=_metric(0.08),
        field_curvature_tangential_delta_mm=_metric(0.03),
        field_curvature_sagittal_delta_mm=_metric(-0.02),
        max_distortion_pct=_metric(1.4),
        relative_illumination=_metric(),
    )


def _manufacturability() -> ManufacturabilityProxy:
    return ManufacturabilityProxy(
        total_track_mm=_CASE.paraxial.total_track_mm,
        n_pieces=5,
        has_special_glass=False,
        aspheric_term_count=_metric(),
        aspheric_surface_count=_metric(),
        chief_ray_angle_deg=_metric(28.4),
    )


def _deviations(mode: GenerationMode) -> list[TargetDeviation]:
    conv = {"efl"} if mode is GenerationMode.TARGET_CONVERGED else set()
    rows = [
        ("efl", "exact", 3.8, 3.79, 0.01, 0.01 / 3.8),
        ("fov", "exact", 78.0, 76.5, 1.5, 1.5 / 78.0),
        ("fnum", "exact", 1.9, 1.95, 0.05, 0.05 / 1.9),
        ("imh", "exact", 3.2, 3.18, 0.02, 0.02 / 3.2),
    ]
    deviations = [
        TargetDeviation(
            field=field,
            constraint_kind=kind,
            target=target,
            achieved=achieved,
            violation=violation,
            rel_violation=rel,
            converged_toward_target=field in conv,
        )
        for field, kind, target, achieved, violation, rel in rows
    ]
    deviations.append(
        TargetDeviation(
            field="ttl",
            constraint_kind="unconstrained",
            target=None,
            achieved=_CASE.paraxial.total_track_mm,
            violation=0.0,
            rel_violation=None,
            converged_toward_target=False,
        )
    )
    return deviations


def _ranked_result() -> RankResult:
    return RankResult(score=0.812, status="ranked", coverage_pct=1.0, missing_metrics=[])


def _target_spec() -> TargetSpec:
    assert _CASE.metadata is not None
    return TargetSpec(
        scenario=_CASE.metadata.scenario,
        efl_mm=3.8,
        fov_deg=78.0,
        fnum=1.9,
        image_height_mm=3.2,
        n_elements=6,
    )


def _retrieved_candidate() -> ScoredCandidate:
    """A real Mode1 candidate whose payload IS a real case — its
    `metadata.source_zmx` genuinely exists under `ZMX_AMMO_DIR` (Mode1 never
    touches a temp directory), so this is representative of production, not
    a shortcut."""
    assert _CASE.metadata is not None
    candidate_id = f"{_CASE.metadata.case_id}::best_match"
    generated = GeneratedCandidate(
        candidate_id=candidate_id,
        mode=GenerationMode.RETRIEVED,
        source_case_id=_CASE.metadata.case_id,
        payload=_CASE,
        optical_extras=OpticalExtras(ri_by_field={"0.0": _metric(0.9)}),
        generation_notes=["检索最近邻 seed，未朝 target 优化", "role=best_match"],
    )
    scorecard = ScorecardRow(
        candidate_id=candidate_id,
        mode=GenerationMode.RETRIEVED,
        target_deviations=_deviations(GenerationMode.RETRIEVED),
        image_quality=_image_quality(),
        manufacturability=_manufacturability(),
        rank=_ranked_result(),
        rank_explanation="coverage_pct=100%, ranked by weighted score",
    )
    return ScoredCandidate(generated=generated, scorecard=scorecard)


def _target_converged_candidate(*, optimized_zmx_resolvable: bool = False) -> ScoredCandidate:
    """A Mode3 candidate. By default its payload's `source_zmx` points at a
    filename that does NOT exist under `ZMX_AMMO_DIR` — representative of
    the real pipeline (the optimized ZMX lived in a per-job temp directory
    that's already been cleaned up by the time an export request arrives).
    `optimized_zmx_resolvable=True` exercises the (currently unreachable in
    production, but forward-compatible) path where the file does resolve."""
    assert _CASE.metadata is not None
    candidate_id = f"{_CASE.metadata.case_id}::target-converged-both"
    payload = _CASE if optimized_zmx_resolvable else _CASE.model_copy(
        update={
            "metadata": _CASE.metadata.model_copy(
                update={"source_zmx": "atelier-c1-mode3-tmp-optimized-both.zmx"}
            )
        }
    )
    codev_post_aut = {
        "post_aut.efl_y_mm": 3.79,
        "autovig.edge_used": 0.4,
        "aut_converged": "1",
    }
    generated = GeneratedCandidate(
        candidate_id=candidate_id,
        mode=GenerationMode.TARGET_CONVERGED,
        source_case_id=_CASE.metadata.case_id,
        payload=payload,
        optical_extras=OpticalExtras(ri_by_field=None, codev_post_aut=codev_post_aut),
        generation_notes=["Mode3：③ target 优化标准入口"],
    )
    scorecard = ScorecardRow(
        candidate_id=candidate_id,
        mode=GenerationMode.TARGET_CONVERGED,
        target_deviations=_deviations(GenerationMode.TARGET_CONVERGED),
        image_quality=_image_quality(),
        manufacturability=_manufacturability(),
        rank=_ranked_result(),
        rank_explanation="coverage_pct=100%, ranked by weighted score",
    )
    return ScoredCandidate(generated=generated, scorecard=scorecard)


def _candidate_set(*candidates: ScoredCandidate) -> CandidateSet:
    mode_counts: dict[GenerationMode, int] = {}
    for sc in candidates:
        mode_counts[sc.mode] = mode_counts.get(sc.mode, 0) + 1
    summary = CandidateSetSummary(
        candidate_count=len(candidates),
        mode_counts=mode_counts,
        ranked_count=len(candidates),
        withheld_count=0,
        ri_missing_count=sum(
            1
            for sc in candidates
            if sc.scorecard.image_quality.relative_illumination.status == "unavailable"
        ),
        notes=["fixture: export test batch"],
    )
    return CandidateSet(target=_target_spec(), candidates=list(candidates), summary=summary)


# ---------------------------------------------------------------------------
# ① xlsx workbook
# ---------------------------------------------------------------------------


def test_workbook_has_summary_and_candidates_sheets_with_same_source_values():
    candidate_set = _candidate_set(_retrieved_candidate(), _target_converged_candidate())
    workbook_bytes = build_candidate_set_workbook(
        candidate_set, job_id="job-abc123", requirement="wide phone camera"
    )
    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes))

    assert wb.sheetnames == ["Summary", "Candidates"]

    summary_rows = [tuple(row) for row in wb["Summary"].iter_rows(values_only=True)]
    summary_text = "\n".join(str(v) for row in summary_rows for v in row if v is not None)
    assert "job-abc123" in summary_text
    assert "wide phone camera" in summary_text
    assert candidate_set.honesty_banner is None  # both modes present -> no banner in this fixture
    assert "3.8" in summary_text  # target EFL echoed

    candidates_rows = list(wb["Candidates"].iter_rows(values_only=True))
    header = candidates_rows[0]
    assert "candidate_id" in header
    assert "rank_score" in header
    body = candidates_rows[1:]
    assert len(body) == 2
    candidate_id_idx = header.index("candidate_id")
    rank_score_idx = header.index("rank_score")
    ids = {row[candidate_id_idx] for row in body}
    assert ids == {sc.scorecard.candidate_id for sc in candidate_set.candidates}
    # P17 对抗审 M3：xlsx 单元格 = 页面同一格式化器产出的同一字符串
    # （页面 rank 行显示 "score=0.812"），不再是原始 float。
    for row in body:
        assert row[rank_score_idx] == "0.812"

    # P17 sub-item 3: repeatability columns present, honest default state
    # (these fixtures never supply repeat samples -> unavailable/run_count=1,
    # same as the page's own default rendering).
    rc_idx = header.index("repeatability_run_count")
    rs_idx = header.index("repeatability_status")
    for row in body:
        assert row[rc_idx] == 1
        assert row[rs_idx] == "unavailable"


def test_workbook_nonzero_tiny_value_never_renders_as_zero():
    """P17 对抗审 M3 假零钉死（xlsx 侧）：`0 < RI < 0.0005` 曾以原始 float
    进 xlsx、页面显示 "0.000"——统一格式化器后，两侧都必须显示 "<0.001"，
    绝不显示假零。"""
    sc = _retrieved_candidate()
    tiny_ri = MetricValue(value=0.0004, status="available")
    sc = sc.model_copy(
        update={
            "scorecard": sc.scorecard.model_copy(
                update={
                    "image_quality": sc.scorecard.image_quality.model_copy(
                        update={"relative_illumination": tiny_ri}
                    )
                }
            )
        }
    )
    candidate_set = _candidate_set(sc)
    workbook_bytes = build_candidate_set_workbook(candidate_set, job_id="job-tz", requirement=None)
    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes))
    rows = list(wb["Candidates"].iter_rows(values_only=True))
    header, body = rows[0], rows[1]
    ri_idx = header.index("Relative illumination (worst field)")
    assert body[ri_idx] == "<0.001"
    assert body[ri_idx] != "0.000"


def test_workbook_never_contains_pass_fail_verdict_wording():
    candidate_set = _candidate_set(_retrieved_candidate(), _target_converged_candidate())
    workbook_bytes = build_candidate_set_workbook(candidate_set, job_id="job-1", requirement=None)
    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes))

    all_text = "\n".join(
        str(cell)
        for ws in wb.worksheets
        for row in ws.iter_rows(values_only=True)
        for cell in row
        if cell is not None
    )
    assert "合格" not in all_text
    assert "良品" not in all_text
    assert "pass" not in all_text.lower()
    assert "fail" not in all_text.lower()


def test_workbook_summary_sheet_echoes_honesty_banner_when_present():
    candidate_set = _candidate_set(_retrieved_candidate())  # Mode1-only -> banner set
    assert candidate_set.honesty_banner is not None
    workbook_bytes = build_candidate_set_workbook(candidate_set, job_id="job-2", requirement=None)
    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes))
    summary_text = "\n".join(
        str(v)
        for row in wb["Summary"].iter_rows(values_only=True)
        for v in row
        if v is not None
    )
    assert candidate_set.honesty_banner in summary_text


def test_workbook_handles_zero_candidates():
    empty_set = _candidate_set()
    workbook_bytes = build_candidate_set_workbook(empty_set, job_id="job-empty", requirement=None)
    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes))
    candidates_rows = list(wb["Candidates"].iter_rows(values_only=True))
    assert len(candidates_rows) == 1  # header only


# ---------------------------------------------------------------------------
# ② per-candidate ZMX + reproduction .seq + README bundle
# ---------------------------------------------------------------------------


def test_bundle_zip_includes_real_zmx_for_retrieved_candidate():
    sc = _retrieved_candidate()
    zip_bytes = build_candidate_bundle_zip(sc, target=_target_spec())

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "candidate.zmx" in names
        assert "README.txt" in names
        assert "reproduction.seq" not in names  # Mode1: nothing to reproduce

        assert _CASE.metadata is not None
        real_bytes = (ZMX_AMMO_DIR / _CASE.metadata.source_zmx).read_bytes()
        assert zf.read("candidate.zmx") == real_bytes

        readme = zf.read("README.txt").decode("utf-8")
    assert "candidate.zmx: included" in readme
    assert "not applicable" in readme  # .seq n/a for Mode1
    assert "合格" not in readme
    assert "良品" not in readme
    assert "pass" not in readme.lower()
    assert "fail" not in readme.lower()


def test_bundle_zip_omits_zmx_and_explains_when_not_persisted():
    """The known Mode3 limitation: the optimized ZMX lived in a per-job temp
    directory already cleaned up by export time — the bundle must fail
    closed (no candidate.zmx entry) with an honest README, never a broken or
    silently-missing artifact."""
    sc = _target_converged_candidate(optimized_zmx_resolvable=False)
    zip_bytes = build_candidate_bundle_zip(sc, target=_target_spec())

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "candidate.zmx" not in names
        assert "README.txt" in names
        readme = zf.read("README.txt").decode("utf-8")
    assert "NOT included" in readme
    assert "temporary directory" in readme


def test_bundle_zip_includes_zmx_once_mode3_artifact_is_persisted():
    """Forward-compatibility check: if a candidate's payload does resolve to
    a real file under ZMX_AMMO_DIR (e.g. once the generators.py-side
    persistence gap is closed), the same mode-agnostic resolution path picks
    it up with no code change needed."""
    sc = _target_converged_candidate(optimized_zmx_resolvable=True)
    zip_bytes = build_candidate_bundle_zip(sc, target=_target_spec())

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert "candidate.zmx" in zf.namelist()


def test_bundle_zip_reconstructs_mode3_reproduction_seq_when_provenance_complete():
    sc = _target_converged_candidate()
    target = _target_spec()
    zip_bytes = build_candidate_bundle_zip(sc, target=target)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "reproduction.seq" in names
        seq_text = zf.read("reproduction.seq").decode("ascii")
        readme = zf.read("README.txt").decode("utf-8")

    assert seq_text.strip()  # non-empty macro text
    assert f"{target.efl_mm}" in seq_text or f"{target.efl_mm:.6f}" in seq_text
    assert "reproduction.seq: included" in readme


def test_bundle_zip_seq_fails_closed_without_edge_used():
    """P17 对抗审 M2：`autovig.edge_used` 缺失 → 实际跑次的渐晕/裁瞳配置
    不可重建，用 native/no-clip 猜测重建出的宏不是"复现"——必须 fail closed
    不交付 .seq，README 写明缺的就是 edge_used。（本测试从此前"缺 edge 仍
    交付"的旧行为翻转为钉住修复。）"""
    sc = _target_converged_candidate()
    sc = sc.model_copy(
        update={
            "generated": sc.generated.model_copy(
                update={
                    "optical_extras": OpticalExtras(
                        ri_by_field=None, codev_post_aut={"post_aut.efl_y_mm": 3.79}
                    )
                }
            )
        }
    )
    zip_bytes = build_candidate_bundle_zip(sc, target=_target_spec())
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert "reproduction.seq" not in zf.namelist()
        readme = zf.read("README.txt").decode("utf-8")
    assert "NOT included" in readme
    assert "autovig edge_used missing" in readme
    assert "复现宏不可用" in readme


def test_bundle_zip_seq_fails_closed_when_edge_used_nonfinite():
    """NaN/inf edge_used 同属"不可重建"（fail closed），不是可用的裁瞳量。"""
    sc = _target_converged_candidate()
    sc = sc.model_copy(
        update={
            "generated": sc.generated.model_copy(
                update={
                    "optical_extras": OpticalExtras(
                        ri_by_field=None,
                        codev_post_aut={"autovig.edge_used": float("nan")},
                    )
                }
            )
        }
    )
    zip_bytes = build_candidate_bundle_zip(sc, target=_target_spec())
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert "reproduction.seq" not in zf.namelist()


def test_bundle_zip_seq_included_when_edge_used_is_zero():
    """`edge_used == 0.0` 是合法完整 provenance（实际跑次零裁瞳），必须与
    "缺失"严格区分——照常交付 .seq（`_autovig_profile(0)` → 无渐晕 = 忠实
    复现该跑次）。"""
    sc = _target_converged_candidate()
    sc = sc.model_copy(
        update={
            "generated": sc.generated.model_copy(
                update={
                    "optical_extras": OpticalExtras(
                        ri_by_field=None,
                        codev_post_aut={"autovig.edge_used": 0.0},
                    )
                }
            )
        }
    )
    zip_bytes = build_candidate_bundle_zip(sc, target=_target_spec())
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert "reproduction.seq" in zf.namelist()
        readme = zf.read("README.txt").decode("utf-8")
    assert "reproduction.seq: included" in readme


def test_bundle_zip_seq_omitted_when_seed_zmx_unresolvable():
    sc = _target_converged_candidate()
    sc = sc.model_copy(
        update={
            "generated": sc.generated.model_copy(update={"source_case_id": "no-such-seed-case"})
        }
    )
    zip_bytes = build_candidate_bundle_zip(sc, target=_target_spec())
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "reproduction.seq" not in names
        readme = zf.read("README.txt").decode("utf-8")
    assert "NOT included" in readme
    assert "seed ZMX not resolvable" in readme  # concrete missing-provenance reason (M2)


def test_bundle_zip_seq_not_applicable_for_retrieved_candidate():
    sc = _retrieved_candidate()
    zip_bytes = build_candidate_bundle_zip(sc, target=_target_spec())
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert "reproduction.seq" not in zf.namelist()
