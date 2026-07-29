"""P4 · 可独立复核: does a *different* engine reproduce the numbers we report?

NORTH-STAR §3 defines P4 as "第三方用自己的 Zemax/CODE V 复算出我们报的每个数字",
and records it as never measured. We have no third party and no Zemax licence, so
this measures the part that is available and says plainly what it does not cover:

* Everything the trial reports comes out of **CODE V**, driven by our macros.
* This script re-reads the very same ZMX files with **Optiland** -- a separate,
  independently-implemented sequential ray tracer -- and compares.

Two engines agreeing is not the same as a third party agreeing, and this file
never claims otherwise. What it does buy is the failure mode P4 exists to catch:
a number that only exists because of how *we* drive one particular engine. A
quantity both engines reproduce from the exported ZMX alone is one an outsider
can check; a quantity they disagree on is one we must not report without saying so.

Method
------
For each trial record produced by ``p2_crosssource_trial``:

1. Take the ZMX the trial itself points at (candidate and control).
2. Recompute EFL, F/#, and max RMS spot radius with Optiland.
3. Compare against what the trial recorded from CODE V.

Fail-closed, and honest about which side of a mismatch is which:

* Optiland failing is reported as ``engine_failed``, **never** as a CODE V error.
  This corpus has measured cases CODE V traces and Optiland cannot.
* A metric CODE V withheld is not "reproduced" by an Optiland number; it stays
  withheld and is counted separately.

Each recompute runs in its own subprocess with a timeout: Optiland is known to
hang on a minority of this corpus, and a hang inside a loop reads as slowness.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ZMX_DIR = ROOT / "data" / "zmx"

#: Optiland's field handling needs an angular field set to avoid an inverse solve
#: that effectively never terminates on a real multi-element design (see
#: ``zmx_ingest.regularize_fields_to_angle``). The angle comes from the file
#: itself, not from the manifest -- the manifest is exactly what was found to
#: carry two different units.
_WORKER = """
import json, math, sys, warnings
warnings.simplefilter("ignore")
sys.path.insert(0, sys.argv[1])
from app.core.aberration import compute_mtf
from app.core.engines.seed_field_rebuild import max_field_angle_deg
from app.core.engines.zmx_import_prep import decode_zmx_text
from app.core.zmx_ingest import load_normalized_zmx, regularize_fields_to_angle

path = sys.argv[2]
half = max_field_angle_deg(decode_zmx_text(open(path, "rb").read())[0])
optic = load_normalized_zmx(path)
out = {"half_field_angle_deg": half}
out["efl_mm"] = float(optic.paraxial.f2())
try:
    out["f_number"] = float(optic.paraxial.FNO())
except Exception:
    out["f_number"] = None
if half is not None:
    regularize_fields_to_angle(optic, 2.0 * half)
    rms = [float(v) for v in compute_mtf(optic).rms_spot_radius_um_by_field]
    out["max_rms_spot_um"] = max(rms) if rms else None
else:
    out["max_rms_spot_um"] = None
print(json.dumps(out))
"""


def _recompute(worker: Path, zmx: Path, timeout_s: float) -> dict[str, object] | str:
    try:
        proc = subprocess.run(
            [sys.executable, str(worker), str(ROOT), str(zmx)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return "engine_failed"
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return "unparsed"


def _ratio(ours: object, theirs: object) -> float | None:
    if not isinstance(ours, (int, float)) or not isinstance(theirs, (int, float)):
        return None
    if not math.isfinite(ours) or not math.isfinite(theirs) or ours == 0:
        return None
    return float(theirs) / float(ours)


def recheck(*, run_dir: Path, worker: Path, timeout_s: float) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for trial_path in sorted(run_dir.glob("trial_*.json")):
        record = json.loads(trial_path.read_text(encoding="utf-8"))
        plan = record.get("plan") or {}
        sides = {
            "candidate": (record.get("candidate_zmx"), record.get("candidate_quality")),
            "control": (
                str(ZMX_DIR / str(plan.get("control_zmx", ""))),
                record.get("control_quality"),
            ),
        }
        for side, (zmx_path, reported) in sides.items():
            if not zmx_path or not Path(str(zmx_path)).is_file() or not reported:
                continue
            other = _recompute(worker, Path(str(zmx_path)), timeout_s)
            row: dict[str, object] = {
                "control_case_id": plan.get("control_case_id"),
                "side": side,
                "zmx": Path(str(zmx_path)).name,
                "codev": {
                    "efl_mm": reported.get("efl_y_mm"),
                    "f_number": reported.get("f_number"),
                    "max_rms_spot_um": reported.get("rms_spot_um"),
                },
            }
            if isinstance(other, str):
                row["optiland"] = other
            else:
                row["optiland"] = other
                row["ratios"] = {
                    "efl_mm": _ratio(reported.get("efl_y_mm"), other.get("efl_mm")),
                    "f_number": _ratio(reported.get("f_number"), other.get("f_number")),
                    "max_rms_spot_um": _ratio(
                        reported.get("rms_spot_um"), other.get("max_rms_spot_um")
                    ),
                }
            rows.append(row)

    def spread(metric: str) -> dict[str, object]:
        values = [
            r["ratios"][metric]  # type: ignore[index]
            for r in rows
            if isinstance(r.get("ratios"), dict)
            and isinstance(r["ratios"].get(metric), float)  # type: ignore[union-attr]
        ]
        return {
            "n": len(values),
            "median": round(statistics.median(values), 4) if values else None,
            "min": round(min(values), 4) if values else None,
            "max": round(max(values), 4) if values else None,
        }

    return {
        "run_dir": str(run_dir),
        "sides_checked": len(rows),
        "engine_failed": sum(
            1 for r in rows if isinstance(r.get("optiland"), str)
        ),
        "reproduction_ratio_optiland_over_codev": {
            metric: spread(metric) for metric in ("efl_mm", "f_number", "max_rms_spot_um")
        },
        "caveat": (
            "Optiland is a second engine, not a third party. Agreement here means a "
            "number survives being recomputed from the exported ZMX alone; it does not "
            "close P4."
        ),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="a p2 trial run directory")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args(argv)

    worker = args.out.parent / "_p4_worker.py"
    worker.parent.mkdir(parents=True, exist_ok=True)
    worker.write_text(_WORKER, encoding="utf-8")
    result = recheck(run_dir=args.run, worker=worker, timeout_s=args.timeout)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"sides checked        {result['sides_checked']}")
    print(f"optiland failed      {result['engine_failed']}")
    for metric, spread in result["reproduction_ratio_optiland_over_codev"].items():  # type: ignore[union-attr]
        print(f"{metric:<20} {spread}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
