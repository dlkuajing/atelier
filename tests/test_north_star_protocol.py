from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from enum import StrEnum

import pytest

from app.core.north_star import (
    ELIGIBILITY_DECISION_SET_DOMAIN,
    ELIGIBILITY_INPUT_DOMAIN,
    ELIGIBILITY_RULE_DOMAIN,
    PLANNED_IDENTITY_MAPPING_DOMAIN,
    PREREGISTRATION_FREEZE_DOMAIN,
    EligibilityDecision,
    PreregistrationSpec,
    ProtocolViolation,
    TargetIdentityMember,
    freeze_preregistration,
)


def _digest(number: int) -> str:
    return f"{number:064x}"


def _domain_hash(domain: str, value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(domain.encode() + b"\x00" + canonical).hexdigest()


def _content_hash(domain: str, value: dict[str, object]) -> str:
    assert value["domain_tag"] == domain
    return _domain_hash(domain, {key: item for key, item in value.items() if key != "domain_tag"})


def make_spec(
    *,
    target_count: int = 2,
    slots_per_target: int = 2,
    runs_per_candidate: int = 1,
    retries_per_run: int = 1,
) -> dict[str, object]:
    target_names = ["target-z", "target-a", "target-m"][:target_count]
    targets: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    runs: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    candidate_index = 0
    run_index = 0
    attempt_index = 0
    for target_ordinal, target_id in enumerate(target_names):
        source_hash = _digest(20 + target_ordinal)
        target = {
            "target_id": target_id,
            "seed_cluster_id": f"seed-{target_ordinal}",
            "patent_family_id": f"patent-{target_ordinal}",
            "immutable_source_record_hash": source_hash,
            "draw_ordinal": target_ordinal,
        }
        targets.append(target)
        for slot_ordinal in range(slots_per_target):
            slot_id = f"slot-{candidate_index:02d}"
            candidates.append(
                {
                    "planned_candidate_slot_id": slot_id,
                    "target_id": target_id,
                    "seed_cluster_id": target["seed_cluster_id"],
                    "patent_family_id": target["patent_family_id"],
                    "candidate_slot_ordinal": slot_ordinal,
                }
            )
            candidate_index += 1
            for run_ordinal in range(runs_per_candidate):
                run_id = f"run-{run_index:02d}"
                runs.append(
                    {
                        "run_id": run_id,
                        "planned_candidate_slot_id": slot_id,
                        "run_ordinal": run_ordinal,
                    }
                )
                run_index += 1
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
            "planned_candidate_slots_per_target": slots_per_target,
            "planned_run_units_per_candidate": runs_per_candidate,
            "permitted_retry_attempts_per_run": retries_per_run,
            "retry_aggregation_rule": "first_delivered_else_last_permitted_attempt",
            "candidate_reported_delivery_aggregation_rule": (
                "any_non_rejected_run_reported_delivered"
            ),
        },
        "eligibility_rule": {
            "rule_kind": "immutable_source_record_hash_allowlist",
            "eligible_immutable_source_record_hashes": [_digest(20)],
        },
        "eligibility_evaluated_at": "2026-07-14T00:00:00Z",
        "invalid_input_exclusion_reason_allowlist": ["SOURCE_BYTES_INVALID"],
        "ordered_target_identity_members": targets,
        "ordered_candidate_slot_identity_members": candidates,
        "ordered_planned_run_unit_identity_members": runs,
        "ordered_permitted_attempt_identity_members": attempts,
    }


def test_freeze_recomputes_inline_domain_separated_mapping_and_eligibility() -> None:
    frozen = freeze_preregistration(make_spec())

    assert frozen.authority_status == "UNRATIFIED"
    assert frozen.confirmatory_authorized is False
    freeze_content = frozen.preregistration_freeze_content.model_dump(mode="json")
    assert frozen.preregistration_freeze_content_hash == _content_hash(
        PREREGISTRATION_FREEZE_DOMAIN, freeze_content
    )
    mapping = frozen.planned_identity_mapping_content.model_dump(mode="json")
    decisions = frozen.eligibility_decision_set_content.model_dump(mode="json")
    rule = frozen.eligibility_rule.model_dump(mode="json")
    assert frozen.planned_identity_mapping_content_hash == _content_hash(
        PLANNED_IDENTITY_MAPPING_DOMAIN, mapping
    )
    assert frozen.eligibility_rule_hash == _domain_hash(ELIGIBILITY_RULE_DOMAIN, rule)
    assert frozen.eligibility_decision_set_content_hash == _content_hash(
        ELIGIBILITY_DECISION_SET_DOMAIN, decisions
    )
    assert frozen.planned_identity_mapping_content_hash != (
        frozen.eligibility_decision_set_content_hash
    )

    members = frozen.eligibility_decision_set_content.ordered_eligibility_decision_members
    assert [member.target_id for member in members] == ["target-z", "target-a"]
    assert [member.decision for member in members] == [
        EligibilityDecision.ELIGIBLE,
        EligibilityDecision.INELIGIBLE,
    ]
    for member in members:
        content = member.eligibility_input_content.model_dump(mode="json")
        assert content["domain_tag"] == ELIGIBILITY_INPUT_DOMAIN
        assert member.eligibility_input_content_hash == _content_hash(
            ELIGIBILITY_INPUT_DOMAIN, content
        )


def test_freeze_uses_protocol_ordinals_not_lexical_identifier_order() -> None:
    frozen = freeze_preregistration(make_spec())

    mapping = frozen.planned_identity_mapping_content
    assert [target.target_id for target in mapping.ordered_target_identity_members] == [
        "target-z",
        "target-a",
    ]
    assert [candidate.planned_candidate_slot_id for candidate in mapping.ordered_candidate_slot_identity_members] == [
        "slot-00",
        "slot-01",
        "slot-02",
        "slot-03",
    ]


@pytest.mark.parametrize("missing_field", ["target_id", "draw_ordinal"])
def test_freeze_rejects_missing_target_fields(missing_field: str) -> None:
    spec = make_spec()
    del spec["ordered_target_identity_members"][0][missing_field]  # type: ignore[index]

    with pytest.raises(ProtocolViolation):
        freeze_preregistration(spec)


def test_freeze_rejects_candidate_id_alias_and_extra_fields() -> None:
    spec = make_spec()
    candidate = spec["ordered_candidate_slot_identity_members"][0]  # type: ignore[index]
    candidate["candidate_id"] = candidate.pop("planned_candidate_slot_id")

    with pytest.raises(ProtocolViolation):
        freeze_preregistration(spec)


def test_freeze_rejects_reordered_or_gapped_targets() -> None:
    reordered = make_spec()
    reordered["ordered_target_identity_members"].reverse()  # type: ignore[union-attr]
    with pytest.raises(ProtocolViolation, match="draw_ordinal"):
        freeze_preregistration(reordered)

    gapped = make_spec()
    gapped["ordered_target_identity_members"][1]["draw_ordinal"] = 2  # type: ignore[index]
    with pytest.raises(ProtocolViolation, match="draw_ordinal"):
        freeze_preregistration(gapped)


def test_freeze_rejects_reparented_candidate_run_and_attempt() -> None:
    candidate = make_spec()
    candidate["ordered_candidate_slot_identity_members"][0]["seed_cluster_id"] = "seed-1"  # type: ignore[index]
    with pytest.raises(ProtocolViolation, match="parentage"):
        freeze_preregistration(candidate)

    run = make_spec()
    run["ordered_planned_run_unit_identity_members"][0]["planned_candidate_slot_id"] = "slot-01"  # type: ignore[index]
    with pytest.raises(ProtocolViolation, match="planned runs"):
        freeze_preregistration(run)

    attempt = make_spec()
    attempt["ordered_permitted_attempt_identity_members"][1][  # type: ignore[index]
        "predecessor_attempt_id_or_initial_genesis_marker"
    ] = "attempt-99"
    with pytest.raises(ProtocolViolation, match="predecessor-bound"):
        freeze_preregistration(attempt)


def test_freeze_rejects_duplicate_primary_ids_and_allocation_mismatch() -> None:
    duplicate = make_spec()
    duplicate["ordered_planned_run_unit_identity_members"][1]["run_id"] = "run-00"  # type: ignore[index]
    with pytest.raises(ProtocolViolation, match="unique"):
        freeze_preregistration(duplicate)

    wrong_count = make_spec()
    wrong_count["ordered_candidate_slot_identity_members"].pop()  # type: ignore[union-attr]
    with pytest.raises(ProtocolViolation, match="allocation rule"):
        freeze_preregistration(wrong_count)


def test_freeze_rejects_rule_duplicates_and_does_not_accept_submitted_decisions() -> None:
    duplicated_rule = make_spec()
    duplicated_rule["eligibility_rule"]["eligible_immutable_source_record_hashes"].append(  # type: ignore[index, union-attr]
        _digest(20)
    )
    with pytest.raises(ProtocolViolation, match="must be unique"):
        freeze_preregistration(duplicated_rule)

    submitted_decision = deepcopy(make_spec())
    submitted_decision["eligibility_decisions"] = [{"target_id": "target-z", "decision": True}]
    with pytest.raises(ProtocolViolation):
        freeze_preregistration(submitted_decision)


@pytest.mark.parametrize(
    ("container", "field"),
    [
        ("allocation_rule", "retry_aggregation_rule"),
        ("allocation_rule", "candidate_reported_delivery_aggregation_rule"),
        ("eligibility_rule", "rule_kind"),
        (None, "invalid_input_exclusion_reason_allowlist"),
    ],
)
def test_freeze_rejects_missing_closed_rule_fields(container: str | None, field: str) -> None:
    spec = make_spec()
    target = spec if container is None else spec[container]
    del target[field]  # type: ignore[index]

    with pytest.raises(ProtocolViolation):
        freeze_preregistration(spec)


def test_freeze_rejects_reserved_initial_genesis_as_a_primary_id() -> None:
    spec = make_spec()
    spec["ordered_permitted_attempt_identity_members"][0]["attempt_id"] = "INITIAL_GENESIS"  # type: ignore[index]

    with pytest.raises(ProtocolViolation, match="reserved marker"):
        freeze_preregistration(spec)


@pytest.mark.parametrize(
    ("path", "bad_value"),
    [
        (("protocol_package_hash",), _digest(1).encode()),
        (("ordered_target_identity_members", 0, "target_id"), b"target-z"),
        (("ordered_permitted_attempt_identity_members", 0, "attempt_kind"), b"INITIAL"),
    ],
)
def test_freeze_rejects_bytes_at_scalar_and_enum_boundaries(
    path: tuple[str | int, ...], bad_value: object
) -> None:
    spec = make_spec()
    target: object = spec
    for component in path[:-1]:
        target = target[component]  # type: ignore[index]
    target[path[-1]] = bad_value  # type: ignore[index]

    with pytest.raises(ProtocolViolation):
        freeze_preregistration(spec)


@pytest.mark.parametrize("container_kind", ["set", "frozenset", "generator"])
def test_freeze_rejects_unordered_or_streaming_containers(container_kind: str) -> None:
    spec = make_spec()
    if container_kind == "set":
        spec["eligibility_rule"]["eligible_immutable_source_record_hashes"] = {  # type: ignore[index]
            _digest(20)
        }
    elif container_kind == "frozenset":
        spec["invalid_input_exclusion_reason_allowlist"] = frozenset(
            {"SOURCE_BYTES_INVALID"}
        )
    else:
        targets = spec["ordered_target_identity_members"]
        spec["ordered_target_identity_members"] = (item for item in targets)  # type: ignore[union-attr]

    with pytest.raises(ProtocolViolation):
        freeze_preregistration(spec)


def test_freeze_rejects_raw_container_subclasses() -> None:
    class DictSubclass(dict[str, object]):
        pass

    class ListSubclass(list[object]):
        pass

    with pytest.raises(ProtocolViolation, match="exact JSON primitives"):
        freeze_preregistration(DictSubclass(make_spec()))

    spec = make_spec()
    spec["ordered_target_identity_members"] = ListSubclass(
        spec["ordered_target_identity_members"]  # type: ignore[arg-type]
    )
    with pytest.raises(ProtocolViolation, match="exact JSON primitives"):
        freeze_preregistration(spec)


def test_freeze_rejects_raw_subclass_without_invoking_class_hook() -> None:
    class ClassHookDict(dict[str, object]):
        calls = 0

        @property
        def __class__(self):  # type: ignore[no-untyped-def]
            type(self).calls += 1
            raise RuntimeError("class hook must not run")

    payload = ClassHookDict(make_spec())

    with pytest.raises(ProtocolViolation, match="exact JSON primitives"):
        freeze_preregistration(payload)
    assert ClassHookDict.calls == 0


def test_freeze_rejects_raw_value_without_invoking_type_hash_hook() -> None:
    hash_calls: list[str] = []

    class HashHookMeta(type):
        def __hash__(cls) -> int:
            hash_calls.append("hash")
            raise RuntimeError("type hash hook must not run")

    class HashHookValue(metaclass=HashHookMeta):
        pass

    payload = make_spec()
    payload["schema_version"] = HashHookValue()

    with pytest.raises(ProtocolViolation, match="exact JSON primitives"):
        freeze_preregistration(payload)
    assert hash_calls == []


def test_freeze_rejects_model_copy_extra_field_bypass() -> None:
    spec = PreregistrationSpec.model_validate(make_spec())
    bypass = spec.model_copy(update={"eligibility_decisions": []})

    with pytest.raises(ProtocolViolation, match="exactly match"):
        freeze_preregistration(bypass)

    targets = list(spec.ordered_target_identity_members)
    targets[0] = targets[0].model_copy(update={"hidden_target_fact": "bypass"})
    nested_bypass = spec.model_copy(
        update={"ordered_target_identity_members": tuple(targets)}
    )
    with pytest.raises(ProtocolViolation, match="exactly match"):
        freeze_preregistration(nested_bypass)


@pytest.mark.parametrize("slot", ["__pydantic_extra__", "__pydantic_private__"])
def test_freeze_rejects_missing_hidden_model_slots(slot: str) -> None:
    spec = PreregistrationSpec.model_validate(make_spec())
    object.__delattr__(spec, slot)

    with pytest.raises(ProtocolViolation, match="retain its required extra/private Pydantic slots"):
        freeze_preregistration(spec)


@pytest.mark.parametrize("slot", ["__pydantic_extra__", "__pydantic_private__"])
def test_freeze_rejects_falsey_hidden_model_slots(slot: str) -> None:
    class FalseyHiddenState(dict[str, object]):
        def __bool__(self) -> bool:
            return False

    spec = PreregistrationSpec.model_validate(make_spec())
    object.__setattr__(
        spec, slot, FalseyHiddenState(expert_worth_reviewing=True)
    )

    with pytest.raises(ProtocolViolation, match="exactly match"):
        freeze_preregistration(spec)


def test_freeze_rejects_root_model_storage_dict_subclass() -> None:
    class CamouflagedDict(dict[str, object]):
        def __iter__(self):  # type: ignore[no-untyped-def]
            return iter(key for key in dict.keys(self) if not key.startswith("expert_"))

    spec = PreregistrationSpec.model_validate(make_spec())
    storage = CamouflagedDict(object.__getattribute__(spec, "__dict__"))
    storage["expert_worth_reviewing"] = True
    object.__setattr__(spec, "__dict__", storage)

    with pytest.raises(ProtocolViolation, match="storage must be an exact dict"):
        freeze_preregistration(spec)


def test_freeze_rejects_nested_model_storage_dict_subclass() -> None:
    class CamouflagedDict(dict[str, object]):
        def __iter__(self):  # type: ignore[no-untyped-def]
            return iter(key for key in dict.keys(self) if not key.startswith("expert_"))

    spec = PreregistrationSpec.model_validate(make_spec())
    target = spec.ordered_target_identity_members[0]
    storage = CamouflagedDict(object.__getattribute__(target, "__dict__"))
    storage["expert_production_usable"] = True
    object.__setattr__(target, "__dict__", storage)

    with pytest.raises(ProtocolViolation, match="storage must be an exact dict"):
        freeze_preregistration(spec)


@pytest.mark.parametrize("model_location", ["root", "nested"])
def test_freeze_rejects_non_exact_model_storage_keys_without_hash_hook(
    model_location: str,
) -> None:
    class HookedKey(str):
        armed = False
        calls = 0

        def __hash__(self) -> int:
            type(self).calls += 1
            if type(self).armed:
                raise RuntimeError("hash hook must not run during validation")
            return str.__hash__(self)

    spec = PreregistrationSpec.model_validate(make_spec())
    if model_location == "root":
        model = spec
        field_name = "schema_version"
    else:
        model = spec.ordered_target_identity_members[0]
        field_name = "target_id"
    storage = object.__getattribute__(model, "__dict__")
    field_value = dict.pop(storage, field_name)
    dict.__setitem__(storage, HookedKey(field_name), field_value)
    HookedKey.calls = 0
    HookedKey.armed = True

    with pytest.raises(ProtocolViolation, match="fields must be exact strings"):
        freeze_preregistration(spec)
    assert HookedKey.calls == 0


def test_freeze_rejects_hidden_duplicate_storage_key_by_physical_count() -> None:
    class DynamicHashKey(str):
        armed = False
        calls = 0

        def __hash__(self) -> int:
            type(self).calls += 1
            if type(self).armed:
                raise RuntimeError("hash hook must not run during validation")
            return str.__hash__(self) ^ 1

    spec = PreregistrationSpec.model_validate(make_spec())
    storage = object.__getattribute__(spec, "__dict__")
    dict.__setitem__(
        storage,
        DynamicHashKey("allocation_rule"),
        spec.allocation_rule,
    )
    DynamicHashKey.calls = 0
    DynamicHashKey.armed = True
    assert dict.__len__(storage) == len(PreregistrationSpec.model_fields) + 1

    with pytest.raises(ProtocolViolation, match="exactly match"):
        freeze_preregistration(spec)
    assert DynamicHashKey.calls == 0


def test_freeze_rejects_dynamic_mapping_before_invoking_hook() -> None:
    class SwapMapping(dict[str, object]):
        calls = 0

        def __init__(self, parent: PreregistrationSpec, replacement: object) -> None:
            super().__init__()
            self.parent = parent
            self.replacement = replacement

        def items(self):  # type: ignore[no-untyped-def]
            type(self).calls += 1
            object.__setattr__(self.parent, "allocation_rule", self.replacement)
            return super().items()

    spec = PreregistrationSpec.model_validate(make_spec())
    replacement = spec.allocation_rule
    object.__setattr__(spec, "allocation_rule", SwapMapping(spec, replacement))

    with pytest.raises(ProtocolViolation, match="expected UniformAllocationRule"):
        freeze_preregistration(spec)
    assert SwapMapping.calls == 0


def test_freeze_rejects_model_mismatch_without_reading_attacker_class_name() -> None:
    name_reads: list[str] = []

    class NameHookMeta(type):
        def __getattribute__(cls, name: str) -> object:
            if name == "__name__":
                name_reads.append(name)
                raise RuntimeError("class-name hook must not run")
            return type.__getattribute__(cls, name)

    class NameHookMapping(dict[str, object], metaclass=NameHookMeta):
        pass

    spec = PreregistrationSpec.model_validate(make_spec())
    object.__setattr__(spec, "allocation_rule", NameHookMapping())

    with pytest.raises(ProtocolViolation, match="expected UniformAllocationRule"):
        freeze_preregistration(spec)
    assert name_reads == []


def test_freeze_rejects_dynamic_list_before_invoking_hook() -> None:
    class SwapList(list[object]):
        calls = 0

        def __init__(self, parent: PreregistrationSpec, replacement: object) -> None:
            super().__init__()
            self.parent = parent
            self.replacement = replacement

        def __iter__(self):  # type: ignore[no-untyped-def]
            type(self).calls += 1
            object.__setattr__(
                self.parent, "ordered_target_identity_members", self.replacement
            )
            return super().__iter__()

    spec = PreregistrationSpec.model_validate(make_spec())
    replacement = spec.ordered_target_identity_members
    object.__setattr__(
        spec,
        "ordered_target_identity_members",
        SwapList(spec, replacement),
    )

    with pytest.raises(ProtocolViolation, match="exact runtime type as a tuple"):
        freeze_preregistration(spec)
    assert SwapList.calls == 0


def test_freeze_rejects_declared_nested_model_subclass_fields() -> None:
    class ExtendedTarget(TargetIdentityMember):
        hidden_expert_fact: str

    spec = PreregistrationSpec.model_validate(make_spec())
    targets = list(spec.ordered_target_identity_members)
    targets[0] = ExtendedTarget(
        **targets[0].model_dump(mode="python"), hidden_expert_fact="BYPASS"
    )
    bypass = spec.model_copy(update={"ordered_target_identity_members": tuple(targets)})

    with pytest.raises(ProtocolViolation, match="exact runtime type"):
        freeze_preregistration(bypass)


def test_freeze_model_input_rejects_scalar_normalization() -> None:
    class ForeignRuleValue(StrEnum):
        RETRY = "first_delivered_else_last_permitted_attempt"

    class TextSubclass(str):
        pass

    spec = PreregistrationSpec.model_validate(make_spec())
    bad_digest = spec.model_copy(
        update={"protocol_package_hash": TextSubclass(spec.protocol_package_hash)}
    )
    with pytest.raises(ProtocolViolation, match="exact runtime type"):
        freeze_preregistration(bad_digest)

    bad_allocation = spec.allocation_rule.model_copy(
        update={"retry_aggregation_rule": ForeignRuleValue.RETRY}
    )
    bad_rule = spec.model_copy(update={"allocation_rule": bad_allocation})
    with pytest.raises(ProtocolViolation, match="exact runtime type"):
        freeze_preregistration(bad_rule)


@pytest.mark.parametrize("container_kind", ["dict", "list"])
def test_freeze_rejects_cyclic_raw_containers(container_kind: str) -> None:
    spec = make_spec()
    if container_kind == "dict":
        spec["cycle"] = spec
    else:
        cycle: list[object] = []
        cycle.append(cycle)
        spec["ordered_target_identity_members"] = cycle

    with pytest.raises(ProtocolViolation, match="cyclic raw container"):
        freeze_preregistration(spec)


def test_freeze_wraps_deep_acyclic_raw_recursion() -> None:
    deeply_nested: object = []
    for _ in range(1200):
        deeply_nested = [deeply_nested]
    spec = make_spec()
    spec["ordered_target_identity_members"] = deeply_nested

    with pytest.raises(ProtocolViolation, match="nesting exceeds supported recursion depth"):
        freeze_preregistration(spec)
