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

Degrades per field, not per side
-------------------------------
Optiland's MTF entry point builds one ``GeometricMTF`` over every field on the
optic and dies whole when any single field's real rays come back all-NaN --
matplotlib, reached through the spot-diagram path, raises ``autodetected range of
[nan, nan] is not finite``. Measured 2026-07-30 on the 6-trial run
``p2-gated-20260729``: **18 of 22 recomputes returned ``engine_failed``, 9 of 11
sides, identically in both arms** -- so the failure has nothing to do with the
measurement recipe. On control ``US-11933948-B2-e10``, which CODE V measures at 2
of 2 fields, the paraxial trace is fine (``efl = 4.3073``, ``fno = 2.35``) and only
the field loop dies: the fields that *did* compute were discarded along with the
one that did not.

So the recompute walks the fields one at a time and records which of them produced
a finite reading, mirroring the ``rms_fields_ok`` / ``mtf_fields_ok`` witnesses the
trial already carries on the CODE V side. A reduction over a subset of the fields is
not the reduction we claim to report, so a partial reading is never pooled with a
complete one: ``reproduction_ratio_optiland_over_codev`` holds full-coverage
readings only, and partial ones are reported beside it, labelled, with the coverage
fraction that makes them partial. A reading that arrives with no witness at all is
excluded from both rather than assumed complete.

EFL and F/# are exempt from that gate by construction -- they come from the paraxial
trace, which succeeds on sides where every real-ray field dies, and there is no
field reduction in them to be partial about. Gating them would throw away readings
that are complete.

Why Optiland's rays go NaN where CODE V's do not is not chased here. That CODE V
traces what Optiland cannot is already established in this corpus; the point of
this pass is to stop losing the fields that do trace.
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


def emit(out):
    # A cumulative snapshot after every field. If a later field hangs until the parent's
    # timeout, or dies somewhere this file does not catch, the newest snapshot still
    # carries the fields that traced -- and its own coverage counters (ok < of) make it
    # report itself as partial, so a truncated run can never pass for a full-field one.
    print(json.dumps(out), flush=True)


def finite(value):
    # Optiland returns NaN for a field whose rays died, and NaN is not a reading.
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


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
    # Whatever set the fields, read the resulting angles back off the optic rather than
    # recomputing them, so the per-field loop measures exactly the set this arm chose.
    declared = list(optic.fields.fields)
    out['num_fields'] = len(declared)
    out['fields'] = []
    # ok/of per metric, so a reader of one row can tell whether that number is a
    # reduction over every field or over the survivors. 'of' is the declared count and
    # never shrinks: a max over a subset is not the max we claim to report.
    coverage = {
        'max_rms_spot_um': {'ok': 0, 'of': len(declared), 'unit': 'fields'},
        'mtf_min': {'ok': 0, 'of': len(declared), 'unit': 'fields'},
    }
    out['coverage'] = coverage
    out['max_rms_spot_um'] = None
    out['mtf_min'] = None
    diameters = []
    modulations = []
    emit(out)
    # One field per compute_mtf call. Optiland builds a single GeometricMTF over every
    # field on the optic and dies whole if any one of them yields all-NaN spot data
    # (matplotlib: "autodetected range of [nan, nan] is not finite"), which threw the
    # fields that traced away with the one that did not -- 9 of 11 sides on the
    # p2-gated-20260729 run, including a control CODE V reads at 2 of 2 fields.
    # Restricting the field list is safe for the angle traced: Optiland normalises field
    # coords by fields.max_field, so a lone field keeps its own angle (and its own
    # vignetting factors, which travel on the Field object).
    for index, field in enumerate(declared):
        record = {'index': index, 'angle_deg': float(field.y)}
        optic.fields.fields[:] = [field]
        try:
            mtf = compute_mtf(optic)
        except Exception as exc:
            record['error'] = type(exc).__name__ + ': ' + str(exc)[:200]
            out['fields'].append(record)
            emit(out)
            continue
        per_field = list(mtf.rms_spot_radius_um_by_field)
        radius_um = finite(per_field[0]) if per_field else None
        if radius_um is None:
            record['rms_spot_diameter_um'] = None
        else:
            # Optiland's rms_spot_radius() is an RMS **radius**; CODE V's SPOTDATA
            # output(1) -- what @rmssum reports -- is an RMS **diameter**: the CODE V
            # Geometrical Analysis manual states it outright ("The RMS spot diameter ...
            # is computed as twice the square root of the mean squared spot radius").
            # Comparing them raw was a factor-of-two apples-to-oranges, and it showed:
            # the first run's median ratio came out at 0.4925.
            record['rms_spot_diameter_um'] = 2.0 * radius_um
            diameters.append(2.0 * radius_um)
            coverage['max_rms_spot_um']['ok'] += 1
        # Same frequency the trial's CODE V probe uses, and the same "worst over every
        # field and both azimuths" reduction as @mtfmin. Both azimuths must be finite or
        # the field does not count: a min over one azimuth is the flattering direction.
        idx = nearest_mtf_freq_index(mtf, 100.0)
        azimuths = []
        if idx is not None and mtf.fields:
            azimuths = [
                finite(mtf.fields[0].sagittal[idx]),
                finite(mtf.fields[0].tangential[idx]),
            ]
        if azimuths and all(value is not None for value in azimuths):
            record['mtf_min'] = min(azimuths)
            modulations.append(min(azimuths))
            coverage['mtf_min']['ok'] += 1
            out['mtf_freq_lp_per_mm'] = float(mtf.freq_lp_per_mm[idx])
        else:
            record['mtf_min'] = None
        out['fields'].append(record)
        out['max_rms_spot_um'] = max(diameters) if diameters else None
        out['mtf_min'] = min(modulations) if modulations else None
        emit(out)
    optic.fields.fields[:] = declared
    # f-tan(theta) reference, which is what a distortion percentage means and what
    # CODE V's @dstpct reports. Worst magnitude over fields and wavelengths.
    try:
        # Optiland's Distortion sweeps num_points normalised field positions from the
        # axis out to fields.max_field -- it is not a reduction over the declared fields,
        # so its witness counts sweep points. It needs the full field list restored above:
        # max_field of a lone axial field is 0 and the reference height divides by it.
        data = np.asarray(Distortion(optic, distortion_type="f-tan").data, dtype=float)
        good = np.isfinite(data)
        out["distortion_pct"] = float(np.max(np.abs(data[good]))) if good.any() else None
        coverage["distortion_pct"] = {
            "ok": int(good.sum()),
            "of": int(data.size),
            "unit": "sweep_points",
        }
    except Exception as exc:
        out["distortion_pct"] = None
        out["distortion_error"] = type(exc).__name__ + ': ' + str(exc)[:200]
else:
    out["max_rms_spot_um"] = None
    out["mtf_min"] = None
    out["distortion_pct"] = None
emit(out)
"""

#: Everything compared. EFL and F/# are deliberately absent from
#: ``FIELD_REDUCED_METRICS``: they come from the paraxial trace, which reproduces even
#: on the sides where every real-ray field dies, and they carry no field reduction that
#: could be partial. Gating them on field coverage would discard complete readings.
METRICS = ("efl_mm", "f_number", "max_rms_spot_um", "mtf_min", "distortion_pct")
FIELD_REDUCED_METRICS = ("max_rms_spot_um", "mtf_min", "distortion_pct")

#: Coverage states eligible for the headline ratio. ``partial`` is reported separately
#: and ``unwitnessed`` is reported nowhere: a reading that arrives without an ok/of pair
#: cannot be shown to be complete, and P4 must not assume it is.
_HEADLINE_STATES = frozenset({"complete", "field_independent"})


def _as_text(stream: object) -> str:
    if isinstance(stream, bytes):
        return stream.decode("utf-8", "replace")
    return stream if isinstance(stream, str) else ""


def _newest_snapshot(stdout: object) -> dict[str, object] | None:
    """The furthest the worker got, from its cumulative per-field snapshots.

    Walking backwards is what salvages a run that hung or died after some fields
    traced -- the whole point of degrading per field rather than per side. The
    snapshot's own coverage counters keep it honest: a truncated one has ok < of and
    is classified partial, so it never reaches the full-coverage headline.
    """
    for line in reversed(_as_text(stdout).splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


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
    except subprocess.TimeoutExpired as exc:
        salvaged = _newest_snapshot(exc.stdout)
        if salvaged is None:
            return "timeout"
        salvaged["truncated_by"] = "timeout"
        return salvaged
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        salvaged = _newest_snapshot(proc.stdout)
        if salvaged is None:
            return "engine_failed"
        salvaged["truncated_by"] = "crash"
        salvaged["exit_code"] = proc.returncode
        return salvaged
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    try:
        final = json.loads(lines[-1])
    except json.JSONDecodeError:
        salvaged = _newest_snapshot(proc.stdout)
        if salvaged is None:
            return "unparsed"
        salvaged["truncated_by"] = "unparsed_tail"
        return salvaged
    return final if isinstance(final, dict) else "unparsed"


def _ratio(ours: object, theirs: object) -> float | None:
    if not isinstance(ours, (int, float)) or not isinstance(theirs, (int, float)):
        return None
    if not math.isfinite(ours) or not math.isfinite(theirs) or ours == 0:
        return None
    return float(theirs) / float(ours)


def _coverage_entry(payload: object, metric: str) -> tuple[int, int] | None:
    """The worker's ok/of witness for one metric, or None when it did not report one."""
    if not isinstance(payload, dict):
        return None
    coverage = payload.get("coverage")
    entry = coverage.get(metric) if isinstance(coverage, dict) else None
    if not isinstance(entry, dict):
        return None
    ok, of = entry.get("ok"), entry.get("of")
    if not isinstance(ok, int) or not isinstance(of, int) or of <= 0 or ok < 0:
        return None
    return ok, of


def _coverage_state(payload: object, metric: str) -> str:
    """Classify one metric's reading: is it a reduction over *every* field or not?

    ``unwitnessed`` is a distinct state, not a synonym for complete. A number whose
    field coverage we cannot see is a number we cannot claim reproduces ours.
    """
    if metric not in FIELD_REDUCED_METRICS:
        return "field_independent"
    entry = _coverage_entry(payload, metric)
    if entry is None:
        return "unwitnessed"
    ok, of = entry
    if ok == 0:
        return "none"
    return "complete" if ok >= of else "partial"


def _spread(values: list[float]) -> dict[str, object]:
    return {
        "n": len(values),
        "median": round(statistics.median(values), 4) if values else None,
        "min": round(min(values), 4) if values else None,
        "max": round(max(values), 4) if values else None,
    }


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
                    # Beside every ratio, whether that ratio came from a full field set.
                    # Without this the two are indistinguishable in the row, and a
                    # partial reading reads as agreement.
                    row["coverage_state"] = {
                        metric: _coverage_state(other, metric) for metric in METRICS
                    }
                rows.append(row)

    def selected(metric: str, arm: str, states: frozenset[str]) -> list[tuple[dict, float]]:
        picked: list[tuple[dict, float]] = []
        for row in rows:
            if row.get("arm") != arm:
                continue
            ratios, state = row.get("ratios"), row.get("coverage_state")
            if not isinstance(ratios, dict) or not isinstance(state, dict):
                continue
            value = ratios.get(metric)
            if not isinstance(value, float) or state.get(metric) not in states:
                continue
            picked.append((row, value))
        return picked

    def partial(metric: str, arm: str) -> dict[str, object]:
        picked = selected(metric, arm, frozenset({"partial"}))
        out = _spread([value for _, value in picked])
        fractions = []
        for row, _value in picked:
            entry = _coverage_entry(row.get("optiland"), metric)
            if entry is not None:
                fractions.append(entry[0] / entry[1])
        # How partial. A ratio drawn from 1 field of 4 is not the same claim as one
        # drawn from 3 of 4, and the spread alone cannot tell them apart.
        out["coverage_fraction_median"] = (
            round(statistics.median(fractions), 4) if fractions else None
        )
        out["coverage_fraction_min"] = round(min(fractions), 4) if fractions else None
        return out

    def census(metric: str, arm: str) -> dict[str, int]:
        counts = {"complete": 0, "partial": 0, "none": 0, "unwitnessed": 0}
        for row in rows:
            if row.get("arm") != arm:
                continue
            state = row.get("coverage_state")
            if isinstance(state, dict) and state.get(metric) in counts:
                counts[str(state.get(metric))] += 1
        return counts

    return {
        "run_dir": str(run_dir),
        "arms": list(arms),
        "sides_checked": len({(r["zmx"], r["side"]) for r in rows}),
        "recomputes": len(rows),
        "engine_failed": sum(1 for r in rows if isinstance(r.get("optiland"), str)),
        # Salvaged from a hang or a crash after some fields traced. Counted out loud so
        # the failure is not hidden by the partial reading it produced.
        "truncated": sum(
            1
            for r in rows
            if isinstance(r.get("optiland"), dict) and r["optiland"].get("truncated_by")
        ),
        # Keyed by arm, never merged: pooling the arms would average away the very
        # comparison this exists to make. Full field coverage only -- a reduction over
        # the fields that happened to trace is not the number we report.
        "reproduction_ratio_optiland_over_codev": {
            arm: {metric: _spread([v for _, v in selected(metric, arm, _HEADLINE_STATES)])
                  for metric in METRICS}
            for arm in arms
        },
        # The partial readings the per-field degradation buys, kept apart from the
        # headline so they can be read without being averaged into it.
        "partial_field_coverage_ratio_optiland_over_codev": {
            arm: {metric: partial(metric, arm) for metric in FIELD_REDUCED_METRICS}
            for arm in arms
        },
        # Where every side landed, so "82% unmeasurable" can be replaced by a count of
        # what was measured and of which fields failed.
        "field_coverage_census": {
            arm: {metric: census(metric, arm) for metric in FIELD_REDUCED_METRICS}
            for arm in arms
        },
        "caveat": (
            "Optiland is a second engine, not a third party. Agreement here means a "
            "number survives being recomputed from the exported ZMX alone; it does not "
            "close P4. A partial-field reading is not agreement either: it is reported "
            "separately with its coverage fraction, never pooled into the headline."
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
    print(f"truncated (salvaged) {result['truncated']}")
    for arm in result["arms"]:  # type: ignore[union-attr]
        headline = result["reproduction_ratio_optiland_over_codev"][arm]  # type: ignore[index]
        print(f"-- arm {arm}: full field coverage only")
        for metric, values in headline.items():
            print(f"   {metric:<18} {values}")
        print(f"-- arm {arm}: partial field coverage, reported separately")
        for metric, values in result["partial_field_coverage_ratio_optiland_over_codev"][arm].items():  # type: ignore[index]
            print(f"   {metric:<18} {values}")
        print(f"-- arm {arm}: field coverage census")
        for metric, counts in result["field_coverage_census"][arm].items():  # type: ignore[index]
            print(f"   {metric:<18} {counts}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
