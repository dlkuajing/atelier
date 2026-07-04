"""Source provenance labels for serialized optical analysis artefacts."""

from __future__ import annotations

from enum import StrEnum


class ProvenanceSource(StrEnum):
    """Computation source identifiers exposed in serialized analysis payloads."""

    OPTILAND_RAYTRACE = "optiland-raytrace"
    OPTILAND_WAVEFRONT = "optiland-wavefront"
    THIN_LENS_ANALYTIC = "thin-lens-analytic"
    CODEV_RUN = "codev-run"

