"""Web contract for the C1 candidate orchestration path (`/candidates`).

Covers: `/candidates` submission (303 -> job progress -> success), the
`candidate_set.html` render (honesty banner presence/absence, mode badges,
5-dim deviation rows, withheld reasons, the blank [EXPERT] grid), the
wrong-engine 404 guard, and the wizard_confirm second submit button. No CODE V,
no LLM: `orchestrate` is monkeypatched to a small hand-built `CandidateSet`
fixture (mirrors the fixture-building conventions in
`test_orchestration_candidate.py`), and the wizard extraction mock mirrors
`test_web_wizard_flow.py` / `test_demo_e2e.py`.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api import optical
from app.core.aberration import MTFResult
from app.core.case_library import load_case_library
from app.core.job_store import JobStore
from app.core.lens_system import LayoutSVG
from app.core.orchestration import (
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
from app.main import _target_spec_from_candidate_payload, app

# ---------------------------------------------------------------------------
# Fixtures / helpers (mirrors tests/test_orchestration_candidate.py)
# ---------------------------------------------------------------------------


def _first_case_with_metadata():
    for case in load_case_library():
        if case.metadata is not None:
            return case
    raise AssertionError("case library has no case with metadata")


_CASE = _first_case_with_metadata()


def _metric(value: float | None = None) -> MetricValue:
    if value is None:
        return MetricValue(value=None, status="unavailable")
    return MetricValue(value=value, status="available")


def _image_quality(*, ri_available: bool = True) -> ImageQualityMetrics:
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
        relative_illumination=_metric(0.82) if ri_available else _metric(),
    )


def _manufacturability(*, has_special_glass: bool = False) -> ManufacturabilityProxy:
    return ManufacturabilityProxy(
        total_track_mm=_CASE.paraxial.total_track_mm,
        n_pieces=5,
        has_special_glass=has_special_glass,
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
    # ttl left unconstrained (wizard flow has no customer TTL ceiling) —
    # exercises the "(unconstrained)" render path for `target`/`rel_violation`.
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


def _generated_candidate(
    *,
    mode: GenerationMode,
    candidate_id: str,
    generation_notes: list[str],
    codev_post_aut: dict[str, object] | None = None,
    ri_available: bool = True,
) -> GeneratedCandidate:
    assert _CASE.metadata is not None
    return GeneratedCandidate(
        candidate_id=candidate_id,
        mode=mode,
        source_case_id=_CASE.metadata.case_id,
        payload=_CASE,
        optical_extras=OpticalExtras(
            ri_by_field={"0.0": _metric(0.9)} if ri_available else None,
            codev_post_aut=codev_post_aut,
        ),
        generation_notes=generation_notes,
    )


def _ranked_result() -> RankResult:
    return RankResult(score=0.812, status="ranked", coverage_pct=1.0, missing_metrics=[])


def _withheld_result() -> RankResult:
    return RankResult(
        score=None,
        status="withheld",
        coverage_pct=0.6,
        missing_metrics=["rms_wavefront_error_waves", "min_strehl_ratio"],
    )


_RETRIEVED_ID = "3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56::best_match"
_TARGET_CONVERGED_ID = "3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56::target-converged-both"


def _retrieved_candidate() -> ScoredCandidate:
    generated = _generated_candidate(
        mode=GenerationMode.RETRIEVED,
        candidate_id=_RETRIEVED_ID,
        generation_notes=["检索最近邻 seed，未朝 target 优化", "role=best_match"],
    )
    scorecard = ScorecardRow(
        candidate_id=_RETRIEVED_ID,
        mode=GenerationMode.RETRIEVED,
        target_deviations=_deviations(GenerationMode.RETRIEVED),
        image_quality=_image_quality(),
        manufacturability=_manufacturability(),
        rank=_ranked_result(),
        rank_explanation="coverage_pct=100%，全部必需维可用，按 5 维加权得分排序",
    )
    return ScoredCandidate(generated=generated, scorecard=scorecard)


def _target_converged_candidate() -> ScoredCandidate:
    codev_post_aut = {
        "post_aut.efl_y_mm": 3.79,
        "post_aut.max_rms_spot_diameter_um": 4.1,
        "post_aut.max_rms_wavefront_error_waves": 0.09,
        "post_aut.max_distortion_pct": 1.6,
        "post_aut.fno": 1.95,
        "post_aut.maximh_mm": 3.18,
        "efl_target_deviation_pct": 0.26,
        "aut_converged": "yes",
        "autovig.edge_used": 0.92,
        "err_f_ratio": 0.08,
        "aut_termination": "normal",
    }
    generated = _generated_candidate(
        mode=GenerationMode.TARGET_CONVERGED,
        candidate_id=_TARGET_CONVERGED_ID,
        generation_notes=[
            "Mode3：③ target 优化标准入口，seed=3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56",
            "preferred 配置=\"both\"（both config produced lower spot RMS）",
            "玻璃 provenance（preferred=\"both\"）：fictitious-within-plastic-GLA(default)",
            "CONVERGED_FIELDS[TARGET_CONVERGED] 已缩窄为 {efl}：F# 现状锁 native、"
            "IMH/FOV Stage C 场重建未落地——本候选 5 维 target-deviation 中只有 efl "
            "标 converged=True，其余如实标 False",
        ],
        codev_post_aut=codev_post_aut,
        ri_available=False,
    )
    scorecard = ScorecardRow(
        candidate_id=_TARGET_CONVERGED_ID,
        mode=GenerationMode.TARGET_CONVERGED,
        target_deviations=_deviations(GenerationMode.TARGET_CONVERGED),
        image_quality=_image_quality(ri_available=False),
        manufacturability=_manufacturability(has_special_glass=True),
        rank=_withheld_result(),
        rank_explanation="coverage_pct=60%，低于最低覆盖率阈值 80%，本候选打分 withheld，不参与排序",
    )
    return ScoredCandidate(generated=generated, scorecard=scorecard)


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


def _full_candidate_set() -> CandidateSet:
    candidates = [_retrieved_candidate(), _target_converged_candidate()]
    summary = CandidateSetSummary(
        candidate_count=2,
        mode_counts={GenerationMode.RETRIEVED: 1, GenerationMode.TARGET_CONVERGED: 1},
        ranked_count=1,
        withheld_count=1,
        ri_missing_count=1,
        notes=["fixture: 编排批次，仅用于 web 渲染契约测试"],
    )
    return CandidateSet(target=_target_spec(), candidates=candidates, summary=summary)


def _retrieval_only_candidate_set() -> CandidateSet:
    candidates = [_retrieved_candidate()]
    summary = CandidateSetSummary(
        candidate_count=1,
        mode_counts={GenerationMode.RETRIEVED: 1},
        ranked_count=1,
        withheld_count=0,
        ri_missing_count=0,
        notes=[],
    )
    return CandidateSet(target=_target_spec(), candidates=candidates, summary=summary)


def _fake_orchestrate(result: CandidateSet):
    def _orchestrate(spec, target, *, n=4, **kwargs):  # noqa: ANN001, ARG001
        return result

    return _orchestrate


def _candidate_form_payload() -> dict[str, object]:
    return {
        "scenario": "smartphone-wide",
        "scenario_label_en": "Smartphone Wide",
        "focal_length_mm": 3.8,
        "f_number": 1.9,
        "field_of_view_deg": 78.0,
        "image_height_mm": 3.2,
        "n_elements": 6,
        "wavelength_nm": 550.0,
        "total_track_mm": 4.35,
        "airy_disc_diameter_um": 2.6,
        "cutoff_freq_lp_per_mm": 810.0,
        "requirement": "Design a compact wide phone camera; produce a candidate set.",
    }


def _candidate_card_html(html: str, candidate_id: str) -> str:
    match = re.search(
        rf'<article\b(?=[^>]*data-candidate-id="{re.escape(candidate_id)}")[^>]*>.*?</article>',
        html,
        re.S,
    )
    assert match is not None, candidate_id
    return match.group(0)


def _expert_grid_html(html: str) -> str:
    match = re.search(
        r'<section\b(?=[^>]*data-expert-grid)[^>]*>.*?</section>',
        html,
        re.S,
    )
    assert match is not None
    return match.group(0)


# ---------------------------------------------------------------------------
# Spec-field mapping (§B) — direct unit coverage of the honest gaps
# ---------------------------------------------------------------------------


def test_target_spec_from_candidate_payload_maps_wizard_fields_and_leaves_gaps_none():
    payload = {
        "scenario": "smartphone-wide",
        "focal_length_mm": 3.8,
        "field_of_view_deg": 78.0,
        "f_number": 1.9,
        "image_height_mm": 3.2,
        "n_elements": 6,
    }
    target = _target_spec_from_candidate_payload(payload)
    assert target.scenario.value == "smartphone-wide"
    assert target.efl_mm == 3.8
    assert target.fov_deg == 78.0
    assert target.fnum == 1.9
    assert target.image_height_mm == 3.2
    assert target.n_elements == 6
    # Honest gaps: the wizard flow never supplies these, so they must stay None
    # rather than being backfilled from a derived estimate.
    assert target.max_total_track_mm is None
    assert target.max_weight_g is None
    assert target.manufacturing_tier is None
    assert target.priority is None


# ---------------------------------------------------------------------------
# Full submit -> progress -> render round trip (mixed modes, no banner)
# ---------------------------------------------------------------------------


def test_candidate_set_full_batch_round_trip(monkeypatch):
    monkeypatch.setattr(
        "app.core.orchestration.orchestrate", _fake_orchestrate(_full_candidate_set())
    )
    store = JobStore()
    monkeypatch.setattr(optical, "job_store", store)

    with TestClient(app) as client:
        submitted = client.post(
            "/candidates", data=_candidate_form_payload(), follow_redirects=False
        )
        assert submitted.status_code == 303, submitted.text
        location = submitted.headers["location"]
        assert location.startswith("/jobs/")
        job_id = location.rsplit("/", 1)[1]

        progress = client.get(location)
        assert progress.status_code == 200, progress.text
        assert f'data-job-id="{job_id}"' in progress.text
        assert f'data-result-url="/candidates/{job_id}"' in progress.text

        with client.stream("GET", f"/api/optical/jobs/{job_id}/events") as streamed:
            assert streamed.status_code == 200
            sse_body = "".join(streamed.iter_text())
        assert "event: succeeded" in sse_body

        result = client.get(f"/candidates/{job_id}")

    assert result.status_code == 200, result.text
    html = result.text

    assert "data-candidate-set-page" in html
    assert 'data-scenario="smartphone-wide"' in html
    # Both modes present -> no honesty banner (Mode3 candidate exists).
    assert "data-honesty-banner" not in html

    # Mode badges for both modes present in the batch summary.
    assert 'data-mode="retrieved"' in html
    assert 'data-mode="target-converged"' in html
    assert "Retrieved (Mode1)" in html
    assert "Target-converged (Mode3)" in html

    # Batch summary counts.
    assert "2 candidates" in html
    assert "<dd data-batch-ranked-count>1</dd>" in html
    assert "<dd data-batch-withheld-count>1</dd>" in html

    retrieved_card = _candidate_card_html(html, _RETRIEVED_ID)
    assert 'data-rank-status="ranked"' in retrieved_card
    assert "status=ranked, score=0.812" in retrieved_card
    # RETRIEVED converges nothing — every deviation row must say "No".
    assert 'data-deviation-field="efl" data-converged="false"' in retrieved_card

    # Per-candidate layout SVG: same .layout-svg-frame + optiland-raytrace
    # provenance badge pattern as the result page.
    layout_match = re.search(
        r'<section\b(?=[^>]*data-candidate-layout)[^>]*>.*?</section>', retrieved_card, re.S
    )
    assert layout_match is not None
    layout_block = layout_match.group(0)
    assert 'data-available="true"' in layout_block
    assert 'data-provenance="optiland-raytrace"' in layout_block
    assert "layout-svg-frame" in layout_block
    assert "<svg" in layout_block
    assert "data-layout-empty" not in layout_block

    # Per-candidate MTF visual: labeled, honest axes (full 0-1 scale, real
    # frequency range) + provenance badge from payload.mtf.provenance.
    mtf_match = re.search(
        r'<figure\b(?=[^>]*data-candidate-mtf)[^>]*>.*?</figure>', retrieved_card, re.S
    )
    assert mtf_match is not None
    mtf_block = mtf_match.group(0)
    assert 'data-available="true"' in mtf_block
    assert 'data-provenance="optiland-raytrace"' in mtf_block
    assert "mtf-curve-line" in mtf_block
    assert "lp/mm" in mtf_block  # frequency axis stays labeled
    assert "full 0-1 modulation scale" in mtf_block  # honest y-scale copy
    assert "diffraction cutoff" in mtf_block
    assert "data-mtf-empty" not in mtf_block

    converged_card = _candidate_card_html(html, _TARGET_CONVERGED_ID)
    assert 'data-rank-status="withheld"' in converged_card
    assert "status=withheld" in converged_card
    assert "missing_metrics=rms_wavefront_error_waves, min_strehl_ratio" in converged_card
    # Only efl is allowed to show converged=True for Mode3 (CONVERGED_FIELDS honesty).
    assert 'data-deviation-field="efl" data-converged="true"' in converged_card
    assert 'data-deviation-field="fov" data-converged="false"' in converged_card
    assert 'data-deviation-field="fnum" data-converged="false"' in converged_card
    assert 'data-deviation-field="imh" data-converged="false"' in converged_card
    assert 'data-deviation-field="ttl" data-converged="false"' in converged_card
    assert "(unconstrained)" in converged_card  # ttl target echo

    # CODE V post-AUT provenance-only sub-block, with the caveat copied verbatim.
    assert "data-codev-provenance" in converged_card
    assert "裁瞳口径快照，不可与满口径直接横比" in converged_card
    assert "post_aut.efl_y_mm" not in converged_card  # rendered as a label, not a raw key
    assert "post_aut EFL_y (mm)" in converged_card

    # Fictitious-glass provenance, verbatim from generation_notes.
    assert "fictitious-within-plastic-GLA(default)" in converged_card

    # N/A values are muted (value-na hook) so real numbers stand out; the
    # converged fixture's RI is unavailable -> its N/A cell carries the class.
    assert "value-na" in converged_card

    # [EXPERT] grid is present, mentions both candidate ids, and every data cell is empty.
    expert_grid = _expert_grid_html(html)
    assert _RETRIEVED_ID in expert_grid
    assert _TARGET_CONVERGED_ID in expert_grid
    for cell_match in re.finditer(r'<td class="expert-cell"[^>]*>(.*?)</td>', expert_grid, re.S):
        assert cell_match.group(1).strip() == ""

    # Honest copy: no invented pass/fail verdict wording attached to any
    # *candidate* (the [EXPERT] section's own title/intro — "良品率判定
    # （[EXPERT] 留白 — AI 不代判）" — is copied verbatim from the ratified
    # offline report's own header and legitimately names the topic being left
    # blank; it is not a verdict on a candidate, so it is excluded from this
    # scope on purpose).
    for scoped_html in (retrieved_card, converged_card):
        assert "合格" not in scoped_html
        assert "良品" not in scoped_html
        assert "pass" not in scoped_html.lower()
        assert "fail" not in scoped_html.lower()
    # The [EXPERT] grid's actual data cells (already asserted empty above)
    # carry no verdict wording either — only its heading names the topic.
    assert "合格" not in expert_grid
    assert "pass" not in expert_grid.lower()
    assert "fail" not in expert_grid.lower()


# ---------------------------------------------------------------------------
# Retrieval-only batch -> honesty banner surfaces verbatim
# ---------------------------------------------------------------------------


def test_candidate_set_retrieval_only_shows_honesty_banner(monkeypatch):
    monkeypatch.setattr(
        "app.core.orchestration.orchestrate",
        _fake_orchestrate(_retrieval_only_candidate_set()),
    )
    store = JobStore()
    monkeypatch.setattr(optical, "job_store", store)

    with TestClient(app) as client:
        submitted = client.post(
            "/candidates", data=_candidate_form_payload(), follow_redirects=False
        )
        job_id = submitted.headers["location"].rsplit("/", 1)[1]

        with client.stream("GET", f"/api/optical/jobs/{job_id}/events") as streamed:
            "".join(streamed.iter_text())

        result = client.get(f"/candidates/{job_id}")

    assert result.status_code == 200, result.text
    html = result.text
    assert "data-honesty-banner" in html
    assert "本批候选均未朝客户 target 收敛（③/Mode3 未接）" in html
    assert 'data-mode="target-converged"' not in html


# ---------------------------------------------------------------------------
# Degraded visuals -> honest empty states (no fabricated charts)
# ---------------------------------------------------------------------------


def _degraded_visuals_candidate_set() -> CandidateSet:
    """Retrieval-only batch whose single candidate carries an empty layout SVG
    and an MTF payload with no plottable data — both visuals must fall back to
    honest empty-state copy, never a fabricated or blank-but-available chart."""
    degraded_payload = _CASE.model_copy(
        update={
            "layout_svg": LayoutSVG(width_px=100, height_px=50, svg_content="  "),
            "mtf": MTFResult(
                freq_lp_per_mm=[],
                fields=[],
                diff_limited=[],
                cutoff_freq_lp_per_mm=810.0,
                airy_disc_diameter_um=2.6,
                rms_spot_radius_um_by_field=[],
            ),
        }
    )
    assert _CASE.metadata is not None
    generated = GeneratedCandidate(
        candidate_id=_RETRIEVED_ID,
        mode=GenerationMode.RETRIEVED,
        source_case_id=_CASE.metadata.case_id,
        payload=degraded_payload,
        optical_extras=OpticalExtras(),
        generation_notes=["检索最近邻 seed，未朝 target 优化", "role=best_match"],
    )
    scorecard = ScorecardRow(
        candidate_id=_RETRIEVED_ID,
        mode=GenerationMode.RETRIEVED,
        target_deviations=_deviations(GenerationMode.RETRIEVED),
        image_quality=_image_quality(),
        manufacturability=_manufacturability(),
        rank=_ranked_result(),
        rank_explanation="degraded-visuals fixture",
    )
    candidate = ScoredCandidate(generated=generated, scorecard=scorecard)
    summary = CandidateSetSummary(
        candidate_count=1,
        mode_counts={GenerationMode.RETRIEVED: 1},
        ranked_count=1,
        withheld_count=0,
        ri_missing_count=1,
        notes=[],
    )
    return CandidateSet(target=_target_spec(), candidates=[candidate], summary=summary)


def test_candidate_card_degraded_visuals_show_honest_empty_states(monkeypatch):
    monkeypatch.setattr(
        "app.core.orchestration.orchestrate",
        _fake_orchestrate(_degraded_visuals_candidate_set()),
    )
    store = JobStore()
    monkeypatch.setattr(optical, "job_store", store)

    with TestClient(app) as client:
        submitted = client.post(
            "/candidates", data=_candidate_form_payload(), follow_redirects=False
        )
        job_id = submitted.headers["location"].rsplit("/", 1)[1]

        with client.stream("GET", f"/api/optical/jobs/{job_id}/events") as streamed:
            "".join(streamed.iter_text())

        result = client.get(f"/candidates/{job_id}")

    assert result.status_code == 200, result.text
    card = _candidate_card_html(result.text, _RETRIEVED_ID)

    layout_match = re.search(
        r'<section\b(?=[^>]*data-candidate-layout)[^>]*>.*?</section>', card, re.S
    )
    assert layout_match is not None
    layout_block = layout_match.group(0)
    assert 'data-available="false"' in layout_block
    assert "data-layout-empty" in layout_block
    assert "No SVG payload was returned for this candidate." in layout_block
    assert "layout-svg-frame" not in layout_block

    mtf_match = re.search(r'<figure\b(?=[^>]*data-candidate-mtf)[^>]*>.*?</figure>', card, re.S)
    assert mtf_match is not None
    mtf_block = mtf_match.group(0)
    assert 'data-available="false"' in mtf_block
    assert "data-mtf-empty" in mtf_block
    assert "No plottable MTF payload was returned for this candidate." in mtf_block
    assert "mtf-curve-line" not in mtf_block


# ---------------------------------------------------------------------------
# Provenance badge differentiation: estimate dot must not reuse the solid
# real-raytrace default
# ---------------------------------------------------------------------------


def test_site_css_gives_optiland_estimate_a_distinct_badge_dot():
    with TestClient(app) as client:
        response = client.get("/static/site.css")
    assert response.status_code == 200
    css = response.text
    assert '.source-badge[data-provenance="optiland-estimate"]::before' in css
    estimate_rule = css.split('.source-badge[data-provenance="optiland-estimate"]::before', 1)[1]
    estimate_rule = estimate_rule.split("}", 1)[0]
    # Hollow/outlined treatment: transparent fill + visible outline.
    assert "background: transparent" in estimate_rule
    assert "border:" in estimate_rule


# ---------------------------------------------------------------------------
# Wrong-engine job id -> 404 (mirrors /results/{job_id}'s own guard)
# ---------------------------------------------------------------------------


def test_candidate_set_rejects_job_from_other_engine(monkeypatch):
    store = JobStore()
    monkeypatch.setattr(optical, "job_store", store)

    with TestClient(app) as client:
        submitted = client.post(
            "/jobs",
            data={
                "scenario": "smartphone-wide",
                "scenario_label_en": "Smartphone Wide",
                "focal_length_mm": 3.8,
                "f_number": 1.9,
                "field_of_view_deg": 78.0,
                "image_height_mm": 3.2,
                "n_elements": 6,
                "wavelength_nm": 550.0,
                "total_track_mm": 4.35,
                "airy_disc_diameter_um": 2.6,
                "cutoff_freq_lp_per_mm": 810.0,
                "requirement": "Not a candidate-set job.",
            },
            follow_redirects=False,
        )
        assert submitted.status_code == 303, submitted.text
        other_job_id = submitted.headers["location"].rsplit("/", 1)[1]

        # `_is_candidate_orchestration_job` checks `payload.get("job_type")`,
        # which is set synchronously at submit() time — no need to wait for
        # the background computation to finish.
        response = client.get(f"/candidates/{other_job_id}")
        assert response.status_code == 404, response.text

        # Drain the background job so no task is left pending when the
        # TestClient's event loop shuts down.
        with client.stream("GET", f"/api/optical/jobs/{other_job_id}/events") as streamed:
            "".join(streamed.iter_text())


def test_candidate_set_unknown_job_id_404():
    store = JobStore()
    with TestClient(app) as client, patch.object(optical, "job_store", store):
        response = client.get("/candidates/does-not-exist")
    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# P17 sub-item 1: adjust & rerun — candidate-set page reruns through the same
# `/candidates` job mechanism, pre-filled with the batch's own target, gated
# by parameter_guards.
# ---------------------------------------------------------------------------


def test_candidate_set_page_renders_adjust_form_prefilled(monkeypatch):
    monkeypatch.setattr(
        "app.core.orchestration.orchestrate", _fake_orchestrate(_retrieval_only_candidate_set())
    )
    store = JobStore()
    monkeypatch.setattr(optical, "job_store", store)

    with TestClient(app) as client:
        submitted = client.post(
            "/candidates", data=_candidate_form_payload(), follow_redirects=False
        )
        job_id = submitted.headers["location"].rsplit("/", 1)[1]
        with client.stream("GET", f"/api/optical/jobs/{job_id}/events") as streamed:
            "".join(streamed.iter_text())
        result = client.get(f"/candidates/{job_id}")

    assert result.status_code == 200, result.text
    html = result.text
    assert "data-adjust-rerun-form" in html
    assert 'action="/candidates"' in html
    # Pre-filled from the batch's own TargetSpec (not wizard defaults).
    assert 'data-adjust-field="efl_mm" value="3.8"' in html
    assert 'data-adjust-field="fnum" value="1.9"' in html
    assert 'data-adjust-field="fov_deg" value="78.0"' in html
    assert 'data-adjust-field="image_height_mm" value="3.2"' in html
    assert 'data-adjust-field="n_elements" value="6"' in html
    # TTL is never supplied by the wizard flow -> honestly blank, not "None".
    assert 'data-adjust-field="max_total_track_mm" value=""' in html


def test_candidate_set_adjust_rerun_submits_new_job_through_same_route(monkeypatch):
    calls: list[dict[str, object]] = []

    def _recording_orchestrate(spec, target, *, n=4, **kwargs):  # noqa: ANN001, ARG001
        calls.append({"efl_mm": target.efl_mm, "max_total_track_mm": target.max_total_track_mm})
        return _retrieval_only_candidate_set()

    monkeypatch.setattr("app.core.orchestration.orchestrate", _recording_orchestrate)
    store = JobStore()
    monkeypatch.setattr(optical, "job_store", store)

    with TestClient(app) as client:
        # Mirrors the adjust form's field set exactly — no wizard-only
        # total_track_mm/airy_disc/cutoff fields, plus a real TTL ceiling.
        submitted = client.post(
            "/candidates",
            data={
                "scenario": "smartphone-wide",
                "scenario_label_en": "Smartphone Wide",
                "focal_length_mm": 4.1,
                "f_number": 2.0,
                "field_of_view_deg": 80.0,
                "image_height_mm": 3.4,
                "n_elements": 6,
                "max_total_track_mm": 4.6,
                "requirement": "",
            },
            follow_redirects=False,
        )
        assert submitted.status_code == 303, submitted.text
        job_id = submitted.headers["location"].rsplit("/", 1)[1]
        with client.stream("GET", f"/api/optical/jobs/{job_id}/events") as streamed:
            "".join(streamed.iter_text())
        result = client.get(f"/candidates/{job_id}")

    assert result.status_code == 200, result.text
    assert calls == [{"efl_mm": 4.1, "max_total_track_mm": 4.6}]


def test_candidate_submit_rejects_out_of_bounds_target_with_violations():
    with TestClient(app) as client:
        response = client.post(
            "/candidates",
            data={
                "scenario": "smartphone-wide",
                "scenario_label_en": "Smartphone Wide",
                "focal_length_mm": 20.0,  # smartphone-wide EFL bound is [2.4, 5.2]mm
                "f_number": 1.9,
                "field_of_view_deg": 78.0,
                "image_height_mm": 3.2,
                "n_elements": 6,
            },
            follow_redirects=False,
        )
    assert response.status_code == 400, response.text
    html = response.text
    assert "data-error-page" in html
    assert "EFL 20.0mm out of" in html


def test_candidate_submit_accepts_omitted_wizard_only_fields(monkeypatch):
    """The adjust-and-rerun form never sends total_track_mm/airy_disc/cutoff
    (wizard-only derived estimates `/candidates` never reads) — the route
    must not 422 on their absence."""
    monkeypatch.setattr(
        "app.core.orchestration.orchestrate", _fake_orchestrate(_retrieval_only_candidate_set())
    )
    store = JobStore()
    monkeypatch.setattr(optical, "job_store", store)

    with TestClient(app) as client:
        response = client.post(
            "/candidates",
            data={
                "scenario": "smartphone-wide",
                "scenario_label_en": "Smartphone Wide",
                "focal_length_mm": 3.8,
                "f_number": 1.9,
                "field_of_view_deg": 78.0,
                "image_height_mm": 3.2,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        job_id = response.headers["location"].rsplit("/", 1)[1]
        with client.stream("GET", f"/api/optical/jobs/{job_id}/events") as streamed:
            "".join(streamed.iter_text())


# ---------------------------------------------------------------------------
# wizard_confirm second submit button (§C)
# ---------------------------------------------------------------------------


def _mock_chat_response(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


@patch("app.api.wizard.get_async_client")
def test_wizard_confirm_has_candidate_submit_button(mock_get_client):
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "scenario": "smartphone-wide",
              "focal_length_mm": 3.8,
              "f_number": 1.9,
              "field_of_view_deg": 78.0,
              "image_height_mm": 3.2,
              "n_elements": 6,
              "reasoning": "Phone wide request."
            }
            """
        )
    )
    mock_get_client.return_value = mock_client

    with TestClient(app) as client:
        response = client.post(
            "/wizard/confirm",
            data={"requirement": "Design a compact wide phone camera."},
        )

    assert response.status_code == 200, response.text
    html = response.text
    assert 'formaction="/candidates"' in html
    assert "data-candidate-submit" in html
    assert "生成候选集（检索+优化双模，后台深度计算）" in html
    # The instant-result button stays the primary/default action.
    assert 'action="/jobs"' in html
