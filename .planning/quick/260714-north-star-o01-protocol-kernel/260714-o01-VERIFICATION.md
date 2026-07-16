# Verification: O-01 strict preregistration and ITT protocol kernel

## Base and authority boundary

- Base commit: `42803f8de6c6d8f6a2dbd5a0d4eb0c2ed8cf5ad7`.
- Base tree: `839635e5ee732fa6a22ccba193deb27a90246efc`.
- The module always returns `authority_status=UNRATIFIED` and
  `confirmatory_authorized=false`.
- No human signature, expert pass, confidence method, valid exclusion, verified machine terminal,
  A-F gate, or external GO was created or inferred.
- The first O-01 fixed commit `0ae75a923d2f4bd25d3ec198aa3d2ec82a4735e3` / tree
  `5937ae7ced6486895233d5abd06877b800405ea8` failed three independent read-only reviews and is
  forbidden to publish. The second fixed commit `66331983eb73b3f0cf7f2d30fbde1bdee92a940c`
  / tree `f3ab3aafb9b0ea81422e511e97e34f213368d255` was also rejected after independent
  GOVERNANCE and ITT findings; its RELEASE_QUALITY PASS is invalidated. All evidence below describes
  the subsequent fix-forward. The third fixed commit `2d467ae6ef5b4f8777a2dcf3125c2abe8f91c220`
  / tree `344074d6936127510ba929ee428b567695716d86` was then rejected by two GOVERNANCE
  P1 findings; its ITT PASS is invalidated and RELEASE_QUALITY was stopped after invalidation. The
  fourth fixed commit `cc409880dfd3938266bd42d7575eda0a89ad1714` / tree
  `f5cd22c9f5bbb61dcd52c7f588e39b7f22e9e569` was rejected by one GOVERNANCE P1;
  its ITT and RELEASE_QUALITY PASS results are invalidated. The fifth fixed commit
  `536e26f04333eee8dda9b8053b15bc2cffef0f58` / tree
  `23ad364f1bdddf2996a9a4becb8343d3773df517` was rejected by all three reviews:
  GOVERNANCE P1=2/P2=1, ITT P1=3/P2=1, and RELEASE_QUALITY P1=1. The overlapping
  findings were self-replacing model containers, missing Pydantic hidden slots, model-storage dict
  subclasses that hide extra fields, and cyclic raw containers; the tree is forbidden to publish.
  The sixth fixed commit `17a2eaafd8a2b8f25c32bd692e2cd0b8f88860bf` / tree
  `87c50bf3d745dacecf845e9729e1d159bc404f7a` was also rejected by all three reviews,
  each with P1=1/P2=1. The shared P1 was an exact built-in model-storage dict containing a
  non-exact string key whose hash/equality hook could hide an extra or replace observations during
  validation. P2 findings covered premature `__class__`, metaclass `__name__`, and type-hash hooks
  on safe rejection paths plus deep cyclic or acyclic raw inputs leaking `RecursionError`.
- A seventh-iteration adversarial review (39 agents) confirmed 11 findings: 2 BLOCKER resolved via
  the backlog recorded execution split (2026-07-16) plus `canonical_schema_template_hash` binding,
  1 MAJOR reproduced bug (raw `ValidationError` leak on empty member arrays, fixed), MAJOR
  claim/coverage gaps closed with named tests, and 5 MINOR fixed. This slice's scope is **O-01a**
  per the recorded execution split; the split assigns every O-01 clause and negative vector to
  exactly one of O-01a–O-01e, and **O-01 parent closes only when O-01b–O-01e also close**. The
  schema-template obligation implemented here is a BINDING check only: `recompute_itt` requires a
  separately retained `expected_canonical_schema_template_hash` equal to the frozen bound value;
  recomputation from exact final schema bytes under the out-of-band bootstrap suite and
  cross-manifest equality land with X-00A/O-01c.

## Strict protocol and freeze assertions

- Public raw payloads are copied in one recursive pass and accept only exact JSON primitives plus
  exact built-in dicts, lists, or tuples. Container subclasses, bytes, sets, frozensets, generators,
  non-string mapping keys, embedded models, and cyclic raw containers are rejected with
  `ProtocolViolation`.
- Every rejection leaves through the uniform `ProtocolViolation` channel. Empty ordered member
  arrays are rejected by an explicit nonempty pre-check before any content model is built, and all
  derived mapping/eligibility/freeze content construction is wrapped in the same
  `ValidationError`→`ProtocolViolation` translation `_as_model` uses, so raw pydantic
  `ValidationError` can no longer leak from `freeze_preregistration`.
- `canonical_schema_template_hash` is a required strict-`Digest` spec field (identical format
  validation to sibling hash fields: exact lowercase 64-char hex), flows into the
  freeze-content hash preimage, and is exposed on `FrozenPreregistration`. Every
  `recompute_itt` call requires a separately retained
  `expected_canonical_schema_template_hash` equal to the frozen bound value; a coherent foreign
  frozen object with an attacker-recomputed expected freeze-content hash still rejects on this
  binding. This is a BINDING check only (O-01a); byte-level recomputation and cross-manifest
  equality belong to X-00A/O-01c.
- Closed models are strict, frozen, and extra-forbid. A recursive exact model-graph check detects
  root or nested `model_copy(update=extra)` bypasses before `model_dump` can erase the extra field.
  It reads only exact built-in model storage and validates every field against its declared annotation
  before invoking any container iterator or serializer, so a container cannot replace its parent
  field during validation.
- Model inputs are revalidated and recursively compared before/after validation. Exact model class,
  container type/order, scalar runtime type, and scalar value must survive unchanged; declared nested
  subclasses, private state, `0`→`False`, foreign `StrEnum`, and `str` subclasses reject.
- Every closed model must retain an exact built-in `dict` as `__dict__` and must retain both Pydantic
  extra/private storage slots. Missing slots, dict subclasses, and hidden extra keys reject; each slot
  must be exactly `None`, and falsey objects reject by identity without invoking their truthiness.
- Model storage is scanned with built-in dict operations: physical key count must equal the declared
  field count and every key must be an exact built-in string before hashing or equality comparison.
  Key subclasses cannot hide duplicate fields, mutate their parent, or carry unexamined values.
- Raw and mismatched model values use identity-only type dispatch. Rejection does not read attacker
  `__class__`, class-name metadata, or metaclass hash hooks; deep recursion is wrapped as
  `ProtocolViolation` rather than leaking `RuntimeError`/`RecursionError`.
- Target, candidate slot, run, and attempt arrays use exact field sets. `candidate_id` is rejected;
  `planned_candidate_slot_id` is the only candidate-slot ID.
- Primary IDs are globally unique and cannot equal the reserved `INITIAL_GENESIS` marker. Resolved
  target→candidate→run→attempt order is validated only by contiguous numeric ordinals and exact
  parents; lexical identifiers are never an ordering fallback.
- Planned mapping, eligibility rule, every inline eligibility input, the eligibility decision set,
  and the complete preregistration freeze use distinct SHA-256 domains. Paired hashes are recomputed
  from canonical inline content.
- Eligibility contains exactly one verifier-recomputed decision per target in resolved order, and
  every decision member's `evaluated_at` equals the freeze-level evaluation time.
- Every ITT recomputation requires a separately supplied expected freeze-content hash. A coherent
  sampling-frame swap with a recomputed inline hash still rejects against the retained external hash.
- The frozen root must be exactly `FrozenPreregistration`; a raw frozen dict is never accepted or
  normalized, even if it otherwise contains valid fields.
- Every returned ITT report carries that exact freeze-content hash, so reports from distinct freezes
  remain distinguishable after they leave the recomputation call stack.

## ITT assertions

- Attempt observations cover every permitted attempt exactly once in resolved order. Retries remain
  children of the original run and never add denominator units.
- The immutable ten-state `PIPELINE_NUMERATOR_VALUE` map is applied only to the explicitly
  unverified pipeline diagnostic. Caller-reported terminal states and a derived per-run terminal are
  not verified machine evidence.
- The non-diagnostic `pipeline_delivery_rate` numerator remains zero in O-01 because no verified
  machine terminal artifact/receipt verifier exists. The same frozen object can receive all-failed
  and all-delivered naked observations; only `diagnostic_only=true` outputs change.
- A delivered reported attempt forbids a later non-missing retry. Contaminated attempt IDs remain in
  the retained observation set and contribute no pass.
- O-01 accepts no exclusion. Every reference remains enumerated as rejected, never shrinks its
  original denominator, and forces its scoped run/candidate not-passed in unverified conditional
  diagnostics.
- Pipeline run units and expert candidate slots have separate denominators, verified under an
  asymmetric configuration (8 planned runs vs 4 candidate slots) so a population swap is
  detectable, not masked by symmetric counts.
- Eligibility decisions never shrink ITT denominators: a freeze containing an INELIGIBLE decision
  yields exactly the same run/candidate denominators as the all-eligible case (ITT retention).
- Missing verified expert evidence contributes zero; caller-submitted expert booleans are
  forbidden.
- Conditional-on-unverified-reported-delivery expert ratios are diagnostic only. Their dependence
  clusters are filtered to exactly their diagnostic denominator members and empty clusters are
  dropped.
- Candidate reported delivery uses the frozen
  `any_non_rejected_run_reported_delivered` aggregation rule. An explicit selection ledger records
  ordered selected candidate slots plus every rejected run/candidate exclusion hash considered during
  selection; both conditional ratios enumerate those hashes.
- Duplicate-cluster evidence and confidence intervals are explicitly unavailable. O-01 does not
  claim to implement the later pre-label duplicate verifier or a ratified confidence method.

## Claim-to-test index

Every claimed rejection or invariant vector above has at least one named test
(`tests/test_north_star_protocol.py` / `tests/test_north_star_itt.py`):

- Non-string raw mapping keys → `test_freeze_rejects_non_string_raw_mapping_key`.
- BaseModel embedded in raw dict/list payload → `test_freeze_rejects_embedded_model_inside_raw_payload`.
- Empty ordered member arrays reject as `ProtocolViolation`, never raw `ValidationError` →
  `test_freeze_rejects_empty_member_arrays_as_protocol_violation` (all four arrays).
- Raw container subclasses → `test_freeze_rejects_raw_container_subclasses`,
  `test_freeze_rejects_raw_subclass_without_invoking_class_hook`,
  `test_observations_reject_raw_container_subclasses`.
- Bytes at scalar/enum boundaries → `test_freeze_rejects_bytes_at_scalar_and_enum_boundaries`,
  `test_observations_reject_bytes`.
- Sets/frozensets/generators → `test_freeze_rejects_unordered_or_streaming_containers`,
  `test_observations_reject_unordered_or_streaming_containers`.
- Cyclic raw containers → `test_freeze_rejects_cyclic_raw_containers`,
  `test_observations_reject_cyclic_raw_container`.
- Deep recursion normalized to `ProtocolViolation` → `test_freeze_wraps_deep_acyclic_raw_recursion`,
  `test_observations_wrap_deep_cyclic_raw_recursion`.
- `model_copy(update=extra)` bypass → `test_freeze_rejects_model_copy_extra_field_bypass`,
  `test_observation_model_copy_extra_field_bypass_rejects`.
- Missing/falsey Pydantic hidden slots → `test_freeze_rejects_missing_hidden_model_slots`,
  `test_freeze_rejects_falsey_hidden_model_slots`, `test_observations_reject_missing_hidden_model_slots`,
  `test_observations_reject_falsey_private_state`, `test_recompute_rejects_missing_frozen_model_slots`,
  `test_recompute_rejects_falsey_frozen_extra_state`.
- Model-storage dict subclasses → `test_freeze_rejects_root_model_storage_dict_subclass`,
  `test_freeze_rejects_nested_model_storage_dict_subclass`,
  `test_observations_reject_root_model_storage_dict_subclass`,
  `test_observations_reject_nested_model_storage_dict_subclass`.
- Non-exact string storage keys / physical duplicate keys →
  `test_freeze_rejects_non_exact_model_storage_keys_without_hash_hook`,
  `test_freeze_rejects_hidden_duplicate_storage_key_by_physical_count`,
  `test_observations_reject_non_exact_storage_key_without_hash_hook`,
  `test_recompute_rejects_non_exact_frozen_storage_key_without_hash_hook`.
- Self-replacing containers → `test_freeze_rejects_dynamic_mapping_before_invoking_hook`,
  `test_freeze_rejects_dynamic_list_before_invoking_hook`,
  `test_observations_reject_dynamic_list_before_invoking_hook`.
- No attacker class metadata reads on rejection →
  `test_freeze_rejects_model_mismatch_without_reading_attacker_class_name`,
  `test_freeze_rejects_raw_value_without_invoking_type_hash_hook`,
  `test_freeze_rejects_raw_subclass_without_invoking_class_hook`.
- Declared nested model subclasses → `test_freeze_rejects_declared_nested_model_subclass_fields`,
  `test_observation_declared_model_subclass_fields_reject`.
- Scalar normalization (`0`→`False`, foreign `StrEnum`, `str` subclass) →
  `test_freeze_model_input_rejects_scalar_normalization`,
  `test_frozen_model_input_rejects_scalar_normalization`.
- Missing/extra/aliased fields, `candidate_id` alias →
  `test_freeze_rejects_missing_target_fields`,
  `test_freeze_rejects_candidate_id_alias_and_extra_fields`,
  `test_unknown_exclusion_scope_and_candidate_id_alias_reject`.
- Reserved `INITIAL_GENESIS` marker → `test_freeze_rejects_reserved_initial_genesis_as_a_primary_id`.
- Contiguous ordinal ordering / no lexical fallback →
  `test_freeze_rejects_reordered_or_gapped_targets`,
  `test_freeze_uses_protocol_ordinals_not_lexical_identifier_order`.
- Reversed/reparented candidate/run/attempt parentage →
  `test_freeze_rejects_reparented_candidate_run_and_attempt`.
- Duplicate primary IDs / allocation mismatch →
  `test_freeze_rejects_duplicate_primary_ids_and_allocation_mismatch`.
- Missing closed rule fields → `test_freeze_rejects_missing_closed_rule_fields`.
- Domain-separated hash recomputation and pinned domain literals →
  `test_freeze_recomputes_inline_domain_separated_mapping_and_eligibility`,
  `test_hash_domain_constants_are_pinned_exact_literals`.
- Submitted eligibility decisions / duplicate rule hashes →
  `test_freeze_rejects_rule_duplicates_and_does_not_accept_submitted_decisions`.
- Tampered nested hash / eligibility content / evaluation time →
  `test_recompute_rejects_tampered_nested_hash_or_eligibility_content`,
  `test_eligibility_evaluation_time_is_bound_and_recomputed`.
- External expected freeze-content hash binding →
  `test_external_expected_freeze_hash_rejects_coherent_sampling_frame_swap`,
  `test_expected_freeze_hash_rejects_bytes`, `test_report_retains_exact_preregistration_freeze_binding`.
- Canonical schema template hash binding (splice, preimage flow, malformed formats) →
  `test_external_schema_template_hash_rejects_internally_consistent_splice`,
  `test_canonical_schema_template_hash_is_bound_into_freeze_preimage`,
  `test_canonical_schema_template_hash_rejects_malformed_formats`.
- Exact frozen root model required → `test_recompute_requires_exact_frozen_root_model`.
- Attempt-observation coverage exact/ordered/unique →
  `test_attempt_observations_are_exact_closed_world_and_ordered`.
- Retries never expand denominators → `test_retry_attempts_never_expand_pipeline_denominator`.
- Closed terminal→numerator map → `test_exact_terminal_to_pipeline_numerator_map`.
- Delivered run forbids later non-missing retry → `test_delivered_run_rejects_a_later_nonmissing_retry`.
- Exclusion default-deny, denominator retention, forced not-passed →
  `test_unverified_exclusions_never_shrink_itt_populations`,
  `test_rejected_exclusions_force_reported_delivery_not_passed`.
- Distinct run/candidate populations (asymmetric 8 vs 4) and contaminated-attempt retention →
  `test_recompute_itt_keeps_run_and_candidate_populations_distinct`.
- INELIGIBLE decisions never shrink ITT denominators →
  `test_ineligible_eligibility_decision_never_shrinks_itt_denominators`.
- Expert booleans are not a public input → `test_submitted_expert_booleans_are_not_a_public_input`.
- Naked reported terminals change only diagnostics →
  `test_naked_reported_terminals_can_change_only_diagnostics`.
- Frozen candidate-level aggregation rule →
  `test_multi_run_candidate_uses_frozen_reported_delivery_aggregation_rule`.

## Commands and current results

Seventh-iteration fixed tree (this working tree):

```text
PYTHONUTF8=1 ./.venv/Scripts/python.exe -m pytest tests/test_north_star_protocol.py tests/test_north_star_itt.py -q -k "not real" -m "not real_machine"
105 passed in 0.95s

PYTHONUTF8=1 ./.venv/Scripts/python.exe -m ruff check app/core/north_star tests/test_north_star_protocol.py tests/test_north_star_itt.py
All checks passed!

PYTHONUTF8=1 ./.venv/Scripts/python.exe -m mypy app/core/north_star
Success: no issues found in 4 source files
```

The sixth fixed tree previously passed the full offline regression suite
(`2267 passed, 1 skipped, 545 deselected`); the full-suite rerun on the seventh fixed tree, three
fresh independent read-only reviews, and the PR/CI/merge/main-CI release chain remain pending.
The first full-regression attempt on the old `7f53436d` base exposed two pre-existing Windows CRLF
hard-pin failures. They were isolated and released separately through PR #84; O-01 is based on
`42803f8d`. No real-machine test, runner, CODE V process, holdout, or expert-review surface is
selected by these commands.
