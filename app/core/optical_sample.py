"""OpticalSampleData composite model + per-case metadata (phase v2-02).

Mirrors the frontend contract in `src/app/[locale]/agent/_data/types.ts`. The
five-piece payload (paraxial / surfaces / trace / mtf / layout_svg) reuses the
existing backend models; `CaseMetadata` is new — honest provenance for each
real design (piece count, imaging-vs-filter split, materials, EFL accuracy).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.aberration import MTFResult
from app.core.field_analysis import FieldAnalysisResult
from app.core.lens_system import LayoutSVG, RayTraceResult, Scenario
from app.core.optical_engine import ParaxialSummary, SurfaceDescriptor
from app.core.provenance import ProvenanceSource
from app.core.spot_diagram import SpotDiagramResult
from app.core.wavefront_metrics import WavefrontMetricsResult


class CaseMetadata(BaseModel):
    """Honest provenance for one real design (BRIEF principle 3)."""

    case_id: str = Field(..., description="Source zmx filename without extension")
    source_zmx: str = Field(..., description="Original zmx filename")
    scenario: Scenario = Field(..., description="smartphone-wide / smartphone-ultrawide")
    n_pieces: int = Field(..., description="Imaging element count from filename (NP prefix)")
    n_imaging: int = Field(..., description="Imaging lens elements detected (curved, glass)")
    n_filter: int = Field(..., description="Flat IR-filter / cover-glass plates")
    materials: list[str] = Field(..., description="Distinct real material names used (datasheet)")
    fov_deg: float = Field(..., description="Nominal full FOV from the manifest")
    image_height_mm: float | None = Field(None, description="Nominal image height from index.json")
    nominal_efl_mm: float = Field(..., description="Design-nominal EFL from filename")
    computed_efl_mm: float = Field(..., description="Optiland-recomputed EFL")
    efl_error_pct: float = Field(..., description="abs(computed-nominal)/nominal*100")
    mtf_max_field_frac: float = Field(
        1.0,
        description=(
            "Max field fraction MTF was computed to. <1.0 means full-field "
            "ray-aiming hit NaN and we fell back to a smaller field set."
        ),
    )


class CandidateComparison(BaseModel):
    """One seed worth comparing before local optimization."""

    case_id: str
    role: str = Field(
        ...,
        description=(
            "best_match / cost_variant / thin_variant / performance_variant / nearby_alternative_N"
        ),
    )
    score: float = Field(..., ge=0.0, le=1.0)
    normalized_distance: float = Field(..., ge=0.0)
    scenario: Scenario
    efl_mm: float
    f_number: float
    fov_deg: float
    image_height_mm: float
    total_track_mm: float
    n_pieces: int
    mtf_max_field_frac: float
    tolerance_risk_score: float | None = Field(None, ge=0.0, le=1.0)
    tolerance_risk_level: str | None = Field(None, description="low / medium / high")
    process_yield_score: float | None = Field(None, ge=0.0, le=1.0)
    process_yield_level: str | None = Field(None, description="low / medium / high")
    mass_proxy_g: float | None = Field(None, ge=0.0)
    review_proxy_notes: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)


class SeedSelectionMetricScore(BaseModel):
    """One active metric contribution in real-seed ranking."""

    metric_id: str
    label: str
    weight: float = Field(..., ge=0.0, le=1.0)
    target: str
    actual: str
    normalized_miss: float = Field(..., ge=0.0)
    contribution: float = Field(..., ge=0.0)
    status: str = Field(..., description="dominant / tradeoff / aligned")
    rationale: str


class SeedSelectionScorecard(BaseModel):
    """Why the selected real seed ranked first for the normalized brief."""

    selected_case_id: str
    selected_rank: int = Field(..., ge=1)
    selected_score: float = Field(..., ge=0.0, le=1.0)
    normalized_distance: float = Field(..., ge=0.0)
    scoring_profile: str
    metric_scores: list[SeedSelectionMetricScore] = Field(default_factory=list)
    top_penalty_metric_id: str | None = None
    accepted_tradeoffs: list[str] = Field(default_factory=list)
    rejected_alternatives: list[str] = Field(default_factory=list)
    summary: str
    next_action: str


class DesignReadiness(BaseModel):
    """First-pass readiness of the selected seed before local optimization."""

    level: str = Field(..., description="green / yellow / red")
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str


class DesignRisk(BaseModel):
    """One design-review risk with evidence and mitigation."""

    risk: str
    severity: str = Field(..., description="low / medium / high")
    evidence: str
    mitigation: str


class RequirementCoverageItem(BaseModel):
    """One user requirement checked against the selected seed and evidence."""

    requirement_id: str
    label: str
    status: str = Field(..., description="met / tradeoff / miss / unscored")
    priority: str = Field(..., description="critical / important / context")
    target: str
    actual: str
    delta: float | None = None
    tolerance: float | None = None
    unit: str | None = None
    evidence: list[str] = Field(default_factory=list)
    next_action: str | None = None


class RequirementCoverageSummary(BaseModel):
    """Compact rollup of the per-requirement coverage matrix."""

    status: str = Field(..., description="met / tradeoff / blocked")
    met_count: int = Field(..., ge=0)
    tradeoff_count: int = Field(..., ge=0)
    miss_count: int = Field(..., ge=0)
    unscored_count: int = Field(..., ge=0)
    summary: str


class DesignIntentConstraintItem(BaseModel):
    """One interpreted requirement in the design brief."""

    requirement_id: str
    label: str
    target: str
    priority: str = Field(..., description="critical / important / context")
    status: str = Field(..., description="met / tradeoff / miss / unscored")
    negotiability: str = Field(
        ...,
        description="locked / explicit_review_required / reviewable / context",
    )
    source: str = Field(..., description="user_request / derived_evidence / preference")
    evidence: list[str] = Field(default_factory=list)
    next_action: str | None = None


class DesignIntentContract(BaseModel):
    """Normalized optical brief before seed handoff or optimization claims."""

    status: str = Field(..., description="ready / review_required / blocked")
    normalized_query: str
    scenario_family: str
    hard_constraints: list[DesignIntentConstraintItem] = Field(default_factory=list)
    soft_preferences: list[DesignIntentConstraintItem] = Field(default_factory=list)
    inferred_assumptions: list[str] = Field(default_factory=list)
    conflict_flags: list[str] = Field(default_factory=list)
    safe_interpretation: str
    next_action: str


class ManufacturabilityCheck(BaseModel):
    """One deterministic first-pass manufacturability check."""

    check_id: str
    label: str
    status: str = Field(..., description="pass / warning / blocker / not_applicable")
    target: str
    actual: str
    evidence: list[str] = Field(default_factory=list)
    mitigation: str | None = None


class ManufacturabilityReview(BaseModel):
    """A first-pass manufacturability proxy, not a full tolerance/yield model."""

    status: str = Field(..., description="pass / warning / blocked")
    tier: str | None = None
    score: float = Field(..., ge=0.0, le=1.0)
    summary: str
    checks: list[ManufacturabilityCheck] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ManufacturingSensitivityFactor(BaseModel):
    """One factor that may dominate first-pass manufacturing sensitivity."""

    factor_id: str
    label: str
    status: str = Field(..., description="pass / watch / risk / blocked")
    sensitivity: str = Field(..., description="low / medium / high")
    source: str
    metric: str
    evidence: list[str] = Field(default_factory=list)
    next_action: str


class ManufacturingSensitivityAudit(BaseModel):
    """Deterministic sensitivity audit derived from review proxies, not simulation."""

    status: str = Field(..., description="clear / watch / risk / blocked")
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str
    dominant_factor_id: str | None = None
    factors: list[ManufacturingSensitivityFactor] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    safe_next_action: str
    limitations: list[str] = Field(default_factory=list)


class ManufacturingClearanceItem(BaseModel):
    """One executable evidence item for clearing manufacturing-sensitive risks."""

    item_id: str
    source_factor_id: str
    priority: int = Field(..., ge=1)
    status: str = Field(
        ...,
        description="clear / ready / external_evidence_required / blocked",
    )
    owner_role: str
    clearance_objective: str
    required_evidence: list[str] = Field(default_factory=list)
    validation_steps: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    current_evidence: list[str] = Field(default_factory=list)
    next_action: str
    blocks_review: bool = False
    blocks_production_claims: bool = True


class ManufacturingClearanceChecklist(BaseModel):
    """Review checklist for moving from proxy manufacturability to claim evidence."""

    status: str = Field(
        ...,
        description="clear / production_evidence_required / blocked",
    )
    summary: str
    dominant_item_id: str | None = None
    items: list[ManufacturingClearanceItem] = Field(default_factory=list)
    review_blocking_count: int = Field(..., ge=0)
    production_blocking_count: int = Field(..., ge=0)
    external_dependency_count: int = Field(..., ge=0)
    next_clearance_action: str
    forbidden_claims: list[str] = Field(default_factory=list)


class ToleranceSensitivityItem(BaseModel):
    """One first-order tolerance-sensitive contributor in the selected seed."""

    item_id: str
    label: str
    variable_type: str = Field(
        ...,
        description="air_gap / curvature_radius / aperture / material_stack / field_coverage",
    )
    status: str = Field(..., description="pass / watch / risk / blocked")
    sensitivity_score: float = Field(..., ge=0.0, le=1.0)
    surface_index: int | None = None
    coupled_surface_index: int | None = None
    nominal_value: str
    perturbation: str
    margin: str
    evidence: list[str] = Field(default_factory=list)
    next_action: str


class ToleranceSensitivityAudit(BaseModel):
    """Deterministic first-order tolerance watch list; not Monte-Carlo."""

    status: str = Field(..., description="clear / watch / risk / blocked")
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str
    dominant_item_id: str | None = None
    items: list[ToleranceSensitivityItem] = Field(default_factory=list)
    pass_criteria: list[str] = Field(default_factory=list)
    safe_next_action: str
    limitations: list[str] = Field(default_factory=list)


class DraftAcceptanceCheck(BaseModel):
    """One check contributing to final draft acceptance."""

    check_id: str
    label: str
    status: str = Field(..., description="pass / warning / blocker")
    evidence: str
    required_action: str | None = None


class DraftAcceptanceUpgradeAction(BaseModel):
    """One prioritized action to move a non-ready draft toward acceptance."""

    action_id: str
    priority: int = Field(..., ge=1)
    source_check_id: str
    action: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    expected_effect: str
    unblocks_claims: list[str] = Field(default_factory=list)


class DraftAcceptanceGate(BaseModel):
    """Final acceptance state for the current draft deliverable."""

    status: str = Field(..., description="ready_for_review / conditional / blocked")
    candidate_id: str | None = None
    deliverable_type: str
    score: float = Field(..., ge=0.0, le=1.0)
    summary: str
    checks: list[DraftAcceptanceCheck] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)
    required_next_actions: list[str] = Field(default_factory=list)
    upgrade_actions: list[DraftAcceptanceUpgradeAction] = Field(default_factory=list)
    allowed_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)


class AcceptanceEvidenceProbe(BaseModel):
    """Deterministic probe attached to an acceptance-improvement task."""

    probe_id: str
    status: str = Field(..., description="satisfied / gap / blocked / not_applicable")
    summary: str
    known_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    next_probe_command: str | None = None


class AcceptanceImprovementTask(BaseModel):
    """Executable task for closing a draft acceptance evidence gap."""

    task_id: str
    source_action_id: str
    priority: int = Field(..., ge=1)
    status: str = Field(..., description="ready / queued / blocked / external_evidence_required")
    stage: str
    owner: str
    objective: str
    required_inputs: list[str] = Field(default_factory=list)
    validation_steps: list[str] = Field(default_factory=list)
    exit_criteria: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    blocks_claims: list[str] = Field(default_factory=list)
    evidence_probe: AcceptanceEvidenceProbe | None = None


class EvidenceCloseoutItem(BaseModel):
    """One evidence obligation that must be closed before stronger claims."""

    item_id: str
    priority: int = Field(..., ge=1)
    source: str
    status: str = Field(
        ...,
        description="ready / external_evidence_required / blocked / reminder",
    )
    owner_role: str
    required_evidence: str
    claim_unblocked: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    next_action: str
    blocks_review: bool = False
    blocks_production_claims: bool = True


class EvidenceCloseoutPlan(BaseModel):
    """Rollup of remaining evidence obligations across the design packet."""

    status: str = Field(..., description="clear / production_evidence_required / blocked")
    summary: str
    highest_priority_item_id: str | None = None
    items: list[EvidenceCloseoutItem] = Field(default_factory=list)
    review_blocking_count: int = Field(..., ge=0)
    production_blocking_count: int = Field(..., ge=0)
    external_dependency_count: int = Field(..., ge=0)
    safe_next_action: str
    forbidden_claims: list[str] = Field(default_factory=list)


class DesignHandoffMetric(BaseModel):
    """One headline metric in the optical design handoff packet."""

    metric_id: str
    label: str
    value: str
    target: str | None = None
    status: str = Field(..., description="met / tradeoff / warning / blocked / context")


class DesignHandoffPacket(BaseModel):
    """Compact front-door summary of the delivered initial optical design."""

    status: str = Field(..., description="ready_for_review / conditional / blocked")
    candidate_id: str
    prescription_source: str
    payload_policy: str
    summary: str
    headline_metrics: list[DesignHandoffMetric] = Field(default_factory=list)
    accepted_tradeoffs: list[str] = Field(default_factory=list)
    review_focus: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    next_decision: str


class DesignTraceabilityManifest(BaseModel):
    """Where the delivered design packet came from and how to replay it."""

    status: str = Field(..., description="ready_for_review / conditional / blocked")
    source_case_id: str
    source_zmx: str
    source_zmx_path: str
    generated_case_path: str
    delivered_candidate_id: str
    delivered_payload: str
    payload_policy: str
    surface_count: int = Field(..., ge=0)
    material_count: int = Field(..., ge=0)
    material_families: list[str] = Field(default_factory=list)
    mtf_field_evidence: str
    change_set_applied: bool = False
    change_set_policy: str | None = None
    report_sections: list[str] = Field(default_factory=list)
    validation_evidence: list[str] = Field(default_factory=list)
    replay_commands: list[str] = Field(default_factory=list)
    forbidden_mutations: list[str] = Field(default_factory=list)
    next_replay_action: str


class DesignConstraintItem(BaseModel):
    """One requirement in the handoff constraint ledger."""

    requirement_id: str
    label: str
    status: str = Field(
        ...,
        description="locked / accepted_tradeoff / unresolved / context",
    )
    target: str
    current: str
    policy: str
    evidence: list[str] = Field(default_factory=list)
    next_action: str | None = None


class DesignVariableGovernanceItem(BaseModel):
    """How a design variable family may be touched after handoff."""

    variable_id: str
    label: str
    status: str = Field(..., description="frozen / allowed / guarded / blocked")
    scope: str
    allowed_action: str
    guardrails: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    next_action: str


class DesignConstraintLedger(BaseModel):
    """Handoff contract for locked constraints and governed variable changes."""

    status: str = Field(..., description="ready_for_review / needs_review / blocked")
    summary: str
    locked_count: int = Field(..., ge=0)
    accepted_tradeoff_count: int = Field(..., ge=0)
    unresolved_count: int = Field(..., ge=0)
    variable_policy_summary: str
    constraints: list[DesignConstraintItem] = Field(default_factory=list)
    variables: list[DesignVariableGovernanceItem] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    next_action: str


class OptimizationAction(BaseModel):
    """One deterministic next action for the optical optimization loop."""

    priority: int = Field(..., ge=1)
    objective: str
    parameter_focus: list[str] = Field(default_factory=list)
    expected_effect: str
    verification: str


class OptimizationVariableChange(BaseModel):
    """One bounded variable change proposed by a protected optimizer attempt."""

    variable: str
    surface_index: int
    before: float
    after: float
    delta: float
    delta_pct: float


class OptimizationVariableCandidate(BaseModel):
    """One optimizer variable considered before a bounded local probe."""

    variable: str = Field(..., description="radius / thickness / asphere_coefficient")
    surface_index: int
    coefficient_index: int | None = None
    before: float | None = None
    min_value: float | None = None
    max_value: float | None = None
    status: str = Field(..., description="eligible / audited_only / skipped")
    reason: str
    asphere_power: int | None = None
    audit_aperture_mm: float | None = None
    edge_sag_delta_um: float | None = None
    edge_slope_delta_mrad: float | None = None
    manufacturability_status: str | None = None


class OptimizationVariableTrial(BaseModel):
    """Replay evidence from probing one optimizer variable candidate."""

    variable: str
    surface_index: int
    coefficient_index: int | None = None
    coupled_variable: str | None = None
    coupled_surface_index: int | None = None
    coupled_before: float | None = None
    coupled_after: float | None = None
    prescreen_rank: int | None = None
    step_fraction: float | None = None
    status: str = Field(..., description="improved / accepted / rejected / failed / skipped")
    reason: str
    before: float | None = None
    after: float | None = None
    merit_before: float | None = None
    merit_after: float | None = None
    efl_improvement_mm: float | None = None
    rms_improvement_um: float | None = None
    rms_improvement_pct: float | None = None
    promotion_score: float | None = None
    image_quality_floor_gap_before: float | None = None
    image_quality_floor_gap_after: float | None = None
    image_quality_floor_gap_closure: float | None = None
    verification_status: str | None = None
    mtf_field_non_regressed: bool | None = None
    mtf_band_non_regressed: bool | None = None
    mtf_field_weighted_non_regressed: bool | None = None
    efl_locked: bool | None = None


class OptimizationMetricSnapshot(BaseModel):
    """Small metric packet before or after a protected optimizer proposal."""

    effective_focal_length_mm: float | None = None
    f_number: float | None = None
    total_track_mm: float | None = None
    mtf_max_field_frac: float | None = None
    mtf_50lpmm_min: float | None = None
    mtf_50lpmm_avg: float | None = None
    mtf_100lpmm_min: float | None = None
    mtf_100lpmm_avg: float | None = None
    mtf_150lpmm_min: float | None = None
    mtf_150lpmm_avg: float | None = None
    mtf_200lpmm_min: float | None = None
    mtf_200lpmm_avg: float | None = None
    mtf_250lpmm_min: float | None = None
    mtf_250lpmm_avg: float | None = None
    mtf_multiband_min_score: float | None = None
    mtf_field_weighted_score: float | None = None
    max_rms_spot_radius_um: float | None = None


class CodeVRefinementMetricSnapshot(BaseModel):
    """Metric packet emitted by the CODE V AUT refinement run."""

    provenance: ProvenanceSource = ProvenanceSource.CODEV_RUN
    efl_y_mm: float
    max_lateral_color_um: float
    max_rms_spot_diameter_um: float
    max_rms_wavefront_error_waves: float
    max_distortion_pct: float


class CodeVToleranceSensitivityRow(BaseModel):
    """One top-N tolerance sensitivity row sourced from CODE V."""

    provenance: ProvenanceSource = ProvenanceSource.CODEV_RUN
    rank: int = Field(..., ge=1)
    parameter_name: str
    perturbation: str
    mtf_drop: float = Field(..., ge=0.0)


class CodeVRefinementComparison(BaseModel):
    """Seed vs CODE V refined comparison carried inside optical_sample payloads."""

    source_zmx: str
    optimization_status: str
    glass_policy: str
    thickness_policy: str
    optimized_readout_path: str | None = None
    optimized_zmx_filename: str
    before: CodeVRefinementMetricSnapshot
    after: CodeVRefinementMetricSnapshot
    efl_deviation_pct: float
    seed_mtf: MTFResult | None = None
    refined_mtf: MTFResult | None = None
    tolerance_sensitivity_top_n: list[CodeVToleranceSensitivityRow] = Field(
        default_factory=list
    )
    cross_validation_status: str = "rebuilt-zmx-ingested"
    cross_validation_provenance: str = "codev-cross-validated"


class DraftCandidate(BaseModel):
    """A branch the agent can recommend, hold, or reject for continued design."""

    candidate_id: str
    source: str = Field(
        ...,
        description=(
            "seed_baseline / protected_optimizer / strategy_option / candidate_proxy / "
            "recovery_probe / requirement_branch / requirement_gap"
        ),
    )
    strategy_option_id: str | None = None
    status: str = Field(
        ...,
        description=(
            "baseline / proposed / warning / diagnostic / fallback / blocked / conditional"
        ),
    )
    recommendation: str = Field(..., description="continue / hold / reject")
    summary: str
    metrics: OptimizationMetricSnapshot | None = None
    evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class DraftBranchSelectionPolicy(BaseModel):
    """How to interpret draft branches when the active payload is not the target path."""

    status: str = Field(..., description="straight_through / strategy_resolution_required")
    active_candidate_id: str
    primary_candidate_id: str | None = None
    current_deliverable_candidate_id: str | None = None
    candidate_priority_order: list[str] = Field(default_factory=list)
    blocked_candidate_ids: list[str] = Field(default_factory=list)
    fallback_candidate_ids: list[str] = Field(default_factory=list)
    summary: str
    rationale: list[str] = Field(default_factory=list)
    promotion_requirements: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)


class DraftBranchTradeoffRow(BaseModel):
    """One row in a decision-grade comparison of draft branches."""

    priority_rank: int
    candidate_id: str
    source: str
    strategy_option_id: str | None = None
    role_tags: list[str] = Field(default_factory=list)
    status: str
    recommendation: str
    case_id: str | None = None
    fov_deg: float | None = None
    delta_fov_deg: float | None = None
    efl_mm: float | None = None
    delta_efl_mm: float | None = None
    f_number: float | None = None
    image_height_mm: float | None = None
    total_track_mm: float | None = None
    n_pieces: int | None = None
    mtf_max_field_frac: float | None = None
    evidence_level: str = Field(
        ...,
        description="missing_seed / partial_field / full_field / optimizer_probe / review_required",
    )
    claim_status: str
    tradeoff_summary: str
    next_action: str


class SpecRepairPreviewPacket(BaseModel):
    """Structured preview for a repaired target before mutating the payload."""

    source_candidate_id: str
    status: str = Field(
        ...,
        description="ready_after_repair / tradeoff_after_repair / blocked_after_repair",
    )
    repaired_target_focal_length_mm: float
    repaired_target_image_height_mm: float | None = None
    target_fov_deg: float
    selected_case_id: str
    score: float = Field(..., ge=0.0, le=1.0)
    normalized_distance: float = Field(..., ge=0.0)
    coverage_summary: RequirementCoverageSummary
    coverage: list[RequirementCoverageItem] = Field(default_factory=list)
    remaining_tradeoffs: list[str] = Field(default_factory=list)
    payload_policy: str
    evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class SpecRepairRerunContract(BaseModel):
    """Exact target inputs for the next run after accepting a spec repair."""

    source_decision: str
    status: str = Field(..., description="ready / blocked")
    target_scenario: Scenario
    target_focal_length_mm: float
    target_f_number: float
    target_fov_deg: float
    target_image_height_mm: float | None = None
    target_n_elements: int | None = None
    target_total_track_mm: float | None = None
    priority: str | None = None
    manufacturing_tier: str | None = None
    expected_case_id: str | None = None
    expected_coverage_summary: RequirementCoverageSummary | None = None
    query_summary: str
    validation_checks: list[str] = Field(default_factory=list)
    payload_policy: str


class SpecRepairDecisionPacket(BaseModel):
    """Reviewable target-spec decision for an EFL/image-height/FOV conflict."""

    source_candidate_id: str
    status: str = Field(
        ...,
        description="recommended / recommended_with_tradeoffs / blocked",
    )
    recommended_decision: str = Field(
        ...,
        description="accept_repaired_efl_target / repair_image_height / waive_fov",
    )
    locked_constraint: str
    repaired_parameter: str
    original_focal_length_mm: float
    repaired_focal_length_mm: float | None = None
    original_image_height_mm: float | None = None
    repaired_image_height_mm: float | None = None
    target_fov_deg: float
    first_order_fov_deg: float | None = None
    implied_image_height_mm: float | None = None
    selected_case_id: str | None = None
    preview_status: str | None = None
    preview_coverage_summary: RequirementCoverageSummary | None = None
    decision_summary: str
    alternatives: list[str] = Field(default_factory=list)
    required_record: str
    acceptance_effect: str
    payload_policy: str
    rerun_contract: SpecRepairRerunContract | None = None
    evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class SpecRepairAutoClosure(BaseModel):
    """A safe minor target-spec repair that can be recorded without blocking review."""

    source_decision: str
    status: str = Field(..., description="auto_closed_for_review")
    repaired_target_focal_length_mm: float
    target_image_height_mm: float | None = None
    target_fov_deg: float
    repair_delta_mm: float
    repair_delta_pct: float
    accepted_tradeoff_ids: list[str] = Field(default_factory=list)
    summary: str
    rationale: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)


class PrescriptionChangeSet(BaseModel):
    """A guarded, not-yet-applied prescription edit packet."""

    source_candidate_id: str
    changes: list[OptimizationVariableChange] = Field(default_factory=list)
    expected_effect: str
    application_policy: str
    verification_checklist: list[str] = Field(default_factory=list)


class RemediationResolutionPath(BaseModel):
    """One concrete path that can resolve a blocked remediation policy."""

    path_id: str
    label: str
    status: str = Field(..., description="available / gap / blocked / manual_required")
    required_evidence: list[str] = Field(default_factory=list)
    command: str | None = None
    next_check: str


class RemediationResolutionPacket(BaseModel):
    """Structured contract for unblocking a held remediation policy."""

    packet_id: str
    policy: str
    policy_action: str
    failed_check_ids: list[str] = Field(default_factory=list)
    base_variables: list[str] = Field(default_factory=list)
    policy_selected_variables: list[str] = Field(default_factory=list)
    paths: list[RemediationResolutionPath] = Field(default_factory=list)
    resume_criteria: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class OptimizationTask(BaseModel):
    """One queued optimization task with explicit stop and verification rules."""

    task_id: str
    candidate_id: str
    stage: str
    status: str = Field(..., description="ready / blocked / queued")
    objective: str
    variables: list[str] = Field(default_factory=list)
    entry_condition: str
    stop_condition: str
    verification: str
    depends_on: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    resolution_packet: RemediationResolutionPacket | None = None


class OptimizationMetricUpdate(BaseModel):
    """One metric delta observed while running an optimization task."""

    metric: str
    before: float | None = None
    after: float | None = None
    unit: str | None = None
    direction: str = Field(..., description="improved / unchanged / regressed / diagnostic")
    interpretation: str


class OptimizationReplayGateCheck(BaseModel):
    """One machine-comparable replay gate check."""

    check_id: str
    label: str
    status: str = Field(..., description="pass / warning / fail / blocked / not_run")
    required_for_promotion: bool = True
    comparator: str | None = None
    measured_value: float | None = None
    target_value: float | None = None
    unit: str | None = None
    evidence: list[str] = Field(default_factory=list)


class OptimizationReplayGate(BaseModel):
    """Structured replay gate attached to a task run."""

    gate_id: str
    status: str = Field(..., description="pass / warning / fail / blocked / not_run")
    promotion_allowed: bool
    summary: str
    checks: list[OptimizationReplayGateCheck] = Field(default_factory=list)
    failed_check_ids: list[str] = Field(default_factory=list)
    recommended_variables: list[str] = Field(default_factory=list)
    remediation_actions: list[str] = Field(default_factory=list)
    next_action: str


class OptimizationTaskRun(BaseModel):
    """Evidence packet from running or probing one queued optimization task."""

    task_id: str
    candidate_id: str
    status: str = Field(..., description="passed / warning / diagnostic")
    summary: str
    metric_updates: list[OptimizationMetricUpdate] = Field(default_factory=list)
    unlocked_tasks: list[str] = Field(default_factory=list)
    next_action: str
    evidence: list[str] = Field(default_factory=list)
    replay_gate: OptimizationReplayGate | None = None
    resolution_packet: RemediationResolutionPacket | None = None


class OptimizationVerification(BaseModel):
    """Post-tweak safety checks for a protected optimizer proposal."""

    status: str = Field(..., description="passed / warning / failed / not_run")
    summary: str
    paraxial_ok: bool = False
    ray_trace_ok: bool = False
    mtf_ok: bool = False
    mtf_max_field_frac: float | None = None
    mtf_50lpmm_min: float | None = None
    mtf_50lpmm_avg: float | None = None
    mtf_100lpmm_min: float | None = None
    mtf_100lpmm_avg: float | None = None
    mtf_150lpmm_min: float | None = None
    mtf_150lpmm_avg: float | None = None
    mtf_200lpmm_min: float | None = None
    mtf_200lpmm_avg: float | None = None
    mtf_250lpmm_min: float | None = None
    mtf_250lpmm_avg: float | None = None
    mtf_multiband_min_score: float | None = None
    mtf_field_weighted_score: float | None = None
    max_rms_spot_radius_um: float | None = None
    diagnostics: list[str] = Field(default_factory=list)


class OptimizationAttempt(BaseModel):
    """Evidence from a guarded local optimization attempt on the real seed."""

    status: str = Field(..., description="proposal / diagnostic_only / not_attempted")
    engine: str
    summary: str
    target_efl_mm: float
    target_total_track_mm: float | None = None
    before_efl_mm: float | None = None
    after_efl_mm: float | None = None
    before_total_track_mm: float | None = None
    after_total_track_mm: float | None = None
    merit_before: float | None = None
    merit_after: float | None = None
    improvement_efl_mm: float | None = None
    improvement_pct: float | None = None
    variable_candidates: list[OptimizationVariableCandidate] = Field(default_factory=list)
    candidate_trials: list[OptimizationVariableTrial] = Field(default_factory=list)
    variable_changes: list[OptimizationVariableChange] = Field(default_factory=list)
    verification: OptimizationVerification | None = None
    before_metrics: OptimizationMetricSnapshot | None = None
    after_metrics: OptimizationMetricSnapshot | None = None
    diagnostics: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    applied_to_payload: bool = False
    elapsed_ms: float | None = None


class OptimizationMeritProbe(BaseModel):
    """Evidence from a guarded image-quality merit probe on a cloned branch."""

    status: str = Field(..., description="proposal / warning / diagnostic_only / not_attempted")
    engine: str
    summary: str
    operand: str
    probe_purpose: str | None = None
    variable_priority: list[str] = Field(default_factory=list)
    field_samples: list[float] = Field(default_factory=list)
    target_efl_mm: float
    target_total_track_mm: float | None = None
    merit_before: float | None = None
    merit_after: float | None = None
    rms_improvement_um: float | None = None
    rms_improvement_pct: float | None = None
    variable_candidates: list[OptimizationVariableCandidate] = Field(default_factory=list)
    candidate_trials: list[OptimizationVariableTrial] = Field(default_factory=list)
    variable_changes: list[OptimizationVariableChange] = Field(default_factory=list)
    verification: OptimizationVerification | None = None
    before_metrics: OptimizationMetricSnapshot | None = None
    after_metrics: OptimizationMetricSnapshot | None = None
    diagnostics: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    applied_to_payload: bool = False
    elapsed_ms: float | None = None


class FullFieldRecoveryTrial(BaseModel):
    """One guarded replay trial for recovering full-field evidence."""

    variable_family: str = Field(..., description="stop_position / chief_ray_height")
    surface_index: int
    before: float | None = None
    after: float | None = None
    delta: float | None = None
    status: str = Field(..., description="recovered / improved / rejected / failed / skipped")
    reason: str
    mtf_max_field_frac: float | None = None
    rms_delta_um: float | None = None
    efl_delta_mm: float | None = None
    total_track_delta_mm: float | None = None
    image_quality_floor_gap_score: float | None = None
    metrics: OptimizationMetricSnapshot | None = None
    variable_changes: list[OptimizationVariableChange] = Field(default_factory=list)


class EdgeFieldStabilityPoint(BaseModel):
    """One explicit edge-field MTF/RMS stability probe."""

    field_frac: float = Field(..., ge=0.0, le=1.0)
    status: str = Field(..., description="pass / unstable / failed")
    rms_spot_radius_um: float | None = None
    reason: str


class FullFieldRecoveryDiagnostic(BaseModel):
    """Structured diagnosis when full-field MTF evidence is not yet proven."""

    status: str = Field(..., description="passed / warning / not_needed")
    failure_mode: str = Field(
        ...,
        description="not_needed / partial_field_stability_gap / verification_failure",
    )
    current_field_frac: float | None = None
    target_field_frac: float = 1.0
    field_gap: float | None = None
    stable_branch: str
    local_variable_families_tested: list[str] = Field(default_factory=list)
    rejected_trial_count: int = 0
    best_partial_rms_delta_um: float | None = None
    recovery_trials: list[FullFieldRecoveryTrial] = Field(default_factory=list)
    best_recovery_trial: FullFieldRecoveryTrial | None = None
    edge_field_scan: list[EdgeFieldStabilityPoint] = Field(default_factory=list)
    highest_scanned_stable_field_frac: float | None = None
    edge_field_cliff_frac: float | None = None
    recommended_variable_family: str
    next_action: str
    evidence: list[str] = Field(default_factory=list)


class LibraryCoverageDiagnostic(BaseModel):
    """Whether the real case library covers the requested design regime."""

    status: str = Field(..., description="covered / gap")
    target_fov_deg: float
    high_fov_full_field_available: bool
    nearest_full_field_case_id: str | None = None
    nearest_full_field_fov_deg: float | None = None
    full_field_fov_gap_deg: float | None = None
    nearest_high_fov_case_id: str | None = None
    nearest_high_fov_mtf_field_frac: float | None = None
    recommended_strategy: str
    evidence: list[str] = Field(default_factory=list)


class ReferenceInfluenceAudit(BaseModel):
    """How the real-reference library influenced this draft decision."""

    status: str = Field(..., description="supported / constrained / conflicted")
    selected_reference_id: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str
    supporting_reference_ids: list[str] = Field(default_factory=list)
    constraining_reference_ids: list[str] = Field(default_factory=list)
    rejected_reference_ids: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    influence_notes: list[str] = Field(default_factory=list)
    safe_next_action: str
    forbidden_claims: list[str] = Field(default_factory=list)


class DesignStrategyOption(BaseModel):
    """One actionable option under a design strategy decision."""

    option_id: str = Field(
        ...,
        description=(
            "add_full_field_high_fov_seed / stable_partial_field_sibling_seed / "
            "relax_fov_to_full_field_seed / near_threshold_partial_field_seed / "
            "partial_field_high_fov_draft"
        ),
    )
    label: str
    recommendation: str = Field(..., description="primary / fallback / hold")
    candidate_id: str | None = None
    target_fov_deg: float
    fov_deg: float | None = None
    mtf_max_field_frac: float | None = None
    evidence_status: str = Field(
        ..., description="needs_seed / full_field_available / partial_field_only"
    )
    spec_impact: str
    required_evidence: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)


class SeedAcquisitionBrief(BaseModel):
    """Reference-data requirement for closing a library coverage gap."""

    target_regime: str
    priority: str = Field(..., description="required_for_full_field_claim / useful")
    source_format: str
    target_fov_deg: float
    minimum_fov_deg: float
    target_efl_mm: float
    efl_window_mm: list[float] = Field(..., min_length=2, max_length=2)
    target_f_number: float
    f_number_window: list[float] = Field(..., min_length=2, max_length=2)
    target_image_height_mm: float | None = None
    image_height_window_mm: list[float] = Field(default_factory=list)
    target_n_elements: int | None = None
    element_count_window: list[int] = Field(default_factory=list)
    max_total_track_mm: float | None = None
    required_mtf_field_frac: float = 1.0
    validation_requirements: list[str] = Field(default_factory=list)
    rejection_filters: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)


class SeedIntakeCandidate(BaseModel):
    """One current-library candidate assessed by the seed-intake audit."""

    case_id: str
    source_zmx: str
    role: str = Field(
        ...,
        description=("accepted / nearest_high_fov / best_stable_high_fov / nearest_full_field"),
    )
    fov_deg: float
    efl_mm: float
    f_number: float
    image_height_mm: float | None = None
    n_pieces: int
    mtf_max_field_frac: float
    highest_stable_field_frac: float | None = None
    edge_field_cliff_frac: float | None = None
    edge_field_evidence: list[str] = Field(default_factory=list)
    miss_reasons: list[str] = Field(default_factory=list)


class SeedIntakeAudit(BaseModel):
    """Operational audit for whether a new reference seed can close a gap."""

    status: str = Field(..., description="satisfied / gap")
    summary: str
    target_fov_deg: float
    minimum_fov_deg: float
    efl_window_mm: list[float] = Field(..., min_length=2, max_length=2)
    f_number_window: list[float] = Field(..., min_length=2, max_length=2)
    image_height_window_mm: list[float] = Field(default_factory=list)
    element_count_window: list[int] = Field(default_factory=list)
    max_total_track_mm: float | None = None
    required_mtf_field_frac: float = 1.0
    total_seed_count: int = Field(..., ge=0)
    full_field_seed_count: int = Field(..., ge=0)
    high_fov_seed_count: int = Field(..., ge=0)
    accepted_seed_count: int = Field(..., ge=0)
    accepted_seed_candidates: list[SeedIntakeCandidate] = Field(default_factory=list)
    nearest_candidates: list[SeedIntakeCandidate] = Field(default_factory=list)
    known_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    next_probe_command: str
    candidate_preflight_command: str


class SeedAcquisitionContract(BaseModel):
    """External reference-seed contract that can unblock a design gap."""

    status: str = Field(
        ...,
        description="not_required / external_evidence_required / satisfied / blocked",
    )
    summary: str
    source_task_id: str | None = None
    owner_role: str
    target_regime: str
    acceptance_target: str
    required_candidate_properties: list[str] = Field(default_factory=list)
    preflight_command: str | None = None
    pass_criteria: list[str] = Field(default_factory=list)
    rejection_filters: list[str] = Field(default_factory=list)
    current_gap_evidence: list[str] = Field(default_factory=list)
    fallback_paths: list[str] = Field(default_factory=list)
    blocked_claims: list[str] = Field(default_factory=list)
    next_action: str


class DesignDeliveryGate(BaseModel):
    """Claims allowed for the generated design packet."""

    status: str = Field(..., description="ready_for_draft / conditional_partial_field / blocked")
    deliverable_type: str
    summary: str
    allowed_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    promotion_requirements: list[str] = Field(default_factory=list)
    blocking_evidence: list[str] = Field(default_factory=list)


class DraftQualityDimension(BaseModel):
    """One dimension in the first-pass draft quality rubric."""

    dimension_id: str
    label: str
    score: float = Field(..., ge=0.0, le=1.0)
    status: str = Field(..., description="pass / warning / blocker")
    evidence: list[str] = Field(default_factory=list)
    recommended_action: str | None = None


class DraftQualityRubric(BaseModel):
    """Overall quality verdict for the first-pass design packet."""

    score: float = Field(..., ge=0.0, le=1.0)
    level: str = Field(..., description="reviewable / conditional / blocked")
    summary: str
    weakest_dimension_id: str | None = None
    minimum_next_action: str | None = None
    promotion_target: str | None = None
    promotion_actions: list[str] = Field(default_factory=list)
    dimensions: list[DraftQualityDimension] = Field(default_factory=list)


class DesignStrategyDecision(BaseModel):
    """Selected design path when the requested regime exceeds proven evidence."""

    status: str = Field(..., description="selected / not_needed")
    selected_strategy: str = Field(
        ...,
        description=(
            "add_full_field_high_fov_seed / stable_partial_field_sibling_seed / "
            "relax_fov_to_full_field_seed / partial_field_high_fov_draft / "
            "continue_full_field_optimization"
        ),
    )
    summary: str
    target_fov_deg: float
    provable_full_field_fov_deg: float | None = None
    full_field_fov_gap_deg: float | None = None
    partial_field_fov_deg: float | None = None
    partial_field_mtf_field_frac: float | None = None
    recommended_candidate_id: str | None = None
    fallback_strategies: list[str] = Field(default_factory=list)
    options: list[DesignStrategyOption] = Field(default_factory=list)
    seed_acquisition_brief: SeedAcquisitionBrief | None = None
    rationale: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)


class DesignerReadinessDimension(BaseModel):
    """One dimension in the junior-draft replacement readiness rubric."""

    dimension_id: str
    label: str
    score: float = Field(..., ge=0.0, le=1.0)
    status: str = Field(..., description="pass / warning / blocker")
    evidence: list[str] = Field(default_factory=list)
    next_action: str | None = None


class DesignerReadinessRubric(BaseModel):
    """Goal-level readout for whether the packet can stand in for a junior draft."""

    status: str = Field(..., description="draft_ready / conditional / blocked")
    score: float = Field(..., ge=0.0, le=1.0)
    summary: str
    weakest_dimension_id: str | None = None
    claim_boundary: str
    blockers: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    next_improvement_action: str
    dimensions: list[DesignerReadinessDimension] = Field(default_factory=list)


class DesignAssessment(BaseModel):
    """How well the selected real case satisfies the user's design intent."""

    matched_case_id: str
    score: float = Field(..., ge=0.0, le=1.0)
    normalized_distance: float = Field(..., ge=0.0)
    seed_selection_scorecard: SeedSelectionScorecard | None = None

    target_focal_length_mm: float
    target_f_number: float
    target_fov_deg: float
    target_image_height_mm: float | None = None
    target_n_elements: int | None = None
    target_total_track_mm: float | None = None
    priority: str | None = None
    manufacturing_tier: str | None = None

    delta_efl_mm: float
    delta_f_number: float
    delta_fov_deg: float
    delta_image_height_mm: float | None = None
    delta_n_elements: int | None = None
    delta_total_track_mm: float | None = None

    warnings: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    candidate_comparison: list[CandidateComparison] = Field(default_factory=list)
    requirement_coverage_summary: RequirementCoverageSummary | None = None
    requirement_coverage: list[RequirementCoverageItem] = Field(default_factory=list)
    design_intent_contract: DesignIntentContract | None = None
    manufacturability_review: ManufacturabilityReview | None = None
    manufacturing_sensitivity_audit: ManufacturingSensitivityAudit | None = None
    manufacturing_clearance_checklist: ManufacturingClearanceChecklist | None = None
    tolerance_sensitivity_audit: ToleranceSensitivityAudit | None = None
    next_steps: list[str] = Field(default_factory=list)
    readiness: DesignReadiness | None = None
    risk_register: list[DesignRisk] = Field(default_factory=list)
    optimization_plan: list[OptimizationAction] = Field(default_factory=list)
    optimization_attempt: OptimizationAttempt | None = None
    merit_optimization_probe: OptimizationMeritProbe | None = None
    full_field_recovery_diagnostic: FullFieldRecoveryDiagnostic | None = None
    library_coverage_diagnostic: LibraryCoverageDiagnostic | None = None
    reference_influence_audit: ReferenceInfluenceAudit | None = None
    design_strategy_decision: DesignStrategyDecision | None = None
    designer_readiness_rubric: DesignerReadinessRubric | None = None
    seed_intake_audit: SeedIntakeAudit | None = None
    seed_acquisition_contract: SeedAcquisitionContract | None = None
    delivery_gate: DesignDeliveryGate | None = None
    draft_quality_rubric: DraftQualityRubric | None = None
    draft_candidates: list[DraftCandidate] = Field(default_factory=list)
    recommended_candidate_id: str | None = None
    branch_selection_policy: DraftBranchSelectionPolicy | None = None
    strategy_tradeoff_matrix: list[DraftBranchTradeoffRow] = Field(default_factory=list)
    spec_repair_preview: SpecRepairPreviewPacket | None = None
    spec_repair_decision: SpecRepairDecisionPacket | None = None
    spec_repair_auto_closure: SpecRepairAutoClosure | None = None
    draft_acceptance_gate: DraftAcceptanceGate | None = None
    acceptance_improvement_tasks: list[AcceptanceImprovementTask] = Field(default_factory=list)
    evidence_closeout_plan: EvidenceCloseoutPlan | None = None
    design_handoff_packet: DesignHandoffPacket | None = None
    design_traceability_manifest: DesignTraceabilityManifest | None = None
    design_constraint_ledger: DesignConstraintLedger | None = None
    prescription_change_set: PrescriptionChangeSet | None = None
    optimization_task_queue: list[OptimizationTask] = Field(default_factory=list)
    optimization_task_runs: list[OptimizationTaskRun] = Field(default_factory=list)


class OpticalSampleData(BaseModel):
    """Full per-design payload the /agent frontend consumes (types.ts mirror)."""

    paraxial: ParaxialSummary
    surfaces: list[SurfaceDescriptor]
    trace: RayTraceResult
    mtf: MTFResult
    layout_svg: LayoutSVG
    spot_diagram: SpotDiagramResult | None = None
    field_analysis: FieldAnalysisResult | None = None
    wavefront: WavefrontMetricsResult | None = None
    codev_optimization: CodeVRefinementComparison | None = None
    # Optional for backward-compat: pre-v2-02 consumers don't pass metadata.
    metadata: CaseMetadata | None = None
    # Present when a real design was selected for a specific user request.
    design_assessment: DesignAssessment | None = None
