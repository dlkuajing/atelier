"""FastAPI app entrypoint."""

import json
import math
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, redirect_stdout, suppress
from io import StringIO
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import FastAPI, Form, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Apply Optiland 0.6 runtime patches FIRST — before any other Optiland import
# happens. See app/core/optiland_patches.py for the bug each one addresses.
from app.core import optiland_patches as _optiland_patches  # noqa: I001

_optiland_patches.apply_all()

from app.api import optical, rag, wizard  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.demo_cache import demo_cache_request, load_demo_cache_bundle_for_request  # noqa: E402
from app.core.field_analysis import compute_field_analysis  # noqa: E402
from app.core.job_store import JobNotFoundError, JobRecord, JobStatus  # noqa: E402
from app.core.lens_system import Scenario  # noqa: E402
from app.core.optical_calc import airy_disk_diameter_um  # noqa: E402
from app.core.optical_sample import OpticalSampleData  # noqa: E402
from app.core.parameter_guards import SCENARIO_BOUNDS  # noqa: E402
from app.core.provenance import ProvenanceSource  # noqa: E402
from app.core.spot_diagram import compute_spot_diagram  # noqa: E402
from app.core.wavefront_metrics import compute_wavefront_metrics  # noqa: E402
from app.core.zmx_ingest import (  # noqa: E402
    ZMX_AMMO_DIR,
    load_normalized_zmx,
    regularize_fields_to_angle,
)


logger = structlog.get_logger(__name__)
WEB_ROOT = Path(__file__).resolve().parent / "web"
templates = Jinja2Templates(directory=WEB_ROOT / "templates")
_JOB_PROGRESS_PERCENT = {
    JobStatus.QUEUED: 10,
    JobStatus.RUNNING: 55,
    JobStatus.SUCCEEDED: 100,
    JobStatus.FAILED: 100,
}
_JOB_STATUS_MESSAGES = {
    JobStatus.QUEUED: "Waiting for the deep optical engine seat.",
    JobStatus.RUNNING: "Engine is computing the optical design package.",
    JobStatus.SUCCEEDED: "Design task completed.",
    JobStatus.FAILED: "Design task failed.",
}
ANALYSIS_PROVENANCE_BADGES = (
    {"label": "Paraxial", "source": ProvenanceSource.THIN_LENS_ANALYTIC.value},
    {"label": "MTF", "source": ProvenanceSource.OPTILAND_RAYTRACE.value},
    {"label": "Spot", "source": ProvenanceSource.OPTILAND_RAYTRACE.value},
    {"label": "Field", "source": ProvenanceSource.OPTILAND_RAYTRACE.value},
    {"label": "Wavefront", "source": ProvenanceSource.OPTILAND_WAVEFRONT.value},
)
_RESULT_ANALYSIS_WAVELENGTH_NM = 587.6
_SUMMARY_FALLBACK_WAVELENGTH_NM = 550.0


def _format_float(value: float | None) -> str:
    if value is None:
        return "Not specified"
    return f"{value:.1f}"


def _format_parameter_rows(
    extraction: wizard.ExtractScenarioResponse,
) -> tuple[dict[str, str], ...]:
    bounds = SCENARIO_BOUNDS[extraction.scenario]
    return (
        {
            "key": "focal_length_mm",
            "label": "Focal length",
            "value": f"{_format_float(extraction.focal_length_mm)} mm"
            if extraction.focal_length_mm is not None
            else "Not specified",
            "bounds": f"{bounds.efl_mm_min:.1f}-{bounds.efl_mm_max:.1f} mm",
        },
        {
            "key": "f_number",
            "label": "F-number",
            "value": f"f/{_format_float(extraction.f_number)}"
            if extraction.f_number is not None
            else "Not specified",
            "bounds": f"f/{bounds.f_number_min:.1f}-f/{bounds.f_number_max:.1f}",
        },
        {
            "key": "field_of_view_deg",
            "label": "Field of view",
            "value": f"{_format_float(extraction.field_of_view_deg)} deg"
            if extraction.field_of_view_deg is not None
            else "Not specified",
            "bounds": f"{bounds.fov_deg_min:.1f}-{bounds.fov_deg_max:.1f} deg",
        },
        {
            "key": "image_height_mm",
            "label": "Image height",
            "value": f"{_format_float(extraction.image_height_mm)} mm"
            if extraction.image_height_mm is not None
            else "Not specified",
            "bounds": (
                f"{bounds.image_height_mm_min:.1f}-{bounds.image_height_mm_max:.1f} mm"
            ),
        },
        {
            "key": "n_elements",
            "label": "Element count",
            "value": str(extraction.n_elements)
            if extraction.n_elements is not None
            else "Not specified",
            "bounds": f"{bounds.n_elements_min}-{bounds.n_elements_max}",
        },
    )


def _resolved_float(value: float | None, lo: float, hi: float) -> float:
    return float(value) if value is not None else (lo + hi) / 2.0


def _resolved_int(value: int | None, lo: int, hi: int) -> int:
    return int(value) if value is not None else round((lo + hi) / 2)


def _fallback_total_track_mm(
    *,
    focal_length_mm: float,
    image_height_mm: float,
    n_elements: int,
) -> float:
    element_stack_allowance = 0.12 * n_elements
    return max(
        focal_length_mm + 0.5,
        image_height_mm + 1.0,
        focal_length_mm + element_stack_allowance,
    )


def _diffraction_cutoff_lp_per_mm(*, wavelength_nm: float, f_number: float) -> float:
    wavelength_mm = wavelength_nm * 1e-6
    return 1.0 / (wavelength_mm * f_number)


def _summary_field(name: str, value: object) -> dict[str, str]:
    return {"name": name, "value": str(value)}


async def _summary_form_fields(
    *,
    extraction: wizard.ExtractScenarioResponse,
    requirement: str,
) -> tuple[dict[str, str], ...]:
    bounds = SCENARIO_BOUNDS[extraction.scenario]
    focal_length_mm = _resolved_float(
        extraction.focal_length_mm, bounds.efl_mm_min, bounds.efl_mm_max
    )
    f_number = _resolved_float(extraction.f_number, bounds.f_number_min, bounds.f_number_max)
    field_of_view_deg = _resolved_float(
        extraction.field_of_view_deg, bounds.fov_deg_min, bounds.fov_deg_max
    )
    image_height_mm = _resolved_float(
        extraction.image_height_mm,
        bounds.image_height_mm_min,
        bounds.image_height_mm_max,
    )
    n_elements = _resolved_int(
        extraction.n_elements,
        bounds.n_elements_min,
        bounds.n_elements_max,
    )

    wavelength_nm = _SUMMARY_FALLBACK_WAVELENGTH_NM
    total_track_mm = _fallback_total_track_mm(
        focal_length_mm=focal_length_mm,
        image_height_mm=image_height_mm,
        n_elements=n_elements,
    )
    airy_disc_diameter_um = airy_disk_diameter_um(wavelength_nm, f_number)
    cutoff_freq_lp_per_mm = _diffraction_cutoff_lp_per_mm(
        wavelength_nm=wavelength_nm,
        f_number=f_number,
    )

    sample = await _result_sample(
        scenario=extraction.scenario,
        focal_length_mm=focal_length_mm,
        f_number=f_number,
        field_of_view_deg=field_of_view_deg,
        image_height_mm=image_height_mm,
        n_elements=n_elements,
        wavelength_nm=wavelength_nm,
        total_track_mm=None,
        enrich_analysis=False,
    )
    if sample is not None:
        wavelength_nm = _RESULT_ANALYSIS_WAVELENGTH_NM
        total_track_mm = sample.paraxial.total_track_mm
        airy_disc_diameter_um = sample.mtf.airy_disc_diameter_um
        cutoff_freq_lp_per_mm = sample.mtf.cutoff_freq_lp_per_mm

    return (
        _summary_field("scenario", extraction.scenario.value),
        _summary_field("scenario_label_en", extraction.scenario.value.replace("-", " ").title()),
        _summary_field("focal_length_mm", focal_length_mm),
        _summary_field("f_number", f_number),
        _summary_field("field_of_view_deg", field_of_view_deg),
        _summary_field("image_height_mm", image_height_mm),
        _summary_field("n_elements", n_elements),
        _summary_field("wavelength_nm", wavelength_nm),
        _summary_field("total_track_mm", total_track_mm),
        _summary_field("airy_disc_diameter_um", airy_disc_diameter_um),
        _summary_field("cutoff_freq_lp_per_mm", cutoff_freq_lp_per_mm),
        _summary_field("requirement", requirement),
        _summary_field("job_id", ""),
    )


def _source_value(source: object) -> str:
    return source.value if hasattr(source, "value") else str(source)


def _finite_float_values(values: list[float]) -> list[float]:
    return [value for value in values if math.isfinite(value)]


def _metric_rows(
    *,
    sample: OpticalSampleData | None,
    focal_length_mm: float,
    f_number: float,
    field_of_view_deg: float,
    image_height_mm: float,
    total_track_mm: float,
    airy_disc_diameter_um: float,
    cutoff_freq_lp_per_mm: float,
) -> tuple[tuple[str, str], ...]:
    if sample is None:
        return (
            ("Focal length", f"{focal_length_mm:.2f} mm"),
            ("F-number", f"f/{f_number:.2f}"),
            ("Field of view", f"{field_of_view_deg:.1f} deg"),
            ("Image height", f"{image_height_mm:.2f} mm"),
            ("Total track", f"{total_track_mm:.2f} mm"),
            ("Airy diameter", f"{airy_disc_diameter_um:.2f} um"),
            ("Cutoff", f"{cutoff_freq_lp_per_mm:.0f} lp/mm"),
        )

    paraxial = sample.paraxial
    return (
        ("Focal length", f"{paraxial.effective_focal_length_mm:.2f} mm"),
        ("F-number", f"f/{paraxial.f_number:.2f}"),
        ("Surfaces", str(paraxial.n_surfaces)),
        ("Sampled rays", str(sample.trace.n_rays)),
        ("Total track", f"{paraxial.total_track_mm:.2f} mm"),
        ("Airy diameter", f"{sample.mtf.airy_disc_diameter_um:.2f} um"),
        ("Cutoff", f"{sample.mtf.cutoff_freq_lp_per_mm:.0f} lp/mm"),
    )


def _sample_case_label(sample: OpticalSampleData | None) -> str:
    if sample is None:
        return "No matched optical_sample payload"
    if sample.metadata is not None:
        return f"{sample.metadata.case_id} / {sample.metadata.source_zmx}"
    return sample.trace.assembly_name


def _analysis_card(
    *,
    artifact: str,
    title: str,
    source: object,
    summary: str,
    detail: str,
    available: bool,
    partial: bool = False,
) -> dict[str, object]:
    return {
        "artifact": artifact,
        "title": title,
        "source": _source_value(source),
        "summary": summary,
        "detail": detail,
        "available": available,
        "partial": partial,
    }


def _analysis_cards(sample: OpticalSampleData | None) -> tuple[dict[str, object], ...]:
    if sample is None:
        unavailable = "Matched optical_sample payload is unavailable for this result."
        return (
            _analysis_card(
                artifact="mtf",
                title="MTF",
                source=ProvenanceSource.OPTILAND_RAYTRACE,
                summary=unavailable,
                detail="No MTF payload was returned.",
                available=False,
            ),
            _analysis_card(
                artifact="spot-diagram",
                title="Spot diagram",
                source=ProvenanceSource.OPTILAND_RAYTRACE,
                summary=unavailable,
                detail="No spot payload was returned.",
                available=False,
            ),
            _analysis_card(
                artifact="field-analysis",
                title="Field curvature / distortion",
                source=ProvenanceSource.OPTILAND_RAYTRACE,
                summary=unavailable,
                detail="No field analysis payload was returned.",
                available=False,
            ),
            _analysis_card(
                artifact="wavefront",
                title="Wavefront",
                source=ProvenanceSource.OPTILAND_WAVEFRONT,
                summary=unavailable,
                detail="No wavefront payload was returned.",
                available=False,
            ),
        )

    rms_values = _finite_float_values(sample.mtf.rms_spot_radius_um_by_field)
    has_spot_diagram = sample.spot_diagram is not None
    spot_summary = (
        f"MTF-linked RMS spot evidence across {len(rms_values)} fields."
        if rms_values
        else "MTF payload returned no finite RMS spot values."
    )
    spot_detail = (
        f"Max RMS spot radius {max(rms_values):.2f} um."
        if rms_values
        else "No finite spot radius could be summarized."
    )
    if sample.spot_diagram is not None:
        spot_summary = (
            f"{sample.spot_diagram.field_count} fields x "
            f"{sample.spot_diagram.wavelength_count} wavelengths."
        )
        spot_detail = (
            f"{sample.spot_diagram.distribution} distribution, "
            f"{sample.spot_diagram.reference} reference."
        )

    field_summary = "Field analysis payload is not attached to this optical_sample."
    field_detail = "The result page keeps the field-curvature/distortion slot visible."
    if sample.field_analysis is not None:
        field_summary = (
            f"{len(sample.field_analysis.field_fraction)} points, "
            f"{sample.field_analysis.field_unit} field axis."
        )
        field_detail = f"{sample.field_analysis.distortion_model} distortion model."

    wavefront_summary = "Wavefront payload is not attached to this optical_sample."
    wavefront_detail = "The wavefront slot is reserved for Optiland wavefront metrics."
    if sample.wavefront is not None:
        strehl_values = [
            field.strehl_ratio
            for field in sample.wavefront.fields
            if math.isfinite(field.strehl_ratio)
        ]
        wavefront_summary = (
            f"{len(sample.wavefront.fields)} fields at "
            f"{sample.wavefront.wavelength_nm:.1f} nm."
        )
        wavefront_detail = (
            f"Minimum Strehl {min(strehl_values):.3f}."
            if strehl_values
            else "No finite Strehl value could be summarized."
        )

    return (
        _analysis_card(
            artifact="mtf",
            title="MTF",
            source=sample.mtf.provenance,
            summary=f"{len(sample.mtf.fields)} fields, {len(sample.mtf.freq_lp_per_mm)} samples.",
            detail=f"Diffraction cutoff {sample.mtf.cutoff_freq_lp_per_mm:.0f} lp/mm.",
            available=True,
        ),
        _analysis_card(
            artifact="spot-diagram",
            title="Spot diagram",
            source=(
                sample.spot_diagram.provenance
                if sample.spot_diagram is not None
                else sample.mtf.provenance
            ),
            summary=spot_summary,
            detail=spot_detail,
            available=has_spot_diagram,
            partial=not has_spot_diagram and bool(rms_values),
        ),
        _analysis_card(
            artifact="field-analysis",
            title="Field curvature / distortion",
            source=(
                sample.field_analysis.provenance
                if sample.field_analysis is not None
                else ProvenanceSource.OPTILAND_RAYTRACE
            ),
            summary=field_summary,
            detail=field_detail,
            available=sample.field_analysis is not None,
        ),
        _analysis_card(
            artifact="wavefront",
            title="Wavefront",
            source=(
                sample.wavefront.provenance
                if sample.wavefront is not None
                else ProvenanceSource.OPTILAND_WAVEFRONT
            ),
            summary=wavefront_summary,
            detail=wavefront_detail,
            available=sample.wavefront is not None,
        ),
    )


def _load_result_analysis_optic(sample: OpticalSampleData):
    if sample.metadata is None or not sample.metadata.source_zmx:
        return None

    source_path = ZMX_AMMO_DIR / sample.metadata.source_zmx
    if not source_path.exists():
        return None

    with warnings.catch_warnings(), redirect_stdout(StringIO()):
        warnings.simplefilter("ignore")
        optic = load_normalized_zmx(source_path)
        regularize_fields_to_angle(optic, sample.metadata.fov_deg)
    return optic


def _enrich_result_sample_analysis(sample: OpticalSampleData) -> OpticalSampleData:
    if (
        sample.spot_diagram is not None
        and sample.field_analysis is not None
        and sample.wavefront is not None
    ):
        return sample

    optic = None
    with suppress(Exception):
        optic = _load_result_analysis_optic(sample)
    if optic is None:
        return sample

    updates: dict[str, object] = {}
    if sample.spot_diagram is None:
        with suppress(Exception):
            updates["spot_diagram"] = compute_spot_diagram(
                optic,
                fields=[(0.0, 0.0), (0.0, 0.5)],
                wavelengths_nm=[_RESULT_ANALYSIS_WAVELENGTH_NM],
                num_rings=3,
            )
    if sample.field_analysis is None:
        with suppress(Exception):
            updates["field_analysis"] = compute_field_analysis(
                optic,
                wavelength_nm=_RESULT_ANALYSIS_WAVELENGTH_NM,
                num_points=32,
            )
    if sample.wavefront is None:
        with suppress(Exception):
            updates["wavefront"] = compute_wavefront_metrics(
                optic,
                fields=[(0.0, 0.0)],
                wavelength_nm=_RESULT_ANALYSIS_WAVELENGTH_NM,
                num_rays=6,
                num_zernike_terms=2,
            )

    return sample.model_copy(update=updates) if updates else sample


async def _result_sample(
    *,
    scenario: Scenario,
    focal_length_mm: float,
    f_number: float,
    field_of_view_deg: float,
    image_height_mm: float,
    n_elements: int | None,
    wavelength_nm: float,
    total_track_mm: float | None,
    enrich_analysis: bool = True,
) -> OpticalSampleData | None:
    try:
        sample = await optical.match(
            response=Response(),
            req=optical.OpticalSpecRequest(
                scenario=scenario,
                focal_length_mm=focal_length_mm,
                f_number=f_number,
                field_of_view_deg=field_of_view_deg,
                image_height_mm=image_height_mm,
                n_elements=n_elements,
                wavelength_nm=wavelength_nm,
                max_total_track_mm=total_track_mm,
                analysis_depth="seed_only",
            )
        )
        return _enrich_result_sample_analysis(sample) if enrich_analysis else sample
    except HTTPException:
        return None


def _job_progress_context(record: JobRecord) -> dict[str, object]:
    result = dict(record.result) if record.result is not None else None
    return {
        "product_name": "Atelier",
        "job_id": record.job_id,
        "engine": record.engine,
        "status": record.status.value,
        "status_label": record.status.value.replace("-", " ").replace("_", " ").title(),
        "status_message": _JOB_STATUS_MESSAGES[record.status],
        "progress_percent": _JOB_PROGRESS_PERCENT[record.status],
        "payload": dict(record.payload),
        "result": result,
        "has_result": result is not None,
        "result_json": json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        if result is not None
        else "",
        "error": record.error,
    }


def _result_progress_context(job_id: str | None) -> dict[str, object]:
    normalized_job_id = job_id.strip() if job_id is not None else ""
    if not normalized_job_id:
        return {
            "job_id": "inline-result",
            "status": JobStatus.SUCCEEDED.value,
            "status_label": "Succeeded",
            "status_message": _JOB_STATUS_MESSAGES[JobStatus.SUCCEEDED],
            "progress_percent": _JOB_PROGRESS_PERCENT[JobStatus.SUCCEEDED],
        }

    return _job_progress_context(optical.job_store.get(normalized_job_id))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("lumira_backend_starting", env=settings.env, version="0.1.0")
    yield
    logger.info("lumira_backend_stopping")


app = FastAPI(
    title="Lumira Atelier Backend",
    description=(
        "Optical Co-Pilot — deterministic optics (Optiland/prysm/rayoptics) + "
        "RAG (pgvector + BGE-M3 + SigLIP-2) + LLM orchestration (Opus 4.7 / GPT-5.5 / Gemini 3.1 Pro via LiteLLM)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=WEB_ROOT / "static"), name="static")

app.include_router(optical.router, prefix="/api/optical", tags=["optical"])
app.include_router(rag.router, prefix="/api/rag", tags=["rag"])
app.include_router(wizard.router, prefix="/api/wizard", tags=["wizard"])


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.get("/", response_class=HTMLResponse, tags=["web"])
async def root(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "product_name": "Atelier",
            "nav_items": (
                ("Workbench", "#request"),
                ("Library", "#library"),
                ("Analysis", "#analysis"),
                ("API", "/docs"),
            ),
            "analysis_provenance_badges": ANALYSIS_PROVENANCE_BADGES,
        },
    )


@app.post("/wizard/confirm", response_class=HTMLResponse, tags=["web"])
async def wizard_confirm(
    request: Request,
    requirement: Annotated[str, Form(min_length=3, max_length=2000)],
) -> HTMLResponse:
    extraction = await wizard.extract_scenario(
        wizard.ExtractScenarioRequest(user_input=requirement)
    )
    summary_form_fields = await _summary_form_fields(
        extraction=extraction,
        requirement=requirement,
    )
    return templates.TemplateResponse(
        request,
        "wizard_confirm.html",
        {
            "product_name": "Atelier",
            "requirement": requirement,
            "scenario": extraction.scenario.value,
            "scenario_label": extraction.scenario.value.replace("-", " ").title(),
            "reasoning": extraction.reasoning,
            "parameters": _format_parameter_rows(extraction),
            "summary_form_fields": summary_form_fields,
            "analysis_provenance_badges": ANALYSIS_PROVENANCE_BADGES,
        },
    )


@app.post("/wizard", response_class=HTMLResponse, include_in_schema=False)
async def wizard_confirm_alias(
    request: Request,
    requirement: Annotated[str, Form(min_length=3, max_length=2000)],
) -> HTMLResponse:
    return await wizard_confirm(request, requirement)


@app.post("/results/summary", response_class=HTMLResponse, tags=["web"])
@app.post("/wizard/summary", response_class=HTMLResponse, include_in_schema=False)
async def result_summary(
    request: Request,
    scenario: Annotated[Scenario, Form()],
    scenario_label_en: Annotated[str, Form(min_length=1, max_length=100)],
    focal_length_mm: Annotated[float, Form(gt=0)],
    f_number: Annotated[float, Form(gt=0)],
    field_of_view_deg: Annotated[float, Form(gt=0, le=180)],
    image_height_mm: Annotated[float, Form(gt=0)],
    total_track_mm: Annotated[float, Form(gt=0)],
    airy_disc_diameter_um: Annotated[float, Form(gt=0)],
    cutoff_freq_lp_per_mm: Annotated[float, Form(gt=0)],
    n_elements: Annotated[int | None, Form(ge=2, le=20)] = None,
    wavelength_nm: Annotated[float, Form(gt=0)] = 550.0,
    requirement: Annotated[str | None, Form(max_length=2000)] = None,
    job_id: Annotated[str | None, Form(max_length=100)] = None,
) -> HTMLResponse:
    try:
        progress = _result_progress_context(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job_not_found", "job_id": job_id},
        ) from exc

    cache_request = demo_cache_request(
        scenario=scenario,
        focal_length_mm=focal_length_mm,
        f_number=f_number,
        field_of_view_deg=field_of_view_deg,
        image_height_mm=image_height_mm,
        n_elements=n_elements,
        wavelength_nm=wavelength_nm,
    )
    cached = load_demo_cache_bundle_for_request(cache_request)
    demo_cache_status = "miss"
    design_assessment = None
    if cached is not None:
        demo_cache_status = "hit"
        sample = cached.sample
        focal_length_mm = sample.paraxial.effective_focal_length_mm
        f_number = sample.paraxial.f_number
        total_track_mm = sample.paraxial.total_track_mm
        airy_disc_diameter_um = sample.mtf.airy_disc_diameter_um
        cutoff_freq_lp_per_mm = sample.mtf.cutoff_freq_lp_per_mm
        if sample.metadata is not None:
            scenario_label_en = sample.metadata.scenario.value.replace("-", " ").title()
            n_elements = sample.metadata.n_pieces
        design_assessment = sample.design_assessment
    else:
        sample = await _result_sample(
            scenario=scenario,
            focal_length_mm=focal_length_mm,
            f_number=f_number,
            field_of_view_deg=field_of_view_deg,
            image_height_mm=image_height_mm,
            n_elements=n_elements,
            wavelength_nm=wavelength_nm,
            total_track_mm=total_track_mm,
        )
        if sample is not None:
            design_assessment = sample.design_assessment
    summary = await wizard.generate_executive_summary(
        wizard.ExecutiveSummaryRequest(
            scenario=scenario,
            scenario_label_en=scenario_label_en,
            focal_length_mm=focal_length_mm,
            f_number=f_number,
            field_of_view_deg=field_of_view_deg,
            image_height_mm=image_height_mm,
            n_elements=n_elements,
            wavelength_nm=wavelength_nm,
            total_track_mm=total_track_mm,
            airy_disc_diameter_um=airy_disc_diameter_um,
            cutoff_freq_lp_per_mm=cutoff_freq_lp_per_mm,
            design_assessment=design_assessment,
        )
    )
    return templates.TemplateResponse(
        request,
        "result_summary.html",
        {
            "product_name": "Atelier",
            "scenario_label": scenario_label_en,
            "scenario": scenario.value,
            "demo_cache_status": demo_cache_status,
            "requirement": requirement,
            "summary": summary,
            "target_metrics": (
                ("Focal length", f"{focal_length_mm:.2f} mm"),
                ("F-number", f"f/{f_number:.2f}"),
                ("Field of view", f"{field_of_view_deg:.1f} deg"),
                ("Image height", f"{image_height_mm:.2f} mm"),
                ("Elements", str(n_elements) if n_elements is not None else "Not specified"),
            ),
            "metrics": _metric_rows(
                sample=sample,
                focal_length_mm=focal_length_mm,
                f_number=f_number,
                field_of_view_deg=field_of_view_deg,
                image_height_mm=image_height_mm,
                total_track_mm=total_track_mm,
                airy_disc_diameter_um=airy_disc_diameter_um,
                cutoff_freq_lp_per_mm=cutoff_freq_lp_per_mm,
            ),
            "sample_case_label": _sample_case_label(sample),
            "analysis_cards": _analysis_cards(sample),
            "analysis_provenance_badges": ANALYSIS_PROVENANCE_BADGES,
            "layout_svg": sample.layout_svg.svg_content if sample is not None else "",
            "has_layout_svg": sample is not None,
            "progress": progress,
        },
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse, tags=["web"])
async def job_progress(request: Request, job_id: str) -> HTMLResponse:
    try:
        record = optical.job_store.get(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job_not_found", "job_id": job_id},
        ) from exc
    return templates.TemplateResponse(request, "job_progress.html", _job_progress_context(record))
