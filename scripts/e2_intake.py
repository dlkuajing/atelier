"""E2-01 patent-seed intake QC + manifest tooling (offline, read-only staging).

Batch-0 infrastructure for ingesting the IDMxS patent ZMX seeds. Reads a staging
directory (idmxs_index.jsonl + *.zmx), and for every candidate:

  * counts elements (GLAS-line heuristic),
  * loads + builds the sample through the *current* (E1-02 vignette-robust)
    metric pipeline, so the quality numbers reflect the real optics -- the
    staging preflight_idmxs.json predates E1-02 and carries the vignette
    artifact,
  * scores the image-quality floor (max RMS / min 50 lp/mm MTF / floor gap),
  * validates the embodiment (nominal focal vs backend-computed EFL),
  * categorises main-wide / telephoto / fisheye, and
  * emits ZMX_AMMO-shaped manifest entries.

It also clusters near-duplicates (by parameters and by patent family) and
cross-checks the existing 17-seed library. Nothing here mutates the repo case
library; it produces a report (and, with --manifest-out, a manifest stub) that a
later ingest batch consumes.

Usage:
  cd lumira-backend && uv run python scripts/e2_intake.py \
      --staging-dir /path/to/lens-data-staging [--report-out report.json] \
      [--manifest-out manifest_entries.json]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.simplefilter("ignore")

from app.core.case_library import build_sample_from_optic, load_case_library  # noqa: E402
from app.core.image_quality_floor import image_quality_floor_gap_score  # noqa: E402
from app.core.local_optimizer import mtf_multiband_summary  # noqa: E402
from app.core.optical_sample import OptimizationMetricSnapshot  # noqa: E402
from app.core.zmx_ingest import load_normalized_zmx  # noqa: E402

EMBODIMENT_EFL_TOL_PCT = 5.0
FISHEYE_FOV_DEG = 110.0
TELEPHOTO_EFL_MM = 5.0
TELEPHOTO_FOV_DEG = 50.0


def _decode_zmx(zmx_path: Path) -> str:
    """Decode a ZMX regardless of encoding (idmxs mixes UTF-8 and UTF-16). Pick
    the candidate decode that actually yields Zemax tokens (SURF/GLAS)."""
    raw = zmx_path.read_bytes()
    best = ""
    best_score = -1
    for enc in ("utf-16", "utf-16-le", "utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(enc)
        except (UnicodeError, LookupError):
            continue
        score = text.count("SURF") + text.count("GLAS")
        if score > best_score:
            best, best_score = text, score
    return best


def _count_glass_elements(zmx_path: Path) -> int:
    """Element count heuristic: number of GLAS rows carrying real glass.

    Handles both encodings: a named catalog glass (GGG seeds) or an explicit
    model glass (idmxs uses `GLAS ___BLANK 1 0 <nd> <vd> ...` -- the material name
    is blank but the refractive index is given inline). An element is counted
    when the row names a real glass, or carries an nd in the physical range.
    Approximate -- flagged as a heuristic upstream (backend cross-checks by
    surface material segments)."""
    count = 0
    for line in _decode_zmx(zmx_path).splitlines():
        s = line.strip()
        if not s.startswith("GLAS"):
            continue
        tok = s.split()
        named = len(tok) > 1 and tok[1] not in ("___BLANK", "0", "MIRROR")
        has_nd = any(_looks_like_index(t) for t in tok[2:6])
        if named or has_nd:
            count += 1
    return count


def _looks_like_index(token: str) -> bool:
    try:
        nd = float(token)
    except ValueError:
        return False
    return 1.3 <= nd <= 2.2


def _floor_metrics(sample) -> dict:
    bands = mtf_multiband_summary(sample.mtf)
    rms_values = [v for v in sample.mtf.rms_spot_radius_um_by_field if v is not None and math.isfinite(v)]
    max_rms = max(rms_values) if rms_values else None
    metrics = OptimizationMetricSnapshot(
        effective_focal_length_mm=sample.metadata.computed_efl_mm,
        f_number=sample.paraxial.f_number,
        total_track_mm=sample.paraxial.total_track_mm,
        mtf_max_field_frac=sample.metadata.mtf_max_field_frac,
        mtf_50lpmm_min=bands.min_50,
        mtf_50lpmm_avg=bands.avg_50,
        mtf_100lpmm_min=bands.min_100,
        mtf_100lpmm_avg=bands.avg_100,
        mtf_150lpmm_min=bands.min_150,
        mtf_150lpmm_avg=bands.avg_150,
        mtf_200lpmm_min=bands.min_200,
        mtf_200lpmm_avg=bands.avg_200,
        mtf_250lpmm_min=bands.min_250,
        mtf_250lpmm_avg=bands.avg_250,
        mtf_multiband_min_score=bands.multiband_min_score,
        mtf_field_weighted_score=bands.field_weighted_score,
        max_rms_spot_radius_um=max_rms,
    )
    gap = image_quality_floor_gap_score(metrics)
    return {"max_rms_um": max_rms, "min_mtf50": bands.min_50, "floor_gap": gap}


def _category(efl: float, fov: float) -> str:
    if fov >= FISHEYE_FOV_DEG:
        return "fisheye"
    if efl >= TELEPHOTO_EFL_MM or fov <= TELEPHOTO_FOV_DEG:
        return "telephoto"
    return "main_wide"


def _manifest_entry(patent: str, sample, imh_mm: float | None) -> dict:
    m = sample.metadata
    return {
        "filename": f"{patent}.zmx",
        "patent": patent,
        "n_pieces": m.n_imaging,
        "nominal_fnum": round(sample.paraxial.f_number, 3),
        "nominal_fov_deg": round(m.fov_deg, 2),
        "nominal_efl_mm": round(m.computed_efl_mm, 3),
        "nominal_imh_mm": round(imh_mm, 3) if imh_mm is not None else None,
        "nominal_ttl_mm": round(sample.paraxial.total_track_mm, 3),
    }


def _cluster_key(rec: dict) -> tuple:
    return (
        rec["n_pieces"],
        round(rec["efl_computed"] / 0.3) * 0.3,
        round(rec["fov_deg"] / 4) * 4,
        round(rec["fnum"] / 0.15) * 0.15,
    )


def analyse(staging_dir: Path) -> dict:
    idmxs = staging_dir / "idmxs"
    index = {}
    with (idmxs / "idmxs_index.jsonl").open() as fh:
        for line in fh:
            rec = json.loads(line)
            index[rec["patent"]] = rec

    records: list[dict] = []
    for patent, meta in sorted(index.items()):
        zmx = idmxs / f"{patent}.zmx"
        if not zmx.exists():
            records.append({"patent": patent, "status": "no_zmx"})
            continue
        rec: dict = {"patent": patent, "year": meta.get("year")}
        try:
            stated_efl = float(meta["focal_mm"]) if meta.get("focal_mm") else None
            half_field = float(meta["half_field_deg"]) if meta.get("half_field_deg") else None
            n_pieces = _count_glass_elements(zmx)
            optic = load_normalized_zmx(zmx)
            nominal_fov = 2.0 * half_field if half_field else 75.0
            sample = build_sample_from_optic(
                optic,
                source_zmx=f"{patent}.zmx",
                n_pieces=n_pieces,
                nominal_efl_mm=stated_efl,
                nominal_fov_deg=nominal_fov,
            )
            m = sample.metadata
            efl = m.computed_efl_mm
            floor = _floor_metrics(sample)
            imh = efl * math.tan(math.radians(nominal_fov / 2.0)) if half_field else None
            efl_pct = abs(efl - stated_efl) / stated_efl * 100.0 if stated_efl else None
            rec.update(
                {
                    "status": "ok",
                    "n_pieces": m.n_imaging,
                    "n_filter": m.n_filter,
                    "n_glas_raw": n_pieces,
                    "efl_computed": round(efl, 4),
                    "efl_stated": stated_efl,
                    "efl_vs_stated_pct": round(efl_pct, 2) if efl_pct is not None else None,
                    "embodiment_ok": (efl_pct is None or efl_pct <= EMBODIMENT_EFL_TOL_PCT),
                    "fnum": round(sample.paraxial.f_number, 3),
                    "fov_deg": round(m.fov_deg, 2),
                    "scenario": m.scenario.value,
                    "mtf_max_field_frac": m.mtf_max_field_frac,
                    "max_rms_um": round(floor["max_rms_um"], 2) if floor["max_rms_um"] else None,
                    "min_mtf50": round(floor["min_mtf50"], 4),
                    "floor_gap": round(floor["floor_gap"], 4) if floor["floor_gap"] is not None else None,
                    "floor_clean": (floor["max_rms_um"] is not None and floor["max_rms_um"] <= 100.0),
                    "category": _category(efl, m.fov_deg),
                    "manifest": _manifest_entry(patent, sample, imh),
                }
            )
        except Exception as exc:  # noqa: BLE001
            rec.update({"status": "build_failed", "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
        records.append(rec)

    ok = [r for r in records if r.get("status") == "ok"]

    # Near-duplicate clusters within candidates + cross-check existing library.
    clusters: dict[tuple, list[str]] = {}
    for r in ok:
        clusters.setdefault(_cluster_key(r), []).append(r["patent"])
    dup_clusters = {str(k): v for k, v in clusters.items() if len(v) > 1}

    existing = [c.metadata for c in load_case_library() if c.metadata]
    existing_keys = {
        (m.n_pieces, round(m.computed_efl_mm / 0.3) * 0.3, round(m.fov_deg / 4) * 4)
        for m in existing
    }
    cross_dups = [
        r["patent"]
        for r in ok
        if (r["n_pieces"], round(r["efl_computed"] / 0.3) * 0.3, round(r["fov_deg"] / 4) * 4)
        in existing_keys
    ]

    from collections import Counter

    summary = {
        "total_candidates": len(records),
        "ok": len(ok),
        "build_failed": sum(1 for r in records if r.get("status") == "build_failed"),
        "by_category": dict(Counter(r["category"] for r in ok)),
        "floor_clean": sum(1 for r in ok if r["floor_clean"]),
        "embodiment_flagged": [r["patent"] for r in ok if not r["embodiment_ok"]],
        "near_dup_clusters": dup_clusters,
        "cross_dups_with_existing_17": cross_dups,
    }
    return {"summary": summary, "records": records}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-dir", required=True, type=Path)
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--category", default=None, help="filter manifest to a category")
    args = parser.parse_args()

    result = analyse(args.staging_dir)
    s = result["summary"]
    print("=== E2-01 intake QC (robust E1-02 metric) ===")
    print(f"candidates={s['total_candidates']} ok={s['ok']} build_failed={s['build_failed']}")
    print(f"by_category={s['by_category']} floor_clean={s['floor_clean']}/{s['ok']}")
    print(f"embodiment_flagged({len(s['embodiment_flagged'])})={s['embodiment_flagged']}")
    print(f"near_dup_clusters={len(s['near_dup_clusters'])} cross_dups_with_17={s['cross_dups_with_existing_17']}")

    if args.report_out:
        args.report_out.write_text(json.dumps(result, indent=2, default=str))
        print(f"report -> {args.report_out}")
    if args.manifest_out:
        entries = [
            r["manifest"]
            for r in result["records"]
            if r.get("status") == "ok" and (args.category is None or r["category"] == args.category)
        ]
        args.manifest_out.write_text(json.dumps(entries, indent=2))
        print(f"manifest ({len(entries)} entries) -> {args.manifest_out}")


if __name__ == "__main__":
    main()
