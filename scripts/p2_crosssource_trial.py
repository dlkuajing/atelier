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
IDLE_TIMEOUT_SECONDS = 60.0
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
    rebuild_seed_field: bool = True,
    wall_clock_budget_s: float | None = None,
) -> dict[str, Any]:
    from app.core.engines.codev_batch import CodeVBatchError
    from app.core.engines.codev_optimize import run_codev_target_standard
    from app.core.engines.seed_field_rebuild import (
        max_field_angle_deg,
        rebuild_seed_field_angles,
        rebuilt_bytes,
    )
    from app.core.engines.zmx_import_prep import declared_field_count, decode_zmx_text

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
    }

    # autovig learns num_fields from its rung-0 run, so a rung-0 timeout leaves
    # it unable to build any higher rung and it abandons the ladder after one
    # attempt per config. The 2026-07-28 pre-fix pilot lost 3/24 trials exactly
    # that way (elapsed pinned at 2 x the 180s hard timeout, to 0.1s). Reading
    # the declared count off the seed costs no CODE V call.
    seed_zmx = ZMX_DIR / plan.seed_zmx
    num_fields = declared_field_count(decode_zmx_text(seed_zmx.read_bytes())[0])
    record["seed_declared_num_fields"] = num_fields

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
            idle_timeout_seconds=IDLE_TIMEOUT_SECONDS,
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
    # The tolerance pair is the most expensive stage by far (51 minutes for one
    # trial, measured 2026-07-29), so it is the one the budget most often lands
    # on. Skipping it does **not** make the trial `budget_exhausted`: the three
    # P2 metrics were measured and their verdict stands. What is lost is a piece
    # of the P3 四件套, and the record says so by name rather than by absence.
    if over_budget():
        record["tolerance"] = {"skipped": "wall_clock_budget", "budget_s": wall_clock_budget_s}
    else:
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
                # The most expensive stage in a trial (51 minutes measured on one
                # trial, 2026-07-29), so a zombie here costs more than anywhere
                # else in the chain -- and it was the one stage still running
                # without the watchdog.
                idle_timeout_seconds=IDLE_TIMEOUT_SECONDS,
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
        "budget_exhausted": budget_exhausted,
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
            record = run_trial(
                plan,
                out_dir=out_dir,
                timeout_seconds=args.timeout,
                rebuild_seed_field=not args.no_field_rebuild,
                wall_clock_budget_s=args.trial_budget_seconds,
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
