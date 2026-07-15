"""Single-embodiment worker for process-isolated patent conversion."""

from __future__ import annotations

import argparse
import contextlib
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.patent_conversion_process import (  # noqa: E402
    PatentConversionRequest,
    PatentWorkerResponse,
    TraceAuditResult,
    canonical_json_bytes,
    conversion_request_sha256,
)
from app.core.zmx_ingest import load_normalized_zmx  # noqa: E402
from scripts.patent_to_zmx import (  # noqa: E402
    PatentParseError,
    PatentPrescription,
    PatentSurface,
    PatentTraceError,
    write_patent_zmx,
)


def convert_request(
    request: PatentConversionRequest,
    *,
    request_sha256: str,
    output_path: Path,
) -> PatentWorkerResponse:
    """Convert one validated request without inferring any prescription value."""

    prescription_input = request.prescription
    prescription = PatentPrescription(
        patent_id=prescription_input.patent_id,
        embodiment=prescription_input.embodiment,
        focal_length_mm=prescription_input.focal_length_mm,
        f_number=prescription_input.f_number,
        hfov_deg=prescription_input.hfov_deg,
        surfaces=[
            PatentSurface(
                index=surface.index,
                label=surface.label,
                radius_mm=surface.radius_mm,
                thickness_mm=surface.thickness_mm,
                material=surface.material,
                nd=surface.nd,
                vd=surface.vd,
                surface_type=surface.surface_type,
                asphere_coefficients=dict(surface.asphere_coefficients),
            )
            for surface in prescription_input.surfaces
        ],
        unsupported_asphere_terms=list(prescription_input.unsupported_asphere_terms),
    )
    try:
        trace_audit = write_patent_zmx(prescription, output_path)
        optic = load_normalized_zmx(output_path)
        efl_mm = float(optic.paraxial.f2())
        if not math.isfinite(efl_mm):
            raise PatentTraceError("generated ZMX loaded but EFL was not finite")
    except PatentParseError as exc:
        _remove_candidate(output_path)
        return PatentWorkerResponse(
            request_sha256=request_sha256,
            status="quality_rejected",
            reason_code="quality_rejected.invalid_prescription",
            detail=f"{type(exc).__name__}: {exc}",
        )
    except PatentTraceError as exc:
        _remove_candidate(output_path)
        return PatentWorkerResponse(
            request_sha256=request_sha256,
            status="trace_failed",
            reason_code="trace_failed.optical_trace_exception",
            detail=f"{type(exc).__name__}: {exc}",
        )
    except Exception as exc:  # noqa: BLE001 - worker must classify and retain the failure.
        _remove_candidate(output_path)
        return PatentWorkerResponse(
            request_sha256=request_sha256,
            status="trace_failed",
            reason_code="trace_failed.worker_exception",
            detail=f"{type(exc).__name__}: {exc}",
        )

    return PatentWorkerResponse(
        request_sha256=request_sha256,
        status="success",
        reason_code="success.worker_converted",
        detail="deterministic prescription converted and worker-validated",
        efl_mm=efl_mm,
        trace_audit=TraceAuditResult(
            semi_diameters_mm=trace_audit.semi_diameters_mm,
            real_image_height_mm=trace_audit.real_image_height_mm,
            sanity_image_height_mm=trace_audit.sanity_image_height_mm,
            measured_surfaces=trace_audit.measured_surfaces,
            interpolated_surfaces=trace_audit.interpolated_surfaces,
            finite_final_rays=trace_audit.finite_final_rays,
            total_rays=trace_audit.total_rays,
        ),
    )


def _remove_candidate(output_path: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        output_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert one patent embodiment in isolation.")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    request_bytes = args.request.read_bytes()
    request = PatentConversionRequest.model_validate_json(request_bytes)
    response = convert_request(
        request,
        request_sha256=conversion_request_sha256(request),
        output_path=args.output,
    )
    args.response.parent.mkdir(parents=True, exist_ok=True)
    temp_path = args.response.with_name(f".{args.response.name}.tmp")
    temp_path.write_bytes(canonical_json_bytes(response))
    temp_path.replace(args.response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
