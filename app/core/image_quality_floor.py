"""Shared first-pass image-quality floor helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

IMAGE_QUALITY_FLOOR_MIN_MTF = 0.08
IMAGE_QUALITY_FLOOR_WEIGHTED_MTF = 0.15
IMAGE_QUALITY_FLOOR_MAX_RMS_UM = 100.0


class ImageQualityFloorMetricLike(Protocol):
    mtf_multiband_min_score: float | None
    mtf_field_weighted_score: float | None
    max_rms_spot_radius_um: float | None


@dataclass(frozen=True)
class ImageQualityFloorComponent:
    component_id: str
    label: str
    metric_value: float | None
    target_value: float
    higher_is_better: bool
    normalized_gap: float

    @property
    def passed(self) -> bool:
        return self.normalized_gap <= 0.0


def _normalized_floor_gap(
    metric_value: float | None,
    target: float,
    *,
    higher_is_better: bool,
) -> float:
    if metric_value is None:
        return 1.0
    if higher_is_better:
        return max(0.0, (target - metric_value) / target)
    return max(0.0, (metric_value - target) / target)


def image_quality_floor_components(
    metrics: ImageQualityFloorMetricLike | None,
) -> list[ImageQualityFloorComponent]:
    """Return ranked first-pass MTF/RMS floor gaps without changing gate semantics."""

    if metrics is None:
        return []

    components: list[ImageQualityFloorComponent] = []
    for band in (50, 100, 150, 200, 250):
        value = getattr(metrics, f"mtf_{band}lpmm_min", None)
        if value is None:
            continue
        components.append(
            ImageQualityFloorComponent(
                component_id=f"mtf_{band}lpmm_floor_gap",
                label=f"{band} lp/mm min MTF",
                metric_value=value,
                target_value=IMAGE_QUALITY_FLOOR_MIN_MTF,
                higher_is_better=True,
                normalized_gap=_normalized_floor_gap(
                    value,
                    IMAGE_QUALITY_FLOOR_MIN_MTF,
                    higher_is_better=True,
                ),
            )
        )

    # Keep the aggregate multiband component for snapshots that do not carry
    # per-band values, and as a stable bridge for existing evidence packets.
    min_mtf = getattr(metrics, "mtf_multiband_min_score", None)
    if min_mtf is not None:
        components.append(
            ImageQualityFloorComponent(
                component_id="mtf_multiband_floor_gap",
                label="50-250 lp/mm min MTF",
                metric_value=min_mtf,
                target_value=IMAGE_QUALITY_FLOOR_MIN_MTF,
                higher_is_better=True,
                normalized_gap=_normalized_floor_gap(
                    min_mtf,
                    IMAGE_QUALITY_FLOOR_MIN_MTF,
                    higher_is_better=True,
                ),
            )
        )

    weighted_mtf = getattr(metrics, "mtf_field_weighted_score", None)
    components.append(
        ImageQualityFloorComponent(
            component_id="mtf_field_weighted_floor_gap",
            label="field-weighted MTF",
            metric_value=weighted_mtf,
            target_value=IMAGE_QUALITY_FLOOR_WEIGHTED_MTF,
            higher_is_better=True,
            normalized_gap=_normalized_floor_gap(
                weighted_mtf,
                IMAGE_QUALITY_FLOOR_WEIGHTED_MTF,
                higher_is_better=True,
            ),
        )
    )

    max_rms = getattr(metrics, "max_rms_spot_radius_um", None)
    components.append(
        ImageQualityFloorComponent(
            component_id="max_rms_floor_gap",
            label="max RMS spot radius",
            metric_value=max_rms,
            target_value=IMAGE_QUALITY_FLOOR_MAX_RMS_UM,
            higher_is_better=False,
            normalized_gap=_normalized_floor_gap(
                max_rms,
                IMAGE_QUALITY_FLOOR_MAX_RMS_UM,
                higher_is_better=False,
            ),
        )
    )
    return sorted(components, key=lambda item: item.normalized_gap, reverse=True)


def image_quality_floor_gap_score(
    metrics: ImageQualityFloorMetricLike | None,
) -> float | None:
    """Normalized distance from the first-pass MTF/RMS review floor."""

    if metrics is None:
        return None
    components = {
        component.component_id: component
        for component in image_quality_floor_components(metrics)
    }
    mtf = components.get("mtf_multiband_floor_gap")
    weighted = components.get("mtf_field_weighted_floor_gap")
    rms = components.get("max_rms_floor_gap")
    gaps = [
        mtf.normalized_gap if mtf is not None else 1.0,
        weighted.normalized_gap if weighted is not None else 1.0,
        rms.normalized_gap if rms is not None else 1.0,
    ]
    return round(sum(gaps), 3)
