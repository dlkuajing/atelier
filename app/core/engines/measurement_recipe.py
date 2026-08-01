"""The measurement recipe that has to ship with a reported number.

P4 asks whether a third party can independently recompute what we report. The first
two-engine recheck (`.planning/evidence/p4-two-engine-recheck-2026-07-29.md`) answered
it in two halves:

  - first-order quantities (EFL, F/#) reproduce from the ZMX alone -- median ratio
    0.9997 / 1.0000 across 7 samples;
  - **the three P2 criteria reproduce in the median and not per lens** -- median
    0.985 / 0.918 / 1.063 but spread 3.7x / 6.1x / 8.1x.

So the gap was never "nobody has looked at it". The gap is that the number depends on
choices that live in *our macro*, not in the ZMX: which fields enter the extremum,
which wavelengths, the MTF frequency and ray density, whether the spot figure is a
radius or a diameter, and whether any outlier rejection ran. An outsider holding only
the ZMX cannot recover those, so "recompute our number" is not a well-posed request.

This module makes it well-posed by shipping those choices *with* the number. It states
them, and -- for the parts where prose would still be interpretation -- it ships the
macro source verbatim, so "recompute" reduces to "run this code". Nothing here is
computed or inferred: every field is either a constant used by the probe or the exact
text handed to CODE V.
"""

from __future__ import annotations

from typing import Any

RECIPE_SCHEMA = "atelier.measurement_recipe/v1"


def build_measurement_recipe(
    *,
    mtf_frequency_lpmm: float,
    mtf_nrd: int,
) -> dict[str, Any]:
    """Describe how the reported CODE V metrics were measured.

    `mtf_frequency_lpmm` / `mtf_nrd` are passed in rather than re-read from the
    module constants on purpose: the recipe must record what *this run* used, and a
    caller that overrides them would otherwise ship a recipe that quietly disagrees
    with its own numbers.
    """

    from app.core.engines.codev_optimize import _metric_function_block

    return {
        "schema": RECIPE_SCHEMA,
        "engine": {
            "name": "CODE V (Synopsys)",
            "invocation": "macro batch, one .seq per run via codev_batch.run_codev_process",
            "zmx_import": "IN CV_MACRO:ZEMAXOS_TO_CV <file>",
            # Left explicitly unfilled rather than guessed. The install is at
            # D:\\CODEV115 on the demo machine, but a path is not a build stamp and
            # the macro syntax for querying the version has not been verified against
            # the manual. Naming it as an open item beats shipping a number nobody
            # checked.
            "build": None,
            "build_unavailable_reason": (
                "not captured by the batch runner yet; recipe consumers must record the "
                "engine build out of band"
            ),
        },
        "sampling": {
            # Both of these are what the macro does, not a policy we chose per run:
            # every FOR loop below runs 1..(NUM F) and the wavelength span is W1..(NUM W).
            "fields": "every field declared in the ZMX -- F1..(NUM F), no subsetting",
            "wavelengths": "every wavelength declared in the ZMX -- W1..(NUM W)",
            "zoom_position": "Z1 only",
        },
        "metrics": {
            "rms_spot_um": {
                "macro": "@rmssum",
                "quantity": "RMS spot diameter",
                "unit": "um",
                "reduction": "maximum over fields that traced successfully",
                # This is the convention that cost a wrong conclusion once: the first
                # P4 pass compared it against Optiland's RMS spot *radius* and read the
                # factor of 2 as engine disagreement.
                "convention": (
                    "CODE V's RMS spot size is twice the square root of the mean squared "
                    "spot radius (Geometrical Analysis manual), i.e. a diameter -- do not "
                    "compare it against a radius"
                ),
                "witness": "rms_fields_ok (fields that produced a reading) vs num_fields",
            },
            "mtf_min": {
                "macro": "@mtfmin",
                "quantity": "modulation transfer",
                "frequency_lp_per_mm": float(mtf_frequency_lpmm),
                "nrd": int(mtf_nrd),
                "computation": "MTF_1FLD(... 'DIF','SIN'), diffraction MTF",
                "orientation": "mean of the 0 deg and 90 deg azimuths",
                "reduction": "minimum over fields that traced successfully",
                "witness": "mtf_fields_ok vs num_fields",
            },
            "distortion_pct": {
                "macro": "@dstpct",
                "unit": "percent",
                "reduction": "maximum absolute value over fields",
            },
            "lateral_color_um": {
                "macro": "@lcum",
                "unit": "um",
                "reduction": "maximum over fields",
                "degeneracy": (
                    "spans W1..W(NUM W); at fewer than three wavelengths both ends point "
                    "at the same wavelength and the value is identically 0"
                ),
            },
            "rms_wavefront_waves": {
                "macro": "@wfewav",
                "unit": "waves",
                "reduction": "maximum over fields",
            },
        },
        "post_processing": {
            # Named because it is the single largest per-lens discrepancy in the P4
            # recheck: switching the Optiland-side MAD clip off moved 3 of 7 ratios
            # from 0.38/0.59/0.99 to 0.78/0.87/1.24, and one ultrawide sample read
            # 278.9 um unclipped versus 2.3 um clipped.
            "outlier_rejection": "none -- CODE V readings are reported as returned",
            "note": (
                "the MAD clip in app/core/optical_calc._robust_clip_spot_data belongs to "
                "the Optiland path only and is not applied to any number described here"
            ),
        },
        # Prose can be read two ways; the macro cannot. Shipping the source means the
        # recipe defines the instrument rather than describing it, and it can never
        # drift from the instrument actually used (see the test that pins them equal).
        "metric_macro_source": tuple(_metric_function_block()),
    }
