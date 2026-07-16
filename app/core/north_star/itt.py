"""Default-deny intention-to-treat recomputation for north-star O-01a.

Recomputes raw ITT reports from a fully revalidated frozen preregistration plus externally
retained freeze-content and canonical-schema-template hash bindings. Exclusions are rejected by
default and never shrink frozen denominators; caller-reported terminals stay diagnostic-only.
Every report is UNRATIFIED and cannot promote any north-star gate.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from enum import StrEnum
from fractions import Fraction
from types import MappingProxyType
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .protocol import (
    Digest,
    FrozenPreregistration,
    OpaqueId,
    ProtocolViolation,
    _as_model,
    _assert_frozen_valid,
    _ordered_tuple_input,
    _reject_ambiguous_text,
    _strict_enum_input,
)


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RunTerminalState(StrEnum):
    DELIVERED = "delivered"
    BLOCKED = "blocked"
    DEGRADED = "degraded"
    FAILED = "failed"
    NON_CONVERGED = "non_converged"
    MISSING = "missing"
    UNDELIVERED = "undelivered"
    SATURATED = "saturated"
    COMPENSATION_FAILED = "compensation_failed"
    CONTAMINATED = "contaminated"


PIPELINE_NUMERATOR_VALUE: Mapping[RunTerminalState, int] = MappingProxyType({
    RunTerminalState.DELIVERED: 1,
    RunTerminalState.BLOCKED: 0,
    RunTerminalState.DEGRADED: 0,
    RunTerminalState.FAILED: 0,
    RunTerminalState.NON_CONVERGED: 0,
    RunTerminalState.MISSING: 0,
    RunTerminalState.UNDELIVERED: 0,
    RunTerminalState.SATURATED: 0,
    RunTerminalState.COMPENSATION_FAILED: 0,
    RunTerminalState.CONTAMINATED: 0,
})


class AttemptObservation(_ClosedModel):
    attempt_id: OpaqueId
    terminal_state: RunTerminalState

    @field_validator("attempt_id")
    @classmethod
    def validate_attempt_id(cls, value: str) -> str:
        return _reject_ambiguous_text(value, "attempt_id")

    @field_validator("terminal_state", mode="before")
    @classmethod
    def validate_terminal_state(cls, value: object) -> RunTerminalState:
        return RunTerminalState(
            _strict_enum_input(value, RunTerminalState, "terminal_state")
        )


class UnverifiedExclusionReference(_ClosedModel):
    record_hash: Digest
    scope_type: Literal["planned_candidate_slot", "planned_run_unit"]
    scope_id: OpaqueId
    preregistered_reason_code: OpaqueId

    @field_validator("scope_id", "preregistered_reason_code")
    @classmethod
    def validate_text(cls, value: str, info: Any) -> str:
        return _reject_ambiguous_text(value, info.field_name)


class IttObservations(_ClosedModel):
    ordered_attempt_observations: tuple[AttemptObservation, ...]
    unverified_exclusion_references: tuple[UnverifiedExclusionReference, ...] = ()

    @field_validator(
        "ordered_attempt_observations", "unverified_exclusion_references", mode="before"
    )
    @classmethod
    def validate_ordered_arrays(cls, value: object, info: Any) -> tuple[object, ...]:
        return _ordered_tuple_input(value, info.field_name)


class ClusterMembership(_ClosedModel):
    cluster_id: OpaqueId
    ordered_member_ids: tuple[OpaqueId, ...]


class ConfidenceInterval(_ClosedModel):
    method: None = None
    confidence_level: None = None
    lower: None = None
    upper: None = None
    availability: Literal["UNAVAILABLE_UNRATIFIED_CONFIDENCE_METHOD"] = (
        "UNAVAILABLE_UNRATIFIED_CONFIDENCE_METHOD"
    )


class RatioReport(_ClosedModel):
    metric_name: OpaqueId
    raw_numerator: Annotated[int, Field(strict=True, ge=0)]
    original_planned_denominator: Annotated[int, Field(strict=True, ge=0)]
    excluded_unit_count: Annotated[int, Field(strict=True, ge=0)]
    raw_denominator: Annotated[int, Field(strict=True, ge=0)]
    accepted_exclusion_record_hashes: tuple[Digest, ...] = ()
    rejected_exclusion_record_hashes: tuple[Digest, ...]
    dependence_clusters: tuple[ClusterMembership, ...]
    duplicate_clusters: tuple[ClusterMembership, ...]
    duplicate_cluster_evidence_status: Literal[
        "NOT_APPLICABLE", "UNAVAILABLE_PRELABEL_FREEZE_NOT_IMPLEMENTED"
    ]
    confidence_interval: ConfidenceInterval
    diagnostic_only: bool
    evidence_status: Literal[
        "UNRATIFIED_TYPED_ATTEMPT_OBSERVATIONS",
        "UNAVAILABLE_NO_VERIFIED_MACHINE_TERMINAL_EVIDENCE",
        "UNAVAILABLE_NO_VERIFIED_EXPERT_LABEL_ENVELOPES",
    ]

    @property
    def rate(self) -> Fraction | None:
        if self.raw_denominator == 0:
            return None
        return Fraction(self.raw_numerator, self.raw_denominator)


class UnverifiedRunTerminalDiagnostic(_ClosedModel):
    run_id: OpaqueId
    planned_candidate_slot_id: OpaqueId
    reported_terminal_state: RunTerminalState
    terminal_evidence_status: Literal[
        "UNAVAILABLE_NO_VERIFIED_MACHINE_TERMINAL_EVIDENCE"
    ]
    forced_not_passed_by_rejected_exclusion: bool
    ordered_attempt_ids: tuple[OpaqueId, ...]
    contaminated_attempt_ids: tuple[OpaqueId, ...]


class RejectedExclusion(_ClosedModel):
    record_hash: Digest
    scope_type: Literal["planned_candidate_slot", "planned_run_unit"]
    scope_id: OpaqueId
    reason: Literal[
        "UNREGISTERED_REASON_CODE",
        "CANONICAL_RECORD_AND_INDEPENDENT_VERIFICATION_UNAVAILABLE_IN_O01",
    ]


class ConditionalDiagnosticSelection(_ClosedModel):
    candidate_reported_delivery_aggregation_rule: Literal[
        "any_non_rejected_run_reported_delivered"
    ]
    ordered_selected_planned_candidate_slot_ids: tuple[OpaqueId, ...]
    rejected_run_exclusion_record_hashes_considered_during_selection: tuple[Digest, ...]
    rejected_candidate_exclusion_record_hashes_considered_during_selection: tuple[Digest, ...]


class IttReport(_ClosedModel):
    authority_status: Literal["UNRATIFIED"]
    confirmatory_authorized: Literal[False]
    preregistration_freeze_content_hash: Digest
    pipeline_delivery_rate: RatioReport
    unverified_pipeline_delivery_diagnostic: RatioReport
    expert_worth_reviewing_rate_itt: RatioReport
    expert_production_usable_rate_itt: RatioReport
    conditional_on_unverified_reported_delivery_diagnostics: tuple[
        RatioReport, RatioReport
    ]
    conditional_unverified_reported_delivery_selection: ConditionalDiagnosticSelection
    ordered_unverified_run_terminal_diagnostics: tuple[
        UnverifiedRunTerminalDiagnostic, ...
    ]
    retained_attempt_observations: tuple[AttemptObservation, ...]
    rejected_exclusions: tuple[RejectedExclusion, ...]


def _as_observations(value: IttObservations | dict[str, object]) -> IttObservations:
    return _as_model(IttObservations, value)


def _clusters(groups: dict[str, list[str]]) -> tuple[ClusterMembership, ...]:
    return tuple(
        ClusterMembership(cluster_id=cluster_id, ordered_member_ids=tuple(member_ids))
        for cluster_id, member_ids in groups.items()
    )


def _derive_unverified_run_terminal_diagnostics(
    frozen: FrozenPreregistration,
    observations: IttObservations,
    rejected_run_ids: set[str],
) -> tuple[UnverifiedRunTerminalDiagnostic, ...]:
    mapping = frozen.planned_identity_mapping_content
    attempts = mapping.ordered_permitted_attempt_identity_members
    actual_ids = tuple(item.attempt_id for item in observations.ordered_attempt_observations)
    expected_ids = tuple(item.attempt_id for item in attempts)
    if actual_ids != expected_ids:
        raise ProtocolViolation(
            "attempt observations must cover every permitted attempt exactly once in resolved order"
        )
    observation_by_id = {
        observation.attempt_id: observation
        for observation in observations.ordered_attempt_observations
    }
    if len(observation_by_id) != len(observations.ordered_attempt_observations):
        raise ProtocolViolation("attempt observations must be unique")

    attempts_by_run: dict[str, list[Any]] = defaultdict(list)
    for attempt in attempts:
        attempts_by_run[attempt.run_id].append(attempt)

    results: list[UnverifiedRunTerminalDiagnostic] = []
    for run in mapping.ordered_planned_run_unit_identity_members:
        run_attempts = attempts_by_run[run.run_id]
        states = [observation_by_id[attempt.attempt_id].terminal_state for attempt in run_attempts]
        delivered_indices = [
            index for index, state in enumerate(states) if state is RunTerminalState.DELIVERED
        ]
        if delivered_indices:
            first_delivered = delivered_indices[0]
            if any(
                state is not RunTerminalState.MISSING for state in states[first_delivered + 1 :]
            ):
                raise ProtocolViolation(
                    "a delivered run cannot have a later non-missing retry observation"
                )
            terminal = RunTerminalState.DELIVERED
        else:
            terminal = states[-1]
        results.append(
            UnverifiedRunTerminalDiagnostic(
                run_id=run.run_id,
                planned_candidate_slot_id=run.planned_candidate_slot_id,
                reported_terminal_state=terminal,
                terminal_evidence_status=(
                    "UNAVAILABLE_NO_VERIFIED_MACHINE_TERMINAL_EVIDENCE"
                ),
                forced_not_passed_by_rejected_exclusion=run.run_id in rejected_run_ids,
                ordered_attempt_ids=tuple(attempt.attempt_id for attempt in run_attempts),
                contaminated_attempt_ids=tuple(
                    attempt.attempt_id
                    for attempt, state in zip(run_attempts, states, strict=True)
                    if state is RunTerminalState.CONTAMINATED
                ),
            )
        )
    return tuple(results)


def _dependence_clusters_for_runs(frozen: FrozenPreregistration) -> tuple[ClusterMembership, ...]:
    mapping = frozen.planned_identity_mapping_content
    target_by_id = {target.target_id: target for target in mapping.ordered_target_identity_members}
    candidate_by_id = {
        candidate.planned_candidate_slot_id: candidate
        for candidate in mapping.ordered_candidate_slot_identity_members
    }
    groups: dict[str, list[str]] = {}
    for run in mapping.ordered_planned_run_unit_identity_members:
        candidate = candidate_by_id[run.planned_candidate_slot_id]
        seed_cluster_id = target_by_id[candidate.target_id].seed_cluster_id
        groups.setdefault(seed_cluster_id, []).append(run.run_id)
    return _clusters(groups)


def _dependence_clusters_for_candidates(
    frozen: FrozenPreregistration,
) -> tuple[ClusterMembership, ...]:
    mapping = frozen.planned_identity_mapping_content
    target_by_id = {target.target_id: target for target in mapping.ordered_target_identity_members}
    groups: dict[str, list[str]] = {}
    for candidate in mapping.ordered_candidate_slot_identity_members:
        seed_cluster_id = target_by_id[candidate.target_id].seed_cluster_id
        groups.setdefault(seed_cluster_id, []).append(candidate.planned_candidate_slot_id)
    return _clusters(groups)


def _filter_clusters(
    clusters: tuple[ClusterMembership, ...], included_member_ids: set[str]
) -> tuple[ClusterMembership, ...]:
    filtered: list[ClusterMembership] = []
    for cluster in clusters:
        members = tuple(
            member_id
            for member_id in cluster.ordered_member_ids
            if member_id in included_member_ids
        )
        if members:
            filtered.append(
                ClusterMembership(cluster_id=cluster.cluster_id, ordered_member_ids=members)
            )
    return tuple(filtered)


def _unavailable_confidence_interval() -> ConfidenceInterval:
    return ConfidenceInterval()


def _expert_report(
    metric_name: str,
    denominator: int,
    dependence_clusters: tuple[ClusterMembership, ...],
    rejected_exclusion_record_hashes: tuple[str, ...],
    *,
    diagnostic_only: bool,
) -> RatioReport:
    return RatioReport(
        metric_name=metric_name,
        raw_numerator=0,
        original_planned_denominator=denominator,
        excluded_unit_count=0,
        raw_denominator=denominator,
        rejected_exclusion_record_hashes=rejected_exclusion_record_hashes,
        dependence_clusters=dependence_clusters,
        duplicate_clusters=(),
        duplicate_cluster_evidence_status="UNAVAILABLE_PRELABEL_FREEZE_NOT_IMPLEMENTED",
        confidence_interval=_unavailable_confidence_interval(),
        diagnostic_only=diagnostic_only,
        evidence_status="UNAVAILABLE_NO_VERIFIED_EXPERT_LABEL_ENVELOPES",
    )


def _rejected_exclusions(
    frozen: FrozenPreregistration,
    observations: IttObservations,
) -> tuple[RejectedExclusion, ...]:
    mapping = frozen.planned_identity_mapping_content
    candidate_ids = {
        candidate.planned_candidate_slot_id
        for candidate in mapping.ordered_candidate_slot_identity_members
    }
    run_ids = {run.run_id for run in mapping.ordered_planned_run_unit_identity_members}
    seen_hashes: set[str] = set()
    rejected: list[RejectedExclusion] = []
    reason_allowlist = set(frozen.invalid_input_exclusion_reason_allowlist)
    for reference in observations.unverified_exclusion_references:
        if reference.record_hash in seen_hashes:
            raise ProtocolViolation("unverified exclusion references must be duplicate-free")
        seen_hashes.add(reference.record_hash)
        valid_scope = (
            reference.scope_id in candidate_ids
            if reference.scope_type == "planned_candidate_slot"
            else reference.scope_id in run_ids
        )
        if not valid_scope:
            raise ProtocolViolation("exclusion reference scope_id is not a planned population member")
        reason: Literal[
            "UNREGISTERED_REASON_CODE",
            "CANONICAL_RECORD_AND_INDEPENDENT_VERIFICATION_UNAVAILABLE_IN_O01",
        ] = (
            "UNREGISTERED_REASON_CODE"
            if reference.preregistered_reason_code not in reason_allowlist
            else "CANONICAL_RECORD_AND_INDEPENDENT_VERIFICATION_UNAVAILABLE_IN_O01"
        )
        rejected.append(
            RejectedExclusion(
                record_hash=reference.record_hash,
                scope_type=reference.scope_type,
                scope_id=reference.scope_id,
                reason=reason,
            )
        )
    return tuple(rejected)


def _require_exact_digest(value: str, label: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ProtocolViolation(f"{label} must be an exact lowercase SHA-256 digest")


def recompute_itt(
    frozen: FrozenPreregistration,
    value: IttObservations | dict[str, object],
    *,
    expected_preregistration_freeze_content_hash: str,
    expected_canonical_schema_template_hash: str,
) -> IttReport:
    """Recompute O-01 ITT counts against externally retained hash bindings.

    ``expected_canonical_schema_template_hash`` is a BINDING check only (O-01a scope): the
    frozen object must bind exactly the externally retained canonical schema template hash,
    mirroring the externally retained expected freeze-content hash check. Recomputing that
    hash from the exact final schema bytes under the out-of-band bootstrap suite, and the
    equality checks across governance anchor, protocol package, sealed manifest, and
    activation objects, land with X-00A/O-01c per the recorded execution split.
    """

    frozen = _assert_frozen_valid(frozen)
    _require_exact_digest(
        expected_preregistration_freeze_content_hash,
        "expected preregistration freeze content hash",
    )
    if (
        expected_preregistration_freeze_content_hash
        != frozen.preregistration_freeze_content_hash
    ):
        raise ProtocolViolation("externally expected preregistration freeze content hash mismatch")
    _require_exact_digest(
        expected_canonical_schema_template_hash,
        "expected canonical schema template hash",
    )
    if (
        expected_canonical_schema_template_hash
        != frozen.canonical_schema_template_hash
    ):
        raise ProtocolViolation("externally expected canonical schema template hash mismatch")
    observations = _as_observations(value)
    rejected_exclusions = _rejected_exclusions(frozen, observations)
    rejected_run_ids = {
        item.scope_id for item in rejected_exclusions if item.scope_type == "planned_run_unit"
    }
    rejected_candidate_ids = {
        item.scope_id
        for item in rejected_exclusions
        if item.scope_type == "planned_candidate_slot"
    }
    run_diagnostics = _derive_unverified_run_terminal_diagnostics(
        frozen, observations, rejected_run_ids
    )
    rejected_run_exclusion_hashes = tuple(
        item.record_hash for item in rejected_exclusions if item.scope_type == "planned_run_unit"
    )
    rejected_candidate_exclusion_hashes = tuple(
        item.record_hash
        for item in rejected_exclusions
        if item.scope_type == "planned_candidate_slot"
    )
    mapping = frozen.planned_identity_mapping_content
    run_dependence = _dependence_clusters_for_runs(frozen)
    candidate_dependence = _dependence_clusters_for_candidates(frozen)

    unverified_pipeline_numerator = sum(
        PIPELINE_NUMERATOR_VALUE[result.reported_terminal_state]
        for result in run_diagnostics
        if not result.forced_not_passed_by_rejected_exclusion
    )
    run_denominator = len(mapping.ordered_planned_run_unit_identity_members)
    candidate_denominator = len(mapping.ordered_candidate_slot_identity_members)
    pipeline = RatioReport(
        metric_name="pipeline_delivery_rate",
        raw_numerator=0,
        original_planned_denominator=run_denominator,
        excluded_unit_count=0,
        raw_denominator=run_denominator,
        rejected_exclusion_record_hashes=rejected_run_exclusion_hashes,
        dependence_clusters=run_dependence,
        duplicate_clusters=(),
        duplicate_cluster_evidence_status="NOT_APPLICABLE",
        confidence_interval=_unavailable_confidence_interval(),
        diagnostic_only=False,
        evidence_status="UNAVAILABLE_NO_VERIFIED_MACHINE_TERMINAL_EVIDENCE",
    )
    unverified_pipeline_diagnostic = RatioReport(
        metric_name="unverified_pipeline_delivery_diagnostic",
        raw_numerator=unverified_pipeline_numerator,
        original_planned_denominator=run_denominator,
        excluded_unit_count=0,
        raw_denominator=run_denominator,
        rejected_exclusion_record_hashes=rejected_run_exclusion_hashes,
        dependence_clusters=run_dependence,
        duplicate_clusters=(),
        duplicate_cluster_evidence_status="NOT_APPLICABLE",
        confidence_interval=_unavailable_confidence_interval(),
        diagnostic_only=True,
        evidence_status="UNRATIFIED_TYPED_ATTEMPT_OBSERVATIONS",
    )
    worth = _expert_report(
        "expert_worth_reviewing_rate_itt",
        candidate_denominator,
        candidate_dependence,
        rejected_candidate_exclusion_hashes,
        diagnostic_only=False,
    )
    production = _expert_report(
        "expert_production_usable_rate_itt",
        candidate_denominator,
        candidate_dependence,
        rejected_candidate_exclusion_hashes,
        diagnostic_only=False,
    )
    aggregation_rule = (
        frozen.allocation_rule.candidate_reported_delivery_aggregation_rule
    )
    if aggregation_rule != "any_non_rejected_run_reported_delivered":
        raise ProtocolViolation("unknown candidate reported-delivery aggregation rule")
    delivered_candidate_ids = {
        result.planned_candidate_slot_id
        for result in run_diagnostics
        if result.reported_terminal_state is RunTerminalState.DELIVERED
        and not result.forced_not_passed_by_rejected_exclusion
        and result.planned_candidate_slot_id not in rejected_candidate_ids
    }
    conditional_denominator = len(delivered_candidate_ids)
    conditional_dependence = _filter_clusters(candidate_dependence, delivered_candidate_ids)
    conditional_rejected_exclusion_hashes = tuple(
        item.record_hash for item in rejected_exclusions
    )
    conditional_selection = ConditionalDiagnosticSelection(
        candidate_reported_delivery_aggregation_rule=aggregation_rule,
        ordered_selected_planned_candidate_slot_ids=tuple(
            candidate.planned_candidate_slot_id
            for candidate in mapping.ordered_candidate_slot_identity_members
            if candidate.planned_candidate_slot_id in delivered_candidate_ids
        ),
        rejected_run_exclusion_record_hashes_considered_during_selection=(
            rejected_run_exclusion_hashes
        ),
        rejected_candidate_exclusion_record_hashes_considered_during_selection=(
            rejected_candidate_exclusion_hashes
        ),
    )
    conditional = (
        _expert_report(
            "expert_worth_reviewing_rate_conditional_on_unverified_reported_delivery",
            conditional_denominator,
            conditional_dependence,
            conditional_rejected_exclusion_hashes,
            diagnostic_only=True,
        ),
        _expert_report(
            "expert_production_usable_rate_conditional_on_unverified_reported_delivery",
            conditional_denominator,
            conditional_dependence,
            conditional_rejected_exclusion_hashes,
            diagnostic_only=True,
        ),
    )
    return IttReport(
        authority_status="UNRATIFIED",
        confirmatory_authorized=False,
        preregistration_freeze_content_hash=(
            frozen.preregistration_freeze_content_hash
        ),
        pipeline_delivery_rate=pipeline,
        unverified_pipeline_delivery_diagnostic=unverified_pipeline_diagnostic,
        expert_worth_reviewing_rate_itt=worth,
        expert_production_usable_rate_itt=production,
        conditional_on_unverified_reported_delivery_diagnostics=conditional,
        conditional_unverified_reported_delivery_selection=conditional_selection,
        ordered_unverified_run_terminal_diagnostics=run_diagnostics,
        retained_attempt_observations=observations.ordered_attempt_observations,
        rejected_exclusions=rejected_exclusions,
    )
