from __future__ import annotations

from pathlib import Path

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
        assert Path(cell["field_reconstruction"]["output_path"]).is_file()
    assert all(arms == {"native", "target-low", "target-high"} for arms in by_seed.values())
