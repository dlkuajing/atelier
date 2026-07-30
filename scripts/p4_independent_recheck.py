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

Units are matched before comparing, not after: Optiland reports an RMS spot
**radius** and CODE V an RMS spot **diameter** (manual: "computed as twice the
square root of the mean squared spot radius"). The first run of this script
missed that and reported a median ratio of 0.4925 -- which read as "the engines
disagree" when half of it was a convention.

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
import numpy as np
from optiland.analysis import Distortion
from app.core.aberration import compute_mtf, nearest_mtf_freq_index
from app.core.engines.seed_field_rebuild import max_field_angle_deg, read_field_profile
from app.core.engines.zmx_import_prep import decode_zmx_text
from app.core.zmx_ingest import load_normalized_zmx, regularize_fields_to_angle

path = sys.argv[2]
# Arm selection. "recipe" honours what the shipped measurement recipe states about the
# CODE V side -- "outlier_rejection: none" -- by disabling our MAD clip. "reported"
# leaves the clip in, i.e. reproduces the number as our own pipeline reports it.
# Running both is the point: the gap between the two arms *is* the part of P4's
# irreproducibility that publishing the recipe removes.
arm = sys.argv[3] if len(sys.argv) > 3 else "reported"
if arm == "recipe":
    import app.core.aberration as _ab

    _ab._robust_clip_spot_data = lambda geometric_mtf: None

text = decode_zmx_text(open(path, "rb").read())[0]
half = max_field_angle_deg(text)
optic = load_normalized_zmx(path)
out = {"half_field_angle_deg": half, "arm": arm}
out["efl_mm"] = float(optic.paraxial.f2())
try:
    out["f_number"] = float(optic.paraxial.FNO())
except Exception:
    out["f_number"] = None
# Set the optic to the ZMX's OWN angular fields instead of canonical fractions.
# regularize_fields_to_angle clears every field and substitutes
# MTF_CANONICAL_FIELD_FRACS = (0.0, 0.5, 0.7, 1.0) x half-FOV. Measured on
# US-11906710-B2-e2: CODE V measures the 2 declared fields (0.0 and 39.0 deg) while
# Optiland was measuring 4 (0, 19.5, 27.3, 39.0). For a max-over-fields metric the two
# extra mid-fields can only raise Optiland's answer -- mid-field is often the worst --
# so part of what the first P4 pass read as 'the engines disagree' was our own recheck
# measuring a field set CODE V never sees. Returns True when the file's own angles
# were used, False when they are unusable.
def _use_declared_fields(optic, text):
    profile = read_field_profile(text)
    # field_type 0 is angular. For a real-image-height file the declared values are
    # heights, and aiming at them makes Optiland solve an inverse that does not
    # terminate on a multi-element design -- the reason the substitution exists at all.
    if profile is None or profile.field_type != 0:
        return False
    angles = [abs(float(y)) for y in profile.y_fields]
    if not angles or max(angles) <= 0.0:
        return False
    optic.set_field_type('angle')
    optic.fields.fields.clear()
    for angle in angles:
        optic.add_field(y=angle)
    try:
        optic.ray_tracer.set_aiming('robust', max_iter=20)
    except Exception:
        pass
    return True

if half is not None:
    used_declared = _use_declared_fields(optic, text) if arm == 'recipe' else False
    if not used_declared:
        regularize_fields_to_angle(optic, 2.0 * half)
    out['field_set'] = 'declared' if used_declared else 'canonical_fractions'
    mtf = compute_mtf(optic)
    rms = [float(v) for v in mtf.rms_spot_radius_um_by_field]
    # Optiland's rms_spot_radius() is an RMS **radius**; CODE V's SPOTDATA
    # output(1) -- what @rmssum reports -- is an RMS **diameter**: the CODE V
    # Geometrical Analysis manual states it outright ("The RMS spot diameter ...
    # is computed as twice the square root of the mean squared spot radius").
    # Comparing them raw was a factor-of-two apples-to-oranges, and it showed:
    # the first run's median ratio came out at 0.4925.
    out["max_rms_spot_um"] = (2.0 * max(rms)) if rms else None
    # Same frequency the trial's CODE V probe uses, and the same "worst over every
    # field and both azimuths" reduction as @mtfmin.
    idx = nearest_mtf_freq_index(mtf, 100.0)
    if idx is None:
        out["mtf_min"] = None
    else:
        vals = []
        for field in mtf.fields:
            vals.extend([float(field.sagittal[idx]), float(field.tangential[idx])])
        out["mtf_min"] = min(vals) if vals else None
        out["mtf_freq_lp_per_mm"] = float(mtf.freq_lp_per_mm[idx])
    # f-tan(theta) reference, which is what a distortion percentage means and what
    # CODE V's @dstpct reports. Worst magnitude over fields and wavelengths.
    try:
        data = np.asarray(Distortion(optic, distortion_type="f-tan").data, dtype=float)
        finite = data[np.isfinite(data)]
        out["distortion_pct"] = float(np.max(np.abs(finite))) if finite.size else None
    except Exception:
        out["distortion_pct"] = None
else:
    out["max_rms_spot_um"] = None
    out["mtf_min"] = None
    out["distortion_pct"] = None
print(json.dumps(out))
"""


def _recompute(
    worker: Path, zmx: Path, timeout_s: float, arm: str = "reported"
) -> dict[str, object] | str:
    try:
        proc = subprocess.run(
            [sys.executable, str(worker), str(ROOT), str(zmx), arm],
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


#: The two arms. "reported" recomputes the number the way our own pipeline reports it
#: (MAD clip on); "recipe" recomputes it the way the shipped measurement recipe says the
#: CODE V side was measured ("outlier_rejection: none"). The delta between the arms is
#: the share of P4's per-lens irreproducibility that publishing the recipe removes --
#: which is the whole question, and it cannot be answered by running one arm.
ARMS = ("reported", "recipe")


def recheck(
    *, run_dir: Path, worker: Path, timeout_s: float, arms: tuple[str, ...] = ARMS
) -> dict[str, object]:
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
            for arm in arms:
                other = _recompute(worker, Path(str(zmx_path)), timeout_s, arm)
                row: dict[str, object] = {
                    "control_case_id": plan.get("control_case_id"),
                    "side": side,
                    "arm": arm,
                    "zmx": Path(str(zmx_path)).name,
                    "codev": {
                        "efl_mm": reported.get("efl_y_mm"),
                        "f_number": reported.get("f_number"),
                        "max_rms_spot_um": reported.get("rms_spot_um"),
                        "mtf_min": reported.get("mtf_min"),
                        "distortion_pct": reported.get("distortion_pct"),
                    },
                }
                row["optiland"] = other
                if not isinstance(other, str):
                    row["ratios"] = {
                        "efl_mm": _ratio(reported.get("efl_y_mm"), other.get("efl_mm")),
                        "f_number": _ratio(reported.get("f_number"), other.get("f_number")),
                        "max_rms_spot_um": _ratio(
                            reported.get("rms_spot_um"), other.get("max_rms_spot_um")
                        ),
                        "mtf_min": _ratio(reported.get("mtf_min"), other.get("mtf_min")),
                        "distortion_pct": _ratio(
                            reported.get("distortion_pct"), other.get("distortion_pct")
                        ),
                    }
                rows.append(row)

    def spread(metric: str, arm: str) -> dict[str, object]:
        values = [
            r["ratios"][metric]  # type: ignore[index]
            for r in rows
            if r.get("arm") == arm
            and isinstance(r.get("ratios"), dict)
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
        "arms": list(arms),
        "sides_checked": len({(r["zmx"], r["side"]) for r in rows}),
        "recomputes": len(rows),
        "engine_failed": sum(1 for r in rows if isinstance(r.get("optiland"), str)),
        # Keyed by arm, never merged: pooling the arms would average away the very
        # comparison this exists to make.
        "reproduction_ratio_optiland_over_codev": {
            arm: {
                metric: spread(metric, arm)
                for metric in ("efl_mm", "f_number", "max_rms_spot_um", "mtf_min", "distortion_pct")
            }
            for arm in arms
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
    parser.add_argument(
        "--arms",
        default=",".join(ARMS),
        help=(
            "comma-separated subset of "
            + "/".join(ARMS)
            + ". Default runs both: 'reported' reproduces the number as our pipeline "
            "reports it (MAD clip on), 'recipe' reproduces it as the shipped measurement "
            "recipe says the CODE V side was measured (no outlier rejection). The delta "
            "is what publishing the recipe buys."
        ),
    )
    args = parser.parse_args(argv)

    worker = args.out.parent / "_p4_worker.py"
    worker.parent.mkdir(parents=True, exist_ok=True)
    worker.write_text(_WORKER, encoding="utf-8")
    result = recheck(run_dir=args.run, worker=worker, timeout_s=args.timeout,
        arms=tuple(a.strip() for a in args.arms.split(",") if a.strip()),
    )
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"sides checked        {result['sides_checked']}")
    print(f"recomputes           {result['recomputes']} over arms {result['arms']}")
    print(f"optiland failed      {result['engine_failed']}")
    for arm, metrics in result["reproduction_ratio_optiland_over_codev"].items():  # type: ignore[union-attr]
        print(f"-- arm: {arm}")
        for metric, spread in metrics.items():
            print(f"   {metric:<18} {spread}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
