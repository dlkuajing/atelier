"""Shared first-pass image-quality floor helpers."""

from __future__ import annotations

from typing import Protocol

IMAGE_QUALITY_FLOOR_MIN_MTF = 0.08
IMAGE_QUALITY_FLOOR_WEIGHTED_MTF = 0.15
IMAGE_QUALITY_FLOOR_MAX_RMS_UM = 100.0


class ImageQualityFloorMetricLike(Protocol):
    mtf_multiband_min_score: float | None
    mtf_field_weighted_score: float | None
    max_rms_spot_radius_um: float | None


def image_quality_floor_gap_score(
    metrics: ImageQualityFloorMetricLike | None,
) -> float | None:
    """Normalized distance from the first-pass MTF/RMS review floor."""

    if metrics is None:
        return None
    min_mtf = getattr(metrics, "mtf_multiband_min_score", None)
    weighted_mtf = getattr(metrics, "mtf_field_weighted_score", None)
    max_rms = getattr(metrics, "max_rms_spot_radius_um", None)
    gaps = [
        1.0
        if min_mtf is None
        else max(0.0, (IMAGE_QUALITY_FLOOR_MIN_MTF - min_mtf) / IMAGE_QUALITY_FLOOR_MIN_MTF),
        1.0
        if weighted_mtf is None
        else max(
            0.0,
            (IMAGE_QUALITY_FLOOR_WEIGHTED_MTF - weighted_mtf)
            / IMAGE_QUALITY_FLOOR_WEIGHTED_MTF,
        ),
        1.0
        if max_rms is None
        else max(0.0, (max_rms - IMAGE_QUALITY_FLOOR_MAX_RMS_UM) / IMAGE_QUALITY_FLOOR_MAX_RMS_UM),
    ]
    return round(sum(gaps), 3)
