from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.image_quality_floor import (
    image_quality_floor_components,
    image_quality_floor_gap_score,
)


def test_floor_components_rank_250lpmm_bottleneck():
    metrics = SimpleNamespace(
        mtf_50lpmm_min=0.20,
        mtf_100lpmm_min=0.18,
        mtf_150lpmm_min=0.12,
        mtf_200lpmm_min=0.09,
        mtf_250lpmm_min=0.01,
        mtf_multiband_min_score=0.01,
        mtf_field_weighted_score=0.20,
        max_rms_spot_radius_um=80.0,
    )

    components = image_quality_floor_components(metrics)

    assert components[0].component_id == "mtf_250lpmm_floor_gap"
    assert components[0].normalized_gap == pytest.approx(0.875)
    assert any(component.component_id == "mtf_multiband_floor_gap" for component in components)
    assert image_quality_floor_gap_score(metrics) == pytest.approx(0.875)
