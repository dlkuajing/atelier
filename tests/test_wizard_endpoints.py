"""Endpoint tests for cover-image + executive-summary — LLM client mocked.

We don't hit the real relay in pytest (network, cost, rate limits). Instead
we monkey-patch app.api.wizard.get_async_client to return an AsyncMock with
the response shape the OpenAI SDK gives. The endpoint code paths under test:
prompt assembly, response parsing, error mapping (502 / 500 / 422).
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# /api/wizard/cover-image
# ---------------------------------------------------------------------------


@patch("app.api.wizard.get_async_client")
def test_cover_image_happy_path(mock_get_client):
    """gpt-image-2 returns b64_json → endpoint relays it verbatim."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(b64_json="ZmFrZS1wbmctcGF5bG9hZA==", revised_prompt="lens module shot")
    ]
    mock_client.images.generate = AsyncMock(return_value=mock_response)
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/cover-image",
        json={
            "scenario": "smartphone-telephoto",
            "efl_mm": 7.0,
            "f_number": 2.4,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["b64_png"] == "ZmFrZS1wbmctcGF5bG9hZA=="
    assert data["scenario"] == "smartphone-telephoto"
    assert data["revised_prompt"] == "lens module shot"
    assert "gpt-image" in data["model"].lower() or data["model"] == "gpt-image-2"


@patch("app.api.wizard.get_async_client")
def test_cover_image_prompt_includes_specs_when_given(mock_get_client):
    """If the request supplies efl_mm + f_number, they appear in the prompt
    so gpt-image-2 produces aesthetically aligned output."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(b64_json="x", revised_prompt=None)]
    mock_client.images.generate = AsyncMock(return_value=mock_response)
    mock_get_client.return_value = mock_client

    client.post(
        "/api/wizard/cover-image",
        json={
            "scenario": "dslr-prime",
            "efl_mm": 85.0,
            "f_number": 1.4,
        },
    )
    call_args = mock_client.images.generate.call_args
    prompt = call_args.kwargs.get("prompt", "")
    assert "85" in prompt or "85.0" in prompt
    assert "f/1.4" in prompt or "1.4" in prompt


@patch("app.api.wizard.get_async_client")
def test_cover_image_relay_failure_returns_502(mock_get_client):
    """Exception bubbling out of the relay call → HTTP 502 with diagnostic."""
    mock_client = AsyncMock()
    mock_client.images.generate = AsyncMock(side_effect=Exception("upstream 503"))
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/cover-image",
        json={"scenario": "smartphone-telephoto"},
    )
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["error"] == "image_relay_failure"
    assert "upstream 503" in detail["message"]


@patch("app.api.wizard.get_async_client")
def test_cover_image_empty_data_returns_502(mock_get_client):
    """Relay returned with no data array → 502 (likely upstream weirdness)."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.data = []
    mock_client.images.generate = AsyncMock(return_value=mock_response)
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/cover-image",
        json={"scenario": "smartphone-telephoto"},
    )
    assert r.status_code == 502
    assert r.json()["detail"]["error"] == "image_relay_empty_response"


def test_cover_image_invalid_scenario_returns_422():
    """Pydantic Scenario enum rejects unknown id before the LLM is called."""
    r = client.post(
        "/api/wizard/cover-image",
        json={"scenario": "warp-drive-objective"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# /api/wizard/executive-summary
# ---------------------------------------------------------------------------


_FULL_EXEC_REQUEST = {
    "scenario": "smartphone-telephoto",
    "scenario_label_en": "Smartphone Telephoto",
    "focal_length_mm": 7.0,
    "f_number": 2.4,
    "field_of_view_deg": 30.0,
    "image_height_mm": 3.7,
    "n_elements": 7,
    "wavelength_nm": 550,
    "total_track_mm": 5.85,
    "airy_disc_diameter_um": 3.22,
    "cutoff_freq_lp_per_mm": 758,
}

_DESIGN_ASSESSMENT_CONTEXT = {
    "matched_case_id": "5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15",
    "score": 0.868,
    "normalized_distance": 0.153,
    "target_focal_length_mm": 3.0,
    "target_f_number": 2.0,
    "target_fov_deg": 78.0,
    "target_image_height_mm": 2.3,
    "target_n_elements": 5,
    "target_total_track_mm": 6.0,
    "priority": "balanced",
    "manufacturing_tier": "premium",
    "delta_efl_mm": -0.06,
    "delta_f_number": -0.20,
    "delta_fov_deg": -3.9,
    "delta_image_height_mm": 0.0,
    "delta_n_elements": 0,
    "delta_total_track_mm": -1.85,
    "warnings": ["FOV differs from target by -3.9 deg"],
    "rationale": ["image height participated in seed scoring"],
    "candidate_comparison": [
        {
            "case_id": "5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15",
            "role": "best_match",
            "score": 0.868,
            "normalized_distance": 0.153,
            "scenario": "smartphone-wide",
            "efl_mm": 2.94,
            "f_number": 1.80,
            "fov_deg": 74.1,
            "image_height_mm": 2.3,
            "total_track_mm": 4.15,
            "n_pieces": 5,
            "mtf_max_field_frac": 1.0,
            "strengths": ["lowest weighted-distance seed for the request"],
            "tradeoffs": ["FOV differs by -3.9 deg"],
        },
        {
            "case_id": "3P_F2.5_FOV78.1_EFL2.8_IMH2.3_TTL4.33",
            "role": "cost_variant",
            "score": 0.70,
            "normalized_distance": 0.42,
            "scenario": "smartphone-wide",
            "efl_mm": 2.76,
            "f_number": 2.45,
            "fov_deg": 78.1,
            "image_height_mm": 2.3,
            "total_track_mm": 4.33,
            "n_pieces": 3,
            "mtf_max_field_frac": 0.7,
            "strengths": ["lowest element-count branch in the allowed family"],
            "tradeoffs": ["aperture is slower by +0.45 F/#"],
        },
    ],
    "requirement_coverage_summary": {
        "status": "tradeoff",
        "met_count": 5,
        "tradeoff_count": 1,
        "miss_count": 0,
        "unscored_count": 1,
        "summary": "5 requirement(s) met, 1 tradeoff(s), 1 unscored context item(s)",
    },
    "requirement_coverage": [
        {
            "requirement_id": "effective_focal_length",
            "label": "Effective focal length",
            "status": "met",
            "priority": "critical",
            "target": "3.00",
            "actual": "2.94",
            "delta": -0.06,
            "tolerance": 0.25,
            "unit": "mm",
            "evidence": ["selected seed=5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15"],
        },
        {
            "requirement_id": "field_of_view",
            "label": "Field of view",
            "status": "tradeoff",
            "priority": "critical",
            "target": "78.0",
            "actual": "74.1",
            "delta": -3.9,
            "tolerance": 5.0,
            "unit": "deg",
            "evidence": ["selected scenario=smartphone-wide"],
            "next_action": "select a relaxed-FOV fallback or acquire a closer high-FOV seed",
        },
        {
            "requirement_id": "manufacturing_tier",
            "label": "Manufacturing tier",
            "status": "tradeoff",
            "priority": "context",
            "target": "premium",
            "actual": "warning proxy score=0.88",
            "evidence": ["1 first-pass manufacturability warning(s) need review"],
            "next_action": "protect tight gaps during merit tuning and packaging review",
        },
    ],
    "manufacturability_review": {
        "status": "warning",
        "tier": "premium",
        "score": 0.88,
        "summary": "1 first-pass manufacturability warning(s) need review",
        "checks": [
            {
                "check_id": "element_count_complexity",
                "label": "Element-count complexity",
                "status": "pass",
                "target": "phone main/wide reference library target <=5P",
                "actual": "5P imaging seed",
                "evidence": ["n_imaging=5", "n_filter=1"],
            },
            {
                "check_id": "minimum_axial_spacing",
                "label": "Minimum axial spacing",
                "status": "warning",
                "target": ">=0.08 mm preferred; >=0.025 mm hard floor for protected spacing edits",
                "actual": "0.040 mm",
                "evidence": ["computed from finite serialized surface z positions"],
                "mitigation": "protect tight gaps during merit tuning and packaging review",
            },
        ],
        "limitations": [
            "not a Monte-Carlo tolerance or yield analysis",
            "no material density, molding cost, or supplier process table is available yet",
        ],
    },
    "next_steps": [
        "Use the selected seed as the starting prescription.",
        "Resolve FOV mismatch before merit-function tuning.",
    ],
    "readiness": {
        "level": "yellow",
        "confidence": 0.80,
        "summary": "usable seed with explicit tradeoffs",
    },
    "risk_register": [
        {
            "risk": "field-of-view mismatch",
            "severity": "medium",
            "evidence": "selected seed FOV differs from target by -3.9 deg",
            "mitigation": "close the field angle first",
        }
    ],
    "optimization_plan": [
        {
            "priority": 1,
            "objective": "close the field-angle mismatch",
            "parameter_focus": ["field weights", "stop position"],
            "expected_effect": "moves the seed toward requested FOV",
            "verification": "recompute paraxial FOV and edge-field ray trace",
        }
    ],
    "optimization_attempt": {
        "status": "proposal",
        "engine": "optiland.least_squares",
        "summary": "protected local optimizer found a bounded radius tweak",
        "target_efl_mm": 3.0,
        "before_efl_mm": 2.94,
        "after_efl_mm": 2.99,
        "before_total_track_mm": 4.15,
        "after_total_track_mm": 4.15,
        "improvement_efl_mm": 0.05,
        "improvement_pct": 83.0,
        "variable_changes": [
            {
                "variable": "radius",
                "surface_index": 7,
                "before": 3.058,
                "after": 3.132,
                "delta": 0.074,
                "delta_pct": 2.42,
            }
        ],
        "verification": {
            "status": "passed",
            "summary": "post-tweak paraxial, ray trace, and full-field MTF checks passed",
            "paraxial_ok": True,
            "ray_trace_ok": True,
            "mtf_ok": True,
            "mtf_max_field_frac": 1.0,
            "max_rms_spot_radius_um": 7.5,
            "diagnostics": [],
        },
        "before_metrics": {
            "effective_focal_length_mm": 2.94,
            "f_number": 1.8,
            "total_track_mm": 4.15,
            "mtf_max_field_frac": 1.0,
            "max_rms_spot_radius_um": 8.1,
        },
        "after_metrics": {
            "effective_focal_length_mm": 2.99,
            "f_number": 1.8,
            "total_track_mm": 4.15,
            "mtf_max_field_frac": 1.0,
            "max_rms_spot_radius_um": 7.5,
        },
        "diagnostics": ["radius variables constrained to +/-5%"],
        "failures": [],
        "applied_to_payload": False,
        "elapsed_ms": 120.0,
    },
    "draft_candidates": [
        {
            "candidate_id": "seed-baseline",
            "source": "seed_baseline",
            "strategy_option_id": "partial_field_high_fov_draft",
            "status": "baseline",
            "recommendation": "hold",
            "summary": "real seed baseline kept as rollback branch",
            "metrics": {
                "effective_focal_length_mm": 2.94,
                "f_number": 1.8,
                "total_track_mm": 4.15,
                "mtf_max_field_frac": 1.0,
                "max_rms_spot_radius_um": 8.1,
            },
            "evidence": ["matched real case"],
            "risks": [],
        },
        {
            "candidate_id": "optimizer-proposal",
            "source": "protected_optimizer",
            "status": "proposed",
            "recommendation": "continue",
            "summary": "recommended protected optimizer branch",
            "metrics": {
                "effective_focal_length_mm": 2.99,
                "f_number": 1.8,
                "total_track_mm": 4.15,
                "mtf_max_field_frac": 1.0,
                "max_rms_spot_radius_um": 7.5,
            },
            "evidence": ["verification gate passed"],
            "risks": ["proposal still requires full tolerancing before release"],
        },
    ],
    "recommended_candidate_id": "optimizer-proposal",
    "branch_selection_policy": {
        "status": "strategy_resolution_required",
        "active_candidate_id": "seed-baseline",
        "primary_candidate_id": "high-fov-full-field-seed-needed",
        "current_deliverable_candidate_id": "partial-field-high-fov-draft",
        "candidate_priority_order": [
            "high-fov-full-field-seed-needed",
            "relaxed-fov-full-field",
            "partial-field-high-fov-draft",
        ],
        "blocked_candidate_ids": ["high-fov-full-field-seed-needed"],
        "fallback_candidate_ids": [
            "relaxed-fov-full-field",
            "partial-field-high-fov-draft",
        ],
        "summary": "active payload remains a partial-field holding branch",
        "rationale": ["active candidate is not a full-field approval"],
        "promotion_requirements": ["ingest a seed with MTF at 1.0 field"],
        "forbidden_claims": ["full-field edge-performance claim"],
    },
    "draft_acceptance_gate": {
        "status": "conditional",
        "candidate_id": "seed-baseline",
        "deliverable_type": "partial-field concept only",
        "score": 0.76,
        "summary": "3 warning(s) require explicit review before release",
        "checks": [
            {
                "check_id": "requirement_coverage",
                "label": "Requirement coverage",
                "status": "warning",
                "evidence": "5 requirement(s) met, 1 tradeoff(s), 1 unscored context item(s)",
                "required_action": "select a relaxed-FOV fallback or acquire a closer high-FOV seed",
            },
            {
                "check_id": "delivery_gate",
                "label": "Delivery gate",
                "status": "warning",
                "evidence": "conditional_partial_field: partial-field concept only",
                "required_action": "ingest a seed with MTF at 1.0 field",
            },
        ],
        "blockers": [],
        "required_next_actions": ["ingest a seed with MTF at 1.0 field"],
        "upgrade_actions": [
            {
                "action_id": "delivery_gate-1",
                "priority": 1,
                "source_check_id": "delivery_gate",
                "action": "ingest a seed with MTF at 1.0 field",
                "acceptance_criteria": [
                    "ingest a seed with MTF at 1.0 field",
                    "delivery gate no longer restricts the draft deliverable",
                ],
                "expected_effect": "removes or narrows delivery restrictions and moves the draft toward reviewable status",
                "unblocks_claims": ["full-field edge-performance claim"],
            }
        ],
        "allowed_claims": ["real high-FOV seed match"],
        "forbidden_claims": ["full-field edge-performance claim"],
    },
    "seed_acquisition_contract": {
        "status": "external_evidence_required",
        "summary": (
            "high-FOV visible-light full-field phone main/wide seed requires external "
            "seed evidence before full-field or edge-performance claims can be promoted"
        ),
        "source_task_id": "ingest-high-fov-full-field-seed",
        "owner_role": "case_library + optical_designer",
        "target_regime": "high-FOV visible-light full-field phone main/wide seed",
        "acceptance_target": "visible-light seed with FOV >= 85.0 deg and MTF at 1.0 field",
        "required_candidate_properties": [
            "visible-light ZMX prescription",
            "FOV >= 85.0 deg",
            "MTF evaluates at 1.0 field without fallback",
        ],
        "preflight_command": (
            "cd lumira-backend && uv run python scripts/audit_seed_intake.py "
            "--target-fov 88.0 --target-efl 2.80 --candidate-zmx /path/to/candidate.zmx --json"
        ),
        "pass_criteria": ["seed intake audit returns status=satisfied"],
        "rejection_filters": ["MTF max stable field below 1.0"],
        "current_gap_evidence": [
            "no accepted high-FOV full-field seed satisfies the intake window",
            "accepted high-FOV full-field seeds=0",
            "high-FOV seeds=2",
            "full-field seeds=9",
            (
                "near miss nearest_high_fov=5P_F1.9_FOV89.5_EFL2.8_IMH2.9_TTL4.29: "
                "MTF field 0.8 < required 1.0"
            ),
            (
                "near miss nearest_full_field=5P_F2.0_FOV78.8_EFL3.8_IMH3.2_TTL4.30: "
                "FOV 78.8 < required 85.0"
            ),
        ],
        "fallback_paths": ["partial-field-high-fov-draft: keep concept conditional"],
        "blocked_claims": ["full-field edge-performance claim"],
        "next_action": "run candidate preflight",
    },
    "acceptance_improvement_tasks": [
        {
            "task_id": "ingest-high-fov-full-field-seed",
            "source_action_id": "delivery_gate-1",
            "priority": 1,
            "status": "external_evidence_required",
            "stage": "seed_ingestion",
            "owner": "case_library",
            "objective": "ingest a seed with MTF at 1.0 field",
            "required_inputs": [
                "Zemax/Optiland-compatible visible-light prescription with material metadata",
                "FOV >= 85.0 deg",
                "required MTF field 1.0",
            ],
            "validation_steps": [
                "run case generation and confirm no MTF fallback below 1.0 field",
                "rerun the design-agent fixed eval case high_fov_main_uses_89deg_seed",
            ],
            "exit_criteria": ["ingest a seed with MTF at 1.0 field"],
            "depends_on": [],
            "blocks_claims": ["full-field edge-performance claim"],
            "evidence_probe": {
                "probe_id": "high-fov-full-field-seed-intake",
                "status": "gap",
                "summary": "current library has no accepted high-FOV full-field seed",
                "known_evidence": [
                    "target FOV=88.0 deg",
                    "full-field high-FOV seeds=0",
                ],
                "missing_evidence": [
                    "visible-light prescription with FOV >= 85.0 deg",
                    "MTF evaluates at 1.0 field without fallback",
                ],
                "next_probe_command": (
                    "cd lumira-backend && uv run python scripts/audit_seed_intake.py "
                    "--target-fov 88.0 --target-efl 2.80 --json"
                ),
            },
        }
    ],
    "merit_optimization_probe": {
        "status": "proposal",
        "engine": "optiland.least_squares",
        "summary": "protected RMS merit probe found a verified image-quality improvement",
        "operand": "rms_spot_size",
        "field_samples": [0.0, 0.2, 0.3],
        "target_efl_mm": 3.0,
        "target_total_track_mm": 6.0,
        "merit_before": 0.069,
        "merit_after": 0.036,
        "rms_improvement_um": 8.7,
        "rms_improvement_pct": 2.1,
        "variable_changes": [
            {
                "variable": "radius",
                "surface_index": 5,
                "before": 2.522,
                "after": 2.603,
                "delta": 0.081,
                "delta_pct": 3.2,
            }
        ],
        "verification": {
            "status": "passed",
            "summary": "post-tweak paraxial, ray trace, and full-field MTF checks passed",
            "paraxial_ok": True,
            "ray_trace_ok": True,
            "mtf_ok": True,
            "mtf_max_field_frac": 1.0,
            "max_rms_spot_radius_um": 398.9,
            "diagnostics": [],
        },
        "before_metrics": {
            "effective_focal_length_mm": 2.99,
            "f_number": 1.8,
            "total_track_mm": 4.15,
            "mtf_max_field_frac": 1.0,
            "max_rms_spot_radius_um": 407.6,
        },
        "after_metrics": {
            "effective_focal_length_mm": 3.0,
            "f_number": 1.8,
            "total_track_mm": 4.15,
            "mtf_max_field_frac": 1.0,
            "max_rms_spot_radius_um": 398.9,
        },
        "diagnostics": ["finite RMS operand fields: (0.0, 0.2, 0.3)"],
        "failures": [],
        "applied_to_payload": False,
        "elapsed_ms": 200.0,
    },
    "prescription_change_set": {
        "source_candidate_id": "optimizer-proposal",
        "changes": [
            {
                "variable": "radius",
                "surface_index": 7,
                "before": 3.058,
                "after": 3.132,
                "delta": 0.074,
                "delta_pct": 2.42,
            }
        ],
        "expected_effect": "reduce first-order EFL miss by 0.050 mm",
        "application_policy": "not applied to delivered payload",
        "verification_checklist": [
            "apply the listed variable changes only to a cloned prescription",
            "recompute paraxial EFL, F-number, and total track after applying the delta",
            "rerun finite ray trace on sampled chief and marginal rays",
        ],
    },
    "optimization_task_queue": [
        {
            "task_id": "apply-protected-change-set",
            "candidate_id": "optimizer-proposal",
            "stage": "apply_change_set",
            "status": "ready",
            "objective": "apply the protected prescription change set to a cloned branch",
            "variables": ["surface 7 radius"],
            "entry_condition": "verification gate passed on the protected optimizer proposal",
            "stop_condition": "post-apply EFL, F-number, TTL, ray trace, and MTF stay inside the checked bounds",
            "verification": "recompute paraxial summary, sampled ray trace, and MTF after applying the delta",
            "depends_on": [],
            "evidence": ["radius S7 3.0580->3.1320"],
        },
        {
            "task_id": "lock-first-order",
            "candidate_id": "optimizer-proposal",
            "stage": "first_order_lock",
            "status": "queued",
            "objective": "lock EFL, F-number, image height, and TTL before image-quality merit tuning",
            "variables": ["effective focal length", "F-number"],
            "entry_condition": "selected branch has a stable prescription clone",
            "stop_condition": "EFL/F-number/image-height/TTL deltas remain inside the design review tolerances",
            "verification": "compare paraxial deltas after every solve",
            "depends_on": ["apply-protected-change-set"],
            "evidence": ["dEFL=-0.060 mm"],
        },
        {
            "task_id": "local-merit-tuning",
            "candidate_id": "optimizer-proposal",
            "stage": "image_quality_tuning",
            "status": "queued",
            "objective": "improve mid-field and edge-field image quality without drifting off the brief",
            "variables": ["stop position", "air gaps"],
            "entry_condition": "first-order targets are locked",
            "stop_condition": "RMS/MTF improve while first-order targets remain locked",
            "verification": "compare MTF, RMS spot, and ray trace against seed baseline and optimizer branch",
            "depends_on": ["lock-first-order"],
            "evidence": ["after max RMS=7.50 um"],
        },
    ],
    "optimization_task_runs": [
        {
            "task_id": "apply-protected-change-set",
            "candidate_id": "optimizer-proposal",
            "status": "passed",
            "summary": "post-tweak paraxial, ray trace, and full-field MTF checks passed",
            "metric_updates": [
                {
                    "metric": "efl_error",
                    "before": 0.06,
                    "after": 0.01,
                    "unit": "mm",
                    "direction": "improved",
                    "interpretation": "EFL miss 0.060->0.010 mm against target 3.000 mm",
                },
                {
                    "metric": "max_rms_spot_radius",
                    "before": 8.1,
                    "after": 7.5,
                    "unit": "um",
                    "direction": "improved",
                    "interpretation": "max RMS 8.10->7.50 um",
                },
            ],
            "unlocked_tasks": ["lock-first-order"],
            "next_action": "unlock lock-first-order on the optimizer-proposal clone",
            "evidence": [
                "radius S7 3.0580->3.1320",
                "verification gate=passed",
                "applied_to_payload=False",
            ],
        },
        {
            "task_id": "lock-first-order",
            "candidate_id": "optimizer-proposal",
            "status": "passed",
            "summary": "first-order targets are inside review tolerance on the protected branch",
            "metric_updates": [
                {
                    "metric": "f_number_delta",
                    "before": 0.20,
                    "after": 0.20,
                    "unit": "F/#",
                    "direction": "unchanged",
                    "interpretation": "F-number delta remains within review tolerance",
                }
            ],
            "unlocked_tasks": ["local-merit-tuning"],
            "next_action": "unlock local-merit-tuning for image-quality and packaging work",
            "evidence": ["EFL ok=True", "F-number ok=True"],
        },
        {
            "task_id": "local-merit-tuning",
            "candidate_id": "optimizer-proposal",
            "status": "passed",
            "summary": "protected branch improved or preserved RMS/MTF merit evidence",
            "metric_updates": [
                {
                    "metric": "max_rms_spot_radius",
                    "before": 407.6,
                    "after": 398.9,
                    "unit": "um",
                    "direction": "improved",
                    "interpretation": "protected branch max RMS 407.60->398.90 um",
                }
            ],
            "unlocked_tasks": ["production-validation"],
            "next_action": "unlock production-validation for production validation",
            "evidence": ["RMS non-worse=True", "MTF field non-worse=True"],
        },
    ],
}


def _mock_chat_response(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


@patch("app.api.wizard.get_async_client")
def test_exec_summary_happy_path(mock_get_client):
    """Claude returns bilingual JSON → endpoint splits + relays."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            '{"summary_en": "A 7mm telephoto module built on a Largan-class 7-element reference. Compact total track keeps it phone-realistic.", "summary_zh": "基于大立光 7 片式参考的 7mm 长焦镜组，总长保持在手机可塞入的尺度。"}'
        )
    )
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/executive-summary",
        json=_FULL_EXEC_REQUEST,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "telephoto" in data["summary_en"].lower()
    assert "长焦" in data["summary_zh"]
    assert data["fallback_reason"] is None


@patch("app.api.wizard.get_async_client")
def test_exec_summary_includes_design_assessment_context(mock_get_client):
    """v2-07: executive summary prompt sees match score, candidates, and next steps."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            '{"summary_en": "Seed-aware summary.", "summary_zh": "带有 seed 判断的摘要。"}'
        )
    )
    mock_get_client.return_value = mock_client

    req = dict(_FULL_EXEC_REQUEST)
    req["design_assessment"] = _DESIGN_ASSESSMENT_CONTEXT
    r = client.post("/api/wizard/executive-summary", json=req)

    assert r.status_code == 200, r.text
    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    user_msg = messages[1]["content"]
    assert "Design-agent match assessment" in user_msg
    assert "Matched real seed" in user_msg
    assert "5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15" in user_msg
    assert "cost_variant" in user_msg
    assert "Suggested next steps" in user_msg
    assert "Requirement coverage: tradeoff" in user_msg
    assert "field_of_view: tradeoff" in user_msg
    assert "manufacturing_tier: tradeoff" in user_msg
    assert "Manufacturability review: warning" in user_msg
    assert "minimum_axial_spacing: warning" in user_msg
    assert "not a Monte-Carlo tolerance or yield analysis" in user_msg
    assert "Readiness: yellow" in user_msg
    assert "Risk register" in user_msg
    assert "Optimization plan" in user_msg
    assert "Protected optimizer attempt: proposal" in user_msg
    assert "Proposed variable: radius S7" in user_msg
    assert "Verification gate: passed" in user_msg
    assert "Verified MTF field: 1.0" in user_msg
    assert "Metric delta: EFL 2.940->2.990 mm" in user_msg
    assert "Protected RMS merit probe: proposal" in user_msg
    assert "Merit variable: radius S5" in user_msg
    assert "Merit verification gate: passed" in user_msg
    assert "Recommended draft candidate: optimizer-proposal" in user_msg
    assert "Branch selection policy: strategy_resolution_required" in user_msg
    assert "primary=high-fov-full-field-seed-needed" in user_msg
    assert "deliverable=partial-field-high-fov-draft" in user_msg
    assert "Candidate priority: high-fov-full-field-seed-needed" in user_msg
    assert "Branch forbidden claims: full-field edge-performance claim" in user_msg
    assert "Draft acceptance gate: conditional" in user_msg
    assert "delivery_gate: warning" in user_msg
    assert "Acceptance next actions: ingest a seed with MTF at 1.0 field" in user_msg
    assert "Acceptance upgrade actions" in user_msg
    assert "P1 delivery_gate-1 from delivery_gate" in user_msg
    assert "criteria=ingest a seed with MTF at 1.0 field" in user_msg
    assert "unblocks=full-field edge-performance claim" in user_msg
    assert "Acceptance forbidden claims: full-field edge-performance claim" in user_msg
    assert "Acceptance improvement tasks" in user_msg
    assert "P1 ingest-high-fov-full-field-seed" in user_msg
    assert "external_evidence_required/seed_ingestion" in user_msg
    assert "blocks claims: full-field edge-performance claim" in user_msg
    assert "probe=gap" in user_msg
    assert "full-field high-FOV seeds=0" in user_msg
    assert "Seed current gap evidence" in user_msg
    assert "near miss nearest_high_fov" in user_msg
    assert "MTF field 0.8 < required 1.0" in user_msg
    assert "near miss nearest_full_field" in user_msg
    assert "FOV 78.8 < required 85.0" in user_msg
    assert "audit_seed_intake.py" in user_msg
    assert "seed-baseline: baseline/hold, strategy=partial_field_high_fov_draft" in user_msg
    assert "MTF field=1.0" in user_msg
    assert "evidence: matched real case" in user_msg
    assert "risk: proposal still requires full tolerancing before release" in user_msg
    assert "Prescription change set from optimizer-proposal" in user_msg
    assert "Change: radius S7" in user_msg
    assert "Optimization task queue" in user_msg
    assert "apply-protected-change-set: ready/apply_change_set" in user_msg
    assert "lock-first-order: queued/first_order_lock" in user_msg
    assert "Optimization task run evidence" in user_msg
    assert "apply-protected-change-set: passed" in user_msg
    assert "lock-first-order: passed" in user_msg
    assert "local-merit-tuning: passed" in user_msg
    assert "efl_error 0.060->0.010" in user_msg
    assert "unlocked: lock-first-order" in user_msg


@patch("app.api.wizard.get_async_client")
def test_exec_summary_strips_markdown_fences(mock_get_client):
    """Defensive: Claude sometimes wraps JSON in ```json``` despite prompt."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            '```json\n{"summary_en": "en text", "summary_zh": "zh text"}\n```'
        )
    )
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/executive-summary",
        json=_FULL_EXEC_REQUEST,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["summary_en"] == "en text"
    assert body["summary_zh"] == "zh text"


@patch("app.api.wizard.get_async_client")
def test_exec_summary_relay_failure_returns_deterministic_fallback(mock_get_client):
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("rate_limit"))
    mock_get_client.return_value = mock_client

    req = dict(_FULL_EXEC_REQUEST)
    req["design_assessment"] = _DESIGN_ASSESSMENT_CONTEXT
    r = client.post(
        "/api/wizard/executive-summary",
        json=req,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fallback_reason"].startswith("llm_relay_failure")
    assert body["model"].startswith("deterministic-fallback:")
    assert "5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15" in body["summary_en"]
    assert "Main tradeoff" in body["summary_en"]
    assert "Next action" in body["summary_en"]
    assert "production-ready prescription" in body["summary_en"]
    assert "5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15" in body["summary_zh"]
    assert "主要取舍" in body["summary_zh"]
    assert "下一步" in body["summary_zh"]


@patch("app.api.wizard.get_async_client")
def test_exec_summary_unparseable_json_returns_deterministic_fallback(mock_get_client):
    """If Claude returns prose instead of JSON, keep the report narrative alive."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response("Sorry, I cannot help with that.")
    )
    mock_get_client.return_value = mock_client

    req = dict(_FULL_EXEC_REQUEST)
    req["design_assessment"] = _DESIGN_ASSESSMENT_CONTEXT
    r = client.post(
        "/api/wizard/executive-summary",
        json=req,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fallback_reason"] == "llm_response_unparseable"
    assert "Requirement coverage" in body["summary_en"]
    assert "FOV" in body["summary_en"]
    assert "初始设计包" in body["summary_zh"]


@patch("app.api.wizard.get_async_client")
def test_exec_summary_non_object_json_returns_deterministic_fallback(mock_get_client):
    """Edge case: Claude returned a valid JSON array, not an object."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_mock_chat_response("[1, 2, 3]"))
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/executive-summary",
        json=_FULL_EXEC_REQUEST,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fallback_reason"] == "llm_response_not_object: list"
    assert "the computed seed" in body["summary_en"]
    assert "not a production-ready prescription" in body["summary_en"]


@patch("app.api.wizard.get_async_client")
def test_exec_summary_empty_object_returns_deterministic_fallback(mock_get_client):
    """Valid JSON without summary fields should still produce a report paragraph."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_mock_chat_response("{}"))
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/executive-summary",
        json=_FULL_EXEC_REQUEST,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fallback_reason"] == "llm_response_missing_summary"
    assert body["summary_en"]
    assert body["summary_zh"]


def test_exec_summary_missing_required_field_returns_422():
    """Pydantic catches missing focal_length_mm before the LLM is called."""
    bad = dict(_FULL_EXEC_REQUEST)
    del bad["focal_length_mm"]
    r = client.post("/api/wizard/executive-summary", json=bad)
    assert r.status_code == 422


def test_exec_summary_zero_focal_length_returns_422():
    """Pydantic gt=0 constraint."""
    bad = dict(_FULL_EXEC_REQUEST)
    bad["focal_length_mm"] = 0
    r = client.post("/api/wizard/executive-summary", json=bad)
    assert r.status_code == 422
