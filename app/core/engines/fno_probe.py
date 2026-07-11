"""FNO (explicit F# target) failure-mode evidence probe — Phase 15 Stage A/B.

Context (see ``.planning/debug/codev-target-convergence.md`` and
``.planning/loop/opt3-final-handoff-2026-07-09.md`` limitation #1): the
existing target-mode machinery in ``codev_optimize.py`` (``run_codev_target``
/ ``run_codev_target_autovig``) already supports an explicit CODE V ``FNO
<target>`` command via ``target_f_number``, but it has only ever been
exercised at the seed's *own* native F# (Stage A parity smoke) or left unset.
Setting ``FNO`` to a value that genuinely differs from the seed's native F#
on a wide-FOV seed is documented to break AUT's ray tracing (chief ray
missing / total internal reflection) because CODE V does not automatically
redo ray-aiming for a new aperture stop after a ZEMAXOS_TO_CV import.

This module is the **failure-mode evidence harness** for that specific gap:
it builds a short, isolated CODE V probe (EFL held at the seed's own native
value so any observed failure is attributable to the FNO retarget alone, not
a simultaneous EFL retarget) and classifies *how* the probe failed (or
didn't) from the CODE V ``.lis`` listing text.

It reuses ``codev_optimize.build_codev_target_sequence`` /
``codev_optimize.run_codev_target`` directly — already real-machine-validated
macro syntax for the ``FNO``/``AUT``/three-snapshot contract — rather than
inventing new ``.seq`` syntax. The only new logic here is the ``.lis``
failure classifier and a thin isolation wrapper around the existing runner.

Honesty invariant (AGENTS.md 北极星 [EXPERT] 红线): this module only
*classifies* failure signatures from real CODE V output. It never judges
design quality or "good enough" — that judgment stays with 资深设计师.

Regex patterns for ``TIR`` and ``chief-ray-missing`` are derived from real
``.lis`` evidence already on disk (see
``.planning/loop/candidates-2026-07-09/US20170045714A1/both/
atelier_codev_target_A_vig020.lis`` lines ~876-895: ``RAY ERROR: REFL <n>``
and ``RAY ERROR: MISS <n>`` co-occurring with a ``WARNING - Ray aiming not
used.`` header). The ``aperture-conflict`` pattern is **pending-real-machine
validation** (no confirmed real ``.lis`` sample yet showing this specific
failure mode under an explicit off-native FNO target) — it is seeded from
the one aperture-scaling termination phrase already known to
``codev_optimize.parse_aut_error_trace``
(``"Unable to scale up Pupil and Field specifications"``) plus a generic
aperture/EPD conflict regex. Stage 15-2 real-machine evidence should be used
to refine or replace this pattern if it never fires or fires on the wrong
things.
"""

from __future__ import annotations

import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.core.engines.codev_batch import DEFAULT_CODEV_EXECUTABLE, CodeVBatchError
from app.core.engines.codev_optimize import build_codev_target_sequence, run_codev_target

FnoFailureCategory = Literal[
    "ok", "TIR", "chief-ray-missing", "aperture-conflict", "other", "timeout"
]

# Real-evidence patterns (see module docstring for the .lis line numbers this
# was derived from).
_TIR_RE = re.compile(r"RAY ERROR:\s*REFL\b|Total\s+reflection", re.IGNORECASE)
_CHIEF_RAY_MISS_RE = re.compile(r"RAY ERROR:\s*MISS\b", re.IGNORECASE)
_RAY_AIMING_WARNING_RE = re.compile(r"Ray aiming not used", re.IGNORECASE)
# pending-real-machine validation — see module docstring.
_APERTURE_CONFLICT_RE = re.compile(
    r"Unable to scale up Pupil and Field specifications"
    r"|aperture[^\n]{0,40}(?:conflict|exceed|error)"
    r"|EPD[^\n]{0,40}(?:conflict|exceed|error)",
    re.IGNORECASE,
)
_AUT_STRUCTURE_RE = re.compile(r"CYCLE NUMBER|AUTO Completion", re.IGNORECASE)
_EXCERPT_CHARS = 500


@dataclass(frozen=True)
class FnoFailureClassification:
    """Failure-mode classification of one CODE V ``.lis`` listing.

    ``category`` is one of the five text-derived buckets from the module
    docstring (``timeout`` is never produced by this pure-text classifier —
    it is a process-level outcome added by ``run_fno_probe``, not something
    visible in ``.lis`` content alone).
    """

    category: Literal["ok", "TIR", "chief-ray-missing", "aperture-conflict", "other"]
    refl_count: int
    miss_count: int
    ray_aiming_warning: bool
    aperture_conflict_matched: str | None
    excerpt: str | None
    note: str

    def describe(self) -> dict[str, object]:
        return {
            "category": self.category,
            "refl_count": self.refl_count,
            "miss_count": self.miss_count,
            "ray_aiming_warning": self.ray_aiming_warning,
            "aperture_conflict_matched": self.aperture_conflict_matched,
            "excerpt": self.excerpt,
            "note": self.note,
        }


def classify_fno_listing(listing_text: str | None) -> FnoFailureClassification:
    """Classify a CODE V ``.lis`` listing's ray-tracing failure signature.

    Pure text -> classification, never raises. Priority order when multiple
    marker types co-occur (real evidence shows ``REFL`` and ``MISS`` often
    appear together in the same listing, e.g. 14 REFL + 105 MISS in the
    US20170045714A1 both/vig020 sample): ``TIR`` > ``aperture-conflict`` >
    ``chief-ray-missing`` > ``ok`` > ``other``. Rationale: the existing
    diagnosis (``.planning/debug/codev-target-convergence.md`` "诊断：EFL
    收敛拉不动=SETUP 非本征") identifies total-internal-reflection at
    marginal rays as the deeper root cause; ``MISS`` errors are frequently a
    downstream symptom of the same ray-solving breakdown. This is a
    priority-ordered heuristic for bucketing, not a quality judgment.
    """

    if not listing_text or not listing_text.strip():
        return FnoFailureClassification(
            category="other",
            refl_count=0,
            miss_count=0,
            ray_aiming_warning=False,
            aperture_conflict_matched=None,
            excerpt=None,
            note="no-listing-text",
        )

    refl_count = len(_TIR_RE.findall(listing_text))
    miss_count = len(_CHIEF_RAY_MISS_RE.findall(listing_text))
    ray_aiming_warning = bool(_RAY_AIMING_WARNING_RE.search(listing_text))
    aperture_match = _APERTURE_CONFLICT_RE.search(listing_text)
    aperture_conflict_matched = aperture_match.group(0) if aperture_match else None

    if refl_count > 0:
        category: Literal["ok", "TIR", "chief-ray-missing", "aperture-conflict", "other"] = (
            "TIR"
        )
        note = f"{refl_count} RAY ERROR: REFL occurrence(s)"
    elif aperture_conflict_matched is not None:
        category = "aperture-conflict"
        note = f"matched: {aperture_conflict_matched!r}"
    elif miss_count > 0:
        category = "chief-ray-missing"
        note = f"{miss_count} RAY ERROR: MISS occurrence(s)"
        if ray_aiming_warning:
            note += "; Ray aiming not used"
    elif _AUT_STRUCTURE_RE.search(listing_text):
        category = "ok"
        note = "no RAY ERROR / aperture-conflict markers; AUT structure present"
    else:
        category = "other"
        note = "no known failure markers and no recognizable AUT structure"

    excerpt = listing_text[:_EXCERPT_CHARS] if category == "other" else None

    return FnoFailureClassification(
        category=category,
        refl_count=refl_count,
        miss_count=miss_count,
        ray_aiming_warning=ray_aiming_warning,
        aperture_conflict_matched=aperture_conflict_matched,
        excerpt=excerpt,
        note=note,
    )


def _fmt_fnum_filename_token(value: float) -> str:
    """Dot-free filename token for an explicit F# probe target.

    Same CODE V ``BUF EXP`` "Unable to open file." filename hazard documented
    on ``codev_optimize._fmt_edge_filename_token`` (dot infix followed by
    non-extension content aborts the macro), but F# probe targets are not
    bounded to ``[0,1)`` like vignetting edges, so this is a dedicated helper
    at 0.01 resolution rather than a reuse of the vignetting-specific one.
    """
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"value must be finite and non-negative: {value!r}")
    return f"_fno{round(numeric * 100):04d}"


def build_fno_probe_sequence(
    *,
    source_zmx: Path | str,
    result_path: Path | str,
    native_efl_mm: float,
    target_f_number: float,
    stage: str = "probe",
    max_cycles: int = 2,
    min_cycles: int = 1,
) -> str:
    """Build a short, isolated FNO-retarget probe sequence.

    Thin wrapper over ``codev_optimize.build_codev_target_sequence`` that
    fixes the invariants this module needs for clean attribution:

    - ``target_efl_mm=native_efl_mm`` — EFL is held at the seed's own native
      value, so any observed ray-tracing failure is attributable to the FNO
      retarget alone, not a simultaneous EFL retarget.
    - ``extra_dof="none"``, ``vignetting=None`` — no asphere/glass DOF, no
      autovig clipping; this probe isolates the raw FNO effect.
    - ``max_cycles``/``min_cycles`` default to a short probe (2/1) because
      the ray-tracing failure modes under investigation manifest at CYCLE 0
      (already proven in ``.planning/debug/codev-target-convergence.md``:
      "从 CYCLE 0 就 RAY ERROR: REFL 4/14") — a short probe is enough
      evidence without paying for a full 25-cycle optimization search.
    """
    return build_codev_target_sequence(
        source_zmx=source_zmx,
        result_path=result_path,
        target_efl_mm=native_efl_mm,
        target_f_number=target_f_number,
        stage=stage,
        extra_dof="none",
        vignetting=None,
        max_cycles=max_cycles,
        min_cycles=min_cycles,
    )


@dataclass(frozen=True)
class FnoProbeResult:
    """One (seed, target F#) cell of the Stage B failure-mode matrix."""

    source_zmx: str
    native_fnum: float
    native_efl_mm: float
    target_f_number: float
    direction: Literal["tighten", "loosen"]
    outcome: FnoFailureCategory
    classification: FnoFailureClassification | None
    aut_converged: bool | None
    efl_target_deviation_pct: float | None
    post_aut_fno: float | None
    error_kind: str | None
    error_detail: str | None
    preflight: str | None
    duration_seconds: float | None
    seq_path: str | None
    lis_path: str | None
    tsv_path: str | None

    def describe(self) -> dict[str, object]:
        return {
            "source_zmx": self.source_zmx,
            "native_fnum": self.native_fnum,
            "native_efl_mm": self.native_efl_mm,
            "target_f_number": self.target_f_number,
            "direction": self.direction,
            "outcome": self.outcome,
            "classification": self.classification.describe()
            if self.classification is not None
            else None,
            "aut_converged": self.aut_converged,
            "efl_target_deviation_pct": self.efl_target_deviation_pct,
            "post_aut_fno": self.post_aut_fno,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "preflight": self.preflight,
            "duration_seconds": self.duration_seconds,
            "seq_path": self.seq_path,
            "lis_path": self.lis_path,
            "tsv_path": self.tsv_path,
        }


def _expected_probe_paths(work_dir: Path, stage: str, tag: str) -> tuple[Path, Path, Path]:
    """Predict the .seq/.tsv/.lis paths ``run_codev_target`` will use for a
    given ``rung_filename_tag`` (mirrors the naming in
    ``codev_optimize.run_codev_target`` exactly — kept in sync deliberately
    rather than importing a private helper, since the naming is a stable,
    documented contract of that function's ``rung_filename_tag`` parameter).
    """
    stem = f"atelier_codev_target_{stage}{tag}"
    return work_dir / f"{stem}.seq", work_dir / f"{stem}.tsv", work_dir / f"{stem}.lis"


def _read_lis_fail_open(lis_path: Path) -> str | None:
    try:
        if not lis_path.is_file():
            return None
        return lis_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def run_fno_probe(
    *,
    source_zmx: Path | str,
    work_dir: Path | str,
    native_efl_mm: float,
    native_fnum: float,
    target_f_number: float,
    direction: Literal["tighten", "loosen"],
    stage: str = "probe",
    executable: Path | str | os.PathLike[str] = DEFAULT_CODEV_EXECUTABLE,
    timeout_seconds: float = 90.0,
    platform_name: str = os.name,
    max_cycles: int = 2,
    min_cycles: int = 1,
) -> FnoProbeResult:
    """Run one isolated FNO-retarget probe and classify its outcome.

    Always attempts to read the run's ``.lis`` listing from disk (via the
    predictable ``rung_filename_tag``-derived path) regardless of whether
    ``run_codev_target`` raised — CODE V may have produced a listing even on
    a path that ultimately raises (e.g. a preflight rejection happens
    *after* a successful batch run; a timeout kill may still leave a partial
    listing behind, claimed via ``codev_batch``'s before/after snapshot
    diff). Falls back to ``CodeVBatchError.details["listing_tail"]`` when the
    on-disk file is unavailable (e.g. genuinely never produced).

    A run timeout always reports ``outcome="timeout"`` regardless of what a
    partial listing might suggest — the timeout itself is the primary
    evidence (see brief: "超时也是一类证据"); the partial classification (if
    any) is still attached as ``classification`` for extra context.
    """

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    tag = _fmt_fnum_filename_token(target_f_number)
    seq_path, tsv_path, lis_path = _expected_probe_paths(work_dir, stage, tag)

    started = time.monotonic()
    try:
        data = run_codev_target(
            source_zmx=source_zmx,
            work_dir=work_dir,
            target_efl_mm=native_efl_mm,
            target_f_number=target_f_number,
            stage=stage,
            executable=executable,
            timeout_seconds=timeout_seconds,
            platform_name=platform_name,
            extra_dof="none",
            vignetting=None,
            max_cycles=max_cycles,
            min_cycles=min_cycles,
            rung_filename_tag=tag,
        )
    except CodeVBatchError as exc:
        duration = time.monotonic() - started
        listing_text = _read_lis_fail_open(lis_path)
        if listing_text is None:
            tail = exc.details.get("listing_tail")
            listing_text = tail if isinstance(tail, str) and tail else None
        classification = classify_fno_listing(listing_text) if listing_text else None
        preflight = exc.details.get("preflight")
        outcome: FnoFailureCategory
        if exc.kind == "timeout":
            outcome = "timeout"
        elif classification is not None:
            outcome = classification.category
        else:
            outcome = "other"
        return FnoProbeResult(
            source_zmx=Path(source_zmx).name,
            native_fnum=native_fnum,
            native_efl_mm=native_efl_mm,
            target_f_number=target_f_number,
            direction=direction,
            outcome=outcome,
            classification=classification,
            aut_converged=None,
            efl_target_deviation_pct=None,
            post_aut_fno=None,
            error_kind=exc.kind,
            error_detail=exc.message,
            preflight=str(preflight) if preflight else None,
            duration_seconds=duration,
            seq_path=str(seq_path) if seq_path.is_file() else None,
            lis_path=str(lis_path) if lis_path.is_file() else None,
            tsv_path=None,
        )

    duration = time.monotonic() - started
    listing_text = _read_lis_fail_open(lis_path)
    classification = classify_fno_listing(listing_text)

    def _f(key: str) -> float | None:
        try:
            value = float(str(data.get(key, "")))
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None

    return FnoProbeResult(
        source_zmx=Path(source_zmx).name,
        native_fnum=native_fnum,
        native_efl_mm=native_efl_mm,
        target_f_number=target_f_number,
        direction=direction,
        outcome=classification.category,
        classification=classification,
        aut_converged=str(data.get("aut_converged")) == "1",
        efl_target_deviation_pct=_f("efl_target_deviation_pct"),
        post_aut_fno=_f("post_aut.fno"),
        error_kind=None,
        error_detail=None,
        preflight=None,
        duration_seconds=duration,
        seq_path=str(seq_path) if seq_path.is_file() else None,
        lis_path=str(lis_path) if lis_path.is_file() else None,
        tsv_path=str(tsv_path) if tsv_path.is_file() else None,
    )
