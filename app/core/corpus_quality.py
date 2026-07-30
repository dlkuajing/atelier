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
"""

from __future__ import annotations

import bisect
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DISTRIBUTION_PATH = Path(__file__).resolve().parents[1] / "data" / "corpus_quality_distribution.json"

DISTRIBUTION_SCHEMA = "atelier.corpus_quality_distribution/v1"


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
