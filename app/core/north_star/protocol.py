"""Closed-world preregistration freeze kernel for north-star O-01a.

Validates exact public payloads, freezes planned identity mappings and verifier-recomputed
eligibility decisions, and binds them under domain-separated SHA-256 content hashes. Every
violation is rejected fail-closed as ProtocolViolation, every output is UNRATIFIED, and nothing
produced here can promote any north-star gate.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from enum import StrEnum
from typing import Annotated, Any, Literal, cast, get_args, get_origin

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

from ._canonical import domain_separated_hash, exact_content_hash

PLANNED_IDENTITY_MAPPING_DOMAIN = (
    "atelier.north-star.planned-identity-mapping-content.v0.1"
)
ELIGIBILITY_RULE_DOMAIN = "atelier.north-star.eligibility-rule-content.v0.1"
ELIGIBILITY_INPUT_DOMAIN = "atelier.north-star.eligibility-input-content.v0.1"
ELIGIBILITY_DECISION_SET_DOMAIN = (
    "atelier.north-star.eligibility-decision-set-content.v0.1"
)
PREREGISTRATION_FREEZE_DOMAIN = (
    "atelier.north-star.o01-preregistration-freeze-content.v0.1"
)
INITIAL_ATTEMPT_GENESIS_MARKER = "INITIAL_GENESIS"

Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
OpaqueId = Annotated[str, StringConstraints(min_length=1)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]


class ProtocolViolation(ValueError):
    """Raised when a closed-world preregistration invariant is violated."""


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _ordered_tuple_input(value: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be an ordered JSON array or tuple")
    return tuple(value)


def _strict_enum_input(value: object, enum_type: type[StrEnum], field_name: str) -> StrEnum:
    if isinstance(value, enum_type):
        return value
    if type(value) is not str:
        raise ValueError(f"{field_name} must be an exact string or {enum_type.__name__}")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a closed enum value") from exc


def _exact_model_storage(
    value: BaseModel, expected_type: type[BaseModel], path: str
) -> dict[str, object]:
    if type(value) is not expected_type:
        raise ProtocolViolation(
            f"{path} must preserve its exact runtime type: expected "
            f"{expected_type.__name__}"
        )
    try:
        storage = object.__getattribute__(value, "__dict__")
        extra_fields = object.__getattribute__(value, "__pydantic_extra__")
        private_fields = object.__getattribute__(value, "__pydantic_private__")
    except AttributeError as exc:
        raise ProtocolViolation(
            f"{path} must retain its required extra/private Pydantic slots"
        ) from exc
    if type(storage) is not dict:
        raise ProtocolViolation(f"{path} model storage must be an exact dict")
    expected_fields = tuple(expected_type.model_fields)
    actual_fields = tuple(dict.__iter__(storage))
    if dict.__len__(storage) != len(expected_fields):
        raise ProtocolViolation(f"{path} model fields must exactly match its declared schema")
    if any(type(field_name) is not str for field_name in actual_fields):
        raise ProtocolViolation(f"{path} model fields must be exact strings")
    actual_field_names = cast(tuple[str, ...], actual_fields)
    if (
        set(actual_field_names) != set(expected_fields)
        or extra_fields is not None
        or private_fields is not None
    ):
        raise ProtocolViolation(f"{path} model fields must exactly match its declared schema")
    return storage


def _assert_exact_annotated_value(value: object, annotation: object, path: str) -> None:
    origin = get_origin(annotation)
    if origin is Annotated:
        annotated_type, *_ = get_args(annotation)
        _assert_exact_annotated_value(value, annotated_type, path)
        return
    if origin is Literal:
        if not any(
            type(value) is type(allowed) and value == allowed
            for allowed in get_args(annotation)
        ):
            raise ProtocolViolation(
                f"{path} must preserve its exact runtime type and declared literal"
            )
        return
    if origin is tuple:
        if type(value) is not tuple:
            raise ProtocolViolation(
                f"{path} must preserve its exact runtime type as a tuple"
            )
        item_annotations = get_args(annotation)
        if len(item_annotations) == 2 and item_annotations[1] is Ellipsis:
            for index, item in enumerate(tuple.__iter__(value)):
                _assert_exact_annotated_value(
                    item, item_annotations[0], f"{path}[{index}]"
                )
            return
        if tuple.__len__(value) != len(item_annotations):
            raise ProtocolViolation(f"{path} must preserve its declared tuple length")
        for index, (item, item_annotation) in enumerate(
            zip(tuple.__iter__(value), item_annotations, strict=True)
        ):
            _assert_exact_annotated_value(item, item_annotation, f"{path}[{index}]")
        return
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        _assert_exact_model_graph(value, annotation, path)
        return
    if isinstance(annotation, type):
        if type(value) is not annotation:
            raise ProtocolViolation(f"{path} must preserve its exact runtime type")
        return
    raise ProtocolViolation(f"{path} uses an unsupported closed-world field annotation")


def _assert_exact_model_graph(
    value: object, expected_type: type[BaseModel], path: str
) -> None:
    if type(value) is not expected_type:
        raise ProtocolViolation(
            f"{path} must preserve its exact runtime type: expected "
            f"{expected_type.__name__}"
        )
    assert isinstance(value, BaseModel)
    storage = _exact_model_storage(value, expected_type, path)
    for field_name, field in expected_type.model_fields.items():
        _assert_exact_annotated_value(
            dict.__getitem__(storage, field_name),
            field.annotation,
            f"{path}.{field_name}",
        )


def _assert_exact_runtime_graph(original: object, validated: object, path: str) -> None:
    if type(original) is not type(validated):
        raise ProtocolViolation(f"{path} must preserve its exact runtime type")
    if isinstance(original, BaseModel):
        assert isinstance(validated, BaseModel)
        model_type = type(original)
        original_storage = _exact_model_storage(original, model_type, path)
        validated_storage = _exact_model_storage(validated, model_type, path)
        for field_name in model_type.model_fields:
            _assert_exact_runtime_graph(
                dict.__getitem__(original_storage, field_name),
                dict.__getitem__(validated_storage, field_name),
                f"{path}.{field_name}",
            )
        return
    if type(original) is dict:
        assert type(validated) is dict
        original_keys = tuple(dict.keys(original))
        validated_keys = tuple(dict.keys(validated))
        if original_keys != validated_keys:
            raise ProtocolViolation(f"{path} must preserve exact mapping keys and order")
        for key in original_keys:
            _assert_exact_runtime_graph(
                dict.__getitem__(original, key),
                dict.__getitem__(validated, key),
                f"{path}[{key!r}]",
            )
        return
    if type(original) is list:
        assert type(validated) is list
        original_list = cast(list[object], original)
        validated_list = cast(list[object], validated)
        if list.__len__(original_list) != list.__len__(validated_list):
            raise ProtocolViolation(f"{path} must preserve exact ordered length")
        for index, (original_item, validated_item) in enumerate(
            zip(
                list.__iter__(original_list),
                list.__iter__(validated_list),
                strict=True,
            )
        ):
            _assert_exact_runtime_graph(
                original_item, validated_item, f"{path}[{index}]"
            )
        return
    if type(original) is tuple:
        assert type(validated) is tuple
        original_tuple = cast(tuple[object, ...], original)
        validated_tuple = cast(tuple[object, ...], validated)
        if tuple.__len__(original_tuple) != tuple.__len__(validated_tuple):
            raise ProtocolViolation(f"{path} must preserve exact ordered length")
        for index, (original_item, validated_item) in enumerate(
            zip(
                tuple.__iter__(original_tuple),
                tuple.__iter__(validated_tuple),
                strict=True,
            )
        ):
            _assert_exact_runtime_graph(
                original_item, validated_item, f"{path}[{index}]"
            )
        return
    if original != validated:
        raise ProtocolViolation(f"{path} must preserve its exact value")


def _snapshot_strict_public_payload(
    value: object,
    path: str = "input",
    active_container_ids: set[int] | None = None,
) -> object:
    container_type = type(value)
    if container_type is dict or container_type is list or container_type is tuple:
        active_ids = active_container_ids if active_container_ids is not None else set()
        container_id = id(value)
        if container_id in active_ids:
            raise ProtocolViolation(f"{path} cannot contain a cyclic raw container")
        active_ids.add(container_id)
        try:
            if container_type is dict:
                snapshot: dict[str, object] = {}
                raw_mapping = cast(dict[object, object], value)
                for key, item in dict.items(raw_mapping):
                    if type(key) is not str:
                        raise ProtocolViolation(f"{path} mapping keys must be exact strings")
                    snapshot[key] = _snapshot_strict_public_payload(
                        item, f"{path}.{key}", active_ids
                    )
                return snapshot
            if container_type is list:
                raw_list = cast(list[object], value)
                return [
                    _snapshot_strict_public_payload(
                        item, f"{path}[{index}]", active_ids
                    )
                    for index, item in enumerate(list.__iter__(raw_list))
                ]
            raw_tuple = cast(tuple[object, ...], value)
            return tuple(
                _snapshot_strict_public_payload(
                    item, f"{path}[{index}]", active_ids
                )
                for index, item in enumerate(tuple.__iter__(raw_tuple))
            )
        finally:
            active_ids.remove(container_id)
    if (
        value is None
        or container_type is str
        or container_type is int
        or container_type is float
        or container_type is bool
    ):
        return value
    raise ProtocolViolation(
        f"{path} must contain only exact JSON primitives, dicts, lists, or tuples"
    )


def _reject_ambiguous_text(value: str, field_name: str) -> str:
    if not value or value != value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError(f"{field_name} must be a nonblank opaque string without edge whitespace")
    return value


class AttemptKind(StrEnum):
    INITIAL = "INITIAL"
    RETRY = "RETRY"


class EligibilityDecision(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"


class TargetIdentityMember(_ClosedModel):
    target_id: OpaqueId
    seed_cluster_id: OpaqueId
    patent_family_id: OpaqueId
    immutable_source_record_hash: Digest
    draw_ordinal: NonNegativeInt

    @field_validator("target_id", "seed_cluster_id", "patent_family_id")
    @classmethod
    def validate_ids(cls, value: str, info: Any) -> str:
        return _reject_ambiguous_text(value, info.field_name)


class CandidateSlotIdentityMember(_ClosedModel):
    planned_candidate_slot_id: OpaqueId
    target_id: OpaqueId
    seed_cluster_id: OpaqueId
    patent_family_id: OpaqueId
    candidate_slot_ordinal: NonNegativeInt

    @field_validator(
        "planned_candidate_slot_id", "target_id", "seed_cluster_id", "patent_family_id"
    )
    @classmethod
    def validate_ids(cls, value: str, info: Any) -> str:
        return _reject_ambiguous_text(value, info.field_name)


class PlannedRunUnitIdentityMember(_ClosedModel):
    run_id: OpaqueId
    planned_candidate_slot_id: OpaqueId
    run_ordinal: NonNegativeInt

    @field_validator("run_id", "planned_candidate_slot_id")
    @classmethod
    def validate_ids(cls, value: str, info: Any) -> str:
        return _reject_ambiguous_text(value, info.field_name)


class PermittedAttemptIdentityMember(_ClosedModel):
    attempt_id: OpaqueId
    run_id: OpaqueId
    attempt_sequence: NonNegativeInt
    attempt_kind: AttemptKind
    predecessor_attempt_id_or_initial_genesis_marker: OpaqueId

    @field_validator(
        "attempt_id", "run_id", "predecessor_attempt_id_or_initial_genesis_marker"
    )
    @classmethod
    def validate_ids(cls, value: str, info: Any) -> str:
        return _reject_ambiguous_text(value, info.field_name)

    @field_validator("attempt_kind", mode="before")
    @classmethod
    def validate_attempt_kind(cls, value: object) -> AttemptKind:
        return AttemptKind(_strict_enum_input(value, AttemptKind, "attempt_kind"))


class UniformAllocationRule(_ClosedModel):
    planned_candidate_slots_per_target: PositiveInt
    planned_run_units_per_candidate: PositiveInt
    permitted_retry_attempts_per_run: NonNegativeInt
    retry_aggregation_rule: Literal["first_delivered_else_last_permitted_attempt"]
    candidate_reported_delivery_aggregation_rule: Literal[
        "any_non_rejected_run_reported_delivered"
    ]


class SourceHashEligibilityRule(_ClosedModel):
    rule_kind: Literal["immutable_source_record_hash_allowlist"]
    eligible_immutable_source_record_hashes: tuple[Digest, ...]

    @field_validator("eligible_immutable_source_record_hashes", mode="before")
    @classmethod
    def validate_ordered_hash_array(cls, value: object) -> tuple[object, ...]:
        return _ordered_tuple_input(value, "eligible_immutable_source_record_hashes")

    @field_validator("eligible_immutable_source_record_hashes")
    @classmethod
    def validate_unique_hashes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("eligible source-record hashes must be unique")
        return value


class PreregistrationSpec(_ClosedModel):
    schema_version: OpaqueId
    north_star_goal_instance_id: OpaqueId
    ratification_instance_id: OpaqueId
    confirmatory_batch_id: OpaqueId
    draw_event_id: OpaqueId
    protocol_package_hash: Digest
    protocol_authority_signature_set_hash: Digest
    canonical_schema_template_hash: Digest
    sampling_frame_commitment_hash: Digest
    sampling_source_snapshot_hash: Digest
    minimum_claim_envelope_hash: Digest
    allocation_rule: UniformAllocationRule
    eligibility_rule: SourceHashEligibilityRule
    eligibility_evaluated_at: OpaqueId
    invalid_input_exclusion_reason_allowlist: tuple[OpaqueId, ...]
    ordered_target_identity_members: tuple[TargetIdentityMember, ...]
    ordered_candidate_slot_identity_members: tuple[CandidateSlotIdentityMember, ...]
    ordered_planned_run_unit_identity_members: tuple[PlannedRunUnitIdentityMember, ...]
    ordered_permitted_attempt_identity_members: tuple[PermittedAttemptIdentityMember, ...]

    @field_validator(
        "schema_version",
        "north_star_goal_instance_id",
        "ratification_instance_id",
        "confirmatory_batch_id",
        "draw_event_id",
        "eligibility_evaluated_at",
    )
    @classmethod
    def validate_text(cls, value: str, info: Any) -> str:
        return _reject_ambiguous_text(value, info.field_name)

    @field_validator("invalid_input_exclusion_reason_allowlist")
    @classmethod
    def validate_reason_allowlist(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for reason in value:
            _reject_ambiguous_text(reason, "invalid_input_exclusion_reason_allowlist")
        if len(set(value)) != len(value):
            raise ValueError("invalid-input reason allowlist must be duplicate-free")
        return value

    @field_validator(
        "invalid_input_exclusion_reason_allowlist",
        "ordered_target_identity_members",
        "ordered_candidate_slot_identity_members",
        "ordered_planned_run_unit_identity_members",
        "ordered_permitted_attempt_identity_members",
        mode="before",
    )
    @classmethod
    def validate_ordered_arrays(cls, value: object, info: Any) -> tuple[object, ...]:
        return _ordered_tuple_input(value, info.field_name)


class PlannedIdentityMappingContent(_ClosedModel):
    domain_tag: Literal["atelier.north-star.planned-identity-mapping-content.v0.1"]
    schema_version: OpaqueId
    north_star_goal_instance_id: OpaqueId
    ratification_instance_id: OpaqueId
    confirmatory_batch_id: OpaqueId
    draw_event_id: OpaqueId
    protocol_package_hash: Digest
    protocol_authority_signature_set_hash: Digest
    target_member_count: PositiveInt
    candidate_slot_member_count: PositiveInt
    planned_run_unit_member_count: PositiveInt
    permitted_attempt_member_count: PositiveInt
    ordered_target_identity_members: tuple[TargetIdentityMember, ...]
    ordered_candidate_slot_identity_members: tuple[CandidateSlotIdentityMember, ...]
    ordered_planned_run_unit_identity_members: tuple[PlannedRunUnitIdentityMember, ...]
    ordered_permitted_attempt_identity_members: tuple[PermittedAttemptIdentityMember, ...]


class EligibilityInputContent(_ClosedModel):
    domain_tag: Literal["atelier.north-star.eligibility-input-content.v0.1"]
    target_id: OpaqueId
    immutable_source_record_hash: Digest
    sampling_source_snapshot_hash: Digest
    minimum_claim_envelope_hash: Digest
    eligibility_rule_hash: Digest


class EligibilityDecisionMember(_ClosedModel):
    target_id: OpaqueId
    eligibility_rule_hash: Digest
    eligibility_input_content: EligibilityInputContent
    eligibility_input_content_hash: Digest
    decision: EligibilityDecision
    evaluated_at: OpaqueId

    @field_validator("decision", mode="before")
    @classmethod
    def validate_decision(cls, value: object) -> EligibilityDecision:
        return EligibilityDecision(_strict_enum_input(value, EligibilityDecision, "decision"))


class EligibilityDecisionSetContent(_ClosedModel):
    domain_tag: Literal["atelier.north-star.eligibility-decision-set-content.v0.1"]
    schema_version: OpaqueId
    north_star_goal_instance_id: OpaqueId
    ratification_instance_id: OpaqueId
    confirmatory_batch_id: OpaqueId
    draw_event_id: OpaqueId
    protocol_package_hash: Digest
    protocol_authority_signature_set_hash: Digest
    planned_identity_mapping_content_hash: Digest
    eligibility_rule_hash: Digest
    eligibility_decision_count: PositiveInt
    ordered_eligibility_decision_members: tuple[EligibilityDecisionMember, ...]


class PreregistrationFreezeContent(_ClosedModel):
    domain_tag: Literal["atelier.north-star.o01-preregistration-freeze-content.v0.1"]
    canonical_schema_template_hash: Digest
    sampling_frame_commitment_hash: Digest
    sampling_source_snapshot_hash: Digest
    minimum_claim_envelope_hash: Digest
    allocation_rule: UniformAllocationRule
    eligibility_rule: SourceHashEligibilityRule
    eligibility_rule_hash: Digest
    eligibility_evaluated_at: OpaqueId
    invalid_input_exclusion_reason_allowlist: tuple[OpaqueId, ...]
    planned_identity_mapping_content: PlannedIdentityMappingContent
    planned_identity_mapping_content_hash: Digest
    eligibility_decision_set_content: EligibilityDecisionSetContent
    eligibility_decision_set_content_hash: Digest

    @field_validator("eligibility_evaluated_at")
    @classmethod
    def validate_evaluated_at(cls, value: str) -> str:
        return _reject_ambiguous_text(value, "eligibility_evaluated_at")

    @field_validator("invalid_input_exclusion_reason_allowlist")
    @classmethod
    def validate_reason_allowlist(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for reason in value:
            _reject_ambiguous_text(reason, "invalid_input_exclusion_reason_allowlist")
        if len(set(value)) != len(value):
            raise ValueError("invalid-input exclusion reason allowlist must be duplicate-free")
        return value


class FrozenPreregistration(_ClosedModel):
    authority_status: Literal["UNRATIFIED"]
    confirmatory_authorized: Literal[False]
    preregistration_freeze_content: PreregistrationFreezeContent
    preregistration_freeze_content_hash: Digest

    @property
    def canonical_schema_template_hash(self) -> str:
        return self.preregistration_freeze_content.canonical_schema_template_hash

    @property
    def sampling_frame_commitment_hash(self) -> str:
        return self.preregistration_freeze_content.sampling_frame_commitment_hash

    @property
    def sampling_source_snapshot_hash(self) -> str:
        return self.preregistration_freeze_content.sampling_source_snapshot_hash

    @property
    def minimum_claim_envelope_hash(self) -> str:
        return self.preregistration_freeze_content.minimum_claim_envelope_hash

    @property
    def allocation_rule(self) -> UniformAllocationRule:
        return self.preregistration_freeze_content.allocation_rule

    @property
    def eligibility_rule(self) -> SourceHashEligibilityRule:
        return self.preregistration_freeze_content.eligibility_rule

    @property
    def eligibility_rule_hash(self) -> str:
        return self.preregistration_freeze_content.eligibility_rule_hash

    @property
    def eligibility_evaluated_at(self) -> str:
        return self.preregistration_freeze_content.eligibility_evaluated_at

    @property
    def invalid_input_exclusion_reason_allowlist(self) -> tuple[str, ...]:
        return self.preregistration_freeze_content.invalid_input_exclusion_reason_allowlist

    @property
    def planned_identity_mapping_content(self) -> PlannedIdentityMappingContent:
        return self.preregistration_freeze_content.planned_identity_mapping_content

    @property
    def planned_identity_mapping_content_hash(self) -> str:
        return self.preregistration_freeze_content.planned_identity_mapping_content_hash

    @property
    def eligibility_decision_set_content(self) -> EligibilityDecisionSetContent:
        return self.preregistration_freeze_content.eligibility_decision_set_content

    @property
    def eligibility_decision_set_content_hash(self) -> str:
        return self.preregistration_freeze_content.eligibility_decision_set_content_hash


@contextmanager
def _translated_protocol_errors() -> Iterator[None]:
    """Translate every construction/validation failure into the uniform rejection channel."""

    try:
        yield
    except ProtocolViolation:
        raise
    except RecursionError as exc:
        raise ProtocolViolation("input nesting exceeds supported recursion depth") from exc
    except (ValidationError, TypeError, ValueError) as exc:
        raise ProtocolViolation(str(exc)) from exc


def _as_model[ModelT: BaseModel](
    model_type: type[ModelT], value: BaseModel | Mapping[str, object]
) -> ModelT:
    with _translated_protocol_errors():
        source_model: BaseModel | None = None
        input_type = type(value)
        if input_type is model_type:
            _assert_exact_model_graph(value, model_type, model_type.__name__)
            assert isinstance(value, BaseModel)
            source_model = value
            payload: object = value.model_dump(mode="python")
        elif input_type is not dict:
            raise ProtocolViolation(
                f"input must be exactly {model_type.__name__} or an exact built-in "
                "dict containing exact JSON primitives"
            )
        else:
            payload = _snapshot_strict_public_payload(value)
        validated = model_type.model_validate(payload, strict=True)
        if source_model is not None:
            _assert_exact_runtime_graph(source_model, validated, model_type.__name__)
    return validated


def _require_unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ProtocolViolation(f"{label} must be unique")


def _validate_mapping_members(
    mapping: PlannedIdentityMappingContent,
    allocation: UniformAllocationRule,
) -> None:
    targets = mapping.ordered_target_identity_members
    candidates = mapping.ordered_candidate_slot_identity_members
    runs = mapping.ordered_planned_run_unit_identity_members
    attempts = mapping.ordered_permitted_attempt_identity_members

    expected_candidate_count = len(targets) * allocation.planned_candidate_slots_per_target
    expected_run_count = expected_candidate_count * allocation.planned_run_units_per_candidate
    attempts_per_run = allocation.permitted_retry_attempts_per_run + 1
    expected_attempt_count = expected_run_count * attempts_per_run
    declared = (
        mapping.target_member_count,
        mapping.candidate_slot_member_count,
        mapping.planned_run_unit_member_count,
        mapping.permitted_attempt_member_count,
    )
    actual = (len(targets), len(candidates), len(runs), len(attempts))
    if declared != actual:
        raise ProtocolViolation("declared mapping counts must equal exact member-array lengths")
    # Nonemptiness needs no separate guard here: declared counts are PositiveInt model fields,
    # so after the declared == actual check every member array is provably nonempty. The public
    # nonempty rejection lives in freeze_preregistration, before any content model is built.
    if actual[1:] != (expected_candidate_count, expected_run_count, expected_attempt_count):
        raise ProtocolViolation("mapping member counts do not match the frozen allocation rule")

    primary_ids = [member.target_id for member in targets]
    primary_ids.extend(member.planned_candidate_slot_id for member in candidates)
    primary_ids.extend(member.run_id for member in runs)
    primary_ids.extend(member.attempt_id for member in attempts)
    _require_unique(primary_ids, "target/candidate-slot/run/attempt primary IDs")
    if INITIAL_ATTEMPT_GENESIS_MARKER in primary_ids:
        raise ProtocolViolation("INITIAL_GENESIS is a reserved marker and cannot be a primary ID")

    for expected_ordinal, target in enumerate(targets):
        if target.draw_ordinal != expected_ordinal:
            raise ProtocolViolation("targets must be in contiguous draw_ordinal order")

    candidate_index = 0
    for target in targets:
        for expected_ordinal in range(allocation.planned_candidate_slots_per_target):
            candidate = candidates[candidate_index]
            if candidate.candidate_slot_ordinal != expected_ordinal:
                raise ProtocolViolation(
                    "candidate slots must be contiguous within resolved target order"
                )
            if (
                candidate.target_id,
                candidate.seed_cluster_id,
                candidate.patent_family_id,
            ) != (target.target_id, target.seed_cluster_id, target.patent_family_id):
                raise ProtocolViolation(
                    "candidate slot target/seed-cluster/patent-family parentage is inconsistent"
                )
            candidate_index += 1

    run_index = 0
    for candidate in candidates:
        for expected_ordinal in range(allocation.planned_run_units_per_candidate):
            run = runs[run_index]
            if (
                run.planned_candidate_slot_id != candidate.planned_candidate_slot_id
                or run.run_ordinal != expected_ordinal
            ):
                raise ProtocolViolation(
                    "planned runs must be contiguous within resolved candidate-slot order"
                )
            run_index += 1

    attempt_index = 0
    for run in runs:
        previous_attempt_id = INITIAL_ATTEMPT_GENESIS_MARKER
        for expected_sequence in range(attempts_per_run):
            attempt = attempts[attempt_index]
            expected_kind = AttemptKind.INITIAL if expected_sequence == 0 else AttemptKind.RETRY
            if (
                attempt.run_id != run.run_id
                or attempt.attempt_sequence != expected_sequence
                or attempt.attempt_kind != expected_kind
                or attempt.predecessor_attempt_id_or_initial_genesis_marker
                != previous_attempt_id
            ):
                raise ProtocolViolation(
                    "attempts must be contiguous, correctly typed, and predecessor-bound "
                    "within resolved run order"
                )
            previous_attempt_id = attempt.attempt_id
            attempt_index += 1


def _mapping_from_spec(spec: PreregistrationSpec) -> PlannedIdentityMappingContent:
    return PlannedIdentityMappingContent(
        domain_tag="atelier.north-star.planned-identity-mapping-content.v0.1",
        schema_version=spec.schema_version,
        north_star_goal_instance_id=spec.north_star_goal_instance_id,
        ratification_instance_id=spec.ratification_instance_id,
        confirmatory_batch_id=spec.confirmatory_batch_id,
        draw_event_id=spec.draw_event_id,
        protocol_package_hash=spec.protocol_package_hash,
        protocol_authority_signature_set_hash=spec.protocol_authority_signature_set_hash,
        target_member_count=len(spec.ordered_target_identity_members),
        candidate_slot_member_count=len(spec.ordered_candidate_slot_identity_members),
        planned_run_unit_member_count=len(spec.ordered_planned_run_unit_identity_members),
        permitted_attempt_member_count=len(spec.ordered_permitted_attempt_identity_members),
        ordered_target_identity_members=spec.ordered_target_identity_members,
        ordered_candidate_slot_identity_members=spec.ordered_candidate_slot_identity_members,
        ordered_planned_run_unit_identity_members=spec.ordered_planned_run_unit_identity_members,
        ordered_permitted_attempt_identity_members=spec.ordered_permitted_attempt_identity_members,
    )


def _eligibility_decisions(
    *,
    mapping: PlannedIdentityMappingContent,
    mapping_hash: str,
    sampling_source_snapshot_hash: str,
    minimum_claim_envelope_hash: str,
    eligibility_rule: SourceHashEligibilityRule,
    evaluated_at: str,
) -> tuple[str, EligibilityDecisionSetContent]:
    rule_payload = eligibility_rule.model_dump(mode="json")
    rule_hash = domain_separated_hash(ELIGIBILITY_RULE_DOMAIN, rule_payload)
    eligible_sources = set(eligibility_rule.eligible_immutable_source_record_hashes)
    members: list[EligibilityDecisionMember] = []
    for target in mapping.ordered_target_identity_members:
        input_content = EligibilityInputContent(
            domain_tag="atelier.north-star.eligibility-input-content.v0.1",
            target_id=target.target_id,
            immutable_source_record_hash=target.immutable_source_record_hash,
            sampling_source_snapshot_hash=sampling_source_snapshot_hash,
            minimum_claim_envelope_hash=minimum_claim_envelope_hash,
            eligibility_rule_hash=rule_hash,
        )
        input_hash = exact_content_hash(
            ELIGIBILITY_INPUT_DOMAIN, input_content.model_dump(mode="json")
        )
        members.append(
            EligibilityDecisionMember(
                target_id=target.target_id,
                eligibility_rule_hash=rule_hash,
                eligibility_input_content=input_content,
                eligibility_input_content_hash=input_hash,
                decision=(
                    EligibilityDecision.ELIGIBLE
                    if target.immutable_source_record_hash in eligible_sources
                    else EligibilityDecision.INELIGIBLE
                ),
                evaluated_at=evaluated_at,
            )
        )
    content = EligibilityDecisionSetContent(
        domain_tag="atelier.north-star.eligibility-decision-set-content.v0.1",
        schema_version=mapping.schema_version,
        north_star_goal_instance_id=mapping.north_star_goal_instance_id,
        ratification_instance_id=mapping.ratification_instance_id,
        confirmatory_batch_id=mapping.confirmatory_batch_id,
        draw_event_id=mapping.draw_event_id,
        protocol_package_hash=mapping.protocol_package_hash,
        protocol_authority_signature_set_hash=mapping.protocol_authority_signature_set_hash,
        planned_identity_mapping_content_hash=mapping_hash,
        eligibility_rule_hash=rule_hash,
        eligibility_decision_count=len(members),
        ordered_eligibility_decision_members=tuple(members),
    )
    return rule_hash, content


def freeze_preregistration(
    value: PreregistrationSpec | dict[str, object],
) -> FrozenPreregistration:
    """Freeze exact mapping and verifier-derived eligibility content.

    The returned object is deliberately UNRATIFIED. It is an offline protocol artifact, not a
    governance signature or permission to start confirmatory work.
    """

    spec = _as_model(PreregistrationSpec, value)
    assert isinstance(spec, PreregistrationSpec)
    for member_field_name in (
        "ordered_target_identity_members",
        "ordered_candidate_slot_identity_members",
        "ordered_planned_run_unit_identity_members",
        "ordered_permitted_attempt_identity_members",
    ):
        if not getattr(spec, member_field_name):
            raise ProtocolViolation(f"{member_field_name} must be nonempty")
    with _translated_protocol_errors():
        mapping = _mapping_from_spec(spec)
        _validate_mapping_members(mapping, spec.allocation_rule)
        mapping_hash = exact_content_hash(
            PLANNED_IDENTITY_MAPPING_DOMAIN, mapping.model_dump(mode="json")
        )
        rule_hash, decisions = _eligibility_decisions(
            mapping=mapping,
            mapping_hash=mapping_hash,
            sampling_source_snapshot_hash=spec.sampling_source_snapshot_hash,
            minimum_claim_envelope_hash=spec.minimum_claim_envelope_hash,
            eligibility_rule=spec.eligibility_rule,
            evaluated_at=spec.eligibility_evaluated_at,
        )
        decision_set_hash = exact_content_hash(
            ELIGIBILITY_DECISION_SET_DOMAIN, decisions.model_dump(mode="json")
        )
        freeze_content = PreregistrationFreezeContent(
            domain_tag="atelier.north-star.o01-preregistration-freeze-content.v0.1",
            canonical_schema_template_hash=spec.canonical_schema_template_hash,
            sampling_frame_commitment_hash=spec.sampling_frame_commitment_hash,
            sampling_source_snapshot_hash=spec.sampling_source_snapshot_hash,
            minimum_claim_envelope_hash=spec.minimum_claim_envelope_hash,
            allocation_rule=spec.allocation_rule,
            eligibility_rule=spec.eligibility_rule,
            eligibility_rule_hash=rule_hash,
            eligibility_evaluated_at=spec.eligibility_evaluated_at,
            invalid_input_exclusion_reason_allowlist=spec.invalid_input_exclusion_reason_allowlist,
            planned_identity_mapping_content=mapping,
            planned_identity_mapping_content_hash=mapping_hash,
            eligibility_decision_set_content=decisions,
            eligibility_decision_set_content_hash=decision_set_hash,
        )
        freeze_content_hash = exact_content_hash(
            PREREGISTRATION_FREEZE_DOMAIN, freeze_content.model_dump(mode="json")
        )
        frozen = FrozenPreregistration(
            authority_status="UNRATIFIED",
            confirmatory_authorized=False,
            preregistration_freeze_content=freeze_content,
            preregistration_freeze_content_hash=freeze_content_hash,
        )
    _assert_frozen_valid(frozen)
    return frozen


def _assert_frozen_valid(value: FrozenPreregistration) -> FrozenPreregistration:
    if type(value) is not FrozenPreregistration:
        raise ProtocolViolation("frozen input must be exactly FrozenPreregistration")
    value = _as_model(FrozenPreregistration, value)
    freeze_content = value.preregistration_freeze_content
    expected_freeze_hash = exact_content_hash(
        PREREGISTRATION_FREEZE_DOMAIN, freeze_content.model_dump(mode="json")
    )
    if value.preregistration_freeze_content_hash != expected_freeze_hash:
        raise ProtocolViolation("preregistration freeze content hash mismatch")
    mapping = value.planned_identity_mapping_content
    _validate_mapping_members(mapping, value.allocation_rule)
    expected_mapping_hash = exact_content_hash(
        PLANNED_IDENTITY_MAPPING_DOMAIN, mapping.model_dump(mode="json")
    )
    if value.planned_identity_mapping_content_hash != expected_mapping_hash:
        raise ProtocolViolation("planned identity mapping content hash mismatch")

    decisions = value.eligibility_decision_set_content
    context = (
        "schema_version",
        "north_star_goal_instance_id",
        "ratification_instance_id",
        "confirmatory_batch_id",
        "draw_event_id",
        "protocol_package_hash",
        "protocol_authority_signature_set_hash",
    )
    if any(getattr(mapping, field) != getattr(decisions, field) for field in context):
        raise ProtocolViolation("mapping and eligibility decision-set context must match")
    if decisions.planned_identity_mapping_content_hash != expected_mapping_hash:
        raise ProtocolViolation("eligibility decision set must bind the exact mapping hash")
    expected_rule_hash = domain_separated_hash(
        ELIGIBILITY_RULE_DOMAIN, value.eligibility_rule.model_dump(mode="json")
    )
    if value.eligibility_rule_hash != expected_rule_hash:
        raise ProtocolViolation("eligibility rule hash mismatch")
    if decisions.eligibility_rule_hash != expected_rule_hash:
        raise ProtocolViolation("decision set eligibility rule hash mismatch")

    members = decisions.ordered_eligibility_decision_members
    targets = mapping.ordered_target_identity_members
    if decisions.eligibility_decision_count != len(members) or len(members) != len(targets):
        raise ProtocolViolation("eligibility must contain exactly one decision per target")
    eligible_sources = set(value.eligibility_rule.eligible_immutable_source_record_hashes)
    for target, member in zip(targets, members, strict=True):
        expected_input = EligibilityInputContent(
            domain_tag="atelier.north-star.eligibility-input-content.v0.1",
            target_id=target.target_id,
            immutable_source_record_hash=target.immutable_source_record_hash,
            sampling_source_snapshot_hash=value.sampling_source_snapshot_hash,
            minimum_claim_envelope_hash=value.minimum_claim_envelope_hash,
            eligibility_rule_hash=expected_rule_hash,
        )
        expected_input_hash = exact_content_hash(
            ELIGIBILITY_INPUT_DOMAIN, expected_input.model_dump(mode="json")
        )
        expected_decision = (
            EligibilityDecision.ELIGIBLE
            if target.immutable_source_record_hash in eligible_sources
            else EligibilityDecision.INELIGIBLE
        )
        if (
            member.target_id != target.target_id
            or member.eligibility_rule_hash != expected_rule_hash
            or member.eligibility_input_content != expected_input
            or member.eligibility_input_content_hash != expected_input_hash
            or member.decision != expected_decision
            or member.evaluated_at != value.eligibility_evaluated_at
        ):
            raise ProtocolViolation(
                "eligibility member must be ordered and recomputed from its exact inline input"
            )
    expected_decision_set_hash = exact_content_hash(
        ELIGIBILITY_DECISION_SET_DOMAIN, decisions.model_dump(mode="json")
    )
    if value.eligibility_decision_set_content_hash != expected_decision_set_hash:
        raise ProtocolViolation("eligibility decision-set content hash mismatch")

    reasons = value.invalid_input_exclusion_reason_allowlist
    if len(reasons) != len(set(reasons)):
        raise ProtocolViolation("invalid-input exclusion reason allowlist must be unique")
    return value
