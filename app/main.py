"""FastAPI app entrypoint."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import FastAPI, Form, HTTPException, Request, status
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
from app.core.job_store import JobNotFoundError, JobRecord, JobStatus  # noqa: E402
from app.core.lens_system import Scenario  # noqa: E402
from app.core.parameter_guards import SCENARIO_BOUNDS  # noqa: E402
from app.core.provenance import ProvenanceSource  # noqa: E402


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
    n_elements: Annotated[int | None, Form(ge=2, le=30)] = None,
    wavelength_nm: Annotated[float, Form(gt=0)] = 550.0,
) -> HTMLResponse:
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
            "summary": summary,
            "metrics": (
                ("Focal length", f"{focal_length_mm:.2f} mm"),
                ("F-number", f"f/{f_number:.2f}"),
                ("Field of view", f"{field_of_view_deg:.1f} deg"),
                ("Image height", f"{image_height_mm:.2f} mm"),
                ("Total track", f"{total_track_mm:.2f} mm"),
                ("Airy diameter", f"{airy_disc_diameter_um:.2f} um"),
                ("Cutoff", f"{cutoff_freq_lp_per_mm:.0f} lp/mm"),
            ),
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
