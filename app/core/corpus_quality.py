"""Where a measured RMS spot sits inside the corpus -- a rank, not a verdict.

The open audit item this closes: a P2 par verdict says nothing useful if the control
it beat is itself a bad lens, and there was no way for a reader to tell. The obvious
fix -- an absolute image-quality floor on the control side -- needs a number nobody
has measured, and reusing an existing constant was tried and does not work (the only
candidate is an RMS *radius* at 50 lp/mm while the probe reports a *diameter*, and the
97.97 um control from the first gated reading sits comfortably inside it).

So this module answers the question without picking a threshold: it reports the
control's **percentile inside a named reference population**. A rank is scale-free and
immune to the distribution's tail -- which matters here, because the tail is not
merely long, it reaches 8.3e20 um.

What a reader gets: "this par was achieved against a control at p85 of the corpus",
i.e. 85% of the reference population images better. They draw their own line. We
report the number and name the denominator.

A second consumer arrived 2026-07-30: the product's own seed routing gate, which
until then compared a *stored Optiland half-field radius* against a bound sized for a
full-field CODE V diameter. This module now also serves the per-case readings that
gate reads, so gate and judgement share one definition of the measured quantity --
see `QUANTITY` and `load_per_case`.
"""

from __future__ import annotations

import bisect
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"

DISTRIBUTION_PATH = _DATA_DIR / "corpus_quality_distribution.json"
PER_CASE_PATH = _DATA_DIR / "corpus_routing_quality.json"

DISTRIBUTION_SCHEMA = "atelier.corpus_quality_distribution/v1"
PER_CASE_SCHEMA = "atelier.corpus_routing_quality/v1"

#: The measured quantity, spelled out once and carried by **both** artifacts.
#:
#: This is not documentation. The recurring defect in this repo is a threshold
#: measured in one convention and applied to another -- the routing gate compared a
#: half-field Optiland *radius* against a bound meant for a full-field CODE V
#: *diameter* (188x apart at the worst case), P4 compared a radius to a diameter, and
#: zmx_writer transposed VDY/VCY, all inside one day. A shared literal turns "same
#: quantity" into something a test can assert instead of something a reader must
#: notice.
QUANTITY = "max over fields of CODE V's RMS spot size, in um -- a diameter, not a radius"

#: Which cases earn a reading at all. `@rmssum` silently skips fields whose trace
#: failed and returns the max over the survivors, so a partially-traced case reports
#: a *smaller* number than it deserves.
CRITERION = (
    "no CODE V error and every declared field produced a positive per-field "
    "SPOTDATA reading (n_positive == num_fields)"
)

#: The call itself. Identical to the operand behind the P2 judgement, which is the
#: whole reason the census is reused instead of re-measured.
INSTRUMENT = (
    "SPOTDATA(1,f,1,0.01,'CEN',0,0,^spot) -> ^spot(1) in mm, x1000 -- "
    "identical to @rmssum's per-field operand"
)


@lru_cache(maxsize=1)
def load_distribution(path: Path | None = None) -> dict[str, Any]:
    """Load the committed distribution artifact.

    Committed rather than recomputed on import because the source census is a runtime
    product that lives outside the worktree (`D:/atelier-stagec-runs/...`), so a
    machine without it must still be able to read a reported percentile.
    """

    payload = json.loads((path or DISTRIBUTION_PATH).read_text(encoding="utf-8"))
    if payload.get("schema") != DISTRIBUTION_SCHEMA:
        raise ValueError(f"unexpected distribution schema: {payload.get('schema')!r}")
    return payload


def rms_percentile(rms_spot_um: float, *, path: Path | None = None) -> float | None:
    """Percentile of `rms_spot_um` in the reference population; None if unusable.

    Returns the fraction of the population that images **better** (smaller spot),
    expressed in percent. `None` for a non-positive or non-finite input -- both are
    already the project's sentinel shapes for "not measured", and a rank for a
    sentinel would be a fabricated reading.
    """

    try:
        value = float(rms_spot_um)
    except (TypeError, ValueError):
        return None
    if not (value > 0.0) or value != value or value in (float("inf"), float("-inf")):
        return None
    sorted_values = load_distribution(path)["sorted_rms_spot_um"]
    if not sorted_values:
        return None
    return 100.0 * bisect.bisect_left(sorted_values, value) / len(sorted_values)


def rms_at_percentile(percentile: float, *, path: Path | None = None) -> float:
    """The population's value at a reported rank -- the inverse of `rms_percentile`.

    Deliberately restricted to the quantiles the artifact reports, so any threshold
    built on this is traceable to a literal line in the committed JSON rather than to
    an interpolation only this function knows how to redo.
    """

    key = f"p{int(percentile)}"
    percentiles = load_distribution(path)["percentiles"]
    if key not in percentiles:
        raise KeyError(f"{key} is not a reported quantile; have {sorted(percentiles)}")
    return float(percentiles[key])


def reference_population(path: Path | None = None) -> dict[str, Any]:
    """The denominator, spelled out. Never report a percentile without it."""

    payload = load_distribution(path)
    return {
        "n": payload["n"],
        "pool": payload["pool"],
        "criterion": payload["criterion"],
        "census_run": payload["provenance"]["census_run"],
        "caveats": payload["caveats"],
    }


# ---------------------------------------------------------------------------
# Per-case readings
#
# The distribution above answers "where does this number sit"; routing needs the
# other direction -- "what is *this case's* number" -- and needs it on a machine with
# no CODE V and no census (the census is a runtime product under
# `D:/atelier-stagec-runs/...`). Hence a second committed artifact carrying the same
# quantity, keyed by case id.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_per_case(path: Path | None = None) -> dict[str, Any]:
    """Load the committed per-case artifact, refusing a mismatched convention.

    The schema check is the cheap half. The `QUANTITY` check is the load-bearing
    half: it is what stops a future rebuild from quietly repopulating this file with
    radii, or with half-field values, while every caller keeps comparing it against a
    full-field diameter threshold.
    """

    payload = json.loads((path or PER_CASE_PATH).read_text(encoding="utf-8"))
    if payload.get("schema") != PER_CASE_SCHEMA:
        raise ValueError(f"unexpected per-case schema: {payload.get('schema')!r}")
    if payload.get("quantity") != QUANTITY:
        raise ValueError(f"per-case artifact measures something else: {payload.get('quantity')!r}")
    return payload


def case_rms_spot_um(case_id: str, *, path: Path | None = None) -> float | None:
    """This case's RMS spot in `QUANTITY`, or None when it has no reading.

    `None` means "not measured", never "fine": the corpus contains cases CODE V
    cannot trace at all and cases that traced only part of the field, and both would
    otherwise inherit whatever optimistic number an earlier pipeline stored. Callers
    gating on quality must fail closed on `None`.
    """

    value = load_per_case(path)["rms_spot_um_by_case_id"].get(case_id)
    if value is None:
        return None
    reading = float(value)
    if not (reading > 0.0) or reading != reading:
        return None
    return reading


def per_case_population(path: Path | None = None) -> dict[str, Any]:
    """The per-case artifact's denominator and provenance, for the same reason."""

    payload = load_per_case(path)
    return {
        "n": payload["n"],
        "pool": payload["pool"],
        "criterion": payload["criterion"],
        "quantity": payload["quantity"],
        "census_run": payload["provenance"]["census_run"],
        "census_sha256": payload["provenance"]["census_sha256"],
        "caveats": payload["caveats"],
    }
