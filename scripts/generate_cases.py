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
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.simplefilter("ignore")

from app.core.case_library import CASES_DIR, build_sample_from_optic  # noqa: E402
from app.core.zmx_ingest import ZMX_AMMO_DIR, load_normalized_zmx  # noqa: E402
from tests.data.zmx_manifest import ZMX_AMMO  # noqa: E402

SEED_IMH_OVERRIDES_PATH = (
    Path(__file__).resolve().parents[1] / "tests" / "data" / "seed_imh_overrides.json"
)
LIGHTWEIGHT_INTAKE_BATCH_PREFIXES = ("DATA-06", "DATA-09d1")


def _uses_lightweight_artifacts(entry: dict) -> bool:
    return str(entry.get("intake_batch", "")).startswith(LIGHTWEIGHT_INTAKE_BATCH_PREFIXES)


def _load_seed_imh_overrides() -> dict[str, float]:
    if not SEED_IMH_OVERRIDES_PATH.exists():
        return {}
    records = json.loads(SEED_IMH_OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {str(case_id): float(value) for case_id, value in records.items()}


def main() -> None:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    index: list[dict] = []
    errors: list[tuple[str, str]] = []
    seed_imh_overrides = _load_seed_imh_overrides()

    for a in ZMX_AMMO:
        fn = a["filename"]
        try:
            optic = load_normalized_zmx(ZMX_AMMO_DIR / fn)
            sample = build_sample_from_optic(
                optic,
                source_zmx=fn,
                n_pieces=a["n_pieces"],
                nominal_efl_mm=a["nominal_efl_mm"],
                nominal_fov_deg=a["nominal_fov_deg"],
                lightweight_artifacts=_uses_lightweight_artifacts(a),
            )
            case_id = fn.rsplit(".", 1)[0]
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

    (CASES_DIR / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False))
    print(f"\n=== generated {len(index)} cases + index.json; failed {len(errors)} ===", flush=True)
    for fn, err in errors:
        print(f"  FAIL {fn}: {err}", flush=True)


if __name__ == "__main__":
    main()
