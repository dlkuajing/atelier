"""Precompute offline demo analysis bundles under data/demo_cache/.

Run:
    python scripts/precompute_demo_cache.py 3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import math
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api import wizard  # noqa: E402
from app.core.aberration import compute_mtf  # noqa: E402
from app.core.demo_cache import (  # noqa: E402
    DEFAULT_DEMO_CASE_IDS,
    DEMO_CACHE_DIR,
    DemoAnalysisBundle,
    build_demo_cache_bundle_for_case,
    write_demo_cache_bundle,
)
from app.core.engines.codev import probe_code_v_installation  # noqa: E402
from app.core.engines.codev_batch import CodeVBatchError, resolve_default_codev_executable  # noqa: E402
from app.core.engines.codev_optimize import CodeVOptimizeResult, run_codev_optimize  # noqa: E402
from app.core.mtf_fields import MTF_FIELD_FALLBACK_SETS  # noqa: E402
from app.core.zmx_ingest import ZMX_AMMO_DIR, load_normalized_zmx  # noqa: E402

_CODEV_CACHE_WORK_ROOT = ROOT / ".tmp" / "demo-cache-codev"
_CODEV_CACHE_TIMEOUT_SECONDS = 240.0
_CODEV_CACHE_MAX_CYCLES = 3
_CODEV_CACHE_MIN_CYCLES = 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Precompute Atelier demo analysis cache bundles.",
    )
    parser.add_argument(
        "case_ids",
        nargs="*",
        help="Generated case ids, with or without .json/.zmx suffix.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEMO_CACHE_DIR,
        help=f"Output cache directory (default: {DEMO_CACHE_DIR}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable summary.",
    )
    parser.add_argument(
        "--skip-codev",
        action="store_true",
        help="Skip CODE V refinement even when CODE V is available.",
    )
    return parser.parse_args()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_zmx_path(bundle: DemoAnalysisBundle) -> Path:
    path = ZMX_AMMO_DIR / bundle.source_zmx
    if not path.is_file():
        raise FileNotFoundError(f"source ZMX not found: {path}")
    return path


def _executive_summary_request(bundle: DemoAnalysisBundle) -> wizard.ExecutiveSummaryRequest:
    sample = bundle.sample
    metadata = sample.metadata
    scenario = metadata.scenario if metadata is not None else bundle.request.scenario
    scenario_label_en = scenario.value.replace("-", " ").title()
    return wizard.ExecutiveSummaryRequest(
        scenario=scenario,
        scenario_label_en=scenario_label_en,
        focal_length_mm=sample.paraxial.effective_focal_length_mm,
        f_number=sample.paraxial.f_number,
        field_of_view_deg=metadata.fov_deg if metadata is not None else bundle.request.field_of_view_deg,
        image_height_mm=bundle.request.image_height_mm,
        n_elements=metadata.n_pieces if metadata is not None else bundle.request.n_elements,
        wavelength_nm=bundle.request.wavelength_nm,
        total_track_mm=sample.paraxial.total_track_mm,
        airy_disc_diameter_um=sample.mtf.airy_disc_diameter_um,
        cutoff_freq_lp_per_mm=sample.mtf.cutoff_freq_lp_per_mm,
        design_assessment=sample.design_assessment,
    )


async def _with_executive_summary(bundle: DemoAnalysisBundle) -> DemoAnalysisBundle:
    request = _executive_summary_request(bundle)
    try:
        summary = await wizard.generate_executive_summary(request)
    except Exception as exc:  # noqa: BLE001 - precompute must still write offline bundles.
        summary = wizard._deterministic_executive_summary(
            request,
            model="precompute-fallback",
            fallback_reason=f"executive_summary_precompute_failure: {type(exc).__name__}",
        )
    return bundle.model_copy(
        update={"executive_summary": summary.model_dump(mode="json")},
        deep=True,
    )


def _codev_run_evidence(
    *,
    bundle: DemoAnalysisBundle,
    result: CodeVOptimizeResult,
    run_started_at_utc: str,
) -> dict[str, object]:
    installation = probe_code_v_installation()
    codev_version = installation.version if installation is not None else None
    return {
        "run_started_at_utc": run_started_at_utc,
        "codev_executable": str(result.batch.executable),
        "codev_version": codev_version,
        "codev_installation": installation.describe() if installation is not None else None,
        "returncode": result.batch.returncode,
        "duration_seconds": result.batch.duration_seconds,
        "source_zmx_sha256": bundle.source_zmx_sha256,
        "sequence_sha256": _sha256_file(result.batch.sequence_path),
        "result_sha256": _sha256_file(result.batch.result_path),
        "optimized_readout_sha256": _sha256_file(result.optimized_readout_path),
        "optimized_zmx_sha256": _sha256_file(result.optimized_zmx),
        "sequence_filename": result.batch.sequence_path.name,
        "result_filename": result.batch.result_path.name,
        "optimized_readout_filename": result.optimized_readout_path.name,
        "optimized_zmx_filename": result.optimized_zmx.name,
    }


def _mtf_has_nan_payload(payload: dict[str, object]) -> bool:
    for value in payload.get("rms_spot_radius_um_by_field", []):
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return True
    for field in payload.get("fields", []):
        if not isinstance(field, dict):
            continue
        for value in (*field.get("sagittal", []), *field.get("tangential", [])):
            if value is None or (isinstance(value, float) and math.isnan(value)):
                return True
    return False


def _refined_mtf_payload(bundle: DemoAnalysisBundle, result: CodeVOptimizeResult) -> dict[str, object]:
    optic = load_normalized_zmx(result.optimized_zmx)
    fov_deg = bundle.sample.metadata.fov_deg if bundle.sample.metadata is not None else bundle.request.field_of_view_deg
    half_fov = fov_deg / 2.0
    last_error: Exception | None = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for fractions in MTF_FIELD_FALLBACK_SETS:
            optic.set_field_type("angle")
            optic.fields.fields.clear()
            for fraction in fractions:
                optic.add_field(y=half_fov * fraction)
            with contextlib.suppress(Exception):
                optic.ray_tracer.set_aiming("robust", max_iter=20)
            try:
                payload = compute_mtf(
                    optic,
                    wavelength_nm=bundle.request.wavelength_nm,
                ).model_dump(mode="json")
            except Exception as exc:  # noqa: BLE001 - fallback tries smaller field sets.
                last_error = exc
                continue
            if not _mtf_has_nan_payload(payload):
                return payload
            last_error = RuntimeError(f"refined MTF returned NaN at field set {fractions}")
    raise RuntimeError(f"refined MTF unusable for all field sets: {last_error}")


def _codev_artifact_from_result(
    *,
    bundle: DemoAnalysisBundle,
    result: CodeVOptimizeResult,
    run_started_at_utc: str,
) -> dict[str, object]:
    artifact = result.summary.describe()
    artifact.update(
        {
            "artifact_schema": "atelier-demo-codev-artifact-v1",
            "seed_mtf": bundle.sample.mtf.model_dump(mode="json"),
            "refined_mtf": _refined_mtf_payload(bundle, result),
            "cross_validation_status": "rebuilt-zmx-ingested",
            "cross_validation_provenance": "codev-cross-validated",
            "ingested_efl_mm": result.ingested_efl_mm,
            "run_evidence": _codev_run_evidence(
                bundle=bundle,
                result=result,
                run_started_at_utc=run_started_at_utc,
            ),
        }
    )
    return artifact


def _with_codev_artifact(bundle: DemoAnalysisBundle) -> tuple[DemoAnalysisBundle, str]:
    executable = resolve_default_codev_executable()
    if not executable.is_file():
        return bundle, "skipped:codev-executable-missing"

    work_dir = _CODEV_CACHE_WORK_ROOT / bundle.cache_key
    run_started_at_utc = datetime.now(UTC).isoformat()
    try:
        result = run_codev_optimize(
            source_zmx=_source_zmx_path(bundle),
            work_dir=work_dir,
            executable=executable,
            timeout_seconds=_CODEV_CACHE_TIMEOUT_SECONDS,
            max_cycles=_CODEV_CACHE_MAX_CYCLES,
            min_cycles=_CODEV_CACHE_MIN_CYCLES,
        )
    except CodeVBatchError as exc:
        return bundle, f"skipped:{exc.kind}"

    artifact = _codev_artifact_from_result(
        bundle=bundle,
        result=result,
        run_started_at_utc=run_started_at_utc,
    )
    return bundle.model_copy(update={"codev_artifact": artifact}, deep=True), "attached"


def main() -> int:
    args = _parse_args()
    case_ids = tuple(args.case_ids) or DEFAULT_DEMO_CASE_IDS
    written: list[dict[str, str]] = []

    for case_id in case_ids:
        bundle = build_demo_cache_bundle_for_case(case_id)
        bundle = asyncio.run(_with_executive_summary(bundle))
        codev_status = "skipped:requested"
        if not args.skip_codev:
            bundle, codev_status = _with_codev_artifact(bundle)
        path = write_demo_cache_bundle(bundle, cache_dir=args.cache_dir)
        item = {
            "case_id": bundle.source_case_id,
            "cache_key": bundle.cache_key,
            "path": str(path),
            "codev_artifact": codev_status,
        }
        written.append(item)
        if not args.json:
            print(
                f"OK {item['case_id']} -> {item['path']} ({item['codev_artifact']})",
                flush=True,
            )

    if args.json:
        print(json.dumps({"written": written}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
