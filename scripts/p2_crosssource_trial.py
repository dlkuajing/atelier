"""First measurement of the North Star main indicator: 异源打平率 (P2).

`.planning/NORTH-STAR.md` §3 defines P2 as "seed 与对照专利不同家族时，候选在
RMS spot / MTF / 畸变上不劣于该规格专利原设计的比例" and records it as **zero
data** -- never systematically measured. Two prior shovels supplied the inputs:

* `scripts/p2_pair_census.py` (PR #99) answered *how many* 异源 trials the corpus
  supports -- 167, but from only 31 distinct seeds. This script reuses its
  pairing and provenance rules verbatim rather than re-deriving them.
* `.planning/evidence/p2-control-baseline-2026-07-28.md` (PR #104) measured the
  control side once and found a **sixth degenerate mode**: 3/30 seeds reported
  RMS spot radii around 1e+20 µm, which sail straight through the project's
  `>0` positive-definite check because they degenerate toward +∞ rather than
  toward the ideal reading. That screen is implemented here (see
  `ImageQuality.from_data`) as a self-evident bound: **a spot cannot be larger
  than the image circle it lives in**. No magic constant is introduced -- the
  bound comes from the lens' own image height.

What one trial is
-----------------
1. Pick a control patent design ``C`` that passes every eligibility screen.
2. Derive the structured spec from ``C`` itself (EFL / F# / image height). This
   is the "需求" a designer would receive, and ``C`` is by construction a design
   that satisfies it.
3. Route a seed ``S`` = nearest usable case **from a different assignee brand**
   (the conservative same-family superset from `p2_pair_census`).
4. Optimise ``S`` toward the spec through the production entry point
   ``run_codev_target_standard(emit_optimized_zmx=True)`` -> candidate ZMX.
5. Measure candidate and control with **the same probe at the same settings**,
   which is what NORTH-STAR §3 means by "同一张表同时施于候选与对照".
6. 打平 on a metric := candidate is not worse than control. Trial 打平 := all
   three metrics 打平.

What this script deliberately does NOT do
-----------------------------------------
It sets **no threshold**. 红线③ forbids pre-set numbers, and the comparison
"不劣于" is a 口径 (<= for lower-is-better, >= for higher-is-better), not a
tuned number. The 打平率 threshold that would make P2 "green" stays blank.

A trial whose candidate or control cannot be measured is reported as
``unmeasurable`` -- **never** silently dropped and never counted as 打平.
Dropping them would bias the headline in the flattering direction, which is the
same failure mode the fidelity audit and the absurd-value screen exist to stop.

Usage::

    uv run python scripts/p2_crosssource_trial.py --plan --census <perfield.jsonl>
    uv run python scripts/p2_crosssource_trial.py --run --census <perfield.jsonl> \
        --out D:/atelier-stagec-runs/p2-pilot --limit 12
    uv run python scripts/p2_crosssource_trial.py --report --out <dir>
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
import warnings
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ZMX_DIR = ROOT / "data" / "zmx"
CASE_INDEX = ROOT / "app" / "data" / "optical_cases" / "index.json"

#: Same MTF sampling as the production tolerance block, so a number produced
#: here is comparable with one produced by `codev_optimize`. Changing either of
#: these changes what "MTF" means and invalidates cross-run comparison.
MTF_FREQUENCY_LPMM = 100.0
MTF_NRD = 32

PROBE_RESULT_SCHEMA = "atelier-p2-image-quality-v1"
TRIAL_RESULT_SCHEMA = "atelier-p2-crosssource-trial-v1"

_PROBE_REQUIRED_KEYS = (
    "schema",
    "status",
    "source_zmx",
    "efl_y_mm",
    "f_number",
    "num_wavelengths",
    "num_fields",
    "image_height_mm",
    "rms_spot_um",
    "rms_wavefront_waves",
    "distortion_pct",
    "lateral_color_um",
    "mtf_min",
)


# ---------------------------------------------------------------------------
# 红线① — CODE V single instance
# ---------------------------------------------------------------------------


CODEV_PROCESS_NAMES = frozenset({"codev", "codev.exe", "codevm", "codevm.exe"})


def sessions_from_snapshot(snapshot: object) -> list[dict[str, object]]:
    """CODE V *sessions*, not processes.

    One CODE V instance spawns a ``codev`` and a ``codevm`` process, so a raw
    process count reads 2 for a single healthy session and makes the red line
    impossible to satisfy. A session is a codev/codevm process whose parent is
    **not** itself codev/codevm.
    """

    processes = list(snapshot)  # type: ignore[call-overload]
    codev_pids = {p.pid for p in processes if p.name.casefold() in CODEV_PROCESS_NAMES}
    return [
        {"pid": p.pid, "ppid": p.ppid, "name": p.name}
        for p in processes
        if p.pid in codev_pids and p.ppid not in codev_pids
    ]


def codev_sessions() -> list[dict[str, object]]:
    from app.core.batch_run_lock import _process_snapshot

    return sessions_from_snapshot(_process_snapshot())


def assert_no_codev_session(stage: str) -> list[dict[str, object]]:
    sessions = codev_sessions()
    if sessions:
        raise RuntimeError(f"红线①: {len(sessions)} CODE V session(s) alive at {stage}: {sessions}")
    return sessions


# ---------------------------------------------------------------------------
# Image-quality probe
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImageQuality:
    """One measured snapshot. Every ``None`` means "not measurable", never 0.

    The withholding rules below are the project's accumulated list of degenerate
    modes; each one cost a real-machine investigation to find.
    """

    source: str
    efl_y_mm: float | None
    f_number: float | None
    num_wavelengths: int | None
    num_fields: int | None
    image_height_mm: float | None
    rms_spot_um: float | None
    rms_wavefront_waves: float | None
    distortion_pct: float | None
    lateral_color_um: float | None
    mtf_min: float | None
    withheld: tuple[str, ...] = ()

    @property
    def comparable(self) -> bool:
        """True when all three North Star metrics survived every screen."""

        return (
            self.rms_spot_um is not None
            and self.mtf_min is not None
            and self.distortion_pct is not None
        )

    @classmethod
    def from_data(cls, data: Mapping[str, str], *, source: str) -> ImageQuality:
        withheld: list[str] = []

        def num(key: str) -> float | None:
            raw = data.get(key)
            if raw is None:
                return None
            try:
                value = float(str(raw).strip())
            except (TypeError, ValueError):
                return None
            return value if math.isfinite(value) else None

        efl = num("efl_y_mm")
        fno = num("f_number")
        raw_wavelengths = num("num_wavelengths")
        raw_fields = num("num_fields")
        wavelengths = int(raw_wavelengths) if raw_wavelengths is not None else None
        fields = int(raw_fields) if raw_fields is not None else None

        # ``^maximh`` starts at 0 and is filled from paraxial data, which does not
        # need a traced ray. A zero here therefore does not mean "tracing failed",
        # it means the field loop produced nothing at all -- and it is also the
        # anchor for the absurd-value bound below, so without it nothing that
        # depends on scale can be judged.
        image_height = num("image_height_mm")
        if image_height is None or image_height <= 0.0:
            image_height = None
            withheld.append("image_height_not_measured")

        # Positive-definite: diffraction sets a floor strictly above zero, so
        # <= 0 can only be the macro's accumulator seed (degenerate modes 1-5).
        rms_spot = num("rms_spot_um")
        if rms_spot is not None and rms_spot <= 0.0:
            rms_spot = None
            withheld.append("rms_spot_seed_value")
        wavefront = num("rms_wavefront_waves")
        if wavefront is not None and wavefront <= 0.0:
            wavefront = None
            withheld.append("rms_wavefront_seed_value")

        # Degenerate mode 6 (2026-07-28, p2-control-baseline): 1e+20 µm spot
        # radii that pass every `> 0` check because they run away toward +∞
        # instead of collapsing to the ideal reading. The bound is self-evident
        # and constant-free: a spot wider than the whole image circle is not an
        # image of anything. Image circle diameter = 2 * max image height.
        if rms_spot is not None:
            if image_height is None:
                rms_spot = None
                withheld.append("rms_spot_unboundable")
            elif rms_spot > 2_000.0 * image_height:
                rms_spot = None
                withheld.append("rms_spot_exceeds_image_circle")

        # ``@mtfmin`` starts at 1 and only decreases; diffraction holds MTF
        # strictly below 1 at any positive frequency, so 1.0 is the seed value.
        mtf = num("mtf_min")
        if mtf is not None and (mtf >= 1.0 or mtf < 0.0):
            mtf = None
            withheld.append("mtf_seed_value")

        # Joint criterion: 0.0 distortion and 0.0 lateral colour are physically
        # legitimate, so they cannot be judged by value. They are only trustworthy
        # when at least one positive-definite metric survived to vouch that
        # something was actually traced.
        distortion = num("distortion_pct")
        lateral = num("lateral_color_um")
        if rms_spot is None and wavefront is None:
            if distortion is not None:
                withheld.append("distortion_no_positive_definite_witness")
            if lateral is not None:
                withheld.append("lateral_color_no_positive_definite_witness")
            distortion = None
            lateral = None
        # @lcum spans W1..W(NUM W); at fewer than three wavelengths both ends
        # point at the same wavelength and the distance is identically 0.
        if lateral is not None and wavelengths is not None and wavelengths < 3:
            lateral = None
            withheld.append("lateral_color_below_three_wavelengths")

        return cls(
            source=source,
            efl_y_mm=efl,
            f_number=fno,
            num_wavelengths=wavelengths,
            num_fields=fields,
            image_height_mm=image_height,
            rms_spot_um=rms_spot,
            rms_wavefront_waves=wavefront,
            distortion_pct=distortion,
            lateral_color_um=lateral,
            mtf_min=mtf,
            withheld=tuple(withheld),
        )


def build_probe_sequence(
    *,
    source_zmx: Path | str,
    result_path: Path | str,
    mtf_frequency_lpmm: float = MTF_FREQUENCY_LPMM,
    mtf_nrd: int = MTF_NRD,
) -> str:
    """Macro that imports one ZMX and exports the three P2 metrics plus witnesses.

    The metric functions are imported from ``codev_optimize`` rather than
    re-implemented, which is the whole point: candidate and control must be
    judged by the *same* instrument, and that instrument must be the production
    one, or the comparison measures the probe instead of the lenses.
    """

    from app.core.engines.codev_batch import ensure_codev_safe_input_path
    from app.core.engines.codev_optimize import _metric_function_block, _quote_codev_path

    source_zmx = Path(source_zmx)
    ensure_codev_safe_input_path(source_zmx, role="source_zmx")
    result_path = Path(result_path)

    lines: list[str] = [
        # ASCII only: the macro is written with encoding="ascii" because CODE V
        # reads .seq as plain bytes, so a Chinese comment here is a hard crash.
        "! Generated by scripts/p2_crosssource_trial.py -- P2 cross-source comparator.",
        *_metric_function_block(),
        "OUT NO",
        f"IN CV_MACRO:ZEMAXOS_TO_CV {_quote_codev_path(source_zmx)}",
        "^row == 1",
        "^efl == ABSF((EFY))",
        "^ftyp == (TYP FLD)",
        "^maximh == 0",
        "FOR ^f 1 (NUM F)",
        "  ^yh == (YRI F^f Z1)",
        '  IF ^ftyp = "ANG"',
        "    ^yh == ^efl * TANF((YAN F^f Z1)*4*ATANF(1)/180)",
        '  ELS IF ^ftyp = "IMG"',
        "    ^yh == (YIM F^f Z1)",
        "  END IF",
        "  IF ABSF(^yh) > ^maximh",
        "    ^maximh == ABSF(^yh)",
        "  END IF",
        "END FOR",
        "^rms == @rmssum(1)",
        "^wfe == @wfewav(1)",
        "^dst == @dstpct(1)",
        "^lat == @lcum(1)",
        f"^mtf == @mtfmin({_fmt(mtf_frequency_lpmm)},{int(mtf_nrd)})",
    ]

    def put(key: str, value: str) -> None:
        lines.append(f"BUF PUT B1 I^row J1 {key}")
        lines.append(f"BUF PUT B1 I^row J2 {value}")
        lines.append("^row == ^row+1")

    put('"schema"', f'"{PROBE_RESULT_SCHEMA}"')
    put('"status"', '"ok"')
    put('"source_zmx"', f'"{source_zmx.name}"')
    put('"efl_y_mm"', "^efl")
    put('"f_number"', "ABSF((FNO))")
    put('"num_wavelengths"', "(NUM W)")
    put('"num_fields"', "(NUM F)")
    put('"image_height_mm"', "^maximh")
    put('"rms_spot_um"', "^rms")
    put('"rms_wavefront_waves"', "^wfe")
    put('"distortion_pct"', "^dst")
    put('"lateral_color_um"', "^lat")
    put('"mtf_min"', "^mtf")
    put('"mtf_frequency_lpmm"', _fmt(mtf_frequency_lpmm))
    put('"mtf_nrd"', str(int(mtf_nrd)))

    lines += [
        f"BUF EXP B1 {_quote_codev_path(result_path)}",
        "BUF DEL B1",
        "OUT YES",
        "EXI YES",
        "",
    ]
    return "\n".join(lines)


def _fmt(value: float) -> str:
    from app.core.engines.codev_optimize import _fmt_number

    return _fmt_number(value)


def measure_image_quality(
    *,
    source_zmx: Path | str,
    work_dir: Path | str,
    tag: str,
    timeout_seconds: float = 180.0,
) -> ImageQuality:
    """Import one ZMX and read the three P2 metrics back out of CODE V."""

    from app.core.engines.codev_batch import run_codev_batch
    from app.core.engines.zmx_import_prep import stage_zmx_for_codev

    source_zmx = Path(source_zmx).resolve()
    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    # Never import the raw file: without the WAVM flush sentinel CODE V silently
    # drops to one default wavelength (PR #93). A single-wavelength import would
    # make every colour-sensitive metric here quietly wrong.
    staged = stage_zmx_for_codev(source_zmx, work_dir)
    sequence_path = work_dir / f"{tag}_probe.seq"
    result_path = work_dir / f"{tag}_probe.tsv"
    sequence_path.write_text(
        build_probe_sequence(source_zmx=staged, result_path=result_path),
        encoding="ascii",
    )
    batch = run_codev_batch(
        sequence_path=sequence_path,
        result_path=result_path,
        work_dir=work_dir,
        timeout_seconds=timeout_seconds,
        expected_schema=PROBE_RESULT_SCHEMA,
        required_keys=_PROBE_REQUIRED_KEYS,
        allow_nonzero_ok_result=True,
    )
    return ImageQuality.from_data(batch.data, source=source_zmx.name)


# ---------------------------------------------------------------------------
# Trial planning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrialPlan:
    control_case_id: str
    control_zmx: str
    control_brand: str
    seed_case_id: str
    seed_zmx: str
    seed_brand: str
    spec_efl_mm: float
    spec_f_number: float
    spec_imh_mm: float
    spec_fov_deg: float
    spec_n_pieces: int


def plan_trials(census_path: Path, *, limit: int | None = None) -> tuple[list[TrialPlan], dict]:
    """Pair every eligible control with its nearest cross-brand seed.

    Pairing is delegated to ``p2_pair_census.census`` so the two shovels cannot
    drift: the same eligibility screens (strictly traceable ∧ fidelity-clean),
    the same conservative brand bucketing, the same ``rank_seeds`` argmin.
    """

    warnings.simplefilter("ignore")
    from scripts.p2_pair_census import census

    result = census(census_path)
    index = {r["case_id"]: r for r in json.loads(CASE_INDEX.read_text(encoding="utf-8"))}

    plans: list[TrialPlan] = []
    for pair in result["trial_pairs"]:
        control = index.get(pair["control"])
        seed = index.get(pair["seed"])
        if control is None or seed is None:
            continue
        plans.append(
            TrialPlan(
                control_case_id=pair["control"],
                control_zmx=control["source_zmx"],
                control_brand=pair["control_brand"],
                seed_case_id=pair["seed"],
                seed_zmx=seed["source_zmx"],
                seed_brand=pair["seed_brand"],
                # The spec is the control's own realised prescription: a customer
                # asking for exactly what that patent delivers.
                spec_efl_mm=float(control["efl_mm"]),
                spec_f_number=float(control["fnum"]),
                spec_imh_mm=float(control["image_height_mm"]),
                spec_fov_deg=float(control["fov_deg"]),
                spec_n_pieces=int(control["n_pieces"]),
            )
        )

    plans.sort(key=lambda p: p.control_case_id)
    # Stride sampling, not head-N: the corpus index is grouped by generation
    # batch, so the first N controls come from one contiguous slice of it. This
    # is still not a random sample and is reported as such.
    if limit is not None and limit < len(plans):
        step = len(plans) / limit
        plans = [plans[int(i * step)] for i in range(limit)]
    return plans, result


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

#: metric -> True when lower is better.
P2_METRICS: dict[str, bool] = {
    "rms_spot_um": True,
    "mtf_min": False,
    "distortion_pct": True,
}


def compare(candidate: ImageQuality, control: ImageQuality) -> dict[str, object]:
    """Per-metric 不劣于 verdict plus the trial-level roll-up.

    ``None`` on either side makes the whole trial ``unmeasurable``. It is never
    resolved to a pass, and never dropped from the denominator: a trial we could
    not judge is a trial we did not win.
    """

    per_metric: dict[str, object] = {}
    measurable = True
    for metric, lower_is_better in P2_METRICS.items():
        cand = getattr(candidate, metric)
        ctrl = getattr(control, metric)
        if cand is None or ctrl is None:
            per_metric[metric] = {
                "candidate": cand,
                "control": ctrl,
                "verdict": "unmeasurable",
            }
            measurable = False
            continue
        won = cand <= ctrl if lower_is_better else cand >= ctrl
        per_metric[metric] = {
            "candidate": cand,
            "control": ctrl,
            "lower_is_better": lower_is_better,
            "verdict": "par" if won else "worse",
            "ratio": (cand / ctrl) if ctrl not in (0.0,) else None,
        }
    if not measurable:
        verdict = "unmeasurable"
    elif all(m["verdict"] == "par" for m in per_metric.values()):  # type: ignore[index]
        verdict = "par"
    else:
        verdict = "worse"
    return {"verdict": verdict, "metrics": per_metric}


# ---------------------------------------------------------------------------
# One trial
# ---------------------------------------------------------------------------


def run_trial(plan: TrialPlan, *, out_dir: Path, timeout_seconds: float = 180.0) -> dict[str, Any]:
    from app.core.engines.codev_batch import CodeVBatchError
    from app.core.engines.codev_optimize import run_codev_target_standard
    from app.core.engines.zmx_import_prep import declared_field_count, decode_zmx_text

    started = time.time()
    work = out_dir / f"trial_{plan.control_case_id}"
    work.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "schema": TRIAL_RESULT_SCHEMA,
        "plan": asdict(plan),
        "mtf_frequency_lpmm": MTF_FREQUENCY_LPMM,
        "mtf_nrd": MTF_NRD,
    }

    # autovig learns num_fields from its rung-0 run, so a rung-0 timeout leaves
    # it unable to build any higher rung and it abandons the ladder after one
    # attempt per config. The 2026-07-28 pre-fix pilot lost 3/24 trials exactly
    # that way (elapsed pinned at 2 x the 180s hard timeout, to 0.1s). Reading
    # the declared count off the seed costs no CODE V call.
    seed_zmx = ZMX_DIR / plan.seed_zmx
    num_fields = declared_field_count(decode_zmx_text(seed_zmx.read_bytes())[0])
    record["seed_declared_num_fields"] = num_fields

    # --- candidate: optimise the cross-brand seed toward the control's spec ---
    try:
        standard = run_codev_target_standard(
            source_zmx=seed_zmx,
            work_dir=work / "optimize",
            target_efl_mm=plan.spec_efl_mm,
            target_f_number=plan.spec_f_number,
            target_imh_mm=plan.spec_imh_mm,
            num_fields=num_fields,
            timeout_seconds=timeout_seconds,
            emit_optimized_zmx=True,
        )
    except CodeVBatchError as exc:
        record["candidate_error"] = {"kind": exc.kind, "detail": exc.message}
        record["verdict"] = "unmeasurable"
        record["blocked_at"] = "optimize"
        record["elapsed_s"] = round(time.time() - started, 1)
        return record

    preferred = standard.get("preferred")
    record["preferred_config"] = preferred
    record["preferred_reason"] = standard.get("preferred_reason")
    if preferred is None:
        record["verdict"] = "unmeasurable"
        record["blocked_at"] = "optimize_no_preferred"
        record["configs"] = {k: _config_summary(v) for k, v in standard.get("configs", {}).items()}
        record["elapsed_s"] = round(time.time() - started, 1)
        return record

    config = dict(standard["configs"][preferred])  # type: ignore[index]
    record["autovig_edge_used"] = config.get("autovig.edge_used")
    record["autovig_converged"] = config.get("autovig.converged")
    record["aut_converged"] = config.get("aut_converged")
    record["efl_target_deviation_pct"] = config.get("efl_target_deviation_pct")
    candidate_zmx = config.get("optimized_zmx_path")
    if not candidate_zmx or not Path(str(candidate_zmx)).exists():
        record["verdict"] = "unmeasurable"
        record["blocked_at"] = "candidate_zmx_missing"
        record["zmx_rebuild_error"] = config.get("zmx_rebuild_error")
        record["elapsed_s"] = round(time.time() - started, 1)
        return record
    record["candidate_zmx"] = str(candidate_zmx)

    # --- measure both sides with the same probe ---
    measurements: dict[str, ImageQuality | None] = {}
    for side, zmx in (
        ("candidate", Path(str(candidate_zmx))),
        ("control", ZMX_DIR / plan.control_zmx),
    ):
        try:
            measurements[side] = measure_image_quality(
                source_zmx=zmx,
                work_dir=work / f"measure_{side}",
                tag=side,
                timeout_seconds=timeout_seconds,
            )
        except CodeVBatchError as exc:
            record[f"{side}_probe_error"] = {"kind": exc.kind, "detail": exc.message}
            measurements[side] = None

    record["candidate_quality"] = (
        asdict(measurements["candidate"]) if measurements["candidate"] else None
    )
    record["control_quality"] = asdict(measurements["control"]) if measurements["control"] else None

    # Fourth 交付物 piece (NORTH-STAR §1.1). Read straight off both ZMX files, so
    # it costs no CODE V time and is available even when a trial is unjudgeable
    # on image quality. Reported as a ratio only -- an absolute is meaningless
    # here and 「绝对成本报价」 is an explicit 反目标.
    record["relative_cost_index"] = _relative_cost(
        Path(str(candidate_zmx)), ZMX_DIR / plan.control_zmx
    )

    # Third 交付物 piece (NORTH-STAR §1.1): 公差敏感度 + 良率. Same table on both
    # sides -- that equal treatment is what §3's 「表错了两边一起错，排序不变」
    # rests on, and it is why the sequence has to run SNS rather than TOR's
    # default inverse mode, which would derive a *different* table per lens.
    record["tolerance"] = _tolerance_pair(
        Path(str(candidate_zmx)), ZMX_DIR / plan.control_zmx,
        work / "tolerance", timeout_seconds,
    )

    if measurements["candidate"] is None or measurements["control"] is None:
        record["verdict"] = "unmeasurable"
        record["blocked_at"] = "probe"
    else:
        record.update(compare(measurements["candidate"], measurements["control"]))
        # A candidate that missed the spec is not a design for that spec, and
        # comparing it to the control is not a comparison -- a lens that came out
        # 20% short of the target EFL has a smaller spot for free. The metrics
        # stay in the record for diagnosis; the verdict does not.
        if str(record.get("aut_converged")) != "1":
            record["spec_verdict_override"] = record["verdict"]
            record["verdict"] = "spec_not_met"
            record["blocked_at"] = "aut_not_converged"
    record["elapsed_s"] = round(time.time() - started, 1)
    return record



#: Uncalibrated starter tolerances, mobile moulded-plastic order of magnitude
#: (thickness +/-5um, radius +/-10um). NORTH-STAR §3 permits coarse absolute
#: values *because the same table goes to both sides*, so there is one table
#: here and no per-side knob. It is not a manufacturing budget and must never be
#: reported as one.
TOLERANCE_COMMANDS = ("DLT S1..I 0.005", "DLR S1..I 0.01")
COMPENSATOR_COMMANDS = ("CMP DLZ SI",)
TOLERANCE_TRIALS = 20

#: Illustrative, uncalibrated. Applied identically to candidate and control, so
#: the comparison survives the number being wrong; the absolute yield does not.
YIELD_THRESHOLD_WAVES = 0.25
#: Above this share of samples outside TOR's linear model the yield is refused
#: rather than disclosed -- see tor_yield for why disclosure needs a ceiling.
MAX_OUT_OF_MODEL_FRACTION = 0.25


def _tolerance_pair(
    candidate_zmx: Path, control_zmx: Path, work_dir: Path, timeout_seconds: float
) -> dict[str, object]:
    """Run the same tolerance table on both sides and report yield + disclosure."""

    from app.core.engines.codev_batch import CodeVBatchError
    from app.core.engines.codev_tolerance import (
        TorCompensators,
        TorMonteCarlo,
        TorToleranceTable,
        run_codev_tor,
    )
    from app.core.engines.tor_yield import TorYieldPolicy, compute_mc_yield

    policy = TorYieldPolicy(
        metric="RMS",
        threshold=YIELD_THRESHOLD_WAVES,
        direction="max",
        semantics_ratified=True,
        semantics_evidence=(
            "TOR linear-model out-of-range rate measured across 26 real runs "
            "(2026-07-29): 11.7%/4.4%/2.9% by nominal-RMS field rank"
        ),
        max_saturation_fraction=1.0,
        max_out_of_model_fraction=MAX_OUT_OF_MODEL_FRACTION,
    )
    out: dict[str, object] = {
        "tolerance_commands": list(TOLERANCE_COMMANDS),
        "compensator_commands": list(COMPENSATOR_COMMANDS),
        "trials": TOLERANCE_TRIALS,
        "yield_threshold_waves": YIELD_THRESHOLD_WAVES,
        "max_out_of_model_fraction": MAX_OUT_OF_MODEL_FRACTION,
        "calibrated": False,
    }
    for side, zmx in (("candidate", candidate_zmx), ("control", control_zmx)):
        try:
            run = run_codev_tor(
                source_zmx=zmx,
                work_dir=work_dir / side,
                tolerance_table=TorToleranceTable(TOLERANCE_COMMANDS, "uncalibrated starter set"),
                compensators=TorCompensators(
                    COMPENSATOR_COMMANDS, "image-plane focus only", "back focus refocus at assembly"
                ),
                monte_carlo=TorMonteCarlo(TOLERANCE_TRIALS),
                metric="rms",
                timeout_seconds=timeout_seconds,
            )
        except (CodeVBatchError, OSError, ValueError) as exc:
            out[side] = {"error": f"{type(exc).__name__}: {exc}"[:400]}
            continue
        computed = compute_mc_yield(run.parse_result, policy)
        out[side] = {
            "status": computed.status,
            "yield_fraction": computed.yield_fraction,
            "judged_samples": computed.trials,
            "out_of_model_samples": computed.out_of_model_samples,
            "out_of_model_fraction": computed.out_of_model_fraction,
            "per_field_yield": computed.per_field_yield,
            "reason": computed.reason,
        }
    return out

def _relative_cost(candidate_zmx: Path, control_zmx: Path) -> dict[str, object] | None:
    """Candidate cost relative to its control, or ``None`` when either is unreadable."""

    from app.core.cost_index import CostIndex, cost_index_from_zmx, cost_ratio
    from app.core.engines.zmx_import_prep import decode_zmx_text

    def read(path: Path) -> CostIndex | None:
        try:
            return cost_index_from_zmx(decode_zmx_text(path.read_bytes())[0])
        except OSError:
            return None

    candidate, control = read(candidate_zmx), read(control_zmx)
    ratio = cost_ratio(candidate, control)
    if ratio is None:
        return None
    return {
        "ratio": ratio,
        "candidate_units": candidate.total_units,  # type: ignore[union-attr]
        "control_units": control.total_units,  # type: ignore[union-attr]
        "candidate_elements": candidate.element_count,  # type: ignore[union-attr]
        "control_elements": control.element_count,  # type: ignore[union-attr]
        "candidate_aspheric_surfaces": candidate.aspheric_surface_count,  # type: ignore[union-attr]
        "control_aspheric_surfaces": control.aspheric_surface_count,  # type: ignore[union-attr]
    }


def _config_summary(config: object) -> dict[str, object]:
    if not isinstance(config, dict):
        return {"unexpected": repr(config)[:200]}
    keep = ("error", "skipped", "aut_converged", "autovig.converged", "autovig.trace")
    return {k: config[k] for k in keep if k in config}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _edge_used(record: Mapping[str, Any]) -> float | None:
    try:
        return float(str(record.get("autovig_edge_used")))
    except (TypeError, ValueError):
        return None


def summarise(records: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts: dict[str, int] = {}
    for record in records:
        verdicts[str(record.get("verdict", "missing"))] = (
            verdicts.get(str(record.get("verdict", "missing")), 0) + 1
        )
    judged = verdicts.get("par", 0) + verdicts.get("worse", 0)
    seeds = {r["plan"]["seed_case_id"] for r in records if "plan" in r}
    summary: dict[str, Any] = {
        "trials": len(records),
        "verdicts": verdicts,
        "judged": judged,
        # Two denominators, always reported together. The first is the honest
        # North Star reading; the second is only useful for diagnosing why
        # trials could not be judged.
        "par_rate_over_all_trials": (verdicts.get("par", 0) / len(records)) if records else None,
        "par_rate_over_judged": (verdicts.get("par", 0) / judged) if judged else None,
        "distinct_seeds_used": len(seeds),
        "blocked_at": {},
    }
    for record in records:
        if record.get("blocked_at"):
            key = str(record["blocked_at"])
            summary["blocked_at"][key] = summary["blocked_at"].get(key, 0) + 1
    # Per-metric counts are restricted to judged trials. A candidate that missed
    # the spec can still "win" a metric, and counting that would be a free win.
    judged_records = [r for r in records if r.get("verdict") in {"par", "worse"}]
    for metric in P2_METRICS:
        summary[f"{metric}_par"] = sum(
            1
            for r in judged_records
            if isinstance(r.get("metrics"), dict)
            and r["metrics"].get(metric, {}).get("verdict") == "par"
        )
    # Vignetting stratification. autovig clips the off-axis pupil to make the
    # optimiser converge, and that clipping is written into the candidate ZMX --
    # so a candidate with edge > 0 is measured with a narrower aperture than the
    # control, which biases the headline UP. Reported, not silently folded in.
    unclipped = [r for r in judged_records if _edge_used(r) == 0.0]
    summary["judged_unclipped"] = len(unclipped)
    summary["par_rate_unclipped_only"] = (
        sum(1 for r in unclipped if r["verdict"] == "par") / len(unclipped) if unclipped else None
    )
    elapsed = [r["elapsed_s"] for r in records if isinstance(r.get("elapsed_s"), (int, float))]
    if elapsed:
        summary["elapsed_s_median"] = round(statistics.median(elapsed), 1)
        summary["elapsed_s_total"] = round(sum(elapsed), 1)
    return summary


def render(summary: dict[str, Any]) -> str:
    lines = [
        "P2 异源打平率 (cross-source par rate)",
        "=" * 44,
        f"trials                    {summary['trials']}",
        f"  par                     {summary['verdicts'].get('par', 0)}",
        f"  worse                   {summary['verdicts'].get('worse', 0)}",
        f"  spec_not_met            {summary['verdicts'].get('spec_not_met', 0)}",
        f"  unmeasurable            {summary['verdicts'].get('unmeasurable', 0)}",
        f"distinct seeds used       {summary['distinct_seeds_used']}",
    ]
    rate_all = summary["par_rate_over_all_trials"]
    rate_judged = summary["par_rate_over_judged"]
    lines.append(
        "par rate / all trials     "
        + (f"{rate_all:.1%}" if rate_all is not None else "n/a")
        + "   <- the honest reading"
    )
    lines.append(
        "par rate / judged only    " + (f"{rate_judged:.1%}" if rate_judged is not None else "n/a")
    )
    rate_unclipped = summary.get("par_rate_unclipped_only")
    lines.append(
        "par rate / unclipped only "
        + (f"{rate_unclipped:.1%}" if rate_unclipped is not None else "n/a")
        + f"   (n={summary.get('judged_unclipped', 0)}, no autovig pupil clipping)"
    )
    for metric in P2_METRICS:
        lines.append(f"  {metric:<22} par on {summary.get(f'{metric}_par', 0)} of judged")
    if summary.get("blocked_at"):
        lines.append("blocked at:")
        for key, count in sorted(summary["blocked_at"].items()):
            lines.append(f"  {key:<24} {count}")
    if "elapsed_s_median" in summary:
        lines.append(f"median trial wall time    {summary['elapsed_s_median']}s")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="offline: list the trials")
    mode.add_argument("--run", action="store_true", help="real machine: run the trials")
    mode.add_argument("--report", action="store_true", help="offline: summarise a finished run")
    parser.add_argument("--census", type=Path, help="perfield census jsonl (strict traceability)")
    parser.add_argument("--out", type=Path, help="run directory")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args(argv)

    if args.plan:
        if args.census is None:
            parser.error("--plan needs --census")
        plans, census_result = plan_trials(args.census, limit=args.limit)
        payload = {
            "trials_available": census_result["trials"],
            "distinct_seeds_available": census_result["distinct_seeds_used"],
            "planned": [asdict(p) for p in plans],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.report:
        if args.out is None:
            parser.error("--report needs --out")
        records = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(Path(args.out).glob("trial_*.json"))
        ]
        print(render(summarise(records)))
        return 0

    if args.census is None or args.out is None:
        parser.error("--run needs --census and --out")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    plans, census_result = plan_trials(args.census, limit=args.limit)
    (out_dir / "plan.json").write_text(
        json.dumps(
            {
                "trials_available": census_result["trials"],
                "distinct_seeds_available": census_result["distinct_seeds_used"],
                "planned": [asdict(p) for p in plans],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    before = assert_no_codev_session("pre-run")
    print(f"红线① pre-run CODE V sessions: {len(before)}", flush=True)
    records: list[dict[str, Any]] = []
    try:
        for position, plan in enumerate(plans, start=1):
            print(
                f"[{position}/{len(plans)}] control={plan.control_case_id} "
                f"seed={plan.seed_case_id}",
                flush=True,
            )
            record = run_trial(plan, out_dir=out_dir, timeout_seconds=args.timeout)
            (out_dir / f"trial_{plan.control_case_id}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            records.append(record)
            print(f"    -> {record.get('verdict')} ({record.get('elapsed_s')}s)", flush=True)
    finally:
        after = codev_sessions()
        print(f"红线① post-run CODE V sessions: {len(after)} {after}", flush=True)
        summary = summarise(records)
        summary["red_line_sessions_before"] = len(before)
        summary["red_line_sessions_after"] = len(after)
        (out_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(render(summary))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    raise SystemExit(main())
