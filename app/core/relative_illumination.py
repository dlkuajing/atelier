"""Relative illumination (RI) compute — generator-stage, uses a real Optic.

权威依据: `docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`
§7-D. `RI(field) = cos^4(field_angle) * vignetting_factor(field)`, normalized so
the on-axis field is `vignetting_factor(0) == 1.0` by construction.

`score_candidate` (`app/core/orchestration/scorecard.py`) is a pure function
that only consumes `GeneratedCandidate.optical_extras.ri_by_field` — it never
touches `optic`/ZMX. This module is where the one-time optic-based compute
happens, at generator stage (`RetrievalGenerator._generate`,
`app/core/orchestration/generators.py`), reusing the exact same
load-normalize pattern as `demo_cache.py::_compute_analysis_family`
(`load_normalized_zmx` + `regularize_fields_to_angle`) — no new optical
engine, per spec §7-D ("能力仍是现有渐晕+光追，非新引擎").

**Vignetting-factor honesty note** (fact-checked against the current ZMX ammo
library, 2026-07-09): none of the `data/zmx/*.zmx` patent-derived
prescriptions declare a `CLAP`/`FLAP` per-surface clear aperture, nor a
nonzero `VCXN`/`VCYN` vignetting-compression factor (grep-verified across the
whole `data/zmx/` tree — zero matches). Optiland's ray tracer therefore
performs no physical aperture clipping on these optics today: a full-aperture
real-ray bundle at any field reaches the image plane un-blocked (empirically
confirmed — see task report). `vignetting_factor` below is computed from a
*real* ray trace (fraction of traced rays that land finite with nonzero
intensity, relative to the same fraction on-axis) — it is not fabricated, and
today it honestly reports ~1.0 for this library because there is no declared
clear-aperture geometry to violate. If a future intake pipeline starts
carrying `CLAP` data, this function picks it up automatically with no code
change. The `cos^4(theta)` term remains the real, always-active falloff
signal for wide-FOV phone lenses.
"""

from __future__ import annotations

import math
import warnings
from functools import lru_cache

import numpy as np

from app.core.mtf_fields import MTF_CANONICAL_FIELD_FRACS, format_mtf_field_fraction
from app.core.optical_sample import OpticalSampleData
from app.core.orchestration.candidate import MetricValue
from app.core.zmx_ingest import ZMX_AMMO_DIR, load_normalized_zmx, regularize_fields_to_angle

# Coarse hexapolar ring count for the pass/fail pupil sample. RI only needs a
# pass-fraction estimate (not fine image-quality metrology), so this stays
# far below the ~32-64 rings used for MTF/spot-diagram fidelity — keeps
# generator-stage RI compute in the ~100ms/case range (benchmarked).
_RI_NUM_RAYS = 8
_RI_DISTRIBUTION = "hexapolar"


def _empty_result() -> dict[str, MetricValue]:
    return {
        format_mtf_field_fraction(frac): MetricValue(value=None, status="unavailable")
        for frac in MTF_CANONICAL_FIELD_FRACS
    }


def _traced_pass_fraction(optic, hx: float, hy: float, wavelength_um: float) -> float | None:
    """Fraction of a coarse pupil ray grid that reaches the image plane finite
    and with nonzero intensity. `None` on any tracing failure (fail closed)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            optic.trace(hx, hy, wavelength_um, _RI_NUM_RAYS, _RI_DISTRIBUTION)
            surf = optic.surfaces.surfaces[-1]
            x = np.asarray(surf.x, dtype=float).flatten()
            y = np.asarray(surf.y, dtype=float).flatten()
            intensity = np.asarray(surf.intensity, dtype=float).flatten()
    except Exception:  # noqa: BLE001 - any Optiland trace failure fails closed, not a crash
        return None
    if x.size == 0 or x.shape != y.shape or x.shape != intensity.shape:
        return None
    passed = np.isfinite(x) & np.isfinite(y) & np.isfinite(intensity) & (intensity > 0)
    return float(passed.sum()) / float(x.size)


def _compute_ri_by_field(source_zmx: str, fov_deg: float) -> dict[str, MetricValue]:
    """Rebuild a fresh Optic from `source_zmx` and compute RI at the
    canonical MTF field fractions. Fail closed (all-unavailable) on any
    load/trace error — never guesses a value."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            optic = load_normalized_zmx(ZMX_AMMO_DIR / source_zmx)
            regularize_fields_to_angle(optic, fov_deg)
            wavelength_um = float(optic.primary_wavelength)
            max_field_deg = float(optic.fields.max_field)
            coords = list(optic.fields.get_field_coords())
    except Exception:  # noqa: BLE001 - zmx load/regularize failure fails closed
        return _empty_result()

    if not coords or not math.isfinite(max_field_deg) or max_field_deg <= 0:
        return _empty_result()

    pass_fractions: dict[tuple[float, float], float | None] = {
        (hx, hy): _traced_pass_fraction(optic, hx, hy, wavelength_um) for hx, hy in coords
    }

    axis_coord = min(coords, key=lambda c: math.hypot(c[0], c[1]))
    axis_pass_fraction = pass_fractions[axis_coord]

    result: dict[str, MetricValue] = {}
    for hx, hy in coords:
        field_fraction = math.hypot(hx, hy)
        key = format_mtf_field_fraction(field_fraction)
        pass_fraction = pass_fractions[(hx, hy)]
        if (
            pass_fraction is None
            or axis_pass_fraction is None
            or axis_pass_fraction <= 0.0
        ):
            result[key] = MetricValue(value=None, status="unavailable")
            continue
        field_angle_deg = field_fraction * max_field_deg
        cos4 = math.cos(math.radians(field_angle_deg)) ** 4
        vignetting_factor = min(pass_fraction / axis_pass_fraction, 1.0)
        ri = cos4 * vignetting_factor
        if not math.isfinite(ri):
            result[key] = MetricValue(value=None, status="unavailable")
        else:
            result[key] = MetricValue(value=float(ri), status="available")

    # Canonical fractions the caller expects a key for, even if `optic.fields`
    # ended up with a different subset (defensive; regularize_fields_to_angle
    # always uses MTF_CANONICAL_FIELD_FRACS today).
    for frac in MTF_CANONICAL_FIELD_FRACS:
        result.setdefault(format_mtf_field_fraction(frac), MetricValue(value=None, status="unavailable"))

    return result


@lru_cache(maxsize=512)
def _compute_ri_by_field_cached(
    source_zmx: str, fov_deg: float
) -> tuple[tuple[str, float | None, str], ...]:
    """Memoized core compute, keyed by the (source_zmx, fov_deg) pair that
    fully determines the result. Pure/deterministic — safe to cache; avoids
    redundant ZMX reloads when the same seed appears across multiple
    orchestrator calls (e.g. `RetrievalGenerator` invoked for several `n`)."""
    computed = _compute_ri_by_field(source_zmx, fov_deg)
    return tuple((key, metric.value, metric.status) for key, metric in computed.items())


def compute_relative_illumination(sample: OpticalSampleData) -> dict[str, MetricValue]:
    """Compute per-field RI for one case, keyed by canonical MTF field
    fraction strings (`app.core.mtf_fields.format_mtf_field_fraction`).

    Generator-stage compute (§7-D): rebuilds a fresh `Optic` from the case's
    source ZMX. Fail closed per field on any load/trace error or missing
    metadata — never fabricates a value.
    """
    if sample.metadata is None:
        return _empty_result()
    cached = _compute_ri_by_field_cached(sample.metadata.source_zmx, sample.metadata.fov_deg)
    return {key: MetricValue(value=value, status=status) for key, value, status in cached}
