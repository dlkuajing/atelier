from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from app.core.case_library import load_case_library, match_case
from app.core.lens_system import Scenario
from app.core.mtf_fields import MTF_FIELD_FALLBACK_SETS
from app.core.zmx_ingest import ZMX_AMMO_DIR
from app.main import app
from scripts.audit_seed_intake import _audit, _parse_args

client = TestClient(app)


def test_high_fov_seed_intake_audit_reports_current_gap():
    args = _parse_args(
        [
            "--target-fov",
            "88",
            "--target-efl",
            "2.8",
            "--target-fnum",
            "1.9",
            "--min-fov",
            "85",
            "--required-field",
            "1.0",
            "--target-image-height",
            "2.9",
            "--image-height-lo",
            "2.55",
            "--image-height-hi",
            "3.25",
            "--target-elements",
            "5",
            "--element-count-lo",
            "4",
            "--element-count-hi",
            "6",
        ]
    )

    report = _audit(args)

    assert report["status"] == "gap"
    assert report["minimum_fov_deg"] == 85.0
    assert report["efl_window_mm"] == [2.5, 3.1]
    assert report["f_number_window"] == [1.7, 2.15]
    assert report["image_height_window_mm"] == [2.55, 3.25]
    assert report["element_count_window"] == [4, 6]
    assert report["accepted_seed_candidates"] == []
    assert report["full_field_accepted_seed_count"] == 0
    assert "strict high-FOV full-field" in report["accepted_seed_count_semantics"]
    assert report["lightweight_seed_count"] == 106
    assert report["lightweight_accepted_seed_count"] == 106
    assert report["lightweight_rejected_seed_count"] == 0
    assert report["lightweight_seed_candidates"]
    assert all(
        all(candidate["checks"].values()) for candidate in report["lightweight_seed_candidates"]
    )
    assert any("accepted high-FOV full-field seeds=0" in item for item in report["known_evidence"])
    assert any(
        "DATA-06 lightweight accepted seeds=106/106" in item
        for item in report["known_evidence"]
    )
    assert any("best stable high-FOV seed=" in item for item in report["known_evidence"])
    assert any("FOV >= 85.0 deg" in item for item in report["missing_evidence"])
    assert any("image height in 2.55-3.25 mm" in item for item in report["missing_evidence"])
    assert any("element count 4-6P" in item for item in report["missing_evidence"])
    assert any("1.0" in item for item in report["missing_evidence"])
    nearest = {item["role"]: item for item in report["nearest_candidates"]}
    assert nearest["nearest_high_fov"]["case_id"] == "US-20230288669-A1-e4"
    assert nearest["nearest_high_fov"]["mtf_max_field_frac"] < 1.0
    # DATA-06 keeps bounded 0.5-field payload MTF for converted seeds, but the
    # protected edge scan can still probe the loaded ZMX independently.
    assert nearest["nearest_high_fov"]["highest_stable_field_frac"] == pytest.approx(1.0)
    assert nearest["nearest_high_fov"]["edge_field_cliff_frac"] is None
    # E2-01 batch 1: best_stable_high_fov is now a real >=85 deg full-field(1.0)
    # patent seed (US20170003482A1, 91 deg, all edge fields stable) -- the
    # evidence-layer blocker is cleared. It still is NOT accepted for THIS
    # acquisition window (EFL/F#/image-height/element-count all out of range), so
    # accepted_seed_count stays 0 and the audit still reports a targeted gap.
    assert nearest["best_stable_high_fov"]["case_id"] == "US20170003482A1"
    assert nearest["best_stable_high_fov"]["mtf_max_field_frac"] == pytest.approx(1.0)
    assert nearest["best_stable_high_fov"]["highest_stable_field_frac"] == pytest.approx(1.0)
    assert nearest["best_stable_high_fov"]["edge_field_cliff_frac"] is None
    assert "1.0:pass" in nearest["best_stable_high_fov"]["edge_field_evidence"]
    assert any("MTF field" in item for item in nearest["nearest_high_fov"]["miss_reasons"])
    assert any("outside" in item for item in nearest["best_stable_high_fov"]["miss_reasons"])
    assert "--image-height-lo 2.55" in report["next_probe_command"]
    assert "--element-count-hi 6" in report["next_probe_command"]
    assert "--candidate-zmx /path/to/candidate.zmx" in report["candidate_preflight_command"]
    assert "--image-height-lo 2.55" in report["candidate_preflight_command"]


def test_mtf_fallback_inventory_keeps_085_seed_payloads():
    fallback_sets = list(MTF_FIELD_FALLBACK_SETS)
    assert (0.0, 0.5, 0.7, 0.85) in fallback_sets
    assert fallback_sets.index((0.0, 0.5, 0.7, 0.85)) < fallback_sets.index(
        (0.0, 0.5, 0.7, 0.8)
    )

    cases = {case.metadata.case_id: case for case in load_case_library() if case.metadata}
    high_fov_sibling = cases["5P_F1.9_FOV89.5_EFL2.8_IMH2.9_TTL4.33"]
    compact_main_seed = cases["3P_F2.5_FOV78.1_EFL2.8_IMH2.3_TTL4.33"]

    assert high_fov_sibling.metadata.mtf_max_field_frac == pytest.approx(0.85)
    assert compact_main_seed.metadata.mtf_max_field_frac == pytest.approx(0.85)


def test_seed_intake_cli_matches_runtime_assessment_contract():
    sample = match_case(
        Scenario.SMARTPHONE_WIDE,
        efl_mm=2.8,
        fnum=1.9,
        fov_deg=88.0,
        image_height_mm=2.9,
        n_elements=5,
        priority="performance",
    )
    assert sample is not None
    assert sample.design_assessment is not None
    # E2-01 batch 1: with real full-field high-FOV evidence in the library the 88
    # deg request routes through the covered path, so the runtime assessment no
    # longer embeds a seed_intake_audit -- the gap-only acquisition scaffolding
    # (strategy decision + runtime audit) stood down. The standalone CLI probe
    # stays available and still audits a specific acquisition window.
    assert sample.design_assessment.seed_intake_audit is None
    assert sample.design_assessment.design_strategy_decision is None

    args = _parse_args(
        [
            "--target-fov",
            "88",
            "--target-efl",
            "2.8",
            "--target-fnum",
            "1.9",
            "--min-fov",
            "85",
            "--required-field",
            "1.0",
            "--target-image-height",
            "2.9",
            "--image-height-lo",
            "2.55",
            "--image-height-hi",
            "3.25",
            "--target-elements",
            "5",
            "--element-count-lo",
            "4",
            "--element-count-hi",
            "6",
        ]
    )

    cli_report = _audit(args)

    # The window has real full-field high-FOV evidence in the library but no seed
    # that fits the exact EFL/F#/image-height/element envelope, so the targeted
    # acquisition probe still reports a gap with zero accepted candidates.
    assert cli_report["status"] == "gap"
    assert cli_report["accepted_seed_count"] == 0
    assert cli_report["full_field_accepted_seed_count"] == 0
    assert cli_report["lightweight_accepted_seed_count"] == 106
    assert cli_report["full_field_seed_count"] > 0
    assert cli_report["high_fov_seed_count"] > 0
    assert any(
        "accepted high-FOV full-field seeds=0" in item for item in cli_report["known_evidence"]
    )


def test_seed_intake_audit_can_preflight_raw_candidate_zmx(tmp_path):
    source = ZMX_AMMO_DIR / "5P_F1.9_FOV89.5_EFL2.8_IMH2.9_TTL4.29.zmx"
    candidate = tmp_path / "5P_F1.9_FOV89.5_EFL2.8_IMH2.9_TTL4.29_PREFLIGHT.zmx"
    shutil.copyfile(source, candidate)

    args = _parse_args(
        [
            "--target-fov",
            "88",
            "--target-efl",
            "2.8",
            "--target-fnum",
            "1.9",
            "--min-fov",
            "85",
            "--required-field",
            "1.0",
            "--target-image-height",
            "2.9",
            "--image-height-lo",
            "2.55",
            "--image-height-hi",
            "3.25",
            "--target-elements",
            "5",
            "--element-count-lo",
            "4",
            "--element-count-hi",
            "6",
            "--candidate-zmx",
            str(candidate),
        ]
    )

    report = _audit(args)

    # DATA-06 intake: 145-seed library + 1 preflight candidate = 146 visible
    # seeds, 30 high-FOV (29 in-library + the candidate). Accepted stays 0: no
    # seed fits the full-field acquisition window.
    assert len(load_case_library()) == 145
    assert report["total_seed_count"] == 146
    assert report["high_fov_seed_count"] == 30
    assert report["accepted_seed_count"] == 0
    assert any("total visible phone seeds=146" in item for item in report["known_evidence"])
    assert any("accepted high-FOV full-field seeds=0" in item for item in report["known_evidence"])


def test_seed_intake_preflight_endpoint_audits_uploaded_zmx():
    source = ZMX_AMMO_DIR / "5P_F1.9_FOV89.5_EFL2.8_IMH2.9_TTL4.29.zmx"

    response = client.post(
        "/api/optical/seed-intake/preflight",
        data={
            "target_fov": "88",
            "target_efl": "2.8",
            "target_fnum": "1.9",
            "min_fov": "85",
            "required_field": "1.0",
            "target_image_height": "2.9",
            "image_height_lo": "2.55",
            "image_height_hi": "3.25",
            "target_elements": "5",
            "element_count_lo": "4",
            "element_count_hi": "6",
            "candidate_fov": "88",
            "candidate_efl": "2.8",
            "candidate_n_pieces": "5",
        },
        files={
            "candidate_zmx": (
                source.name,
                source.read_bytes(),
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "gap"
    # DATA-06 intake: 145-seed library + 1 uploaded candidate = 146 seeds,
    # 30 high-FOV.
    assert report["total_seed_count"] == 146
    assert report["high_fov_seed_count"] == 30
    assert report["accepted_seed_count"] == 0
    assert any("total visible phone seeds=146" in item for item in report["known_evidence"])
    assert any("accepted high-FOV full-field seeds=0" in item for item in report["known_evidence"])
