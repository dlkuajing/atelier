"""FastAPI app entrypoint."""

import asyncio
import json
import math
import re
import warnings
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager, redirect_stdout, suppress
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import structlog
from fastapi import FastAPI, Form, HTTPException, Request, Response, status
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

# Apply Optiland 0.6 runtime patches FIRST — before any other Optiland import
# happens. See app/core/optiland_patches.py for the bug each one addresses.
from app.core import optiland_patches as _optiland_patches  # noqa: I001

_optiland_patches.apply_all()

from app.api import optical, rag, wizard  # noqa: E402
from app.core import orchestration  # noqa: E402
from app.core.aberration import MTFResult  # noqa: E402
from app.core.batch_archive import (  # noqa: E402
    BatchArchive,
    BatchArchiveError,
    BatchJobRecord,
    BatchRecord,
    ExpertVerdict,
    build_batch_workbook,
)
from app.core.config import settings  # noqa: E402
from app.core.demo_cache import (  # noqa: E402
    DemoAnalysisBundle,
    demo_cache_request,
    load_demo_cache_bundle_for_request,
)
from app.core.field_analysis import compute_field_analysis  # noqa: E402
from app.core.job_store import (  # noqa: E402
    CODEV_SEAT_LANE,
    JobNotFoundError,
    JobRecord,
    JobStatus,
)
from app.core.lens_system import Scenario  # noqa: E402
from app.core.optical_calc import airy_disk_diameter_um  # noqa: E402
from app.core.optical_sample import (  # noqa: E402
    CodeVRefinementComparison,
    DesignAssessment,
    OpticalSampleData,
)
from app.core.orchestration import formatting  # noqa: E402
from app.core.parameter_guards import (  # noqa: E402
    SCENARIO_BOUNDS,
    ParameterGuardError,
    validate_scenario_params,
)
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
#: P18 batch archive singleton (mirrors `optical.job_store`'s module-level
#: pattern) — file-backed, so this instance carries no state itself; tests
#: monkeypatch it to a `BatchArchive(root=tmp_path)` the same way they
#: monkeypatch `optical.job_store`.
batch_archive_store = BatchArchive()
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
EXAMPLE_REQUIREMENTS = (
    {
        "label": "Sample ultrawide",
        "fields": (
            {"name": "scenario", "value": "smartphone-ultrawide"},
            {"name": "scenario_label_en", "value": "Smartphone Ultrawide"},
            {"name": "focal_length_mm", "value": "3.621"},
            {"name": "f_number", "value": "2.32"},
            {"name": "field_of_view_deg", "value": "91.0"},
            {"name": "image_height_mm", "value": "3.6863"},
            {"name": "n_elements", "value": "7"},
            {"name": "wavelength_nm", "value": "550.0"},
            {"name": "total_track_mm", "value": "5.395"},
            {"name": "airy_disc_diameter_um", "value": "3.11344"},
            {"name": "cutoff_freq_lp_per_mm", "value": "783.69906"},
            {
                "name": "requirement",
                "value": (
                    "Sample request: smartphone ultrawide camera, 3.621 mm EFL, "
                    "f/2.32, 91.0 deg FOV, 3.6863 mm image height, 7 elements."
                ),
            },
        ),
    },
    {
        "label": "Sample wide",
        "fields": (
            {"name": "scenario", "value": "smartphone-wide"},
            {"name": "scenario_label_en", "value": "Smartphone Wide"},
            {"name": "focal_length_mm", "value": "2.7"},
            {"name": "f_number", "value": "2.5"},
            {"name": "field_of_view_deg", "value": "78.0"},
            {"name": "image_height_mm", "value": "2.3"},
            {"name": "n_elements", "value": "3"},
            {"name": "wavelength_nm", "value": "550.0"},
            {"name": "total_track_mm", "value": "3.563803397328498"},
            {"name": "airy_disc_diameter_um", "value": "3.355"},
            {"name": "cutoff_freq_lp_per_mm", "value": "727.272727"},
            {
                "name": "requirement",
                "value": (
                    "Sample request: smartphone wide camera, 2.7 mm EFL, f/2.5, "
                    "78.0 deg FOV, 2.3 mm image height, 3 elements."
                ),
            },
        ),
    },
)
_RESULT_ANALYSIS_WAVELENGTH_NM = 587.6
_SUMMARY_FALLBACK_WAVELENGTH_NM = 550.0
_CODEV_ESTIMATE_SOURCE = "optiland-estimate"
_CODEV_RUN_EVIDENCE_KEYS = (
    "run_started_at_utc",
    "codev_executable",
    "codev_version",
    "returncode",
    "duration_seconds",
    "source_zmx_sha256",
    "sequence_sha256",
    "result_sha256",
    "optimized_readout_sha256",
    "optimized_zmx_sha256",
)
_CODEV_RUN_SHA_KEYS = (
    "source_zmx_sha256",
    "sequence_sha256",
    "result_sha256",
    "optimized_readout_sha256",
    "optimized_zmx_sha256",
)
_HTTP_422_UNPROCESSABLE_CONTENT = 422
_WEB_ERROR_COPY = {
    status.HTTP_404_NOT_FOUND: {
        "title": "Page not found",
        "message_en": "We could not find that page or design result.",
        "message_zh": "没有找到这个页面或设计结果。",
    },
    _HTTP_422_UNPROCESSABLE_CONTENT: {
        "title": "Check the form",
        "message_en": "One or more fields need a valid value before Atelier can continue.",
        "message_zh": "表单里有字段需要修正，Atelier 才能继续。",
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "title": "Something went wrong",
        "message_en": "Atelier hit an internal error while preparing this page.",
        "message_zh": "Atelier 准备这个页面时遇到内部错误。",
    },
}
_WEB_ERROR_FALLBACK_COPY = {
    "title": "Request needs attention",
    "message_en": "Atelier could not complete this page request.",
    "message_zh": "Atelier 暂时无法完成这个页面请求。",
}


def _is_api_request(request: Request) -> bool:
    path = request.url.path
    return path == "/api" or path.startswith("/api/")


def _format_error_detail(detail: object) -> str:
    if isinstance(detail, Mapping):
        message = detail.get("message")
        if message:
            return str(message)
        error = detail.get("error")
        job_id = detail.get("job_id")
        if error and job_id:
            return f"{error}: {job_id}"
        return ", ".join(f"{key}: {value}" for key, value in detail.items())
    if detail:
        return str(detail)
    return ""


def _format_validation_errors(exc: RequestValidationError) -> str:
    items: list[str] = []
    for error in exc.errors()[:4]:
        loc = error.get("loc", ())
        field = ".".join(
            str(part)
            for part in loc
            if part not in {"body", "query", "path", "form"}
        )
        message = str(error.get("msg", "Invalid value"))
        items.append(f"{field or 'request'}: {message}")
    return "; ".join(items)


def _web_error_response(
    request: Request,
    status_code: int,
    *,
    detail: str = "",
) -> HTMLResponse:
    copy = _WEB_ERROR_COPY.get(status_code, _WEB_ERROR_FALLBACK_COPY)
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "product_name": "Atelier",
            "status_code": status_code,
            "detail": detail,
            **copy,
        },
        status_code=status_code,
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


def _looks_like_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in value)


def _has_codev_run_evidence(artifact: object) -> bool:
    if not isinstance(artifact, dict):
        return False
    evidence = artifact.get("run_evidence")
    if not isinstance(evidence, dict):
        return False
    if any(evidence.get(key) in {None, ""} for key in _CODEV_RUN_EVIDENCE_KEYS):
        return False
    if str(evidence.get("codev_version", "")).lower() == "unknown":
        return False
    return all(_looks_like_sha256(evidence.get(key)) for key in _CODEV_RUN_SHA_KEYS)


def _sample_from_cached_bundle(cached: DemoAnalysisBundle) -> OpticalSampleData:
    sample = cached.sample
    updates: dict[str, object] = {}
    if sample.spot_diagram is None:
        updates["spot_diagram"] = cached.spot_diagram
    if sample.field_analysis is None:
        updates["field_analysis"] = cached.field_analysis
    if sample.wavefront is None:
        updates["wavefront"] = cached.wavefront
    if sample.codev_optimization is None and cached.codev_artifact is not None:
        with suppress(Exception):
            updates["codev_optimization"] = CodeVRefinementComparison.model_validate(
                cached.codev_artifact
            )
    return sample.model_copy(update=updates, deep=True) if updates else sample


def _percent_reduction(before: float, after: float) -> float | None:
    if not math.isfinite(before) or not math.isfinite(after) or before <= 0:
        return None
    return (before - after) / before * 100.0


def _format_optional_pct(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:.1f}%"


def _format_signed_waves(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:+.3f} waves"


def _format_mtf_drop(value: float) -> str:
    return f"{value:.4f}"


def _mtf_mean_curve(mtf: MTFResult) -> list[float]:
    if not mtf.fields:
        return []
    field = mtf.fields[0]
    return [
        (sagittal + tangential) / 2.0
        for sagittal, tangential in zip(field.sagittal, field.tangential, strict=False)
        if math.isfinite(sagittal) and math.isfinite(tangential)
    ]


def _mtf_polyline_points(
    *,
    freqs: list[float],
    values: list[float],
    max_freq: float,
    width: int,
    height: int,
    pad: int,
) -> str:
    points: list[str] = []
    plot_width = width - pad * 2
    plot_height = height - pad * 2
    for freq, value in zip(freqs, values, strict=False):
        if not math.isfinite(freq) or not math.isfinite(value):
            continue
        x = pad + max(0.0, min(freq, max_freq)) / max_freq * plot_width
        y = pad + (1.0 - max(0.0, min(value, 1.0))) * plot_height
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _mtf_overlay_svg(seed_mtf: MTFResult, refined_mtf: MTFResult) -> str:
    width = 420
    height = 180
    pad = 24
    seed_values = _mtf_mean_curve(seed_mtf)
    refined_values = _mtf_mean_curve(refined_mtf)
    seed_freqs = _finite_float_values(seed_mtf.freq_lp_per_mm)
    refined_freqs = _finite_float_values(refined_mtf.freq_lp_per_mm)
    seed_count = min(len(seed_freqs), len(seed_values))
    refined_count = min(len(refined_freqs), len(refined_values))
    if seed_count < 2 or refined_count < 2:
        return ""
    seed_freqs = seed_freqs[:seed_count]
    refined_freqs = refined_freqs[:refined_count]
    seed_values = seed_values[:seed_count]
    refined_values = refined_values[:refined_count]
    max_freq = max(max(seed_freqs), max(refined_freqs))
    if max_freq <= 0:
        return ""
    seed_points = _mtf_polyline_points(
        freqs=seed_freqs,
        values=seed_values,
        max_freq=max_freq,
        width=width,
        height=height,
        pad=pad,
    )
    refined_points = _mtf_polyline_points(
        freqs=refined_freqs,
        values=refined_values,
        max_freq=max_freq,
        width=width,
        height=height,
        pad=pad,
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        'aria-label="MTF curve overlay">'
        f'<line class="mtf-axis" x1="{pad}" y1="{height - pad}" '
        f'x2="{width - pad}" y2="{height - pad}"></line>'
        f'<line class="mtf-axis" x1="{pad}" y1="{pad}" '
        f'x2="{pad}" y2="{height - pad}"></line>'
        f'<polyline class="mtf-curve mtf-curve-seed" points="{seed_points}"></polyline>'
        f'<polyline class="mtf-curve mtf-curve-refined" points="{refined_points}"></polyline>'
        "</svg>"
    )


def _codev_metric(
    *,
    key: str,
    label: str,
    value: str,
    detail: str,
    source: object,
) -> dict[str, object]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "detail": detail,
        "source": _source_value(source),
    }


def _codev_perturbation_context(
    comparison: CodeVRefinementComparison,
    *,
    codev_source: str,
) -> dict[str, object]:
    rows = tuple(
        {
            "rank": item.rank,
            "parameter_name": item.parameter_name,
            "perturbation": item.perturbation,
            "mtf_drop": _format_mtf_drop(item.mtf_drop),
            "source": codev_source,
        }
        for item in comparison.tolerance_sensitivity_top_n
    )
    if not rows:
        note = "No CODE V perturbation replay rows are attached to this result."
    elif codev_source == ProvenanceSource.CODEV_RUN.value:
        note = "Ranked by CODE V perturbation replay; this is not a parsed TOR report."
    else:
        note = "Estimated perturbation replay data attached without CODE V run evidence."
    return {
        "available": bool(rows),
        "rows": rows,
        "source": codev_source,
        "metric": "CODE V perturbation replay MTF drop",
        "note": note,
    }


def _codev_comparison_context(
    sample: OpticalSampleData | None,
    codev_artifact: dict[str, object] | None = None,
) -> dict[str, object]:
    if sample is None or sample.codev_optimization is None:
        return {
            "available": False,
            "reason": "No CODE V refinement artifact is attached to this optical_sample.",
        }

    comparison = sample.codev_optimization
    has_codev_evidence = _has_codev_run_evidence(codev_artifact)
    seed_mtf = comparison.seed_mtf or sample.mtf
    refined_mtf = comparison.refined_mtf
    mtf_svg = _mtf_overlay_svg(seed_mtf, refined_mtf) if refined_mtf is not None else ""
    spot_shrink_pct = _percent_reduction(
        comparison.before.max_rms_spot_diameter_um,
        comparison.after.max_rms_spot_diameter_um,
    )
    wavefront_delta = (
        comparison.after.max_rms_wavefront_error_waves
        - comparison.before.max_rms_wavefront_error_waves
    )
    codev_source = (
        ProvenanceSource.CODEV_RUN.value if has_codev_evidence else _CODEV_ESTIMATE_SOURCE
    )
    cross_source = (
        comparison.cross_validation_provenance if has_codev_evidence else _CODEV_ESTIMATE_SOURCE
    )
    return {
        "available": True,
        "source_zmx": comparison.source_zmx,
        "optimized_zmx": comparison.optimized_zmx_filename,
        "status": comparison.optimization_status.replace("_", " "),
        "has_codev_run_evidence": has_codev_evidence,
        "cross_validation_source": cross_source,
        "mtf_available": bool(mtf_svg),
        "mtf_svg": mtf_svg,
        "mtf_summary": (
            f"Overlay uses field {seed_mtf.fields[0].field_index}; "
            f"seed/refined frequency samples "
            f"{len(seed_mtf.freq_lp_per_mm)}/{len(refined_mtf.freq_lp_per_mm) if refined_mtf is not None else 0}."
            if seed_mtf.fields
            else "MTF overlay data is unavailable."
        ),
        "badges": (
            {"label": "Seed MTF trace", "source": _source_value(seed_mtf.provenance)},
            {"label": "CODE V AUT run", "source": _source_value(codev_source)},
            {"label": "Rebuilt ZMX verified", "source": cross_source},
        ),
        "metrics": (
            _codev_metric(
                key="spot-rms-shrink-pct",
                label="Spot RMS shrink",
                value=_format_optional_pct(spot_shrink_pct),
                detail=(
                    f"{comparison.before.max_rms_spot_diameter_um:.2f} -> "
                    f"{comparison.after.max_rms_spot_diameter_um:.2f} um diameter"
                ),
                source=codev_source,
            ),
            _codev_metric(
                key="wavefront-rms-delta",
                label="Wavefront RMS delta",
                value=_format_signed_waves(wavefront_delta),
                detail=(
                    f"{comparison.before.max_rms_wavefront_error_waves:.3f} -> "
                    f"{comparison.after.max_rms_wavefront_error_waves:.3f} waves"
                ),
                source=codev_source,
            ),
            _codev_metric(
                key="efl-cross-check",
                label="CODE V cross-check",
                value=f"{comparison.efl_deviation_pct:.4f}% EFL drift",
                detail=comparison.cross_validation_status.replace("-", " "),
                source=cross_source,
            ),
        ),
        "perturbation_table": _codev_perturbation_context(
            comparison,
            codev_source=codev_source,
        ),
    }


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
    if _is_result_summary_job(record):
        result_url = f"/results/{record.job_id}"
    elif _is_candidate_orchestration_job(record):
        result_url = f"/candidates/{record.job_id}"
    else:
        result_url = ""
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
        "result_url": result_url,
        "has_result_url": bool(result_url),
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


def _is_result_summary_job(record: JobRecord) -> bool:
    return record.payload.get("job_type") == "result-summary"


def _is_candidate_orchestration_job(record: JobRecord) -> bool:
    return record.payload.get("job_type") == "candidate-orchestration"


def _result_job_payload(
    *,
    scenario: Scenario,
    scenario_label_en: str,
    focal_length_mm: float,
    f_number: float,
    field_of_view_deg: float,
    image_height_mm: float,
    total_track_mm: float,
    airy_disc_diameter_um: float,
    cutoff_freq_lp_per_mm: float,
    n_elements: int | None,
    wavelength_nm: float,
    requirement: str | None,
) -> dict[str, object]:
    return {
        "job_type": "result-summary",
        "scenario": scenario.value,
        "scenario_label_en": scenario_label_en,
        "focal_length_mm": focal_length_mm,
        "f_number": f_number,
        "field_of_view_deg": field_of_view_deg,
        "image_height_mm": image_height_mm,
        "total_track_mm": total_track_mm,
        "airy_disc_diameter_um": airy_disc_diameter_um,
        "cutoff_freq_lp_per_mm": cutoff_freq_lp_per_mm,
        "n_elements": n_elements,
        "wavelength_nm": wavelength_nm,
        "requirement": requirement,
    }


def _result_payload_scenario(payload: Mapping[str, object]) -> Scenario:
    value = payload.get("scenario")
    if isinstance(value, Scenario):
        return value
    return Scenario(str(value))


def _optional_int(value: object) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _executive_summary_request(
    *,
    scenario: Scenario,
    scenario_label_en: str,
    focal_length_mm: float,
    f_number: float,
    field_of_view_deg: float,
    image_height_mm: float,
    n_elements: int | None,
    wavelength_nm: float,
    total_track_mm: float,
    airy_disc_diameter_um: float,
    cutoff_freq_lp_per_mm: float,
    design_assessment: DesignAssessment | None,
) -> wizard.ExecutiveSummaryRequest:
    return wizard.ExecutiveSummaryRequest(
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


def _summary_job_payload(req: wizard.ExecutiveSummaryRequest) -> dict[str, object]:
    return {
        "job_type": "executive-summary",
        "request": req.model_dump(mode="json"),
    }


def _pending_executive_summary() -> wizard.ExecutiveSummaryResponse:
    return wizard.ExecutiveSummaryResponse(
        summary_en=(
            "Executive summary is being generated. The optical data and computed "
            "analysis package are already available below."
        ),
        summary_zh="执行摘要正在生成；光学数据与实算分析包已先行渲染在下方。",
        model="pending",
        fallback_reason="executive_summary_pending",
    )


def _cached_executive_summary(cached: DemoAnalysisBundle | None) -> wizard.ExecutiveSummaryResponse | None:
    if cached is None or not isinstance(cached.executive_summary, Mapping):
        return None
    with suppress(Exception):
        return wizard.ExecutiveSummaryResponse.model_validate(cached.executive_summary)
    return None


async def _compute_executive_summary_job(payload: Mapping[str, object]) -> dict[str, object]:
    request_payload = payload.get("request")
    if not isinstance(request_payload, Mapping):
        raise ValueError("executive summary job has invalid request payload")
    summary = await wizard.generate_executive_summary(
        wizard.ExecutiveSummaryRequest.model_validate(request_payload)
    )
    return {
        "job_type": "executive-summary",
        "summary": summary.model_dump(mode="json"),
    }


class ExecutiveSummaryEngine:
    """JobStore-compatible worker for deferred result-page LLM summaries."""

    name = "executive-summary"

    def is_available(self) -> bool:
        return True

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "engine": "ExecutiveSummaryEngine",
            "available": True,
            "capabilities": ["web-executive-summary"],
        }

    def submit(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        return asyncio.run(_compute_executive_summary_job(payload))


def _submit_executive_summary_job(payload: Mapping[str, object]) -> str:
    if not hasattr(optical.job_store, "submit"):
        return ""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return ""
    return optical.job_store.submit(ExecutiveSummaryEngine(), payload)


def _persist_summary_job_id(result_job_id: object, summary_job_id: str) -> None:
    if not summary_job_id or not isinstance(result_job_id, str) or not result_job_id:
        return
    if not hasattr(optical.job_store, "update_result"):
        return
    try:
        record = optical.job_store.get(result_job_id)
    except JobNotFoundError:
        return
    if (
        not _is_result_summary_job(record)
        or record.status is not JobStatus.SUCCEEDED
        or record.result is None
        or record.result.get("summary_job_id") == summary_job_id
    ):
        return
    optical.job_store.update_result(result_job_id, {"summary_job_id": summary_job_id})


async def _compute_result_summary_job(payload: Mapping[str, object]) -> dict[str, object]:
    scenario = _result_payload_scenario(payload)
    scenario_label_en = str(payload["scenario_label_en"])
    focal_length_mm = float(payload["focal_length_mm"])
    f_number = float(payload["f_number"])
    field_of_view_deg = float(payload["field_of_view_deg"])
    image_height_mm = float(payload["image_height_mm"])
    total_track_mm = float(payload["total_track_mm"])
    airy_disc_diameter_um = float(payload["airy_disc_diameter_um"])
    cutoff_freq_lp_per_mm = float(payload["cutoff_freq_lp_per_mm"])
    n_elements = _optional_int(payload.get("n_elements"))
    wavelength_nm = float(payload.get("wavelength_nm", 550.0))
    requirement = payload.get("requirement")
    requirement_text = str(requirement) if requirement not in {None, ""} else None

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
    codev_artifact: dict[str, object] | None = None
    if cached is not None:
        demo_cache_status = "hit"
        sample = _sample_from_cached_bundle(cached)
        focal_length_mm = sample.paraxial.effective_focal_length_mm
        f_number = sample.paraxial.f_number
        total_track_mm = sample.paraxial.total_track_mm
        airy_disc_diameter_um = sample.mtf.airy_disc_diameter_um
        cutoff_freq_lp_per_mm = sample.mtf.cutoff_freq_lp_per_mm
        if sample.metadata is not None:
            scenario_label_en = sample.metadata.scenario.value.replace("-", " ").title()
            n_elements = sample.metadata.n_pieces
        design_assessment = sample.design_assessment
        codev_artifact = cached.codev_artifact
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

    summary_request = _executive_summary_request(
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
    summary = _cached_executive_summary(cached)
    summary_status = "cached" if summary is not None else "pending"
    if summary is None:
        summary = _pending_executive_summary()

    return {
        "job_type": "result-summary",
        "scenario": scenario.value,
        "scenario_label_en": scenario_label_en,
        "requirement": requirement_text,
        "demo_cache_status": demo_cache_status,
        "resolved": {
            "focal_length_mm": focal_length_mm,
            "f_number": f_number,
            "field_of_view_deg": field_of_view_deg,
            "image_height_mm": image_height_mm,
            "n_elements": n_elements,
            "wavelength_nm": wavelength_nm,
            "total_track_mm": total_track_mm,
            "airy_disc_diameter_um": airy_disc_diameter_um,
            "cutoff_freq_lp_per_mm": cutoff_freq_lp_per_mm,
        },
        "summary_status": summary_status,
        "summary_job_payload": _summary_job_payload(summary_request)
        if summary_status == "pending"
        else None,
        "summary": summary.model_dump(mode="json"),
        "sample": sample.model_dump(mode="json") if sample is not None else None,
        "codev_artifact": codev_artifact,
    }


class ResultSummaryEngine:
    """JobStore-compatible worker for the web result summary computation."""

    name = "result-summary"

    def is_available(self) -> bool:
        return True

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "engine": "ResultSummaryEngine",
            "available": True,
            "capabilities": ["web-result-summary"],
        }

    def submit(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        return asyncio.run(_compute_result_summary_job(payload))


def _result_summary_context(
    *,
    result: Mapping[str, object],
    progress: Mapping[str, object],
) -> dict[str, object]:
    resolved = result["resolved"]
    if not isinstance(resolved, Mapping):
        raise ValueError("result summary job has invalid resolved payload")

    sample_payload = result.get("sample")
    sample = (
        OpticalSampleData.model_validate(sample_payload)
        if isinstance(sample_payload, Mapping)
        else None
    )
    summary_payload = result["summary"]
    if not isinstance(summary_payload, Mapping):
        raise ValueError("result summary job has invalid summary payload")
    summary = wizard.ExecutiveSummaryResponse.model_validate(summary_payload)
    scenario = Scenario(str(result["scenario"]))
    codev_artifact = result.get("codev_artifact")
    summary_status = str(result.get("summary_status") or "ready")
    summary_job_id = str(result.get("summary_job_id") or "")
    summary_job_payload = result.get("summary_job_payload")
    if (
        summary_status == "pending"
        and not summary_job_id
        and isinstance(summary_job_payload, Mapping)
    ):
        summary_job_id = _submit_executive_summary_job(summary_job_payload)
        _persist_summary_job_id(progress.get("job_id"), summary_job_id)

    focal_length_mm = float(resolved["focal_length_mm"])
    f_number = float(resolved["f_number"])
    field_of_view_deg = float(resolved["field_of_view_deg"])
    image_height_mm = float(resolved["image_height_mm"])
    total_track_mm = float(resolved["total_track_mm"])
    airy_disc_diameter_um = float(resolved["airy_disc_diameter_um"])
    cutoff_freq_lp_per_mm = float(resolved["cutoff_freq_lp_per_mm"])
    n_elements = _optional_int(resolved.get("n_elements"))
    return {
        "product_name": "Atelier",
        "scenario_label": str(result["scenario_label_en"]),
        "scenario": scenario.value,
        "demo_cache_status": str(result["demo_cache_status"]),
        "requirement": result.get("requirement"),
        "summary": summary,
        "summary_status": summary_status,
        "summary_job_id": summary_job_id,
        "summary_events_url": f"/api/optical/jobs/{summary_job_id}/events"
        if summary_job_id
        else "",
        "summary_poll_url": f"/api/optical/jobs/{summary_job_id}" if summary_job_id else "",
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
        "codev_comparison": _codev_comparison_context(
            sample,
            codev_artifact if isinstance(codev_artifact, dict) else None,
        ),
        "layout_svg": sample.layout_svg.svg_content if sample is not None else "",
        "has_layout_svg": sample is not None,
        "progress": dict(progress),
    }


# ---------------------------------------------------------------------------
# C1 candidate orchestration (Mode1 retrieval + Mode3 CODE V target-converged)
# ---------------------------------------------------------------------------


def _target_spec_from_candidate_payload(payload: Mapping[str, object]) -> orchestration.TargetSpec:
    """Map the wizard-confirmed (or P17 adjust-and-rerun) form fields onto
    `TargetSpec`.

    The wizard flow only ever produces EFL / FOV / F# / image-height / element
    count (see `_summary_form_fields`) — it has no notion of a customer TTL
    ceiling, weight budget, manufacturing tier, or priority. Those fields stay
    honestly `None` rather than being backfilled from the wizard's own derived
    `total_track_mm` (a nominal *achieved* estimate for the mid-bound scenario
    point, not a customer-specified ceiling) — silently promoting an estimate
    into a hard constraint would be exactly the kind of unearned precision the
    North Star forbids. `max_total_track_mm` is the one exception: the
    candidate-set page's "adjust & rerun" form (P17 sub-item 1) lets a
    reviewer type an explicit TTL ceiling, which flows through here as a real
    customer constraint — the wizard form still never sends this key, so
    `payload.get(...)` stays `None` on that path (zero behavior change).
    """
    return orchestration.TargetSpec(
        scenario=_result_payload_scenario(payload),
        efl_mm=_optional_float(payload.get("focal_length_mm")),
        fov_deg=_optional_float(payload.get("field_of_view_deg")),
        fnum=float(payload["f_number"]),
        image_height_mm=_optional_float(payload.get("image_height_mm")),
        max_total_track_mm=_optional_float(payload.get("max_total_track_mm")),
        n_elements=_optional_int(payload.get("n_elements")),
        max_weight_g=None,
        manufacturing_tier=None,
        priority=None,
    )


def _candidate_job_payload(
    *,
    scenario: Scenario,
    focal_length_mm: float,
    f_number: float,
    field_of_view_deg: float,
    image_height_mm: float,
    max_total_track_mm: float | None,
    n_elements: int | None,
    requirement: str | None,
    repeat_runs: int = 1,
    artifact_dir: Path | None = None,
) -> dict[str, object]:
    return {
        "job_type": "candidate-orchestration",
        "scenario": scenario.value,
        "focal_length_mm": focal_length_mm,
        "f_number": f_number,
        "field_of_view_deg": field_of_view_deg,
        "image_height_mm": image_height_mm,
        "max_total_track_mm": max_total_track_mm,
        "n_elements": n_elements,
        "requirement": requirement,
        "repeat_runs": repeat_runs,
        "artifact_dir": str(artifact_dir) if artifact_dir is not None else None,
    }


def _validate_finite_form_numbers_or_400(**fields: float | None) -> None:
    """P17 对抗审 M1：拒绝任何非有限（inf/-inf/NaN）表单数值进入候选 job。

    为什么需要在 pydantic 之外补一层：`Form(gt=0)` 对 `inf` 判真（inf > 0），
    真机探针实证 `max_total_track_mm=inf` 曾拿到 303 直进 job payload /
    `TargetSpec` / 页面 / xlsx。`NaN`/`-inf` 会被 `gt=0` 拦下（NaN 比较恒
    False → 422），但依赖那个副作用不是契约——这里对全部被消费的数值字段
    统一显式 `isfinite` 校验，非有限值以与 parameter_guards 相同的 400 +
    violations 形状拒绝。`None`（可选字段未填）跳过。
    """
    violations = [
        f"{name} must be a finite number, got {value}"
        for name, value in fields.items()
        if value is not None and not math.isfinite(value)
    ]
    if violations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "non_finite_parameter",
                "violations": violations,
                "message": "; ".join(violations),
            },
        )


def _validate_candidate_target_or_400(
    scenario: Scenario,
    *,
    efl_mm: float,
    f_number: float,
    fov_deg: float,
    image_height_mm: float,
    n_elements: int | None,
) -> None:
    """Run `parameter_guards` against a candidate-orchestration submission
    (wizard-derived or the P17 "adjust & rerun" form) and convert a
    `ParameterGuardError` into an honest 400 — mirrors
    `app/api/optical.py::_validate_or_400`, kept as a separate web-layer copy
    since that one raises the JSON-shaped detail the `/api/optical/*` routes
    expect, while this one adds a flat `message` the generic web error
    handler (`_web_error_response` / `_format_error_detail`) renders as a
    single readable line instead of a raw dict dump."""
    try:
        validate_scenario_params(
            scenario,
            efl_mm=efl_mm,
            f_number=f_number,
            fov_deg=fov_deg,
            image_height_mm=image_height_mm,
            n_elements=n_elements,
        )
    except ParameterGuardError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "parameter_guard_failed",
                "scenario": scenario.value,
                "violations": e.violations,
                "message": "; ".join(e.violations),
            },
        ) from e


def _compute_candidate_job(payload: Mapping[str, object]) -> dict[str, object]:
    scenario = _result_payload_scenario(payload)
    target = _target_spec_from_candidate_payload(payload)
    artifact_dir_raw = payload.get("artifact_dir")
    artifact_dir = Path(str(artifact_dir_raw)) if artifact_dir_raw else None
    repeat_runs = int(payload.get("repeat_runs", 1))
    candidate_set = orchestration.orchestrate(
        target, target, n=4, repeat_runs=repeat_runs, artifact_dir=artifact_dir
    )
    requirement = payload.get("requirement")
    return {
        "job_type": "candidate-orchestration",
        "scenario": scenario.value,
        "requirement": str(requirement) if requirement not in {None, ""} else None,
        "candidate_set": candidate_set.model_dump(mode="json"),
        "artifact_dir": str(artifact_dir) if artifact_dir is not None else None,
    }


class CandidateOrchestrationEngine:
    """JobStore-compatible worker for the C1 multi-candidate orchestration
    (Mode1 retrieval + Mode3 CODE V target-converged).

    `is_available()` is unconditionally `True`: Mode3 degrades *internally*
    when CODE V is not present (`TargetConvergedGenerator` returns `[]`, the
    batch falls back to Mode1-only, and `CandidateSet.honesty_banner`
    surfaces the degradation) — that is the honest degraded path per the
    North Star, so this engine must never pre-gate submission on CODE V
    availability the way a hard `DeepEngine` dependency check normally would.

    `seat_lane = CODEV_SEAT_LANE`: a C1 batch runs real CODE V for minutes
    (Mode3). On the dedicated codev lane it serializes against other CODE V
    work (single-instance iron rule) without occupying the default lane's
    seat — the instant demo path (ResultSummaryEngine / ExecutiveSummaryEngine)
    keeps running while a candidate batch computes.
    """

    name = "candidate-orchestration"
    seat_lane = CODEV_SEAT_LANE

    def is_available(self) -> bool:
        return True

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "engine": "CandidateOrchestrationEngine",
            "available": True,
            "capabilities": ["web-candidate-orchestration"],
        }

    def submit(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        return _compute_candidate_job(payload)


def _mode_label(mode: orchestration.GenerationMode) -> str:
    return {
        orchestration.GenerationMode.RETRIEVED: "Retrieved (Mode1)",
        orchestration.GenerationMode.TARGET_CONVERGED: "Target-converged (Mode3)",
    }[mode]


# P17 对抗审 M3：页面与 xlsx 导出共用 `orchestration.formatting` 的单一格式化
# 器（含"非零小值不得显示为 0.000 假零"守卫）——本模块只保留同名薄别名，
# 保证既有调用点零翻新；不得在此重新实现格式化逻辑（会重新引入口径分叉）。
_fmt_metric = formatting.fmt_metric
_fmt_optional_target = formatting.fmt_optional_target


_CANDIDATE_IMAGE_QUALITY_ROWS: tuple[tuple[str, str], ...] = (
    ("MTF sag (representative freq, cross-field conservative)", "mtf_sag"),
    ("MTF tan (representative freq, cross-field conservative)", "mtf_tan"),
    ("Diffraction cutoff (lp/mm)", "diffraction_cutoff_lp_per_mm"),
    ("RMS spot radius max (um)", "rms_spot_radius_max_um"),
    ("RMS spot radius mean (um)", "rms_spot_radius_mean_um"),
    ("Min Strehl ratio", "min_strehl_ratio"),
    ("RMS wavefront error (waves)", "rms_wavefront_error_waves"),
    ("Field curvature tangential peak delta (mm)", "field_curvature_tangential_delta_mm"),
    ("Field curvature sagittal peak delta (mm)", "field_curvature_sagittal_delta_mm"),
    ("Max distortion (%)", "max_distortion_pct"),
    ("Relative illumination (worst field)", "relative_illumination"),
)

_CANDIDATE_CODEV_POST_AUT_ROWS: tuple[tuple[str, str], ...] = (
    ("post_aut EFL_y (mm)", "post_aut.efl_y_mm"),
    ("post_aut RMS spot diameter (um)", "post_aut.max_rms_spot_diameter_um"),
    ("post_aut RMS wavefront error (waves)", "post_aut.max_rms_wavefront_error_waves"),
    ("post_aut distortion (%)", "post_aut.max_distortion_pct"),
    ("post_aut F#", "post_aut.fno"),
    ("post_aut half image height (mm)", "post_aut.maximh_mm"),
    ("EFL target deviation (%)", "efl_target_deviation_pct"),
    ("aut_converged", "aut_converged"),
    ("Vignetting edge_used", "autovig.edge_used"),
    ("AUT err_f_ratio (final/initial)", "err_f_ratio"),
    ("AUT termination", "aut_termination"),
)

_CANDIDATE_CODEV_POST_AUT_CAVEAT = (
    "裁瞳口径快照，不可与满口径直接横比 —— 以下数字来自 CODE V "
    "run_codev_target_standard preferred 配置的批跑读数，裁瞳（vignetted pupil）"
    "口径，与上方 target 偏差/像质摘要的 Optiland 满口径不可直接横比，仅供资深"
    "核对 provenance —— 不参与本页任何排序/打分。"
)


def _fmt_codev_value(value: object) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _candidate_codev_post_aut_context(
    extras: orchestration.OpticalExtras,
) -> dict[str, object] | None:
    if extras.codev_post_aut is None:
        return None
    return {
        "caveat": _CANDIDATE_CODEV_POST_AUT_CAVEAT,
        "rows": [
            {"label": label, "value": _fmt_codev_value(extras.codev_post_aut.get(key))}
            for label, key in _CANDIDATE_CODEV_POST_AUT_ROWS
        ],
    }


def _candidate_deviation_row(dev: orchestration.TargetDeviation) -> dict[str, object]:
    return {
        "field": dev.field,
        "constraint_kind": dev.constraint_kind,
        "target": _fmt_optional_target(dev.target),
        "achieved": formatting.fmt_float(dev.achieved),
        "violation": formatting.fmt_float(dev.violation),
        "rel_violation": formatting.fmt_rel_violation(dev.rel_violation),
        "converged": dev.converged_toward_target,
        "converged_label": formatting.fmt_yes_no(dev.converged_toward_target),
    }


def _candidate_manufacturability_context(
    mfg: orchestration.ManufacturabilityProxy,
) -> dict[str, object]:
    return {
        "total_track_mm": formatting.fmt_float(mfg.total_track_mm),
        "n_pieces": mfg.n_pieces,
        "has_special_glass": formatting.fmt_yes_no(mfg.has_special_glass),
        "aspheric_term_count": _fmt_metric(mfg.aspheric_term_count, precision=0),
        "aspheric_surface_count": _fmt_metric(mfg.aspheric_surface_count, precision=0),
        "chief_ray_angle_deg": _fmt_metric(mfg.chief_ray_angle_deg),
        "note": mfg.note,
    }


def _candidate_repeatability_context(
    rep: orchestration.RepeatabilityMetrics,
) -> dict[str, object]:
    """Render the server-computed repeat distribution without fabrication.

    RMS samples are CODE V post-AUT cropped/vignetted-pupil max spot diameter/2;
    the scorecard headline RMS remains Optiland full-aperture and is not comparable.
    """
    return {
        "run_count": rep.run_count,
        "status": rep.status,
        "status_label": "Available" if rep.status == "available" else "Unavailable",
        "rms_min": _fmt_metric(rep.rms_spot_radius_um_min),
        "rms_max": _fmt_metric(rep.rms_spot_radius_um_max),
        "rms_spread": _fmt_metric(rep.rms_spot_radius_um_spread),
        "wfe_min": _fmt_metric(rep.wfe_waves_min),
        "wfe_max": _fmt_metric(rep.wfe_waves_max),
        "wfe_spread": _fmt_metric(rep.wfe_waves_spread),
        "note": rep.note,
    }


# Compact per-candidate MTF chart geometry. Left/bottom padding leaves room
# for axis tick labels — the axes must stay labeled and honest (full 0-1
# modulation scale, real frequency range), never a truncated scale that
# flatters the curves.
_CANDIDATE_MTF_WIDTH = 380
_CANDIDATE_MTF_HEIGHT = 200
_CANDIDATE_MTF_PAD_LEFT = 40
_CANDIDATE_MTF_PAD_RIGHT = 12
_CANDIDATE_MTF_PAD_TOP = 10
_CANDIDATE_MTF_PAD_BOTTOM = 32

#: Field-index -> CSS class cycle for candidate MTF curves (site.css
#: .mtf-field-N maps onto the token palette).
_CANDIDATE_MTF_FIELD_CLASS_COUNT = 4


def _candidate_mtf_polyline(
    freqs: list[float],
    values: list[float],
    max_freq: float,
) -> str:
    plot_w = _CANDIDATE_MTF_WIDTH - _CANDIDATE_MTF_PAD_LEFT - _CANDIDATE_MTF_PAD_RIGHT
    plot_h = _CANDIDATE_MTF_HEIGHT - _CANDIDATE_MTF_PAD_TOP - _CANDIDATE_MTF_PAD_BOTTOM
    points: list[str] = []
    for freq, value in zip(freqs, values, strict=False):
        if not math.isfinite(freq) or not math.isfinite(value):
            continue
        x = _CANDIDATE_MTF_PAD_LEFT + max(0.0, min(freq, max_freq)) / max_freq * plot_w
        y = _CANDIDATE_MTF_PAD_TOP + (1.0 - max(0.0, min(value, 1.0))) * plot_h
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _candidate_mtf_axes_svg(max_freq: float) -> list[str]:
    left = _CANDIDATE_MTF_PAD_LEFT
    right = _CANDIDATE_MTF_WIDTH - _CANDIDATE_MTF_PAD_RIGHT
    top = _CANDIDATE_MTF_PAD_TOP
    bottom = _CANDIDATE_MTF_HEIGHT - _CANDIDATE_MTF_PAD_BOTTOM
    parts: list[str] = [
        f'<line class="mtf-axis" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}"></line>',
        f'<line class="mtf-axis" x1="{left}" y1="{top}" x2="{left}" y2="{bottom}"></line>',
    ]
    # Y ticks: full honest modulation scale 0 / 0.5 / 1.0.
    for frac in (0.0, 0.5, 1.0):
        y = top + (1.0 - frac) * (bottom - top)
        parts.append(
            f'<line class="mtf-grid" x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}"></line>'
        )
        parts.append(
            f'<text class="mtf-tick-label" x="{left - 6}" y="{y + 3.5:.1f}" '
            f'text-anchor="end">{frac:.1f}</text>'
        )
    # X ticks: 0 / mid / max of the real plotted frequency range.
    for frac in (0.0, 0.5, 1.0):
        x = left + frac * (right - left)
        parts.append(
            f'<text class="mtf-tick-label" x="{x:.1f}" y="{bottom + 14}" '
            f'text-anchor="middle">{max_freq * frac:.0f}</text>'
        )
    parts.append(
        f'<text class="mtf-tick-label" x="{right}" y="{bottom + 27}" '
        'text-anchor="end">spatial frequency (lp/mm)</text>'
    )
    return parts


def _candidate_mtf_svg(mtf: MTFResult) -> str:
    """Compact, honest MTF chart for one candidate card: sagittal solid /
    tangential dashed per field, diffraction-limit reference, labeled axes.
    The y-axis is always the full 0-1 modulation scale and the x-axis spans
    the real computed frequency range — no truncation that flatters curves.
    Returns "" when the payload carries too little finite MTF data to plot
    (the template shows an honest empty state instead)."""
    freqs = _finite_float_values(mtf.freq_lp_per_mm)
    if len(freqs) < 2 or not mtf.fields:
        return ""
    max_freq = max(freqs)
    if max_freq <= 0:
        return ""

    curves: list[str] = []
    for field in mtf.fields:
        css = f"mtf-field-{field.field_index % _CANDIDATE_MTF_FIELD_CLASS_COUNT}"
        sag_points = _candidate_mtf_polyline(mtf.freq_lp_per_mm, field.sagittal, max_freq)
        tan_points = _candidate_mtf_polyline(mtf.freq_lp_per_mm, field.tangential, max_freq)
        if sag_points.count(" ") >= 1:
            curves.append(
                f'<polyline class="mtf-curve-line {css}" points="{sag_points}"></polyline>'
            )
        if tan_points.count(" ") >= 1:
            curves.append(
                f'<polyline class="mtf-curve-line mtf-tan {css}" points="{tan_points}"></polyline>'
            )
    if not curves:
        return ""

    parts = _candidate_mtf_axes_svg(max_freq)
    diff_points = _candidate_mtf_polyline(mtf.freq_lp_per_mm, mtf.diff_limited, max_freq)
    if diff_points.count(" ") >= 1:
        parts.append(
            f'<polyline class="mtf-curve-line mtf-diff-limit" points="{diff_points}"></polyline>'
        )
    parts.extend(curves)
    body = "".join(parts)
    return (
        f'<svg viewBox="0 0 {_CANDIDATE_MTF_WIDTH} {_CANDIDATE_MTF_HEIGHT}" role="img" '
        f'aria-label="Candidate MTF curves, 0 to {max_freq:.0f} lp/mm, '
        'full 0-1 modulation scale">'
        f"{body}</svg>"
    )


def _candidate_mtf_legend(mtf: MTFResult) -> list[dict[str, str]]:
    return [
        {
            "label": f"Field {field.field_index}",
            "css": f"mtf-field-{field.field_index % _CANDIDATE_MTF_FIELD_CLASS_COUNT}",
        }
        for field in mtf.fields
    ]


def _candidate_mtf_caption(mtf: MTFResult, max_freq: float) -> str:
    return (
        f"Sagittal solid / tangential dashed per field; grey dashed = diffraction limit. "
        f"Plotted 0-{max_freq:.0f} lp/mm on the full 0-1 modulation scale; "
        f"diffraction cutoff {mtf.cutoff_freq_lp_per_mm:.0f} lp/mm."
    )


def _candidate_visuals_context(payload: OpticalSampleData) -> dict[str, object]:
    layout_svg = payload.layout_svg.svg_content
    mtf_svg = _candidate_mtf_svg(payload.mtf)
    finite_freqs = _finite_float_values(payload.mtf.freq_lp_per_mm)
    max_freq = max(finite_freqs) if finite_freqs else 0.0
    return {
        "layout_svg": layout_svg,
        "has_layout_svg": bool(layout_svg.strip()),
        "mtf_svg": mtf_svg,
        "has_mtf": bool(mtf_svg),
        "mtf_provenance": _source_value(payload.mtf.provenance),
        "mtf_legend": _candidate_mtf_legend(payload.mtf) if mtf_svg else [],
        "mtf_caption": _candidate_mtf_caption(payload.mtf, max_freq) if mtf_svg else "",
    }


def _candidate_card_context(sc: orchestration.ScoredCandidate) -> dict[str, object]:
    row = sc.scorecard
    gen = sc.generated
    rank = row.rank
    return {
        "candidate_id": row.candidate_id,
        "mode": row.mode.value,
        "mode_label": _mode_label(row.mode),
        "source_case_id": gen.source_case_id or "(none)",
        "generation_notes": list(gen.generation_notes),
        "visuals": _candidate_visuals_context(gen.payload),
        "codev_post_aut": _candidate_codev_post_aut_context(gen.optical_extras),
        "deviations": [_candidate_deviation_row(dev) for dev in row.target_deviations],
        "image_quality": [
            {"label": label, "value": _fmt_metric(getattr(row.image_quality, attr))}
            for label, attr in _CANDIDATE_IMAGE_QUALITY_ROWS
        ],
        "manufacturability": _candidate_manufacturability_context(row.manufacturability),
        "repeatability": _candidate_repeatability_context(row.repeatability),
        "rank_status": rank.status,
        "rank_status_label": "Ranked" if rank.status == "ranked" else "Withheld",
        "rank_score": formatting.fmt_float(rank.score) if rank.score is not None else None,
        "rank_coverage_pct": formatting.fmt_pct(rank.coverage_pct, precision=0),
        "rank_missing_metrics": ", ".join(rank.missing_metrics) or "(none)",
        "rank_explanation": row.rank_explanation,
    }


def _candidate_mode_badges(
    summary: orchestration.CandidateSetSummary,
) -> list[dict[str, object]]:
    return [
        {"mode": mode.value, "label": _mode_label(mode), "count": count}
        for mode, count in summary.mode_counts.items()
    ]


def _candidate_requirement_rows(target: orchestration.TargetSpec) -> list[dict[str, str]]:
    return [
        {"label": "Scenario", "value": target.scenario.value},
        {"label": "EFL (mm)", "value": _fmt_optional_target(target.efl_mm)},
        {"label": "FOV (deg)", "value": _fmt_optional_target(target.fov_deg, precision=1)},
        {"label": "F-number", "value": formatting.fmt_float(target.fnum)},
        {"label": "Image height (mm)", "value": _fmt_optional_target(target.image_height_mm)},
        {
            "label": "Max total track (mm)",
            "value": _fmt_optional_target(target.max_total_track_mm),
        },
        {
            "label": "Element count",
            "value": formatting.fmt_optional_int(target.n_elements),
        },
        {"label": "Max weight (g)", "value": _fmt_optional_target(target.max_weight_g)},
        {"label": "Manufacturing tier", "value": target.manufacturing_tier or "(unspecified)"},
        {"label": "Priority", "value": target.priority or "(unspecified)"},
    ]


def _fmt_form_value(value: float | int | None) -> str:
    """Render a target field for an editable form input's `value` attribute —
    "" (empty, unconstrained) for `None` rather than the literal string
    "None"."""
    return "" if value is None else str(value)


def _candidate_adjust_form_context(target: orchestration.TargetSpec) -> dict[str, str]:
    """Pre-fill values for the candidate-set page's "adjust & rerun" form
    (P17 sub-item 1) — echoes the batch's own `TargetSpec` so a reviewer edits
    the exact numbers that produced this candidate set, not wizard defaults."""
    return {
        "efl_mm": _fmt_form_value(target.efl_mm),
        "fnum": _fmt_form_value(target.fnum),
        "fov_deg": _fmt_form_value(target.fov_deg),
        "image_height_mm": _fmt_form_value(target.image_height_mm),
        "max_total_track_mm": _fmt_form_value(target.max_total_track_mm),
        "n_elements": _fmt_form_value(target.n_elements),
    }


def _candidate_set_context(
    *,
    result: Mapping[str, object],
    progress: Mapping[str, object],
) -> dict[str, object]:
    candidate_set_payload = result.get("candidate_set")
    if not isinstance(candidate_set_payload, Mapping):
        raise ValueError("candidate orchestration job has invalid candidate_set payload")
    candidate_set = orchestration.CandidateSet.model_validate(candidate_set_payload)
    summary = candidate_set.summary
    ri_available = summary.candidate_count - summary.ri_missing_count
    ri_available_label = (
        f"{ri_available}/{summary.candidate_count}" if summary.candidate_count else "0/0"
    )
    requirement = result.get("requirement")
    scenario_value = str(result.get("scenario", candidate_set.target.scenario.value))
    return {
        "product_name": "Atelier",
        "scenario": scenario_value,
        "scenario_label_en": scenario_value.replace("-", " ").title(),
        "requirement": str(requirement) if requirement not in {None, ""} else None,
        "job_id": progress.get("job_id", ""),
        "honesty_banner": candidate_set.honesty_banner,
        "requirement_rows": _candidate_requirement_rows(candidate_set.target),
        "summary": {
            "candidate_count": summary.candidate_count,
            "ranked_count": summary.ranked_count,
            "withheld_count": summary.withheld_count,
            "ri_available_label": ri_available_label,
            "notes": list(summary.notes),
        },
        "mode_badges": _candidate_mode_badges(summary),
        "candidates": [_candidate_card_context(sc) for sc in candidate_set.candidates],
        "expert_rows": [
            {"candidate_id": sc.scorecard.candidate_id} for sc in candidate_set.candidates
        ],
        "adjust_form": _candidate_adjust_form_context(candidate_set.target),
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


@app.exception_handler(StarletteHTTPException)
async def web_http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> Response:
    if _is_api_request(request):
        return await http_exception_handler(request, exc)
    return _web_error_response(
        request,
        exc.status_code,
        detail=_format_error_detail(exc.detail),
    )


@app.exception_handler(RequestValidationError)
async def web_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> Response:
    if _is_api_request(request):
        return await request_validation_exception_handler(request, exc)
    return _web_error_response(
        request,
        _HTTP_422_UNPROCESSABLE_CONTENT,
        detail=_format_validation_errors(exc),
    )


@app.exception_handler(Exception)
async def web_unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    if _is_api_request(request):
        return PlainTextResponse("Internal Server Error", status_code=500)
    logger.exception("web_unhandled_exception", path=request.url.path)
    return _web_error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


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
                ("Batches", "/batches"),
                ("API", "/docs"),
            ),
            "example_requirements": EXAMPLE_REQUIREMENTS,
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

    result = await _compute_result_summary_job(
        _result_job_payload(
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
            requirement=requirement,
        )
    )
    return templates.TemplateResponse(
        request,
        "result_summary.html",
        _result_summary_context(result=result, progress=progress),
    )


@app.post("/jobs", include_in_schema=False, tags=["web"])
async def submit_result_job(
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
) -> RedirectResponse:
    payload = _result_job_payload(
        scenario=scenario,
        scenario_label_en=scenario_label_en,
        focal_length_mm=focal_length_mm,
        f_number=f_number,
        field_of_view_deg=field_of_view_deg,
        image_height_mm=image_height_mm,
        total_track_mm=total_track_mm,
        airy_disc_diameter_um=airy_disc_diameter_um,
        cutoff_freq_lp_per_mm=cutoff_freq_lp_per_mm,
        n_elements=n_elements,
        wavelength_nm=wavelength_nm,
        requirement=requirement,
    )
    job_id = optical.job_store.submit(ResultSummaryEngine(), payload)
    return RedirectResponse(
        url=f"/jobs/{job_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/candidates", include_in_schema=False, tags=["web"])
async def submit_candidate_job(
    scenario: Annotated[Scenario, Form()],
    scenario_label_en: Annotated[str, Form(min_length=1, max_length=100)],
    focal_length_mm: Annotated[float, Form(gt=0)],
    f_number: Annotated[float, Form(gt=0)],
    field_of_view_deg: Annotated[float, Form(gt=0, le=180)],
    image_height_mm: Annotated[float, Form(gt=0)],
    n_elements: Annotated[int | None, Form(ge=2, le=20)] = None,
    max_total_track_mm: Annotated[float | None, Form(gt=0)] = None,
    total_track_mm: Annotated[float | None, Form(gt=0)] = None,
    airy_disc_diameter_um: Annotated[float | None, Form(gt=0)] = None,
    cutoff_freq_lp_per_mm: Annotated[float | None, Form(gt=0)] = None,
    wavelength_nm: Annotated[float, Form(gt=0)] = 550.0,
    requirement: Annotated[str | None, Form(max_length=2000)] = None,
    repeat_runs: Annotated[int, Form()] = 1,
) -> RedirectResponse:
    # `scenario_label_en` / `total_track_mm` / `airy_disc_diameter_um` /
    # `cutoff_freq_lp_per_mm` / `wavelength_nm` are accepted (not used) so this
    # route can share the exact same hidden-field form as `/jobs` — the
    # wizard_confirm page posts the identical confirmed-parameters form to
    # either endpoint via a second submit button's `formaction`. They default
    # to `None`/550.0 (rather than staying required) so the candidate-set
    # page's "adjust & rerun" form (P17 sub-item 1) — which has no wizard
    # derived total-track/Airy-disc/cutoff estimates to echo back — can post
    # a smaller field set without fabricating placeholder values for fields
    # this route never reads.
    #
    # `max_total_track_mm` is different: it IS consumed (a real customer TTL
    # ceiling from the adjust-and-rerun form) — see `_candidate_job_payload` /
    # `_target_spec_from_candidate_payload`. The wizard form never sends it,
    # so it defaults `None` there (honest "no ceiling" gap, unchanged).
    _validate_finite_form_numbers_or_400(
        focal_length_mm=focal_length_mm,
        f_number=f_number,
        field_of_view_deg=field_of_view_deg,
        image_height_mm=image_height_mm,
        max_total_track_mm=max_total_track_mm,
    )
    _validate_candidate_target_or_400(
        scenario,
        efl_mm=focal_length_mm,
        f_number=f_number,
        fov_deg=field_of_view_deg,
        image_height_mm=image_height_mm,
        n_elements=n_elements,
    )
    if not 1 <= repeat_runs <= 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_repeat_runs",
                "message": f"repeat_runs must be between 1 and 3, got {repeat_runs}",
            },
        )
    job_id = uuid4().hex
    artifact_dir = settings.job_artifacts_dir / job_id
    payload = _candidate_job_payload(
        scenario=scenario,
        focal_length_mm=focal_length_mm,
        f_number=f_number,
        field_of_view_deg=field_of_view_deg,
        image_height_mm=image_height_mm,
        max_total_track_mm=max_total_track_mm,
        n_elements=n_elements,
        requirement=requirement,
        repeat_runs=repeat_runs,
        artifact_dir=artifact_dir,
    )
    job_id = optical.job_store.submit(CandidateOrchestrationEngine(), payload, job_id=job_id)
    return RedirectResponse(
        url=f"/jobs/{job_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/results/{job_id}", response_class=HTMLResponse, tags=["web"])
async def result_summary_from_job(request: Request, job_id: str) -> HTMLResponse:
    try:
        record = optical.job_store.get(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job_not_found", "job_id": job_id},
        ) from exc
    if not _is_result_summary_job(record):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "result_not_found", "job_id": job_id},
        )
    if record.status is not JobStatus.SUCCEEDED or record.result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "result_not_ready",
                "job_id": job_id,
                "status": record.status.value,
            },
        )
    return templates.TemplateResponse(
        request,
        "result_summary.html",
        _result_summary_context(
            result=record.result,
            progress=_job_progress_context(record),
        ),
    )


def _load_succeeded_candidate_set_record(job_id: str) -> JobRecord:
    """Shared job lookup + status gate for every `/candidates/{job_id}*`
    route (HTML render, xlsx export, per-candidate zip bundle) — unknown job
    or wrong engine -> 404, still queued/running -> 409, so all three
    surfaces fail identically instead of drifting apart."""
    try:
        record = optical.job_store.get(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job_not_found", "job_id": job_id},
        ) from exc
    if not _is_candidate_orchestration_job(record):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "candidate_set_not_found", "job_id": job_id},
        )
    if record.status is not JobStatus.SUCCEEDED or record.result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "result_not_ready",
                "job_id": job_id,
                "status": record.status.value,
            },
        )
    return record


def _candidate_set_from_record(record: JobRecord) -> orchestration.CandidateSet:
    assert record.result is not None  # guaranteed by _load_succeeded_candidate_set_record
    candidate_set_payload = record.result.get("candidate_set")
    if not isinstance(candidate_set_payload, Mapping):
        raise ValueError("candidate orchestration job has invalid candidate_set payload")
    return orchestration.CandidateSet.model_validate(candidate_set_payload)


def _safe_download_filename(value: str) -> str:
    """Collapse anything outside a conservative filename-safe charset (a
    `candidate_id` embeds `::` — invalid in a Windows filename) into `_`, so
    a suggested download name is safe on every OS the demo runs on."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


#: P17 对抗审 MINOR：导出物在请求线程内整包内存构建、一次性 Response —— 给
#: 产物加一个路由级大小闸，异常膨胀的 payload（今天 n=4 + 小 ZMX 远够不着，
#: 但 job result 没有结构性上限）拒绝为 413 而不是悄悄吃掉演示机内存/带宽。
_MAX_EXPORT_RESPONSE_BYTES = 50 * 1024 * 1024


def _guard_export_size_or_413(content: bytes, *, artifact: str, resource_id: str) -> None:
    # `resource_id` is a job_id for candidate-set exports, a batch_id for
    # P18 batch exports — generalized (was `job_id`) once a second, non-job
    # caller (`batch_export_xlsx`) needed this same guard.
    if len(content) > _MAX_EXPORT_RESPONSE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "error": "export_too_large",
                "artifact": artifact,
                "resource_id": resource_id,
                "size_bytes": len(content),
                "limit_bytes": _MAX_EXPORT_RESPONSE_BYTES,
                "message": (
                    f"{artifact} export is {len(content)} bytes, over the "
                    f"{_MAX_EXPORT_RESPONSE_BYTES}-byte route limit"
                ),
            },
        )


@app.get("/candidates/{job_id}", response_class=HTMLResponse, tags=["web"])
async def candidate_set_from_job(request: Request, job_id: str) -> HTMLResponse:
    record = _load_succeeded_candidate_set_record(job_id)
    return templates.TemplateResponse(
        request,
        "candidate_set.html",
        _candidate_set_context(
            result=record.result,
            progress=_job_progress_context(record),
        ),
    )


@app.get("/candidates/{job_id}/export.xlsx", include_in_schema=False, tags=["web"])
async def candidate_set_export_xlsx(job_id: str) -> Response:
    """P17 sub-item 2 ①: spec-sheet xlsx for the whole candidate set — built
    from the exact same validated `CandidateSet` the HTML page renders (no
    second computation)."""
    record = _load_succeeded_candidate_set_record(job_id)
    candidate_set = _candidate_set_from_record(record)
    assert record.result is not None
    requirement = record.result.get("requirement")
    workbook_bytes = orchestration.build_candidate_set_workbook(
        candidate_set,
        job_id=job_id,
        requirement=str(requirement) if requirement not in {None, ""} else None,
    )
    _guard_export_size_or_413(workbook_bytes, artifact="workbook", resource_id=job_id)
    filename = _safe_download_filename(f"atelier-candidates-{job_id}.xlsx")
    return Response(
        content=workbook_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/candidates/{job_id}/{candidate_id}/bundle.zip", include_in_schema=False, tags=["web"])
async def candidate_bundle_zip(job_id: str, candidate_id: str) -> Response:
    """P17 sub-item 2 ②: one candidate's ZMX + reproduction .seq + README
    download bundle, built from the same validated `CandidateSet` (no second
    computation) — see `app.core.orchestration.export` for the fail-closed
    contract when the underlying ZMX/.seq isn't resolvable."""
    record = _load_succeeded_candidate_set_record(job_id)
    candidate_set = _candidate_set_from_record(record)
    scored = next(
        (sc for sc in candidate_set.candidates if sc.scorecard.candidate_id == candidate_id),
        None,
    )
    if scored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "candidate_not_found", "job_id": job_id, "candidate_id": candidate_id},
        )
    zip_bytes = orchestration.build_candidate_bundle_zip(scored, target=candidate_set.target)
    _guard_export_size_or_413(zip_bytes, artifact="bundle", resource_id=job_id)
    filename = _safe_download_filename(f"atelier-candidate-{candidate_id}.zip")
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



# ---------------------------------------------------------------------------
# P18 batch archive management (/batches, /batches/{batch_id})
#
# Batch jobs are produced offline by `scripts/p18_night_batch.py`
# (`app.core.batch_runner.run_batch`) — a separate execution path from the
# in-memory `optical.job_store` the rest of this file's web routes read
# from. There is deliberately no `/jobs/{job_id}` for a batch job: the two
# systems don't share job ids, and every page here reads straight off the
# P18-1 archive (`batch_archive_store`), never `optical.job_store`.
# ---------------------------------------------------------------------------

_BATCH_STATUS_LABELS: dict[str, str] = {
    "running": "Running",
    "completed": "Completed",
    "budget_exhausted": "Budget exhausted (resumable)",
    "aborted": "Aborted",
}

_JOB_STATUS_LABELS: dict[str, str] = {
    "queued": "Queued",
    "running": "Running",
    "succeeded": "Succeeded",
    "failed": "Failed",
}

_FAILURE_CATEGORY_LABELS: dict[str, str] = {
    "preflight": "Preflight (invalid target spec)",
    "engine": "Engine",
    "timeout": "Timeout",
    "exception": "Unexpected exception",
}


def _batch_success_rate_label(jobs: list[BatchJobRecord]) -> str:
    if not jobs:
        return "0/0"
    succeeded = sum(1 for j in jobs if j.status == "succeeded")
    return f"{succeeded}/{len(jobs)}"


def _load_batch_or_404(batch_id: str) -> BatchRecord:
    try:
        return batch_archive_store.get_batch(batch_id)
    except BatchArchiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "batch_not_found", "batch_id": batch_id},
        ) from exc


def _batch_list_row(batch: BatchRecord) -> dict[str, object]:
    jobs = batch_archive_store.list_jobs(batch.batch_id)
    return {
        "batch_id": batch.batch_id,
        "created_at": batch.created_at,
        "status": batch.status,
        "status_label": _BATCH_STATUS_LABELS.get(batch.status, batch.status),
        "engine": batch.engine,
        "target_source": batch.target_source,
        "target_count": batch.target_count,
        "attempted_count": len(jobs),
        "success_rate_label": _batch_success_rate_label(jobs),
    }


def _batches_list_context() -> dict[str, object]:
    return {
        "product_name": "Atelier",
        "rows": [_batch_list_row(b) for b in batch_archive_store.list_batches()],
    }


def _job_candidate_rows(batch_id: str, job: BatchJobRecord) -> list[dict[str, object]]:
    """Load the job's persisted `CandidateSet` (if any) straight off disk —
    `candidate_set_pointer` is a path, not a URL, this is the only surface
    that ever reads it. Missing/corrupt pointer -> `[]` (fail closed, no
    verdict rows rendered rather than a 500)."""
    if job.candidate_set_pointer is None:
        return []
    path = Path(job.candidate_set_pointer)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidate_set = orchestration.CandidateSet.model_validate(payload)
    except (json.JSONDecodeError, ValueError):
        return []

    rows: list[dict[str, object]] = []
    for sc in candidate_set.candidates:
        candidate_id = sc.scorecard.candidate_id
        verdict = batch_archive_store.get_verdict(batch_id, job.job_id, candidate_id)
        rank = sc.scorecard.rank
        rows.append(
            {
                "candidate_id": candidate_id,
                "mode_label": _mode_label(sc.mode),
                "rank_status": rank.status,
                "rank_score": formatting.fmt_float(rank.score) if rank.score is not None else "N/A",
                "coverage_pct": formatting.fmt_pct(rank.coverage_pct, precision=0),
                "verdict": (
                    {
                        "verdict_text": verdict.verdict_text,
                        "reviewer": verdict.reviewer,
                        "recorded_at": verdict.recorded_at,
                        "note": verdict.note or "",
                    }
                    if verdict is not None
                    else None
                ),
            }
        )
    return rows


def _job_row_context(batch_id: str, job: BatchJobRecord) -> dict[str, object]:
    result_summary = job.result_summary or {}
    candidates = _job_candidate_rows(batch_id, job)
    return {
        "job_id": job.job_id,
        "target_index": job.target_index,
        "target_label": job.target_label,
        "status": job.status,
        "status_label": _JOB_STATUS_LABELS.get(job.status, job.status),
        "failure_category_label": (
            _FAILURE_CATEGORY_LABELS.get(job.failure.category, job.failure.category)
            if job.failure is not None
            else None
        ),
        "failure_message": job.failure.message if job.failure is not None else None,
        "candidate_count": result_summary.get("candidate_count"),
        "ranked_count": result_summary.get("ranked_count"),
        "candidates": candidates,
        "verdict_recorded_count": sum(1 for c in candidates if c["verdict"] is not None),
    }


def _batch_detail_context(batch: BatchRecord, jobs: list[BatchJobRecord]) -> dict[str, object]:
    job_rows = [_job_row_context(batch.batch_id, job) for job in jobs]
    total_candidates = sum(len(row["candidates"]) for row in job_rows)
    total_verdicts = sum(row["verdict_recorded_count"] for row in job_rows)
    return {
        "product_name": "Atelier",
        "batch": {
            "batch_id": batch.batch_id,
            "created_at": batch.created_at,
            "updated_at": batch.updated_at,
            "status": batch.status,
            "status_label": _BATCH_STATUS_LABELS.get(batch.status, batch.status),
            "engine": batch.engine,
            "target_source": batch.target_source,
            "target_count": batch.target_count,
            "notes": list(batch.notes),
        },
        "attempted_count": len(jobs),
        "success_rate_label": _batch_success_rate_label(jobs),
        "verdict_progress_label": f"{total_verdicts}/{total_candidates}" if total_candidates else "0/0",
        "jobs": job_rows,
    }


@app.get("/batches", response_class=HTMLResponse, tags=["web"])
async def batches_list(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "batch_list.html", _batches_list_context())


@app.get("/batches/{batch_id}", response_class=HTMLResponse, tags=["web"])
async def batch_detail(request: Request, batch_id: str) -> HTMLResponse:
    batch = _load_batch_or_404(batch_id)
    jobs = batch_archive_store.list_jobs(batch_id)
    return templates.TemplateResponse(
        request, "batch_detail.html", _batch_detail_context(batch, jobs)
    )


@app.post(
    "/batches/{batch_id}/jobs/{job_id}/verdicts", include_in_schema=False, tags=["web"]
)
async def submit_batch_verdict(
    batch_id: str,
    job_id: str,
    candidate_key: Annotated[str, Form(min_length=1)],
    verdict_text: Annotated[str, Form(min_length=1, max_length=4000)],
    reviewer: Annotated[str, Form(min_length=1, max_length=200)],
    note: Annotated[str | None, Form(max_length=2000)] = None,
) -> RedirectResponse:
    """[EXPERT] 判定权红线：`verdict_text`/`reviewer` are required, non-blank
    form fields — nothing here defaults, predicts, or backfills a verdict.
    The timestamp is always server-generated (never trusts a client value)."""
    _load_batch_or_404(batch_id)
    try:
        verdict = ExpertVerdict(
            job_id=job_id,
            candidate_key=candidate_key,
            verdict_text=verdict_text,
            reviewer=reviewer,
            recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
            note=note or None,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_verdict", "message": str(exc)},
        ) from exc
    try:
        batch_archive_store.put_verdict(verdict, batch_id=batch_id)
    except BatchArchiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job_not_found", "batch_id": batch_id, "job_id": job_id},
        ) from exc
    return RedirectResponse(url=f"/batches/{batch_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/batches/{batch_id}/export.xlsx", include_in_schema=False, tags=["web"])
async def batch_export_xlsx(batch_id: str) -> Response:
    batch = _load_batch_or_404(batch_id)
    jobs = batch_archive_store.list_jobs(batch_id)
    verdicts = batch_archive_store.list_verdicts(batch_id)
    workbook_bytes = build_batch_workbook(batch, jobs, verdicts)
    _guard_export_size_or_413(workbook_bytes, artifact="batch-workbook", resource_id=batch_id)
    filename = _safe_download_filename(f"atelier-batch-{batch_id}.xlsx")
    return Response(
        content=workbook_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
