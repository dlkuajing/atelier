from __future__ import annotations

import math
from pathlib import Path

import pytest

from app.core.lens_system import Scenario
from app.core.parameter_guards import SCENARIO_BOUNDS
from scripts.p16_stagec_offline_manifest import build_manifest


def test_offline_manifest_has_eight_seeds_three_arms_and_no_machine_claims(
    tmp_path: Path,
) -> None:
    manifest = build_manifest(output_dir=tmp_path, seed_count=8)
    assert manifest["execution_scope"] == "offline-only"
    assert manifest["codev_invoked"] is False
    assert manifest["seed_count"] == 8
    assert manifest["cell_count"] == 24
    cells = manifest["cells"]
    assert isinstance(cells, list)
    by_seed: dict[str, set[str]] = {}
    for cell in cells:
        by_seed.setdefault(cell["case_id"], set()).add(cell["arm"])
        assert cell["machine_execution_status"] == "blocked"
        assert cell["machine_result"] is None
        assert cell["expert_verdict"] is None
        assert cell["field_reconstruction"]["status"] == "constructed"
        assert cell["field_reconstruction"]["target_efl_mm"] == cell["target_efl_mm"]
        assert Path(cell["field_reconstruction"]["output_path"]).is_file()
        bounds = SCENARIO_BOUNDS[Scenario(cell["scenario"])]
        assert bounds.image_height_mm_min <= cell["target_image_height_mm"] <= bounds.image_height_mm_max
        assert bounds.fov_deg_min <= cell["derived_fov_deg"] <= bounds.fov_deg_max
        assert cell["derived_fov_deg"] == pytest.approx(
            2
            * math.degrees(
                math.atan(cell["target_image_height_mm"] / cell["target_efl_mm"])
            )
        )
    assert all(
        arms == {"native-imh-reconstructed-control", "target-low", "target-high"}
        for arms in by_seed.values()
    )
    assert isinstance(manifest["blocked_seeds"], list)
    assert manifest["blocked_seeds"], "ineligible seeds must remain visible, not silently skipped"
    assert all(
        set(blocked) == {"case_id", "reason"} and blocked["reason"]
        for blocked in manifest["blocked_seeds"]
    )
