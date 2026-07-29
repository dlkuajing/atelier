"""Was the corpus's stored image quality measured at the field the lens actually has?

The mechanism, from code
------------------------
`app/core/case_library.py` builds every case's MTF through
``regularize_fields_to_angle(optic, nominal_fov_deg)``, and that helper takes
``full_fov_deg / 2`` as the half field angle. So the stored
``mtf.rms_spot_radius_um_by_field`` is only right if ``fov_deg`` really was a
**full** FOV.

`.planning/evidence/fov-unit-mix-2026-07-29.md` showed it was not: 253 of 442
cases stored a **half** angle there. That makes "the stored quality was computed
at half the lens' true field" a *hypothesis* worth testing -- a smaller field
means smaller spots and higher MTF, so it would be flattering. Testing it is the
point of this script, and the positive control below is what decides it.

What this script measures
-------------------------
For a sample of the affected cases it recomputes the Optiland MTF twice -- once
with the old (halved) ``fov_deg`` and once with the re-anchored one -- and
compares both against the number stored in the case JSON.

* old-recompute ≈ stored  ⇒ would confirm the stored numbers came from the wrong field.
  **Measured 2026-07-29: it does not.** Only 1 of 22 lands within 5% of 1.0; the
  median is 1.43 and the range 0.96-1.88. So today's code does not reproduce the
  stored numbers even at the field they were supposedly computed with, and the
  "stored quality came from half the field" story is **not** established -- other
  things changed between corpus generation and now (ingest repairs, ray clipping,
  Optiland version). The finding that survives is narrower and more useful: the
  stored image quality is **not reproducible with the current code at all**.
* new-recompute vs old-recompute ⇒ what the true field costs, engine held fixed.
  This comparison does not depend on the stored numbers and is the one to trust.

Each case runs in its **own subprocess with a timeout**. Optiland is known to
hang on a minority of this corpus, and a hang inside a batch loop looks exactly
like slowness.

An Optiland failure at the corrected field is reported as ``failed``, never as
"the lens is bad": this project has already measured cases where CODE V traces
what Optiland cannot.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CASES_DIR = ROOT / "app" / "data" / "optical_cases"
ZMX_DIR = ROOT / "data" / "zmx"

_WORKER = """
import json, sys, warnings
warnings.simplefilter("ignore")
sys.path.insert(0, sys.argv[1])
from app.core.aberration import compute_mtf
from app.core.zmx_ingest import load_normalized_zmx, regularize_fields_to_angle

optic = load_normalized_zmx(sys.argv[2])
regularize_fields_to_angle(optic, float(sys.argv[3]))
rms = [float(v) for v in compute_mtf(optic).rms_spot_radius_um_by_field]
print(json.dumps({"max_rms": max(rms) if rms else None}))
"""


def _recompute(worker: Path, zmx: Path, fov_deg: float, timeout_s: float) -> float | str:
    try:
        proc = subprocess.run(
            [sys.executable, str(worker), str(ROOT), str(zmx), str(fov_deg)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return "failed"
    try:
        return float(json.loads(proc.stdout.strip().splitlines()[-1])["max_rms"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return "unparsed"


def _stored_max_rms(case_id: str) -> float | None:
    path = CASES_DIR / f"{case_id}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    values = [
        v
        for v in ((data.get("mtf") or {}).get("rms_spot_radius_um_by_field") or [])
        if isinstance(v, (int, float)) and v > 0
    ]
    return max(values) if values else None


def audit(*, limit: int, timeout_s: float, worker: Path) -> dict[str, object]:
    baseline = subprocess.run(
        ["git", "show", "origin/main:app/data/optical_cases/index.json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    if baseline.returncode != 0:
        raise RuntimeError("cannot read the pre-migration index.json from origin/main")
    old_fov = {row["case_id"]: float(row["fov_deg"]) for row in json.loads(baseline.stdout)}
    index = json.loads((CASES_DIR / "index.json").read_text(encoding="utf-8"))

    # Only the cases the migration actually doubled -- the ones the hypothesis
    # is about.
    affected = [
        row
        for row in index
        if row["case_id"] in old_fov
        and abs(old_fov[row["case_id"]] * 2.0 - float(row["fov_deg"])) < 1e-6
    ]
    # Stride sampling, not head-N: the index is grouped by generation batch.
    chosen = affected
    if limit < len(affected):
        step = len(affected) / limit
        chosen = [affected[int(i * step)] for i in range(limit)]

    rows: list[dict[str, object]] = []
    for row in chosen:
        case_id = row["case_id"]
        zmx = ZMX_DIR / row["source_zmx"]
        if not zmx.is_file():
            continue
        rows.append(
            {
                "case_id": case_id,
                "stored_max_rms_um": _stored_max_rms(case_id),
                "old_fov_deg": old_fov[case_id],
                "new_fov_deg": float(row["fov_deg"]),
                "recompute_old": _recompute(worker, zmx, old_fov[case_id], timeout_s),
                "recompute_new": _recompute(worker, zmx, float(row["fov_deg"]), timeout_s),
            }
        )

    # Positive control: does recomputing at the OLD fov reproduce what is stored?
    control = [
        r
        for r in rows
        if isinstance(r["recompute_old"], float) and isinstance(r["stored_max_rms_um"], float)
    ]
    control_ratio = [r["recompute_old"] / r["stored_max_rms_um"] for r in control]  # type: ignore[operator]
    both = [
        r
        for r in rows
        if isinstance(r["recompute_old"], float) and isinstance(r["recompute_new"], float)
    ]
    inflation = [r["recompute_new"] / r["recompute_old"] for r in both]  # type: ignore[operator]
    return {
        "affected_cases": len(affected),
        "sampled": len(rows),
        "positive_control_n": len(control),
        "positive_control_ratio_median": (
            round(statistics.median(control_ratio), 4) if control_ratio else None
        ),
        "both_recomputed_n": len(both),
        "true_field_over_half_field_median": (
            round(statistics.median(inflation), 3) if inflation else None
        ),
        "true_field_over_half_field_max": (round(max(inflation), 3) if inflation else None),
        "failed_at_new_fov": sum(1 for r in rows if r["recompute_new"] in {"failed", "timeout"}),
        "failed_at_old_fov": sum(1 for r in rows if r["recompute_old"] in {"failed", "timeout"}),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    worker = args.out.parent / "_stored_quality_worker.py"
    worker.parent.mkdir(parents=True, exist_ok=True)
    worker.write_text(_WORKER, encoding="utf-8")
    result = audit(limit=args.limit, timeout_s=args.timeout, worker=worker)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for key, value in result.items():
        if key != "rows":
            print(f"{key:<38} {value}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
