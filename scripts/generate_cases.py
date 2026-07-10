"""Offline: generate the OpticalSampleData case JSON + index.json (phase v2-02).

Reads the real ammo zmx (tests/data/zmx_manifest), runs the full Optiland
pipeline (paraxial / surfaces / trace / MTF / layout-SVG) via
case_library.build_sample_from_optic, and writes one JSON per design to
app/data/optical_cases/ plus a compact index.json for the retrieval layer.

Run:  cd lumira-backend && uv run python scripts/generate_cases.py
"""

from __future__ import annotations

import json
import sys
import threading
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.simplefilter("ignore")

from app.core.case_library import CASES_DIR, build_sample_from_optic  # noqa: E402
from app.core.optical_sample import OpticalSampleData  # noqa: E402
from app.core.zmx_ingest import ZMX_AMMO_DIR, load_normalized_zmx  # noqa: E402
from tests.data.zmx_manifest import ZMX_AMMO  # noqa: E402

SEED_IMH_OVERRIDES_PATH = (
    Path(__file__).resolve().parents[1] / "tests" / "data" / "seed_imh_overrides.json"
)
LIGHTWEIGHT_INTAKE_BATCH_PREFIXES = ("DATA-06", "DATA-09d1", "DATA-10", "P12")
# Full-library regeneration hazard: at least one pre-existing DATA-06f design
# (US-11940597-B2-e2, discovered during the DATA-10a base-library-fill batch)
# hangs inside build_sample_from_optic even on the lightweight path -- no
# amount of waiting resolves it (confirmed hung past 60s in isolation). A
# single hung design would otherwise block the *entire* regeneration forever,
# so every build runs in a daemon thread with a hard wall-clock budget.
BUILD_TIMEOUT_S = 90.0


def _build_with_timeout(optic, **kwargs):
    """Run build_sample_from_optic with a timeout; returns (sample, error)."""
    holder: dict = {}

    def _worker() -> None:
        try:
            holder["sample"] = build_sample_from_optic(optic, **kwargs)
        except Exception as exc:  # noqa: BLE001
            holder["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=BUILD_TIMEOUT_S)
    if thread.is_alive():
        return None, TimeoutError(f"build_sample_from_optic exceeded {BUILD_TIMEOUT_S:.0f}s")
    if "error" in holder:
        return None, holder["error"]
    return holder["sample"], None


def _uses_lightweight_artifacts(entry: dict) -> bool:
    return str(entry.get("intake_batch", "")).startswith(LIGHTWEIGHT_INTAKE_BATCH_PREFIXES)


def _load_seed_imh_overrides() -> dict[str, float]:
    if not SEED_IMH_OVERRIDES_PATH.exists():
        return {}
    records = json.loads(SEED_IMH_OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {str(case_id): float(value) for case_id, value in records.items()}


def _reused_index_entry(case_id: str, fn: str, a: dict, seed_imh_overrides: dict) -> dict | None:
    """Fall back to a case's last-known-good JSON when a fresh build times out.

    Preserves library size across an unrelated build hazard (see
    BUILD_TIMEOUT_S) instead of silently dropping a previously-good seed from
    index.json just because this particular regeneration run couldn't
    re-build it in time.
    """
    path = CASES_DIR / f"{case_id}.json"
    if not path.exists():
        return None
    sample = OpticalSampleData.model_validate_json(path.read_text(encoding="utf-8"))
    if sample.metadata is None:
        return None
    m = sample.metadata
    image_height_mm = seed_imh_overrides.get(case_id, a["nominal_imh_mm"])
    entry = {
        "case_id": case_id,
        "source_zmx": fn,
        "scenario": m.scenario.value,
        "n_pieces": m.n_pieces,
        "n_imaging": m.n_imaging,
        "n_filter": m.n_filter,
        "efl_mm": sample.paraxial.effective_focal_length_mm,
        "fnum": sample.paraxial.f_number,
        "fov_deg": m.fov_deg,
        "image_height_mm": image_height_mm,
        "materials": m.materials,
        "mtf_max_field_frac": m.mtf_max_field_frac,
        "efl_error_pct": m.efl_error_pct,
    }
    if a.get("intake_batch") is not None:
        entry["intake_batch"] = a["intake_batch"]
    if a.get("image_height_source") is not None:
        entry["image_height_source"] = a["image_height_source"]
    return entry


def main() -> None:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    index: list[dict] = []
    errors: list[tuple[str, str]] = []
    reused: list[str] = []
    seed_imh_overrides = _load_seed_imh_overrides()

    for a in ZMX_AMMO:
        fn = a["filename"]
        case_id = fn.rsplit(".", 1)[0]
        try:
            optic = load_normalized_zmx(ZMX_AMMO_DIR / fn)
            sample, build_error = _build_with_timeout(
                optic,
                source_zmx=fn,
                n_pieces=a["n_pieces"],
                nominal_efl_mm=a["nominal_efl_mm"],
                nominal_fov_deg=a["nominal_fov_deg"],
                lightweight_artifacts=_uses_lightweight_artifacts(a),
            )
            if build_error is not None:
                raise build_error
            (CASES_DIR / f"{case_id}.json").write_text(
                sample.model_dump_json(indent=2, exclude_none=True)
            )
            m = sample.metadata
            image_height_mm = seed_imh_overrides.get(case_id, a["nominal_imh_mm"])
            index_entry = {
                "case_id": case_id,
                "source_zmx": fn,
                "scenario": m.scenario.value,
                "n_pieces": m.n_pieces,
                "n_imaging": m.n_imaging,
                "n_filter": m.n_filter,
                "efl_mm": sample.paraxial.effective_focal_length_mm,
                "fnum": sample.paraxial.f_number,
                "fov_deg": m.fov_deg,
                "image_height_mm": image_height_mm,
                "materials": m.materials,
                "mtf_max_field_frac": m.mtf_max_field_frac,
                "efl_error_pct": m.efl_error_pct,
            }
            if a.get("intake_batch") is not None:
                index_entry["intake_batch"] = a["intake_batch"]
            if a.get("image_height_source") is not None:
                index_entry["image_height_source"] = a["image_height_source"]
            index.append(index_entry)
            print(
                f"  OK {case_id[:42]:42} EFL_err={m.efl_error_pct:4.1f}% "
                f"mtf_to={m.mtf_max_field_frac} img={m.n_imaging} flt={m.n_filter} "
                f"mats={len(m.materials)} {m.scenario.value}",
                flush=True,
            )
        except Exception as e:  # noqa: BLE001
            errors.append((fn, f"{type(e).__name__}: {e}"))
            print(f"  FAIL {fn[:42]:42} {type(e).__name__}: {str(e)[:55]}", flush=True)
            reused_entry = _reused_index_entry(case_id, fn, a, seed_imh_overrides)
            if reused_entry is not None:
                index.append(reused_entry)
                reused.append(fn)
                print(f"  REUSED last-known-good JSON for {case_id[:42]:42}", flush=True)

    (CASES_DIR / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False))
    print(f"\n=== generated {len(index)} cases + index.json; failed {len(errors)} ===", flush=True)
    for fn, err in errors:
        print(f"  FAIL {fn}: {err}", flush=True)
    if reused:
        print(f"reused last-known-good JSON for {len(reused)} designs: {reused}", flush=True)


if __name__ == "__main__":
    main()
