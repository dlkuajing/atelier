from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from fractions import Fraction

import pytest

from app.core.north_star import (
    ELIGIBILITY_DECISION_SET_DOMAIN,
    PIPELINE_NUMERATOR_VALUE,
    PREREGISTRATION_FREEZE_DOMAIN,
    AttemptObservation,
    FrozenPreregistration,
    IttObservations,
    IttReport,
    PreregistrationFreezeContent,
    ProtocolViolation,
    RunTerminalState,
    freeze_preregistration,
    recompute_itt,
)


def _digest(number: int) -> str:
    return f"{number:064x}"


def _spec(
    *, retries_per_run: int = 1, runs_per_candidate: int = 1
) -> dict[str, object]:
    targets = [
        {
            "target_id": "target-z",
            "seed_cluster_id": "seed-shared",
            "patent_family_id": "patent-z",
            "immutable_source_record_hash": _digest(20),
            "draw_ordinal": 0,
        },
        {
            "target_id": "target-a",
            "seed_cluster_id": "seed-shared",
            "patent_family_id": "patent-a",
            "immutable_source_record_hash": _digest(21),
            "draw_ordinal": 1,
        },
    ]
    candidates: list[dict[str, object]] = []
    runs: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    attempt_index = 0
    for candidate_index, target in enumerate(targets):
        for slot_ordinal in range(2):
            slot_id = f"slot-{candidate_index * 2 + slot_ordinal:02d}"
            candidates.append(
                {
                    "planned_candidate_slot_id": slot_id,
                    "target_id": target["target_id"],
                    "seed_cluster_id": target["seed_cluster_id"],
                    "patent_family_id": target["patent_family_id"],
                    "candidate_slot_ordinal": slot_ordinal,
                }
            )
            for run_ordinal in range(runs_per_candidate):
                run_id = f"run-{len(runs):02d}"
                runs.append(
                    {
                        "run_id": run_id,
                        "planned_candidate_slot_id": slot_id,
                        "run_ordinal": run_ordinal,
                    }
                )
                predecessor = "INITIAL_GENESIS"
                for sequence in range(retries_per_run + 1):
                    attempt_id = f"attempt-{attempt_index:02d}"
                    attempts.append(
                        {
                            "attempt_id": attempt_id,
                            "run_id": run_id,
                            "attempt_sequence": sequence,
                            "attempt_kind": "INITIAL" if sequence == 0 else "RETRY",
                            "predecessor_attempt_id_or_initial_genesis_marker": predecessor,
                        }
                    )
                    predecessor = attempt_id
                    attempt_index += 1
    return {
        "schema_version": "v0.1-test-root",
        "north_star_goal_instance_id": "goal-test-root",
        "ratification_instance_id": "UNRATIFIED-test-root",
        "confirmatory_batch_id": "batch-test-root",
        "draw_event_id": "draw-test-root",
        "protocol_package_hash": _digest(1),
        "protocol_authority_signature_set_hash": _digest(2),
        "sampling_frame_commitment_hash": _digest(3),
        "sampling_source_snapshot_hash": _digest(4),
        "minimum_claim_envelope_hash": _digest(5),
        "allocation_rule": {
            "planned_candidate_slots_per_target": 2,
            "planned_run_units_per_candidate": runs_per_candidate,
            "permitted_retry_attempts_per_run": retries_per_run,
            "retry_aggregation_rule": "first_delivered_else_last_permitted_attempt",
            "candidate_reported_delivery_aggregation_rule": (
                "any_non_rejected_run_reported_delivered"
            ),
        },
        "eligibility_rule": {
            "rule_kind": "immutable_source_record_hash_allowlist",
            "eligible_immutable_source_record_hashes": [_digest(20), _digest(21)],
        },
        "eligibility_evaluated_at": "2026-07-14T00:00:00Z",
        "invalid_input_exclusion_reason_allowlist": ["SOURCE_BYTES_INVALID"],
        "ordered_target_identity_members": targets,
        "ordered_candidate_slot_identity_members": candidates,
        "ordered_planned_run_unit_identity_members": runs,
        "ordered_permitted_attempt_identity_members": attempts,
    }


def _observations(states: list[str]) -> dict[str, object]:
    return {
        "ordered_attempt_observations": [
            {"attempt_id": f"attempt-{index:02d}", "terminal_state": state}
            for index, state in enumerate(states)
        ]
    }


def _content_hash(domain: str, value: dict[str, object]) -> str:
    assert value["domain_tag"] == domain
    payload = {key: item for key, item in value.items() if key != "domain_tag"}
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(domain.encode() + b"\x00" + canonical).hexdigest()


def _recompute(
    frozen: FrozenPreregistration,
    observations: IttObservations | dict[str, object],
) -> IttReport:
    return recompute_itt(
        frozen,
        observations,
        expected_preregistration_freeze_content_hash=(
            frozen.preregistration_freeze_content_hash
        ),
    )


def _with_rehashed_freeze_content(
    frozen: FrozenPreregistration, content: PreregistrationFreezeContent
) -> FrozenPreregistration:
    content_hash = _content_hash(
        PREREGISTRATION_FREEZE_DOMAIN, content.model_dump(mode="json")
    )
    return frozen.model_copy(
        update={
            "preregistration_freeze_content": content,
            "preregistration_freeze_content_hash": content_hash,
        }
    )


def test_recompute_itt_keeps_run_and_candidate_populations_distinct() -> None:
    frozen = freeze_preregistration(_spec())
    observations = _observations(
        [
            "failed",
            "delivered",
            "delivered",
            "missing",
            "blocked",
            "blocked",
            "contaminated",
            "missing",
        ]
    )

    report = _recompute(frozen, observations)

    assert report.confirmatory_authorized is False
    assert (
        report.preregistration_freeze_content_hash
        == frozen.preregistration_freeze_content_hash
    )
    assert report.pipeline_delivery_rate.raw_numerator == 0
    assert report.pipeline_delivery_rate.raw_denominator == 4
    assert report.pipeline_delivery_rate.rate == Fraction(0, 1)
    assert report.pipeline_delivery_rate.evidence_status == (
        "UNAVAILABLE_NO_VERIFIED_MACHINE_TERMINAL_EVIDENCE"
    )
    assert report.unverified_pipeline_delivery_diagnostic.raw_numerator == 2
    assert report.unverified_pipeline_delivery_diagnostic.rate == Fraction(1, 2)
    assert report.unverified_pipeline_delivery_diagnostic.diagnostic_only is True
    assert len(report.retained_attempt_observations) == 8
    assert [
        result.reported_terminal_state
        for result in report.ordered_unverified_run_terminal_diagnostics
    ] == [
        RunTerminalState.DELIVERED,
        RunTerminalState.DELIVERED,
        RunTerminalState.BLOCKED,
        RunTerminalState.MISSING,
    ]
    assert report.ordered_unverified_run_terminal_diagnostics[-1].contaminated_attempt_ids == (
        "attempt-06",
    )

    worth = report.expert_worth_reviewing_rate_itt
    production = report.expert_production_usable_rate_itt
    assert (worth.raw_numerator, worth.raw_denominator, worth.rate) == (0, 4, Fraction(0, 1))
    assert (production.raw_numerator, production.raw_denominator, production.rate) == (
        0,
        4,
        Fraction(0, 1),
    )
    assert worth.duplicate_clusters == ()
    assert worth.confidence_interval.lower is None
    assert worth.evidence_status == "UNAVAILABLE_NO_VERIFIED_EXPERT_LABEL_ENVELOPES"
    conditional = report.conditional_on_unverified_reported_delivery_diagnostics
    assert all(item.diagnostic_only for item in conditional)
    assert [item.raw_denominator for item in conditional] == [
        2,
        2,
    ]
    assert all(
        sum(len(cluster.ordered_member_ids) for cluster in item.dependence_clusters) == 2
        for item in conditional
    )
    selection = report.conditional_unverified_reported_delivery_selection
    assert selection.candidate_reported_delivery_aggregation_rule == (
        "any_non_rejected_run_reported_delivered"
    )
    assert selection.ordered_selected_planned_candidate_slot_ids == (
        "slot-00",
        "slot-01",
    )


@pytest.mark.parametrize("terminal_state", list(RunTerminalState))
def test_exact_terminal_to_pipeline_numerator_map(terminal_state: RunTerminalState) -> None:
    frozen = freeze_preregistration(_spec(retries_per_run=0))
    observations = _observations([terminal_state.value] * 4)

    report = _recompute(frozen, observations)

    expected = 4 if terminal_state is RunTerminalState.DELIVERED else 0
    assert report.pipeline_delivery_rate.raw_numerator == 0
    assert report.unverified_pipeline_delivery_diagnostic.raw_numerator == expected
    assert PIPELINE_NUMERATOR_VALUE[terminal_state] == (1 if expected else 0)


def test_retry_attempts_never_expand_pipeline_denominator() -> None:
    frozen = freeze_preregistration(_spec(retries_per_run=3))
    observations = _observations(["failed", "failed", "failed", "blocked"] * 4)

    report = _recompute(frozen, observations)

    assert len(report.retained_attempt_observations) == 16
    assert report.pipeline_delivery_rate.original_planned_denominator == 4
    assert report.pipeline_delivery_rate.raw_denominator == 4
    assert all(
        item.raw_denominator == 0 and item.dependence_clusters == ()
        for item in report.conditional_on_unverified_reported_delivery_diagnostics
    )


def test_delivered_run_rejects_a_later_nonmissing_retry() -> None:
    frozen = freeze_preregistration(_spec())
    observations = _observations(
        ["delivered", "failed", "missing", "missing", "missing", "missing", "missing", "missing"]
    )

    with pytest.raises(ProtocolViolation, match="later non-missing retry"):
        _recompute(frozen, observations)


@pytest.mark.parametrize("mutation", ["missing", "reordered", "duplicate"])
def test_attempt_observations_are_exact_closed_world_and_ordered(mutation: str) -> None:
    frozen = freeze_preregistration(_spec())
    observations = _observations(["missing"] * 8)
    members = observations["ordered_attempt_observations"]
    if mutation == "missing":
        members.pop()  # type: ignore[union-attr]
    elif mutation == "reordered":
        members[0], members[1] = members[1], members[0]  # type: ignore[index]
    else:
        members[1]["attempt_id"] = "attempt-00"  # type: ignore[index]

    with pytest.raises(ProtocolViolation, match="every permitted attempt"):
        _recompute(frozen, observations)


def test_unverified_exclusions_never_shrink_itt_populations() -> None:
    frozen = freeze_preregistration(_spec())
    observations = _observations(["missing"] * 8)
    observations["unverified_exclusion_references"] = [
        {
            "record_hash": _digest(50),
            "scope_type": "planned_run_unit",
            "scope_id": "run-00",
            "preregistered_reason_code": "SOURCE_BYTES_INVALID",
        },
        {
            "record_hash": _digest(51),
            "scope_type": "planned_candidate_slot",
            "scope_id": "slot-00",
            "preregistered_reason_code": "OUTCOME_LOOKED_BAD",
        },
    ]

    report = _recompute(frozen, observations)

    assert report.pipeline_delivery_rate.excluded_unit_count == 0
    assert report.pipeline_delivery_rate.raw_denominator == 4
    assert report.pipeline_delivery_rate.rejected_exclusion_record_hashes == (_digest(50),)
    assert report.expert_worth_reviewing_rate_itt.excluded_unit_count == 0
    assert report.expert_worth_reviewing_rate_itt.raw_denominator == 4
    assert report.expert_worth_reviewing_rate_itt.rejected_exclusion_record_hashes == (
        _digest(51),
    )
    assert [item.reason for item in report.rejected_exclusions] == [
        "CANONICAL_RECORD_AND_INDEPENDENT_VERIFICATION_UNAVAILABLE_IN_O01",
        "UNREGISTERED_REASON_CODE",
    ]


def test_rejected_exclusions_force_reported_delivery_not_passed() -> None:
    frozen = freeze_preregistration(_spec(retries_per_run=0))
    observations = _observations(["delivered"] * 4)
    observations["unverified_exclusion_references"] = [
        {
            "record_hash": _digest(50),
            "scope_type": "planned_run_unit",
            "scope_id": "run-00",
            "preregistered_reason_code": "SOURCE_BYTES_INVALID",
        },
        {
            "record_hash": _digest(51),
            "scope_type": "planned_candidate_slot",
            "scope_id": "slot-01",
            "preregistered_reason_code": "SOURCE_BYTES_INVALID",
        },
    ]

    report = _recompute(frozen, observations)

    assert report.pipeline_delivery_rate.raw_numerator == 0
    assert report.unverified_pipeline_delivery_diagnostic.raw_numerator == 3
    first = report.ordered_unverified_run_terminal_diagnostics[0]
    assert first.reported_terminal_state is RunTerminalState.DELIVERED
    assert first.forced_not_passed_by_rejected_exclusion is True
    conditional = report.conditional_on_unverified_reported_delivery_diagnostics
    assert [item.raw_denominator for item in conditional] == [2, 2]
    assert all(
        item.rejected_exclusion_record_hashes == (_digest(50), _digest(51))
        for item in conditional
    )
    assert all(
        sum(len(cluster.ordered_member_ids) for cluster in item.dependence_clusters) == 2
        for item in conditional
    )
    selection = report.conditional_unverified_reported_delivery_selection
    assert selection.ordered_selected_planned_candidate_slot_ids == (
        "slot-02",
        "slot-03",
    )
    assert selection.rejected_run_exclusion_record_hashes_considered_during_selection == (
        _digest(50),
    )
    assert (
        selection.rejected_candidate_exclusion_record_hashes_considered_during_selection
        == (_digest(51),)
    )


def test_unknown_exclusion_scope_and_candidate_id_alias_reject() -> None:
    frozen = freeze_preregistration(_spec())
    unknown = _observations(["missing"] * 8)
    unknown["unverified_exclusion_references"] = [
        {
            "record_hash": _digest(50),
            "scope_type": "planned_run_unit",
            "scope_id": "run-unknown",
            "preregistered_reason_code": "SOURCE_BYTES_INVALID",
        }
    ]
    with pytest.raises(ProtocolViolation, match="not a planned population member"):
        _recompute(frozen, unknown)

    aliased = _observations(["missing"] * 8)
    aliased["unverified_exclusion_references"] = [
        {
            "record_hash": _digest(50),
            "scope_type": "planned_candidate_slot",
            "candidate_id": "slot-00",
            "preregistered_reason_code": "SOURCE_BYTES_INVALID",
        }
    ]
    with pytest.raises(ProtocolViolation):
        _recompute(frozen, aliased)


def test_submitted_expert_booleans_are_not_a_public_input() -> None:
    frozen = freeze_preregistration(_spec())
    observations = _observations(["missing"] * 8)
    observations["expert_worth_reviewing"] = True
    observations["expert_production_usable"] = True

    with pytest.raises(ProtocolViolation):
        _recompute(frozen, observations)


def test_naked_reported_terminals_can_change_only_diagnostics() -> None:
    frozen = freeze_preregistration(_spec(retries_per_run=0))

    failed = _recompute(frozen, _observations(["failed"] * 4))
    delivered = _recompute(frozen, _observations(["delivered"] * 4))

    assert failed.pipeline_delivery_rate.raw_numerator == 0
    assert delivered.pipeline_delivery_rate.raw_numerator == 0
    assert failed.unverified_pipeline_delivery_diagnostic.raw_numerator == 0
    assert delivered.unverified_pipeline_delivery_diagnostic.raw_numerator == 4


def test_report_retains_exact_preregistration_freeze_binding() -> None:
    first = freeze_preregistration(_spec(retries_per_run=0))
    second_spec = _spec(retries_per_run=0)
    second_spec["sampling_frame_commitment_hash"] = _digest(61)
    second = freeze_preregistration(second_spec)
    observations = _observations(["missing"] * 4)

    first_report = _recompute(first, observations)
    second_report = _recompute(second, observations)

    assert first.preregistration_freeze_content_hash != (
        second.preregistration_freeze_content_hash
    )
    assert first_report.preregistration_freeze_content_hash == (
        first.preregistration_freeze_content_hash
    )
    assert second_report.preregistration_freeze_content_hash == (
        second.preregistration_freeze_content_hash
    )
    assert first_report != second_report


def test_multi_run_candidate_uses_frozen_reported_delivery_aggregation_rule() -> None:
    frozen = freeze_preregistration(
        _spec(retries_per_run=0, runs_per_candidate=2)
    )
    observations = _observations(["delivered", "failed"] * 4)

    report = _recompute(frozen, observations)

    assert report.unverified_pipeline_delivery_diagnostic.raw_numerator == 4
    assert report.unverified_pipeline_delivery_diagnostic.raw_denominator == 8
    selection = report.conditional_unverified_reported_delivery_selection
    assert selection.candidate_reported_delivery_aggregation_rule == (
        "any_non_rejected_run_reported_delivered"
    )
    assert selection.ordered_selected_planned_candidate_slot_ids == (
        "slot-00",
        "slot-01",
        "slot-02",
        "slot-03",
    )
    assert all(
        item.raw_denominator == 4
        for item in report.conditional_on_unverified_reported_delivery_diagnostics
    )


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("attempt_id", b"attempt-00"),
        ("terminal_state", b"delivered"),
    ],
)
def test_observations_reject_bytes(field: str, bad_value: object) -> None:
    frozen = freeze_preregistration(_spec())
    observations = _observations(["missing"] * 8)
    observations["ordered_attempt_observations"][0][field] = bad_value  # type: ignore[index]

    with pytest.raises(ProtocolViolation):
        _recompute(frozen, observations)


@pytest.mark.parametrize("container_kind", ["set", "frozenset", "generator"])
def test_observations_reject_unordered_or_streaming_containers(container_kind: str) -> None:
    frozen = freeze_preregistration(_spec())
    observations = _observations(["missing"] * 8)
    members = observations["ordered_attempt_observations"]
    if container_kind == "set":
        observations["ordered_attempt_observations"] = {"attempt-00"}
    elif container_kind == "frozenset":
        observations["unverified_exclusion_references"] = frozenset()
    else:
        observations["ordered_attempt_observations"] = (item for item in members)  # type: ignore[union-attr]

    with pytest.raises(ProtocolViolation):
        _recompute(frozen, observations)


def test_observations_reject_raw_container_subclasses() -> None:
    class ListSubclass(list[object]):
        pass

    frozen = freeze_preregistration(_spec())
    observations = _observations(["missing"] * 8)
    observations["ordered_attempt_observations"] = ListSubclass(
        observations["ordered_attempt_observations"]  # type: ignore[arg-type]
    )

    with pytest.raises(ProtocolViolation, match="exact JSON primitives"):
        _recompute(frozen, observations)


def test_observation_model_copy_extra_field_bypass_rejects() -> None:
    frozen = freeze_preregistration(_spec())
    observations = IttObservations.model_validate(_observations(["missing"] * 8))
    bypass = observations.model_copy(
        update={"expert_worth_reviewing": True, "expert_production_usable": True}
    )

    with pytest.raises(ProtocolViolation, match="exactly match"):
        _recompute(frozen, bypass)


@pytest.mark.parametrize("slot", ["__pydantic_extra__", "__pydantic_private__"])
def test_observations_reject_missing_hidden_model_slots(slot: str) -> None:
    frozen = freeze_preregistration(_spec())
    observations = IttObservations.model_validate(_observations(["missing"] * 8))
    object.__delattr__(observations, slot)

    with pytest.raises(ProtocolViolation, match="retain its required extra/private Pydantic slots"):
        _recompute(frozen, observations)


def test_observations_reject_falsey_private_state() -> None:
    class FalseyHiddenState(dict[str, object]):
        def __bool__(self) -> bool:
            return False

    frozen = freeze_preregistration(_spec())
    observations = IttObservations.model_validate(_observations(["missing"] * 8))
    object.__setattr__(
        observations,
        "__pydantic_private__",
        FalseyHiddenState(expert_worth_reviewing=True),
    )

    with pytest.raises(ProtocolViolation, match="exactly match"):
        _recompute(frozen, observations)


def test_observations_reject_root_model_storage_dict_subclass() -> None:
    class CamouflagedDict(dict[str, object]):
        def __iter__(self):  # type: ignore[no-untyped-def]
            return iter(key for key in dict.keys(self) if not key.startswith("expert_"))

    frozen = freeze_preregistration(_spec())
    observations = IttObservations.model_validate(_observations(["missing"] * 8))
    storage = CamouflagedDict(object.__getattribute__(observations, "__dict__"))
    storage["expert_worth_reviewing"] = True
    object.__setattr__(observations, "__dict__", storage)

    with pytest.raises(ProtocolViolation, match="storage must be an exact dict"):
        _recompute(frozen, observations)


def test_observations_reject_nested_model_storage_dict_subclass() -> None:
    class CamouflagedDict(dict[str, object]):
        def __iter__(self):  # type: ignore[no-untyped-def]
            return iter(key for key in dict.keys(self) if not key.startswith("expert_"))

    frozen = freeze_preregistration(_spec())
    observations = IttObservations.model_validate(_observations(["missing"] * 8))
    attempt = observations.ordered_attempt_observations[0]
    storage = CamouflagedDict(object.__getattribute__(attempt, "__dict__"))
    storage["expert_production_usable"] = True
    object.__setattr__(attempt, "__dict__", storage)

    with pytest.raises(ProtocolViolation, match="storage must be an exact dict"):
        _recompute(frozen, observations)


def test_observations_reject_non_exact_storage_key_without_hash_hook() -> None:
    class HookedKey(str):
        armed = False
        calls = 0

        def __hash__(self) -> int:
            type(self).calls += 1
            if type(self).armed:
                raise RuntimeError("hash hook must not run during validation")
            return str.__hash__(self)

    frozen = freeze_preregistration(_spec())
    observations = IttObservations.model_validate(_observations(["missing"] * 8))
    storage = object.__getattribute__(observations, "__dict__")
    field_name = "ordered_attempt_observations"
    field_value = dict.pop(storage, field_name)
    dict.__setitem__(storage, HookedKey(field_name), field_value)
    HookedKey.calls = 0
    HookedKey.armed = True

    with pytest.raises(ProtocolViolation, match="fields must be exact strings"):
        _recompute(frozen, observations)
    assert HookedKey.calls == 0


def test_observations_reject_dynamic_list_before_invoking_hook() -> None:
    class SwapList(list[object]):
        calls = 0

        def __init__(self, parent: IttObservations, replacement: object) -> None:
            super().__init__()
            self.parent = parent
            self.replacement = replacement

        def __iter__(self):  # type: ignore[no-untyped-def]
            type(self).calls += 1
            object.__setattr__(
                self.parent, "ordered_attempt_observations", self.replacement
            )
            return super().__iter__()

    frozen = freeze_preregistration(_spec())
    observations = IttObservations.model_validate(_observations(["missing"] * 8))
    replacement = observations.ordered_attempt_observations
    object.__setattr__(
        observations,
        "ordered_attempt_observations",
        SwapList(observations, replacement),
    )

    with pytest.raises(ProtocolViolation, match="exact runtime type as a tuple"):
        _recompute(frozen, observations)
    assert SwapList.calls == 0


def test_observations_reject_cyclic_raw_container() -> None:
    frozen = freeze_preregistration(_spec())
    observations = _observations(["missing"] * 8)
    cycle: list[object] = []
    cycle.append(cycle)
    observations["ordered_attempt_observations"] = cycle

    with pytest.raises(ProtocolViolation, match="cyclic raw container"):
        _recompute(frozen, observations)


def test_observations_wrap_deep_cyclic_raw_recursion() -> None:
    frozen = freeze_preregistration(_spec())
    root: list[object] = []
    cursor = root
    for _ in range(1200):
        child: list[object] = []
        cursor.append(child)
        cursor = child
    cursor.append(root)
    observations = _observations(["missing"] * 8)
    observations["ordered_attempt_observations"] = root

    with pytest.raises(ProtocolViolation, match="nesting exceeds supported recursion depth"):
        _recompute(frozen, observations)


def test_observation_declared_model_subclass_fields_reject() -> None:
    class ExtendedAttempt(AttemptObservation):
        expert_worth_reviewing: bool

    frozen = freeze_preregistration(_spec())
    observations = IttObservations.model_validate(_observations(["missing"] * 8))
    members = list(observations.ordered_attempt_observations)
    members[0] = ExtendedAttempt(
        **members[0].model_dump(mode="python"), expert_worth_reviewing=True
    )
    bypass = observations.model_copy(
        update={"ordered_attempt_observations": tuple(members)}
    )

    with pytest.raises(ProtocolViolation, match="exact runtime type"):
        _recompute(frozen, bypass)


def test_frozen_model_input_rejects_scalar_normalization() -> None:
    class ForeignAuthority(StrEnum):
        UNRATIFIED = "UNRATIFIED"

    frozen = freeze_preregistration(_spec())
    observations = _observations(["missing"] * 8)

    false_alias = frozen.model_copy(update={"confirmatory_authorized": 0})
    with pytest.raises(ProtocolViolation, match="exact runtime type"):
        _recompute(false_alias, observations)

    enum_alias = frozen.model_copy(update={"authority_status": ForeignAuthority.UNRATIFIED})
    with pytest.raises(ProtocolViolation, match="exact runtime type"):
        _recompute(enum_alias, observations)


def test_recompute_requires_exact_frozen_root_model() -> None:
    frozen = freeze_preregistration(_spec())
    raw_frozen = frozen.model_dump(mode="python")
    raw_frozen["confirmatory_authorized"] = 0

    with pytest.raises(ProtocolViolation, match="exactly FrozenPreregistration"):
        recompute_itt(  # type: ignore[arg-type]
            raw_frozen,
            _observations(["missing"] * 8),
            expected_preregistration_freeze_content_hash=(
                frozen.preregistration_freeze_content_hash
            ),
        )


def test_recompute_rejects_falsey_frozen_extra_state() -> None:
    class FalseyHiddenState(dict[str, object]):
        def __bool__(self) -> bool:
            return False

    frozen = freeze_preregistration(_spec())
    object.__setattr__(
        frozen,
        "__pydantic_extra__",
        FalseyHiddenState(expert_worth_reviewing=True),
    )

    with pytest.raises(ProtocolViolation, match="exactly match"):
        _recompute(frozen, _observations(["missing"] * 8))


@pytest.mark.parametrize("slot", ["__pydantic_extra__", "__pydantic_private__"])
def test_recompute_rejects_missing_frozen_model_slots(slot: str) -> None:
    frozen = freeze_preregistration(_spec())
    object.__delattr__(frozen, slot)

    with pytest.raises(ProtocolViolation, match="retain its required extra/private Pydantic slots"):
        _recompute(frozen, _observations(["missing"] * 8))


def test_recompute_rejects_non_exact_frozen_storage_key_without_hash_hook() -> None:
    class HookedKey(str):
        armed = False
        calls = 0

        def __hash__(self) -> int:
            type(self).calls += 1
            if type(self).armed:
                raise RuntimeError("hash hook must not run during validation")
            return str.__hash__(self)

    frozen = freeze_preregistration(_spec())
    storage = object.__getattribute__(frozen, "__dict__")
    field_name = "authority_status"
    field_value = dict.pop(storage, field_name)
    dict.__setitem__(storage, HookedKey(field_name), field_value)
    HookedKey.calls = 0
    HookedKey.armed = True

    with pytest.raises(ProtocolViolation, match="fields must be exact strings"):
        _recompute(frozen, _observations(["missing"] * 8))
    assert HookedKey.calls == 0


def test_recompute_rejects_tampered_nested_hash_or_eligibility_content() -> None:
    frozen = freeze_preregistration(_spec())
    observations = _observations(["missing"] * 8)
    content = frozen.preregistration_freeze_content
    bad_content = content.model_copy(
        update={"planned_identity_mapping_content_hash": _digest(63)}
    )
    bad_hash = _with_rehashed_freeze_content(frozen, bad_content)
    with pytest.raises(ProtocolViolation, match="mapping content hash mismatch"):
        _recompute(bad_hash, observations)

    decisions = frozen.eligibility_decision_set_content
    members = list(decisions.ordered_eligibility_decision_members)
    members.reverse()
    bad_decisions = decisions.model_copy(
        update={"ordered_eligibility_decision_members": tuple(members)}
    )
    bad_decision_hash = _content_hash(
        ELIGIBILITY_DECISION_SET_DOMAIN, bad_decisions.model_dump(mode="json")
    )
    bad_content = content.model_copy(
        update={
            "eligibility_decision_set_content": bad_decisions,
            "eligibility_decision_set_content_hash": bad_decision_hash,
        }
    )
    tampered = _with_rehashed_freeze_content(frozen, bad_content)
    with pytest.raises(ProtocolViolation, match="ordered and recomputed"):
        _recompute(tampered, observations)


def test_eligibility_evaluation_time_is_bound_and_recomputed() -> None:
    frozen = freeze_preregistration(_spec())
    content = frozen.preregistration_freeze_content
    decisions = content.eligibility_decision_set_content
    members = list(decisions.ordered_eligibility_decision_members)
    members[0] = members[0].model_copy(update={"evaluated_at": "2026-07-15T00:00:00Z"})
    bad_decisions = decisions.model_copy(
        update={"ordered_eligibility_decision_members": tuple(members)}
    )
    bad_decision_hash = _content_hash(
        ELIGIBILITY_DECISION_SET_DOMAIN, bad_decisions.model_dump(mode="json")
    )
    bad_content = content.model_copy(
        update={
            "eligibility_decision_set_content": bad_decisions,
            "eligibility_decision_set_content_hash": bad_decision_hash,
        }
    )
    tampered = _with_rehashed_freeze_content(frozen, bad_content)

    with pytest.raises(ProtocolViolation, match="ordered and recomputed"):
        _recompute(tampered, _observations(["missing"] * 8))


def test_external_expected_freeze_hash_rejects_coherent_sampling_frame_swap() -> None:
    frozen = freeze_preregistration(_spec())
    original_hash = frozen.preregistration_freeze_content_hash
    bad_content = frozen.preregistration_freeze_content.model_copy(
        update={"sampling_frame_commitment_hash": _digest(62)}
    )
    tampered = _with_rehashed_freeze_content(frozen, bad_content)

    with pytest.raises(ProtocolViolation, match="externally expected"):
        recompute_itt(
            tampered,
            _observations(["missing"] * 8),
            expected_preregistration_freeze_content_hash=original_hash,
        )


def test_expected_freeze_hash_rejects_bytes() -> None:
    frozen = freeze_preregistration(_spec())

    with pytest.raises(ProtocolViolation, match="exact lowercase"):
        recompute_itt(
            frozen,
            _observations(["missing"] * 8),
            expected_preregistration_freeze_content_hash=(
                frozen.preregistration_freeze_content_hash.encode()  # type: ignore[arg-type]
            ),
        )
