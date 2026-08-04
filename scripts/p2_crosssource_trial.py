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

#: Kill a CODE V rung that has produced no new output for this long. CODE V can
#: stop computing after a ray error yet never exit; the hard timeout still bounds
#: the run, this just stops paying it in full for a process that is already dead.
#:
#: **Calibrated 2026-07-30 on the real machine** (the 60.0s this replaced was
#: not -- its comment stated the watchdog's purpose and no measurement).
#: Method and raw runs: `.planning/evidence/idle-watchdog-calibration-2026-07-30.md`,
#: `scripts/codev_idle_gap_bench.py`, D:/atelier-stagec-runs/idle-gap-bench-20260730*.
#: Completed runs cannot supply this number on their own -- each one finished with
#: a gap under the bound by construction -- so the bench replays real rungs with
#: the watchdog **watching but not killing**.
#:
#:   healthy rungs, n=8, 0.5s poll: worst inter-output gap **7.64s**
#:     (range 2.03-7.64s over runs of 6.8-123.22s; the 117s rung logged 86 gaps,
#:      mostly 0.5-2s -- CODE V writes its listing continuously, it does not
#:      buffer the whole thing to the end)
#:   parked rungs, n=3 (rungs the 60s bound had killed, incl. both configs of
#:     the trial that motivated this): silent **581-596s** of a 600s window,
#:     never resumed, never exited. They were genuinely dead, not slow.
#:
#: 150.0s clears two independent anchors:
#:   * 19.6x the worst measured healthy gap;
#:   * above the longest *complete* healthy rung on record (123.22s wall). A run's
#:     duration is the theoretical ceiling on its largest gap, so this anchor
#:     holds even if some unsampled seed/config did buffer its output to the end.
#: It stays under the 180.0s default hard timeout on purpose: at or above it the
#: watchdog can never fire and silently stops existing.
#: `tests/test_p2_idle_timeout_calibration.py` pins both ends.
#:
#: Direction is deliberate. Too tight turns healthy work into `unmeasurable`,
#: which is indistinguishable from a real failure and biases the North Star's
#: main indicator; too loose costs wall clock only, and the hard timeout still
#: bounds the run. Fail toward completing.
IDLE_TIMEOUT_SECONDS = 150.0

#: Worst inter-output gap measured on a healthy rung (see above). The bound must
#: stay a wide multiple of this; the calibration test reads it from here.
MEASURED_HEALTHY_MAX_GAP_SECONDS = 7.64

#: Longest *complete* healthy rung measured, wall clock. An upper bound on that
#: run's largest possible gap, so the watchdog must clear it too.
MEASURED_LONGEST_HEALTHY_RUNG_SECONDS = 123.22
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
    "rms_fields_ok",
    "mtf_fields_ok",
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
    #: CODE V's RMS spot **diameter** in microns -- SPOTDATA output(1), which the
    #: Geometrical Analysis manual defines as "twice the square root of the mean
    #: squared spot radius". `codev_optimize` names the same macro's output
    #: `max_rms_spot_diameter_um`; this shorter name is kept for schema stability,
    #: but anything comparing it against a *radius* (Optiland's
    #: `rms_spot_radius()`, `_SEED_ROUTING_MAX_RMS_UM`) is out by a factor of two.
    rms_spot_um: float | None
    rms_wavefront_waves: float | None
    distortion_pct: float | None
    lateral_color_um: float | None
    mtf_min: float | None
    #: How many fields actually produced a reading, against the declared count.
    #: ``None`` means the probe did not report it.
    rms_fields_ok: int | None = None
    mtf_fields_ok: int | None = None
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

        # Partial-field extrema (2026-07-29 adversarial audit). ``@rmssum`` skips
        # a field whose SPOTDATA errors and ``@mtfmin`` skips one whose MTF_1FLD
        # returns negative, then each returns its extremum over the survivors. A
        # candidate whose outer field died therefore reports its **axial** spot as
        # an all-field maximum and its axial MTF as an all-field minimum -- both
        # in the flattering direction, and invisible because ``num_fields`` is the
        # declared count. A max over a subset is not the max we claim to report.
        raw_rms_ok = num("rms_fields_ok")
        raw_mtf_ok = num("mtf_fields_ok")
        rms_fields_ok = int(raw_rms_ok) if raw_rms_ok is not None else None
        mtf_fields_ok = int(raw_mtf_ok) if raw_mtf_ok is not None else None
        if rms_spot is not None and (
            fields is None or rms_fields_ok is None or rms_fields_ok < fields
        ):
            rms_spot = None
            withheld.append("rms_spot_partial_field_coverage")
        if mtf is not None and (
            fields is None or mtf_fields_ok is None or mtf_fields_ok < fields
        ):
            mtf = None
            withheld.append("mtf_partial_field_coverage")

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
            rms_fields_ok=rms_fields_ok,
            mtf_fields_ok=mtf_fields_ok,
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
        # Witnesses for the two extremum metrics: how many fields actually
        # produced a reading. `(NUM F)` is the **declared** count, so without
        # these a lens that images on axis only is indistinguishable from one
        # that images everywhere -- and every dropped field moves RMS down and
        # MTF up, both of which read as "better".
        "^rmsnf == @rmsnf(1)",
        f"^mtfnf == @mtfnf({_fmt(mtf_frequency_lpmm)},{int(mtf_nrd)})",
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
    put('"rms_fields_ok"', "^rmsnf")
    put('"mtf_fields_ok"', "^mtfnf")
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
    idle_timeout_seconds: float | None = IDLE_TIMEOUT_SECONDS,
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
        # Same zombie mode as the optimiser: CODE V can stop computing after a
        # ray error and never exit. The probe was left without the watchdog when
        # it landed for the optimiser, so a stalled probe still burned its whole
        # hard timeout -- twice per trial, once per side.
        idle_timeout_seconds=idle_timeout_seconds,
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
    #: Which directory `seed_zmx` lives in. Corpus seeds are in `data/zmx`;
    #: since 2026-08-03 a seed may also be a screened `data/zmx-staging` design
    #: (seeds only, never controls -- see `p2_pair_census.load_staging_seeds`).
    #: Carried explicitly rather than inferred, so the run artifact records which
    #: pool every trial was seeded from.
    seed_pool: str = "corpus"
    spec_efl_mm: float = 0.0
    spec_f_number: float = 0.0
    spec_imh_mm: float = 0.0
    spec_fov_deg: float = 0.0
    spec_n_pieces: int = 0


def seed_zmx_path(plan: TrialPlan) -> Path:
    """Where this trial's seed file actually is.

    Two pools since 2026-08-03. Resolving by `plan.seed_pool` rather than by
    "try one directory then the other" so a missing file fails loudly at the
    place it is missing, instead of being answered by a same-named file in the
    other pool.
    """

    from scripts.p2_pair_census import STAGING_ZMX_DIR

    root = STAGING_ZMX_DIR if plan.seed_pool == "staging" else ZMX_DIR
    return root / plan.seed_zmx


def _first_order_imh_disclosure(plan: TrialPlan) -> dict[str, Any]:
    """How far the control's declared image height sits from `efl * tan(fov/2)`.

    `fov_deg` is the full field angle (re-anchored 2026-07-29), hence the halving.
    """

    reference = plan.spec_efl_mm * math.tan(math.radians(plan.spec_fov_deg / 2.0))
    return {
        "spec_imh_mm": plan.spec_imh_mm,
        "first_order_imh_mm": reference,
        "deviation_frac": (
            (plan.spec_imh_mm - reference) / reference if reference > 0.0 else None
        ),
        "note": (
            "declared image height is the max over the exit pupil, not the chief ray "
            "(corpus-truth audit 2026-07-30); reported for disclosure, not screened"
        ),
    }


def plan_trials(census_path: Path, *, limit: int | None = None) -> tuple[list[TrialPlan], dict]:
    """Pair every eligible control with its nearest cross-brand seed.

    Pairing is delegated to ``p2_pair_census.census`` so the two shovels cannot
    drift: the same eligibility screens (strictly traceable ∧ fidelity-clean),
    the same conservative brand bucketing, the same ``rank_seeds`` argmin.
    """

    warnings.simplefilter("ignore")
    from scripts.p2_pair_census import census, load_staging_seeds

    result = census(census_path)
    index = {r["case_id"]: r for r in json.loads(CASE_INDEX.read_text(encoding="utf-8"))}
    staging = {str(r["zmx"]).rsplit(".", 1)[0]: str(r["zmx"]) for r in load_staging_seeds()}

    plans: list[TrialPlan] = []
    unresolved: list[dict] = []
    for pair in result["trial_pairs"]:
        control = index.get(pair["control"])
        seed_file = (
            index[pair["seed"]]["source_zmx"] if pair["seed"] in index else staging.get(pair["seed"])
        )
        if control is None or seed_file is None:
            # Never a silent `continue`. When the seed pool grew to include
            # `data/zmx-staging`, an index-only lookup here dropped 54 of 59
            # trials without a word -- the plan simply came back short, and the
            # missing trials looked like a smaller corpus rather than a bug.
            unresolved.append(
                {
                    "control": pair["control"],
                    "seed": pair["seed"],
                    "reason": "control_not_in_index" if control is None else "seed_in_no_pool",
                }
            )
            continue
        plans.append(
            TrialPlan(
                control_case_id=pair["control"],
                control_zmx=control["source_zmx"],
                control_brand=pair["control_brand"],
                seed_case_id=pair["seed"],
                seed_zmx=seed_file,
                seed_brand=pair["seed_brand"],
                seed_pool=pair.get("seed_pool", "corpus"),
                # The spec is the control's own realised prescription: a customer
                # asking for exactly what that patent delivers.
                spec_efl_mm=float(control["efl_mm"]),
                spec_f_number=float(control["fnum"]),
                spec_imh_mm=float(control["image_height_mm"]),
                spec_fov_deg=float(control["fov_deg"]),
                spec_n_pieces=int(control["n_pieces"]),
            )
        )

    if unresolved:
        raise SystemExit(
            f"{len(unresolved)} of {len(result['trial_pairs'])} planned pairs could not be "
            f"resolved to a ZMX; refusing to run a silently shortened plan. "
            f"First: {unresolved[:3]}"
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

#: Readout-rounding slack for the conformance screens below, **not** a quality
#: threshold. The probe prints ~6 significant figures, so its own relative error
#: is around 1e-6; 1e-3 is a thousandfold allowance and no candidate is decided
#: by it. 红线③ forbids pre-set 判据 numbers -- this is not one, and neither
#: screen has a tunable pass level: both are "the candidate must not have been
#: handed an easier job than the control".
CONFORMANCE_RELATIVE_SLACK = 1e-3

#: How far the candidate's measured EFL may sit from the control's. This is the
#: engine's **own** definition of "the EFL target was achieved"
#: (``codev_optimize.EFL_TARGET_TOLERANCE_PCT`` = 2%), reused rather than
#: reinvented -- a trial whose candidate the optimiser itself calls converged must
#: not then be rejected here for the same number, and 红线③ forbids inventing a
#: fresh threshold. It is a *conformance* tolerance, not a quality one: nothing
#: about how good the candidate is depends on it.
EFL_PARITY_TOLERANCE = 0.02

#: How far the optimiser may be asked to **open** the aperture, as
#: ``seed F/# / spec F/#``. The mirror of `p2_pair_census.MAX_SEED_EFL_STRETCH`
#: for the second quantity `run_codev_target_standard` targets, which nothing
#: gated -- even though opening the aperture is the harder direction.
#:
#: Measured on the 49-trial round of 2026-08-02 (`p1-selectpref-ab-20260802`),
#: growth computable on all 49:
#:
#:     growth > 1.05    n=11   judged  0  (0%)    13013 s (53.4% of the round)
#:     growth <= 1.05   n=38   judged 35  (92%)
#:
#: What makes this causal rather than a correlation across seeds: **41 of the 49
#: trials run the same seed** (`US-12044826-B2-e4`, F/2.03), so within that seed
#: growth varies only because the control's aperture does, and the outcome is
#: monotone in it --
#:
#:     F/2.50 .. F/1.95  (growth 0.812 .. 1.041)   judged, every one
#:     F/1.85, F/1.75, F/1.65  (1.097 .. 1.230)    not one judged, ~1100-1900 s each
#:
#: The bar sits in the gap between 1.0410 (largest growth that still got judged)
#: and 1.0973 (smallest above it). It is deliberately *not* tighter: two trials at
#: growth 0.9902 also failed, so growth above the bar is sufficient for failure
#: and never a complete explanation of it, and tightening to 1.02 would start
#: rejecting a trial that did produce a verdict.
#:
#: Honest limit: the bar is read off the same 49 trials it is evaluated on, so
#: "removes 0 judged trials" holds **by construction here** and is a bound
#: observed once, not validated out of sample. It fails open when the seed states
#: no ``FNUM``.
MAX_PUPIL_GROWTH = 1.05


def field_tangent(quality: ImageQuality) -> float | None:
    """``tan(max field angle)`` = paraxial image height / EFL, or ``None``.

    ``image_height_mm`` comes from ``^maximh``, which CODE V fills from paraxial
    data: it is ``EFL * tan(theta)`` for the outermost field, **not** the real
    ray height. Dividing it by that same side's own EFL therefore recovers the
    field angle the lens was actually evaluated over -- one quantity, derived the
    same way on both sides, so the two are comparable even when the underlying
    ZMX files disagree about how fields are declared.
    """

    if quality.image_height_mm is None or quality.efl_y_mm is None:
        return None
    if quality.efl_y_mm <= 0.0:
        return None
    return quality.image_height_mm / quality.efl_y_mm


def conformance_screen(
    candidate: ImageQuality, control: ImageQuality
) -> tuple[str | None, dict[str, object]]:
    """Is this candidate answering the same question the control answers?

    Two of the spec's fields (NORTH-STAR §1.1 lists 像高 and FOV alongside EFL
    and F/#) are **not** enforced anywhere in the optimisation path --
    ``codev_optimize.build_target_standard`` documents it in so many words:
    "未落地：IMH/FOV ... ``target_imh_mm`` 目前仅透传进三快照读数". The candidate
    therefore inherits its seed's field definition, and two trials measured on
    2026-07-29 confirm it: both candidates came out at ``imh/efl = 0.3317``
    (18.35°) against controls at 37.5° and 33.1°, from the same seed at two
    different EFLs.

    Comparing those is not comparing. A lens evaluated over half the field angle
    is being asked for less, and the 2026-07-29 run shows exactly how that
    flatters the headline: ``US-20230288669-A1-e2`` scored 打平 on 畸变 with
    2.38% against the control's 86.97% -- and the control's 86.97% is *correct*,
    because it is a genuine super-wide design whose real image height (3.58 mm)
    sits far below the paraxial ``EFL*tan(theta)`` reference (27.47 mm) that the
    rectilinear distortion definition measures against. Nothing was broken; the
    two lenses simply cover different fields.

    So a trial is only judged when the candidate was given **at least** the
    control's job on the three counts it can be handed for free:

    * absolute scale -- candidate EFL within the engine's own achieved-target
      tolerance of the control's EFL. Checked **first**, because the other two
      legs are blind to it: both are ratios and survive a uniform scaling of the
      whole lens untouched.
    * field coverage -- candidate ``tan(theta)`` >= control ``tan(theta)``
    * aperture -- candidate F/# <= control F/# (a slower lens has smaller
      aberrations for nothing)

    Over-delivery on either is allowed and judged as-is: it can only make the
    candidate's own numbers harder to win with.

    Returns ``(blocked_at | None, diagnostics)``. The diagnostics are recorded
    whatever the outcome so a rejected trial still says by how much it missed.
    """

    cand_tan, ctrl_tan = field_tangent(candidate), field_tangent(control)
    details: dict[str, object] = {
        "candidate_field_tangent": cand_tan,
        "control_field_tangent": ctrl_tan,
        "field_coverage_ratio": (
            (cand_tan / ctrl_tan) if cand_tan is not None and ctrl_tan else None
        ),
        "candidate_f_number": candidate.f_number,
        "control_f_number": control.f_number,
        "candidate_efl_mm": candidate.efl_y_mm,
        "control_efl_mm": control.efl_y_mm,
        "efl_ratio": (
            (candidate.efl_y_mm / control.efl_y_mm)
            if candidate.efl_y_mm is not None and control.efl_y_mm
            else None
        ),
    }

    # Absolute scale, checked first because the other two legs cannot see it.
    # ``tan(theta) = imh/efl`` and F/# are both invariant under a uniform scale of
    # the whole lens, so a candidate built at 0.65x the control's focal length --
    # measured, `US-20220011544-A1-e5`, 2.84 mm against 4.40 mm -- passes both and
    # collects a linearly smaller spot for nothing. That trial scored **par on RMS
    # spot** at a ratio of 0.036. Optimising against a probe-derived spec (see
    # ``run_trial``) is the root fix; this is the screen that makes a regression
    # of it impossible to miss.
    if candidate.efl_y_mm is None or control.efl_y_mm is None or control.efl_y_mm <= 0:
        return "efl_not_comparable", details
    if abs(candidate.efl_y_mm - control.efl_y_mm) > control.efl_y_mm * EFL_PARITY_TOLERANCE:
        return "efl_not_matched", details

    if cand_tan is None or ctrl_tan is None:
        return "field_not_comparable", details
    if cand_tan < ctrl_tan * (1.0 - CONFORMANCE_RELATIVE_SLACK):
        return "field_not_covered", details
    if candidate.f_number is None or control.f_number is None:
        return "f_number_not_comparable", details
    if candidate.f_number > control.f_number * (1.0 + CONFORMANCE_RELATIVE_SLACK):
        return "f_number_not_met", details
    return None, details


def compare(candidate: ImageQuality, control: ImageQuality) -> dict[str, object]:
    """Per-metric 不劣于 verdict plus the trial-level roll-up.

    ``None`` on either side makes that *metric* unmeasurable. It is never
    resolved to a pass, and never dropped from the denominator: a trial we could
    not judge is a trial we did not win.

    An unmeasurable metric does not, however, make the *trial* unmeasurable when
    another metric already reads ``worse``. 打平 requires **every** metric to be
    不劣于, so one confirmed ``worse`` settles the trial no matter what the rest
    would have said. Filing such a trial as unmeasurable discards something we
    actually know and inflates the "cannot judge" bucket that P1 is measured by.

    Real case (2026-07-29, US-11906710-B2-e5): RMS 30.5x worse and distortion
    14.1x worse, with MTF withheld because the candidate returned the metric
    macro's seed value -- previously filed unmeasurable, though no MTF reading
    could have rescued it.

    The correction only ever moves trials *out* of the unmeasurable bucket and
    into ``worse``; it can never create a 打平, so it cannot flatter the headline.
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
    if any(m["verdict"] == "worse" for m in per_metric.values()):  # type: ignore[index]
        verdict = "worse"
    elif not measurable:
        verdict = "unmeasurable"
    else:
        verdict = "par"
    return {"verdict": verdict, "metrics": per_metric}


# ---------------------------------------------------------------------------
# One trial
# ---------------------------------------------------------------------------


def run_trial(
    plan: TrialPlan,
    *,
    out_dir: Path,
    timeout_seconds: float = 180.0,
    idle_timeout_seconds: float | None = IDLE_TIMEOUT_SECONDS,
    rebuild_seed_field: bool = True,
    wall_clock_budget_s: float | None = None,
    skip_tolerance: bool = False,
    distortion_constraint_pct: float | None = None,
    distortion_weight: float | None = None,
) -> dict[str, Any]:
    from app.core.engines.codev_batch import CodeVBatchError
    from app.core.engines.codev_optimize import run_codev_target_standard
    from app.core.engines.measurement_recipe import build_measurement_recipe
    from app.core.engines.seed_field_rebuild import (
        max_field_angle_deg,
        rebuild_seed_field_angles,
        rebuilt_bytes,
    )
    from app.core.engines.zmx_import_prep import (
        declared_f_number,
        declared_field_count,
        decode_zmx_text,
    )

    started = time.time()

    def over_budget() -> bool:
        """True once this trial has already spent its wall-clock allowance.

        Checked **between** stages, never inside one: a CODE V call in flight is
        bounded by ``timeout_seconds`` and the idle watchdog, not by this. So the
        budget caps what a trial *starts*, and a trial can overrun by at most one
        stage. Saying that plainly matters more than pretending to preempt.
        """

        return (
            wall_clock_budget_s is not None
            and (time.time() - started) >= wall_clock_budget_s
        )

    def exhausted(stage: str) -> dict[str, Any]:
        """`budget_exhausted` is its own verdict and is never folded elsewhere.

        Filing it as ``worse`` would invent a loss we never measured; filing it as
        ``unmeasurable`` would blame the optics for a stopwatch. It sits outside
        ``judged`` either way, so it can never flatter the headline -- but it must
        stay separable, because a run full of it means "buy more time", while a
        run full of ``unmeasurable`` means "the chain is broken".
        """

        record["verdict"] = "budget_exhausted"
        record["blocked_at"] = stage
        record["wall_clock_budget_s"] = wall_clock_budget_s
        record["elapsed_s"] = round(time.time() - started, 1)
        return record

    work = out_dir / f"trial_{plan.control_case_id}"
    work.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "schema": TRIAL_RESULT_SCHEMA,
        "plan": asdict(plan),
        "mtf_frequency_lpmm": MTF_FREQUENCY_LPMM,
        "mtf_nrd": MTF_NRD,
        # P4 gate: a number nobody can recompute is not a deliverable. The ZMX carries
        # the lens; this carries the instrument (which fields/wavelengths enter the
        # extremum, MTF frequency and ray density, radius-vs-diameter, no clipping),
        # plus the metric macro source verbatim so "recompute" means "run this code".
        # Which merit function produced this candidate. Two rounds that differ
        # here are not comparable, and a reader holding one JSON has no other way
        # to tell which one they have.
        "distortion_constraint_pct": distortion_constraint_pct,
        "distortion_weight": distortion_weight,
        "measurement_recipe": build_measurement_recipe(
            mtf_frequency_lpmm=MTF_FREQUENCY_LPMM,
            mtf_nrd=MTF_NRD,
        ),
    }

    # autovig learns num_fields from its rung-0 run, so a rung-0 timeout leaves
    # it unable to build any higher rung and it abandons the ladder after one
    # attempt per config. The 2026-07-28 pre-fix pilot lost 3/24 trials exactly
    # that way (elapsed pinned at 2 x the 180s hard timeout, to 0.1s). Reading
    # the declared count off the seed costs no CODE V call.
    # Disclosure, not a screen: the corpus-truth audit (2026-07-30) confirmed that
    # `image_height_mm` for the 403 ATELIER_REAL_IMH_MM cases is the **maximum over the
    # exit pupil**, not the chief-ray intercept -- 198/403 deviate by more than 10% from
    # their own efl*tan(fov/2), 31 by more than 100%. The spec handed to the optimiser
    # is that number (`spec_imh_mm`), so a reader has to be able to see how far this
    # trial's spec sits from first order. No threshold: a real lens with deliberate
    # distortion legitimately deviates, so the honest move is to report the figure.
    record["spec_imh_vs_first_order"] = _first_order_imh_disclosure(plan)

    seed_zmx = seed_zmx_path(plan)
    seed_text = decode_zmx_text(seed_zmx.read_bytes())[0]
    num_fields = declared_field_count(seed_text)
    record["seed_declared_num_fields"] = num_fields
    seed_f_number = declared_f_number(seed_text)

    if over_budget():
        return exhausted("before_control_probe")

    # --- measure the control BEFORE optimising, and refuse a control the two
    # --- engines disagree about ---
    # The spec used to come from `index.json`, whose `efl_mm` is **Optiland's**
    # paraxial EFL, while the control is scored by the **CODE V** probe. Measured
    # 2026-07-29 across the corpus: **41 of 440** controls disagree by more than
    # 2%, and **37 of those sit at a ratio of 1.5177** -- which is the last
    # element's own index (`GLAS ___BLANK 1 0 1.517 64.2`, the cover glass), so it
    # is a systematic import artefact, not scatter.
    #
    # Which engine is right is decidable from the design's own geometry, and it is
    # not CODE V: for `US-20210364737-A1-e1` (half field 14.205 deg, real image
    # height 2.6112 mm) Optiland's 10.3487 mm gives f*tan(theta) = 2.6197 -- 0.3%
    # off the declared height -- while CODE V's 15.7063 mm gives 3.9759, off by 52%.
    #
    # So this does **not** silently adopt either number. A control the two engines
    # read differently is a control we cannot claim to have measured, and the
    # candidate would be built to whichever scale we picked: at the same F/# and
    # the same field angle a uniformly smaller lens collects a linearly smaller
    # spot for free. `US-20220011544-A1-e5` measured 1.848 um against its
    # control's 51.45 um and scored **par on RMS spot**, ratio 0.036.
    #
    # Probing the control first costs no extra CODE V time -- the trial already
    # probes it once -- and now a control we cannot trust ends the trial *before*
    # the expensive stage instead of after it.
    control_quality = None
    try:
        control_quality = measure_image_quality(
            source_zmx=ZMX_DIR / plan.control_zmx,
            work_dir=work / "measure_control",
            tag="control",
            timeout_seconds=timeout_seconds,
            idle_timeout_seconds=IDLE_TIMEOUT_SECONDS,
        )
    except CodeVBatchError as exc:
        record["control_probe_error"] = {"kind": exc.kind, "detail": exc.message}
    record["control_quality"] = asdict(control_quality) if control_quality else None
    if control_quality is None or control_quality.efl_y_mm is None:
        record["verdict"] = "unmeasurable"
        record["blocked_at"] = "control_probe"
        record["elapsed_s"] = round(time.time() - started, 1)
        return record

    engine_ratio = control_quality.efl_y_mm / plan.spec_efl_mm if plan.spec_efl_mm else None
    record["control_engine_agreement"] = {
        "manifest_efl_mm": plan.spec_efl_mm,
        "probe_efl_mm": control_quality.efl_y_mm,
        "probe_over_manifest": engine_ratio,
        "tolerance": EFL_PARITY_TOLERANCE,
    }
    if engine_ratio is None or abs(engine_ratio - 1.0) > EFL_PARITY_TOLERANCE:
        record["verdict"] = "unmeasurable"
        record["blocked_at"] = "control_engine_disagreement"
        record["elapsed_s"] = round(time.time() - started, 1)
        return record

    # Agreed, so there is no choice left to make -- the two readings are the same
    # number. Taking it from the probe keeps the spec and the score on one engine.
    spec_efl_mm = float(control_quality.efl_y_mm)
    spec_f_number = (
        float(control_quality.f_number)
        if control_quality.f_number is not None
        else plan.spec_f_number
    )

    # --- the aperture half of reachability, which nothing was checking ---
    # `seed_efl_is_reachable` gates how far the optimiser may stretch the focal
    # length. `run_codev_target_standard` targets EFL **and F/#**, and nothing
    # gated the second one -- even though opening the aperture is the harder
    # direction: at a fixed focal length a smaller F/# is a proportionally wider
    # pupil, which is exactly what CODE V reports as "Abnormal AUTO Completion -
    # Unable to scale up Pupil and Field specifications".
    #
    # Not one trial that had to open the pupil by more than 5% produced a verdict,
    # and they burned 53.4% of the round -- see `MAX_PUPIL_GROWTH` for the split
    # and for the single-seed ladder that makes it causal. This preflight follows
    # the same pattern as `seed_field_not_rebuildable` below: record the reason,
    # keep the trial in the denominator, and do not spend CODE V time on it.
    #
    # It sits *after* the control probe on purpose: the spec F/# it divides by is
    # the probe's reading, not the plan's, so that the number being gated is the
    # one `run_codev_target_standard` will actually be handed.
    pupil_growth = (
        seed_f_number / spec_f_number
        if seed_f_number and spec_f_number and spec_f_number > 0
        else None
    )
    record["pupil_growth"] = {
        "seed_f_number": seed_f_number,
        "spec_f_number": spec_f_number,
        "growth": pupil_growth,
        "limit": MAX_PUPIL_GROWTH,
    }
    if pupil_growth is not None and pupil_growth > MAX_PUPIL_GROWTH:
        record["verdict"] = "spec_not_met"
        record["blocked_at"] = "pupil_growth_not_reachable"
        record["elapsed_s"] = round(time.time() - started, 1)
        return record

    # --- re-aim the seed at the requested field before optimising ---
    # Without this the candidate answers a different question: the optimiser
    # targets EFL and F/# only, so the field comes from the seed and the spec's
    # 像高/FOV are decoration. The conformance screen below would then reject
    # every trial, so the rebuild has to happen here rather than be diagnosed
    # after 46 minutes of CODE V time.
    optimise_from = seed_zmx
    if rebuild_seed_field:
        control_text = decode_zmx_text((ZMX_DIR / plan.control_zmx).read_bytes())[0]
        target_angle = max_field_angle_deg(control_text)
        rebuild = (
            rebuild_seed_field_angles(seed_zmx.read_bytes(), target_angle)
            if target_angle is not None
            else None
        )
        record["seed_field_rebuild"] = {
            "target_max_angle_deg": target_angle,
            "source_max_angle_deg": rebuild.source_max_angle_deg if rebuild else None,
            "scale": rebuild.scale if rebuild else None,
            "rebuilt": bool(rebuild and rebuild.rebuilt),
            "reason": (
                rebuild.reason
                if rebuild
                else "control ZMX states no field angle (non-angular FTYP)"
            ),
        }
        if rebuild is None or not rebuild.rebuilt:
            # Fail closed *before* spending CODE V time: a seed we cannot re-aim
            # can only produce a candidate for the wrong field.
            record["verdict"] = "spec_not_met"
            record["blocked_at"] = (
                "control_field_not_angular" if rebuild is None else "seed_field_not_rebuildable"
            )
            record["elapsed_s"] = round(time.time() - started, 1)
            return record
        # Deci-degrees, zero-padded and **dot-free**, mirroring the existing
        # `_vig0700` convention. `f"{angle:g}"` produced `_field45.1`, and a
        # `.<digits>` infix followed by non-extension content makes CODE V abort
        # the macro with "ERROR - Unable to open file" -- which
        # `ensure_buf_exp_safe_filename` exists to catch, and did, on the first
        # real-machine run of the field rebuild (2026-07-29).
        optimise_from = work / f"{seed_zmx.stem}_field{round(target_angle * 10):04d}.zmx"
        optimise_from.write_bytes(rebuilt_bytes(rebuild))
        record["seed_field_rebuild"]["output_zmx"] = str(optimise_from)

    if over_budget():
        return exhausted("before_optimize")

    # --- candidate: optimise the cross-brand seed toward the control's spec ---
    try:
        standard = run_codev_target_standard(
            source_zmx=optimise_from,
            work_dir=work / "optimize",
            target_efl_mm=spec_efl_mm,
            target_f_number=spec_f_number,
            target_imh_mm=plan.spec_imh_mm,
            num_fields=num_fields,
            timeout_seconds=timeout_seconds,
            # CODE V can stop computing after a ray error yet never exit. On one
            # measured trial nine such rungs each burned the full 300s timeout --
            # ~2700s of its 2735s wall clock. Cut those off by absence of output
            # progress, not by the error text (healthy runs print ray errors too).
            # Calibration of the bound itself: see IDLE_TIMEOUT_SECONDS.
            idle_timeout_seconds=idle_timeout_seconds,
            emit_optimized_zmx=True,
            # None (the default) leaves the merit function exactly as it was for
            # every earlier round, so this parameter cannot silently change a
            # baseline. See the `--distortion-bound` CLI flag for why it exists.
            distortion_constraint_pct=distortion_constraint_pct,
            distortion_weight=distortion_weight,
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
    # Both configs, always -- not only when neither could be preferred.
    #
    # `_select_preferred` picks best-of-2 on `post_aut.max_rms_spot_diameter_um`,
    # and RMS spot is **one of the three metrics P2 judges**: choosing on the
    # judged quantity is selection bias, and the comparison also ignores that the
    # two arms may have been optimised at different `autovig.edge_used` (a harder
    # clip is a narrower pupil, which lowers RMS for free). Changing the selection
    # rule alters what the headline means and wants a real-machine A/B, so this
    # records what was chosen over what -- disclosure now, rule change later.
    record["configs"] = {k: _config_summary(v) for k, v in standard.get("configs", {}).items()}
    if preferred is None:
        record["verdict"] = "unmeasurable"
        record["blocked_at"] = "optimize_no_preferred"
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

    if over_budget():
        return exhausted("before_probe")

    # --- measure the candidate with the same probe the control already went through ---
    measurements: dict[str, ImageQuality | None] = {"control": control_quality}
    try:
        measurements["candidate"] = measure_image_quality(
            source_zmx=Path(str(candidate_zmx)),
            work_dir=work / "measure_candidate",
            tag="candidate",
            timeout_seconds=timeout_seconds,
            idle_timeout_seconds=IDLE_TIMEOUT_SECONDS,
        )
    except CodeVBatchError as exc:
        record["candidate_probe_error"] = {"kind": exc.kind, "detail": exc.message}
        measurements["candidate"] = None

    record["candidate_quality"] = (
        asdict(measurements["candidate"]) if measurements["candidate"] else None
    )

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
    # The tolerance pair used to be described here as "the most expensive stage by
    # far (51 minutes for one trial, 2026-07-29)". That is **wrong, and it cost this
    # project a criterion** -- every round shipped `--skip-tolerance` on its strength,
    # so 交付物完整度 stayed `not_assessable`.
    #
    # Where 51 minutes really went, from the artifacts' own mtimes: the only trials in
    # that range are 4 in `D:/atelier-stagec-runs/four-piece-v2`, longest
    # `trial_US-11668898-B2-e6` at 3072.8 s. Its `optimize/` ran 18:17:11 -> 19:08:14 =
    # **3063.8 s, 99.7% of the trial** (the autovig ladder, rungs 300 s apart);
    # `measure_control` took 1.3 s and the tolerance stage finished ~8 s after optimize
    # did. The number was never a tolerance cost, and it was never a TOR failure cost
    # either -- an earlier attempt at this comment said "TOR aborted and the clock went
    # to the failure", which is a *second* wrong provenance. It went to the optimiser.
    #
    # Measured 2026-08-04 over a full 59-trial run with tolerance on: median trial
    # 24.9 s, whole run 31.5 min, `budget_exhausted` 0, ~2.3 s per side for TOR.
    # The 50-minute tail is real but it belongs to the autovig ladder, and it is a P1
    # cost question, not a reason to skip P3.
    # Skipping it does **not** make the trial `budget_exhausted`: the three P2
    # metrics were measured and their verdict stands. What is lost is a piece of the
    # P3 四件套, and the record says so by name rather than by absence.
    if skip_tolerance:
        # Explicit two-phase batching: P2 sample size first (the main indicator), P3
        # on a subset afterwards. Named `cli_request` so a phase-1 run can never be
        # mistaken for a run whose tolerance stage failed or timed out.
        record["tolerance"] = {"skipped": "cli_request"}
    elif over_budget():
        record["tolerance"] = {"skipped": "wall_clock_budget", "budget_s": wall_clock_budget_s}
    else:
        # The probe above already established, per side and for free, whether every
        # field evaluates -- which is exactly TOR's precondition. Pass it in rather
        # than paying CODE V to rediscover it.
        record["tolerance"] = _tolerance_pair(
            Path(str(candidate_zmx)), ZMX_DIR / plan.control_zmx,
            work / "tolerance", timeout_seconds, measurements,
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
        blocked_at, conformance = conformance_screen(
            measurements["candidate"], measurements["control"]
        )
        record["conformance"] = conformance
        if str(record.get("aut_converged")) != "1":
            blocked_at = "aut_not_converged"
        if blocked_at is not None:
            record["spec_verdict_override"] = record["verdict"]
            record["verdict"] = "spec_not_met"
            record["blocked_at"] = blocked_at
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
#: The TOR criterion here is polychromatic RMS wavefront error, so lower is
#: better and the threshold is an upper bound. Stated once and passed explicitly:
#: the orientation decides the sign of every degradation number reported.
TOLERANCE_DIRECTION = "max"

#: Illustrative, uncalibrated. Applied identically to candidate and control, so
#: the comparison survives the number being wrong; the absolute yield does not.
#:
#: Measured 2026-07-30: it also does not survive sitting *below the nominal*, which
#: it does on 13/118 stored field rows. Reported alongside
#: ``yield_is_informative`` and the threshold-free readings in tor_sensitivity --
#: never on its own.
YIELD_THRESHOLD_WAVES = 0.25
#: Above this share of samples outside TOR's linear model the yield is refused
#: rather than disclosed -- see tor_yield for why disclosure needs a ceiling.
MAX_OUT_OF_MODEL_FRACTION = 0.25


def _tor_criterion_block(quality: ImageQuality | None) -> str | None:
    """Why TOR must not be attempted on this side, or ``None`` to proceed.

    TOR needs the reference rays R1-R5 traceable from object to image -- 「Although
    reference rays can be blocked by apertures or obscurations, they must be
    traceable from object to image」 (CODE V 11.5 TroubleshootingGuide, "Analysis
    Errors and Warnings"). A lens that fails that gets ``ERROR - Ray tracing errors
    during clear aperture trace - OPTION TERMINATED`` and exports nothing.

    The probe above already answered it, for free, using the *same* criterion this
    TOR runs on: polychromatic RMS wavefront error. So this is not a proxy -- a
    withheld ``rms_wavefront_waves`` means that quantity was not obtainable from
    this lens, and TOR cannot obtain it either.

    Exact on the six p2-gated-20260729 trials: the one candidate with a wavefront
    reading (e11, 0.348343 waves) is the one whose TOR exported; the four whose
    reading was withheld as ``rms_wavefront_seed_value`` are the four that
    terminated. The reading also cross-checks the number this module keys its
    degeneracy test off -- e11's TOR PER nominal is 0.348154 waves, agreeing with
    the probe to 0.05% by an independent CODE V path.

    Not a threshold: the test is「is there a reading at all」.
    """

    if quality is None:
        return "image-quality probe did not return; nothing attests that TOR's criterion evaluates"
    if quality.rms_wavefront_waves is None:
        return (
            "probe could not measure RMS wavefront error -- TOR's own criterion; "
            f"withheld as {list(quality.withheld) or 'unknown'}"
        )
    return None


def _tolerance_pair(
    candidate_zmx: Path,
    control_zmx: Path,
    work_dir: Path,
    timeout_seconds: float,
    quality: Mapping[str, ImageQuality | None],
) -> dict[str, object]:
    """Run the same tolerance table on both sides and report sensitivity + yield.

    The tolerance table and every reported quantity are uncalibrated. The headline
    reading is the threshold-free degradation, not the absolute yield -- see
    ``app.core.engines.tor_sensitivity`` for why the absolute one goes silent
    whenever a lens's nominal already fails.
    """

    from app.core.engines.codev_batch import CodeVBatchError
    from app.core.engines.codev_tolerance import (
        TorCompensators,
        TorMonteCarlo,
        TorToleranceTable,
        run_codev_tor,
    )
    from app.core.engines.tor_sensitivity import (
        relative_yield_curve,
        tolerance_sensitivity,
        yield_is_informative,
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
        blocked = _tor_criterion_block(quality.get(side))
        if blocked is not None:
            out[side] = {"status": "unavailable", "reason": blocked, "codev_run_skipped": True}
            continue
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
                # Not the most expensive stage -- that claim was retired 2026-08-04
                # (see the block above: the "51 minutes" belonged to optimize, and
                # tolerancing measures at ~2.3 s per side). The watchdog stays because
                # TOR can still zombie on a lens whose rays misbehave, and this was the
                # one stage that ran without one; cheap in the median is not a reason
                # to leave the tail unbounded.
                idle_timeout_seconds=IDLE_TIMEOUT_SECONDS,
            )
        except (CodeVBatchError, OSError, ValueError) as exc:
            out[side] = {
                "error": f"{type(exc).__name__}: {exc}"[:400],
                # CODE V's own account of the failure, when it left one. Reporting
                # the error without it is what sent a whole investigation after
                # XDAT rows and vignetting rows on 2026-07-30.
                "codev_diagnosis": list(getattr(exc, "details", {}).get("codev_diagnosis", [])),
            }
            continue
        computed = compute_mc_yield(run.parse_result, policy)
        sensitivity = tolerance_sensitivity(run.parse_result, TOLERANCE_DIRECTION)
        curve = relative_yield_curve(run.parse_result, sensitivity, TOLERANCE_DIRECTION)
        informative = yield_is_informative(
            sensitivity, YIELD_THRESHOLD_WAVES, TOLERANCE_DIRECTION
        )
        out[side] = {
            "status": computed.status,
            # Threshold-free and therefore the reading to compare across sides.
            "sensitivity": {
                "status": sensitivity.status,
                "criterion": sensitivity.criterion,
                "reason": sensitivity.reason,
                "probability_levels": list(sensitivity.probability_levels),
                "nominal_by_field": {
                    f"z{row.zoom}:f{row.field}": row.nominal for row in sensitivity.fields
                },
                "degradation_by_field": {
                    f"z{row.zoom}:f{row.field}": list(row.degradation)
                    for row in sensitivity.fields
                },
                "worst_degradation": list(sensitivity.worst_degradation),
                "worst_nominal": sensitivity.worst_nominal,
            },
            "relative_yield_curve": {
                "status": curve.status,
                "reason": curve.reason,
                "judged_samples": curve.judged_samples,
                "out_of_model_samples": curve.out_of_model_samples,
                "points": [
                    {"nominal_multiple": point.nominal_multiple, "yield_fraction": point.yield_fraction}
                    for point in curve.points
                ],
            },
            # Kept for continuity, but never to be read alone: when
            # yield_is_informative is False the lens already failed unperturbed and
            # this number measures luck, not manufacturability.
            "yield_fraction": computed.yield_fraction,
            "yield_is_informative": informative,
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
    """What each optimiser arm produced, enough to audit which one was picked.

    ``autovig.edge_used`` and ``post_aut.max_rms_spot_diameter_um`` are the two
    that make the choice auditable: the selection is made on the RMS figure --
    itself one of the three judged metrics -- without regard to the pupil clip the
    arm needed to get there.
    """

    if not isinstance(config, dict):
        return {"unexpected": repr(config)[:200]}
    keep = (
        "error",
        "skipped",
        "aut_converged",
        "autovig.converged",
        "autovig.trace",
        "autovig.edge_used",
        "efl_target_deviation_pct",
        "post_aut.max_rms_spot_diameter_um",
    )
    return {k: config[k] for k in keep if k in config}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _edge_used(record: Mapping[str, Any]) -> float | None:
    try:
        return float(str(record.get("autovig_edge_used")))
    except (TypeError, ValueError):
        return None


def _config_selection_audit(records: list[dict[str, Any]]) -> dict[str, Any]:
    """What actually decided the two-config choice, and how much it was worth.

    The open audit item says the chooser ranks on `post_aut.max_rms_spot_diameter_um`,
    which is one of the three judged metrics -- best-of-2 on the quantity being judged
    is selection bias. Measured 2026-07-30 over 11 trials with two usable configs, the
    claim is true less often than it sounds: 6 of 11 were decided by `aut_converged`
    (which is not a judged metric), and only 5 of 11 by RMS. Where RMS did decide, the
    chosen arm was better by a median of 30%.

    So this reports the split rather than asserting the bias. `rms_gain` is the number a
    reader needs to judge how much the bias could be worth on a given run.

    The decider is derived from `_standard_config_rank` itself, not re-implemented and
    not parsed out of the reason string: a second copy of that ordering would eventually
    disagree with the real one, and then this audit would describe a selection that did
    not happen.
    """

    from app.core.engines.codev_optimize import _standard_config_rank

    deciders: dict[str, int] = {}
    gains: list[float] = []
    for record in records:
        configs = record.get("configs")
        if not isinstance(configs, Mapping) or len(configs) < 2:
            continue
        usable = {
            name: cfg
            for name, cfg in configs.items()
            if isinstance(cfg, Mapping) and "error" not in cfg
        }
        if len(usable) < 2:
            continue
        ranks = {name: _standard_config_rank(cfg) for name, cfg in usable.items()}
        ordered = sorted(ranks, key=ranks.__getitem__)
        best, second = ranks[ordered[0]], ranks[ordered[1]]
        # rank tuple = (errored, not_converged, [fields_dropped,] rms). Walk it and name
        # the first position that differs -- that is what decided the choice.
        names = (
            ("errored", "aut_not_converged", "fields_dropped", "rms_spot")
            if len(best) == 4
            else ("errored", "aut_not_converged", "rms_spot")
        )
        decider = "tie_fixed_priority"
        for index, name in enumerate(names):
            if best[index] != second[index]:
                decider = name
                break
        deciders[decider] = deciders.get(decider, 0) + 1
        if decider == "rms_spot" and best[-1] > 0:
            gains.append((second[-1] - best[-1]) / best[-1])

    gains.sort()
    return {
        "trials_with_two_usable_configs": sum(deciders.values()),
        "decided_by": deciders,
        # Only meaningful for the subset RMS decided; reported with its own n so it can
        # never be read as applying to every trial.
        "rms_gain": {
            "n": len(gains),
            "median": round(statistics.median(gains), 4) if gains else None,
            "min": round(min(gains), 4) if gains else None,
            "max": round(max(gains), 4) if gains else None,
        },
    }


def run_provenance(
    *,
    census_path: Path,
    rebuild_seed_field: bool,
    skip_tolerance: bool,
    trial_budget_seconds: float | None,
    timeout_seconds: float,
    distortion_constraint_pct: float | None = None,
    distortion_weight: float | None = None,
) -> dict[str, Any]:
    """What produced this run. Without it an A/B between two run directories is not
    interpretable: two sets of verdicts and nothing saying which code made them.

    Records the *parsed* flags rather than raw argv -- structured, and it cannot
    accidentally carry something from the command line that does not belong in an
    artifact.

    Every git lookup is defensive. A 12-hour real-machine run must never die because
    provenance collection failed; a missing field says so by name instead.
    """

    import subprocess

    def _git(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0:
            return None
        return (out.stdout or "").strip() or None

    # `_git` collapses "empty output" into None, so a CLEAN tree and an unavailable
    # git are indistinguishable through it. That is the mirror image of the flaw this
    # field exists to avoid -- absent reads as clean -- so probe availability
    # separately and let an empty porcelain mean clean.
    git_available = _git("rev-parse", "HEAD") is not None
    dirty = _git("status", "--porcelain")
    if git_available and dirty is None:
        dirty = ""  # git worked and reported nothing: the tree is clean
    census_digest = None
    if census_path.is_file():
        import hashlib

        census_digest = hashlib.sha256(census_path.read_bytes()).hexdigest()

    return {
        # The merit function this round optimised under. Two run directories that
        # differ here measured different things; without it an A/B is two piles of
        # verdicts with nothing saying which is which.
        "distortion_constraint_pct": distortion_constraint_pct,
        "distortion_weight": distortion_weight,
        "git_sha": _git("rev-parse", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        # A dirty tree means the sha does NOT describe the code that ran. Say so rather
        # than letting the sha imply reproducibility it does not have.
        "git_dirty": None if dirty is None else bool(dirty),
        "git_available": git_available,
        # `git status --porcelain` is "XY PATH" with XY exactly two status characters,
        # but a fixed [3:] slice loses the first path character on some line shapes
        # (observed: "cripts/..."). Strip from index 2 instead of assuming the gap.
        "git_dirty_paths": None if not dirty else sorted(
            stripped for line in dirty.splitlines() if (stripped := line[2:].strip())
        ),
        "census_path": str(census_path),
        "census_sha256": census_digest,
        "flags": {
            "rebuild_seed_field": rebuild_seed_field,
            "skip_tolerance": skip_tolerance,
            "trial_budget_seconds": trial_budget_seconds,
            "timeout_seconds": timeout_seconds,
        },
        "trial_schema": TRIAL_RESULT_SCHEMA,
    }


def _witness_shortfall(records: list[dict[str, Any]]) -> dict[str, Any]:
    """How often each side produced a reading on fewer fields than it declared.

    This is the P1 root cause as a headline number rather than something a reader has
    to grep the records for. Measured 2026-07-30: the dominant `unmeasurable` shape is a
    candidate at 1-of-2 fields against a control at 2-of-2, with the conformance screen
    passing and `aut_converged=1` -- the optimiser hits the spec and stops imaging
    off-axis, because `@rmssum` skips a field whose trace fails and so pays for dropping
    it.

    Reported for BOTH sides on purpose. A control that also drops a field is a different
    problem (the corpus lens is not traceable at its own declared field), and folding
    the two together would hide it.
    """

    counts = {
        "candidate_partial": 0,
        "candidate_zero": 0,
        "control_partial": 0,
        "control_zero": 0,
        "both_full": 0,
        "no_witness": 0,
    }
    for record in records:
        seen_any = False
        full = True
        for side in ("candidate", "control"):
            quality = record.get(f"{side}_quality")
            if not isinstance(quality, Mapping):
                continue
            declared = quality.get("num_fields")
            ok = quality.get("rms_fields_ok")
            if not isinstance(declared, (int, float)) or not isinstance(ok, (int, float)):
                continue
            seen_any = True
            if ok <= 0:
                counts[f"{side}_zero"] += 1
                full = False
            elif ok < declared:
                counts[f"{side}_partial"] += 1
                full = False
        if not seen_any:
            counts["no_witness"] += 1
        elif full:
            counts["both_full"] += 1
    return counts


def _deliverable_pieces(record: Mapping[str, Any]) -> dict[str, bool]:
    """Which of NORTH-STAR §1.1's four 交付物 pieces this trial actually produced.

    「缺一不算交付」 is the criterion's own wording, so the headline is the all-four
    count and the per-piece counts exist to say *which* piece is missing. Each test is
    for the thing being present and usable, never merely for a key existing:

    - 处方 ZMX: a path AND the file on disk. A recorded path to a file that is not
      there is not a deliverable.
    - 像质: all three judged metrics have a candidate reading. A withheld metric is
      absent by design (the witness gates), and counting a partial set would report
      exactly the flattering number those gates exist to refuse.
    - 公差良率: a candidate-side yield fraction. An error or a skip is not a yield.
    - 相对成本: a finite ratio.
    """

    candidate_zmx = record.get("candidate_zmx")
    prescription = bool(candidate_zmx) and Path(str(candidate_zmx)).is_file()

    metrics = record.get("metrics")
    image_quality = isinstance(metrics, Mapping) and all(
        isinstance(metrics.get(metric), Mapping)
        and metrics[metric].get("candidate") is not None
        for metric in P2_METRICS
    )

    tolerance = record.get("tolerance")
    candidate_tolerance = tolerance.get("candidate") if isinstance(tolerance, Mapping) else None
    yield_ok = isinstance(candidate_tolerance, Mapping) and isinstance(
        candidate_tolerance.get("yield_fraction"), (int, float)
    )

    cost = record.get("relative_cost_index")
    ratio = cost.get("ratio") if isinstance(cost, Mapping) else None
    cost_ok = isinstance(ratio, (int, float)) and math.isfinite(float(ratio))

    return {
        "prescription_zmx": prescription,
        "image_quality": image_quality,
        "tolerance_yield": yield_ok,
        "relative_cost": cost_ok,
    }


def _deliverable_completeness(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Criterion ③ over a run: how many trials produced all four pieces.

    A `--skip-tolerance` run can never reach four by construction, so the result says
    `not_assessable` and names the reason rather than reporting a zero that reads as a
    failure. That distinction is the whole point: "we did not measure it" and "it did
    not work" must not share a number.
    """

    per_piece: dict[str, int] = {}
    complete = 0
    on_spec = 0
    for record in records:
        pieces = _deliverable_pieces(record)
        for name, ok in pieces.items():
            per_piece[name] = per_piece.get(name, 0) + int(ok)
        four = all(pieces.values())
        complete += int(four)
        # Producing four pieces is not the same as delivering against the request.
        # Measured 2026-08-04: `US-12436366-B2-e5` produced all four while its
        # `blocked_at` was `efl_not_matched` (EFL +3.31%, candidate RMS 148.8 um) --
        # a design for a focal length nobody asked for. NORTH-STAR ① is "N 需求产 M
        # 交付物", so that row is a deliverable of nothing. Both numbers are reported:
        # `all_four` stays the count of rows that produced four pieces, `on_spec_four`
        # is the count that also hit the spec they were generated for.
        on_spec += int(four and not record.get("blocked_at"))

    skipped_by_request = sum(
        1
        for r in records
        if isinstance(r.get("tolerance"), Mapping)
        and r["tolerance"].get("skipped") == "cli_request"
    )
    assessable = skipped_by_request == 0
    return {
        "trials": len(records),
        "per_piece": per_piece,
        "all_four": complete if assessable else None,
        "on_spec_four": on_spec if assessable else None,
        "status": "measured" if assessable else "not_assessable",
        "reason": (
            None
            if assessable
            else (
                f"tolerance skipped by request on {skipped_by_request}/{len(records)} trials; "
                "四件套完整度 needs a run that measures the tolerance pair"
            )
        ),
    }


def _distinct_design_counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Distinct *designs* behind the trials, by prescription fingerprint.

    A file that cannot be fingerprinted is counted in `unfingerprinted` and left out of
    both counts -- never folded in as "one more design", which would inflate the
    denominator with something unread.
    """

    from app.core.engines.prescription_identity import fingerprint_zmx
    from scripts.p2_pair_census import STAGING_ZMX_DIR

    fingerprints: dict[str, set[str]] = {"controls": set(), "seeds": set(), "candidates": set()}
    unfingerprinted: list[str] = []
    for record in records:
        # The candidate is what criterion ① actually counts, and it was the one side
        # never fingerprinted here -- so `M` was the only headline number in the
        # artifact with no design-level denominator. Measured 2026-08-04: 50 delivered
        # rows are **30** distinct candidate prescriptions (20 rows re-derive a file
        # that already exists, because continuation patents give the same control
        # prescription a new number). `candidate_zmx` is an absolute path into the run
        # directory, not a corpus-relative name, so it is resolved separately below.
        candidate = record.get("candidate_zmx")
        if candidate:
            candidate_path = Path(str(candidate))
            candidate_fp = fingerprint_zmx(candidate_path) if candidate_path.is_file() else None
            if candidate_fp is None:
                unfingerprinted.append(str(candidate))
            else:
                fingerprints["candidates"].add(candidate_fp)

        plan = record.get("plan")
        if not isinstance(plan, dict):
            continue
        for bucket, key in (("controls", "control_zmx"), ("seeds", "seed_zmx")):
            name = plan.get(key)
            if not name:
                continue
            # Seeds live in two pools since 2026-08-03. Resolving both through
            # ZMX_DIR made every staging seed unfingerprintable, and this count is
            # the artifact's own honest denominator -- it silently read 2 when the
            # truth was 12. Exactly the defect `plan_trials` had, one function
            # over, and it landed on the number the caveats are written from.
            root = (
                STAGING_ZMX_DIR
                if bucket == "seeds" and str(plan.get("seed_pool")) == "staging"
                else ZMX_DIR
            )
            path = root / str(name)
            fingerprint = fingerprint_zmx(path) if path.is_file() else None
            if fingerprint is None:
                unfingerprinted.append(str(name))
                continue
            fingerprints[bucket].add(fingerprint)
    return {
        "controls": len(fingerprints["controls"]),
        "seeds": len(fingerprints["seeds"]),
        "candidates": len(fingerprints["candidates"]),
        "unfingerprinted": sorted(set(unfingerprinted)),
    }


def summarise(records: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts: dict[str, int] = {}
    for record in records:
        verdicts[str(record.get("verdict", "missing"))] = (
            verdicts.get(str(record.get("verdict", "missing")), 0) + 1
        )
    judged = verdicts.get("par", 0) + verdicts.get("worse", 0)
    # Kept separable on purpose: a run full of budget_exhausted means "buy more
    # time", a run full of unmeasurable means "the chain is broken". Both sit
    # outside `judged`, so neither can flatter the headline.
    budget_exhausted = verdicts.get("budget_exhausted", 0)
    seeds = {r["plan"]["seed_case_id"] for r in records if "plan" in r}
    designs = _distinct_design_counts(records)
    deliverables = _deliverable_completeness(records)
    witness = _witness_shortfall(records)
    selection = _config_selection_audit(records)
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
        # `case_id` counts *publications*, and the corpus is 442 files carrying 354
        # distinct prescriptions -- continuations republish the same embodiment under a
        # new number, so counting case_ids counts one design up to four times. These
        # two are the honest denominators for "样本量成立": report them next to any rate.
        "distinct_control_designs": designs["controls"],
        "distinct_seed_designs": designs["seeds"],
        "distinct_candidate_designs": designs["candidates"],
        "designs_unfingerprinted": designs["unfingerprinted"],
        # NORTH-STAR criterion ③: 交付物四件套完整度（缺一不算交付）.
        "deliverables": deliverables,
        # Why the unmeasurable trials are unmeasurable, as a number.
        "field_witness": witness,
        # How much of the headline could be best-of-2 on a judged metric.
        "config_selection": selection,
        "budget_exhausted": budget_exhausted,
        "tolerance_skipped_by_request": sum(
            1
            for r in records
            if isinstance(r.get("tolerance"), dict)
            and r["tolerance"].get("skipped") == "cli_request"
        ),
        "tolerance_skipped_for_budget": sum(
            1
            for r in records
            if isinstance(r.get("tolerance"), dict)
            and r["tolerance"].get("skipped") == "wall_clock_budget"
        ),
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
    # How far the pipeline is from producing a design for the requested field at
    # all. Reported over *every* trial that got as far as two measurements, not
    # only judged ones -- the screened-out trials are exactly the interesting
    # ones here, and their absence from the headline is what this number explains.
    coverage = [
        r["conformance"]["field_coverage_ratio"]
        for r in records
        if isinstance(r.get("conformance"), dict)
        and isinstance(r["conformance"].get("field_coverage_ratio"), (int, float))
    ]
    summary["field_coverage_ratio_n"] = len(coverage)
    summary["field_coverage_ratio_median"] = (
        round(statistics.median(coverage), 4) if coverage else None
    )
    summary["field_coverage_ratio_min"] = round(min(coverage), 4) if coverage else None
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
        f"  budget_exhausted        {summary['verdicts'].get('budget_exhausted', 0)}"
        "   <- ran out of clock, not of quality",
        f"distinct seeds used       {summary['distinct_seeds_used']} (publications)",
        # The line a reader must not miss: 442 corpus files are 354 distinct
        # prescriptions, so publication counts overstate independence.
        f"distinct CONTROL designs  {summary['distinct_control_designs']}",
        f"distinct SEED designs     {summary['distinct_seed_designs']}",
        # Criterion ① counts *candidates*, so this is the denominator `M` belongs to.
        # Printed next to the other two because the failure mode is reading a row
        # count as a design count -- measured 2026-08-04: 50 delivered rows, 30 designs.
        f"distinct CAND designs     {summary['distinct_candidate_designs']}",
        # Criterion ③. `all_four` is None on a run that skipped the tolerance pair --
        # printed as the reason, never as a zero that would read as a failure.
        "四件套 all four        "
        + (
            f"{summary['deliverables']['all_four']}/{summary['deliverables']['trials']}"
            f"   on-spec {summary['deliverables']['on_spec_four']}"
            "   <- on-spec is the one criterion ① counts"
            if summary["deliverables"]["all_four"] is not None
            else f"not assessable ({summary['deliverables']['reason']})"
        ),
        "  per piece              "
        + ", ".join(
            f"{name}={count}" for name, count in sorted(summary["deliverables"]["per_piece"].items())
        ),
        # The line that explains the unmeasurable count instead of leaving it a mystery.
        "field witness shortfall   "
        + ", ".join(
            f"{name}={count}" for name, count in sorted(summary["field_witness"].items()) if count
        ),
        "config choice decided by  "
        + (
            ", ".join(
                f"{name}={count}"
                for name, count in sorted(summary["config_selection"]["decided_by"].items())
            )
            or "n/a"
        ),
        "  RMS gain when RMS chose "
        + (
            f"median {summary['config_selection']['rms_gain']['median']:+.1%} "
            f"(n={summary['config_selection']['rms_gain']['n']})"
            if summary["config_selection"]["rms_gain"]["median"] is not None
            else "n/a"
        ),
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
    coverage_median = summary.get("field_coverage_ratio_median")
    if coverage_median is not None:
        lines.append(
            "field coverage cand/ctl   "
            f"median {coverage_median}  min {summary.get('field_coverage_ratio_min')}"
            f"   (n={summary.get('field_coverage_ratio_n', 0)}, 1.0 = same field)"
        )
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
    parser.add_argument(
        "--trial-budget-seconds",
        type=float,
        default=None,
        help=(
            "per-trial wall-clock allowance. Checked between stages, so a trial "
            "can overrun by at most one stage; a trial that runs out is filed as "
            "its own `budget_exhausted` verdict, never as worse or unmeasurable."
        ),
    )
    parser.add_argument(
        "--skip-tolerance",
        action="store_true",
        help=(
            "phase 1 of a two-phase batch: measure the three P2 metrics only. Filed "
            "as `skipped: cli_request` -- the verdict is unaffected, what is lost is "
            "one piece of the P3 四件套, recorded by name not by absence. "
            "NOTE: this flag is no longer a cost saving worth taking by default. It was "
            "introduced when tolerancing was believed to cost 51 minutes a trial; that "
            "51 minutes has since been traced to the optimiser's autovig ladder, not to "
            "TOR (see _tolerance_pair). Measured 2026-08-04 over a full 59-trial run, "
            "tolerancing on costs ~2.3 s per side and the whole run took 31.5 min "
            "(median trial 24.9 s). Skipping it is what kept 交付物完整度 at "
            "`not_assessable` for every prior round."
        ),
    )
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=IDLE_TIMEOUT_SECONDS,
        help=(
            "kill a rung that has written nothing for this long; 0 disables the watchdog. "
            "Runtime-configurable so the bound can be re-calibrated without a code edit "
            "(see scripts/codev_idle_gap_bench.py)."
        ),
    )
    parser.add_argument(
        "--distortion-bound",
        type=float,
        default=None,
        metavar="PCT",
        help=(
            "constrain the optimiser's distortion. Pass -1 for the seed's own "
            "measured value (`codev_optimize.SEED_BASELINE_DISTORTION`), or a "
            "percentage for a fixed bound. Default None = unconstrained, which is "
            "what every round before 2026-08-03 ran. "
            "Why it exists: on the 59-trial round of 2026-08-03 the candidates beat "
            "their controls on 43 of 49 judged trials for RMS spot and 43 of 49 for "
            "MTF, and lost distortion on 49 of 49 -- median 8x worse. 打平 needs "
            "every metric, so distortion alone accounts for the 0%% par rate. The "
            "merit function was never told distortion mattered. "
            "This was measured once before (2026-07-30, see SEED_BASELINE_DISTORTION) "
            "and rejected, but that was against seeds whose candidates read 445 um "
            "RMS -- the optimiser had no slack for another constraint. It does now."
        ),
    )
    parser.add_argument(
        "--distortion-weight",
        type=float,
        default=None,
        metavar="W",
        help=(
            "add a weighted distortion term to the AUT merit (drive @dstpct toward 0 "
            "at this weight) instead of a hard bound. Mutually exclusive with "
            "--distortion-bound. Default None = no operand at all, exactly as every "
            "round before 2026-08-03. "
            "Why this form rather than the bound: measured 2026-08-03, the bound is "
            "emitted into the sequence CODE V runs and is then simply violated -- "
            "AUT constraints are soft, and an infeasible one is left active rather "
            "than raising. A weight cannot be ignored the same way. "
            "`codev_optimize` records that this form has never had its real-machine "
            "A/B; the 2026-07-29 pilot estimated it would move par 2/12 -> 5/12."
        ),
    )
    parser.add_argument(
        "--no-field-rebuild",
        action="store_true",
        help=(
            "keep the pre-2026-07-29 behaviour: optimise the seed at its own field angle. "
            "Kept only so the rebuild can be A/B-ed on the real machine -- candidates "
            "produced this way answer a different spec and the conformance screen "
            "rejects them."
        ),
    )
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
    provenance = run_provenance(
        census_path=args.census,
        rebuild_seed_field=not args.no_field_rebuild,
        skip_tolerance=args.skip_tolerance,
        trial_budget_seconds=args.trial_budget_seconds,
        timeout_seconds=args.timeout,
        distortion_constraint_pct=args.distortion_bound,
        distortion_weight=args.distortion_weight,
    )
    (out_dir / "plan.json").write_text(
        json.dumps(
            {
                "trials_available": census_result["trials"],
                "distinct_seeds_available": census_result["distinct_seeds_used"],
                # The reachability-vs-quality conflict, per control. Measured 2026-07-30:
                # only 6 of 59 controls have a cross-source seed that is BOTH inside the
                # +25% focal-stretch limit and at or below the corpus median image
                # quality. That split is the finding, so it belongs in the run artifact
                # rather than only in a census return value nobody keeps.
                "seed_pool_basis": census_result.get("seed_pool_basis"),
                "seed_quality_limit_um": census_result.get("seed_quality_limit_um"),
                "seed_efl_max_stretch": census_result.get("seed_efl_max_stretch"),
                "run_provenance": provenance,
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
            record = run_trial(
                plan,
                out_dir=out_dir,
                timeout_seconds=args.timeout,
                idle_timeout_seconds=args.idle_timeout or None,
                rebuild_seed_field=not args.no_field_rebuild,
                wall_clock_budget_s=args.trial_budget_seconds,
                skip_tolerance=args.skip_tolerance,
                distortion_constraint_pct=args.distortion_bound,
                distortion_weight=args.distortion_weight,
            )
            (out_dir / f"trial_{plan.control_case_id}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            records.append(record)
            print(f"    -> {record.get('verdict')} ({record.get('elapsed_s')}s)", flush=True)
    finally:
        after = codev_sessions()
        print(f"红线① post-run CODE V sessions: {len(after)} {after}", flush=True)
        summary = summarise(records)
        summary["run_provenance"] = provenance
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
