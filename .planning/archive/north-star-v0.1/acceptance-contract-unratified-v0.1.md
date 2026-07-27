# North-star acceptance and statistics contract v0.1 — UNRATIFIED

status: UNRATIFIED
document_role: preregistration-template
contract_version: v0.1-draft

current_truth: `A=false; B=false; C=false; D=false; E=false; F=false; [EXPERT] unavailable`

> This file specifies a fail-closed protocol surface only. It is not a frozen confirmatory
> protocol until every human-owned field is externally signed and content-hash bound. It does not
> authorize sampling, holdout access, expert labelling, CODE V execution, a threshold, a rate, or
> a GO decision.

## Canonical minimum-claim and protocol mirror — human selections plus immutable pre-draw bindings

This document is a non-authoritative human-readable mirror of
`.planning/north-star/preregistration-manifest-schema-unratified-v0.1.json`, primarily
`$.protocol_manifest_template.contract` and `$.protocol_manifest_template.bindings`. It is never
signed as a second payload. The closed-world protocol manifest selected under that schema is the
only semantic authority; any missing, extra, duplicate, or conflicting mirror field rejects the
package. Approval records, custody records, later-stage hashes, and the final decision are not
protocol selections.

The current canonical schema shape is itself fail-closed: its object registry contains exactly 66
ordered object types; common signer verification applies to exactly 24 ordered signer classes; the
signed digest registry has exactly ten reference classes and exhaustively classifies every runtime
hash/OID/SHA, digest-or-marker and fingerprint path; the
sealed-sample manifest has exactly 26 keys; the selected `machine_execution` object has 19 keys and
its launch-ticket, durable-intent, and receipt-last required binding sets have exactly 27, 27, and 48
members plus a separate exact 33-member ACTIVE-status-CAS set; the evidence-bundle manifest has
exactly 32 keys; the release-evidence package has exactly
43 keys; and the release/evidence shared-binding intersection has exactly 25 members. The protocol
has 20 exact bindings and the authority mirror has 109 null human-owned choices. Template-key counts
include each template's `domain_tag` where present; the `27/27/48` and 33-member binding-set counts
count exact array members and contain no `domain_tag`. These are schema-shape observations, not gate evidence or
human selections; any schema-byte change requires this mirror to be regenerated and does not ratify it.

Two of the 66 registered types are the canonical authority-roster content object and canonical
authority-quorum-rule content object. Every minimum-claim, protocol, activation, and final-GO stage
must resolve its stage-bound roster/quorum hashes to those registered objects. A roster has at least
one role and at least one allowlisted human signer; every quorum role minimum and total minimum is a
positive integer, and every accepted stage signature set contains at least one valid human signature.
Every counted signature's identity, identity-proof hash, public-key fingerprint, and allowlist hash
must exactly match one same-role member in that registered stage roster. Under `AND` the valid tuple
set equals the roster tuple set; under `OR` it is a nonempty duplicate-free subset. Membership only in
the broader external role allowlist confers no stage quorum credit.
Empty rosters, empty allowlists, empty signature sets, zero quorums, or any vacuous-truth evaluation
reject rather than authorize a stage.

Two further registered types are the canonical machine-entry-inventory content object and machine-
admission receipt. They bind closed-world inventory members, raw native machine/OS evidence, external
OS-evidence attestation controls, selected inventory/admission schema and policy values, activation,
and every ticket/intent/pre-spawn/start/terminal tuple. Any drift, stale boundary, uncovered entry,
bypass path or runtime hash mismatch rejects spawn and requires a new inventory/admission/activation
chain.

```text
minimum_claim_envelope_hash_binding: null
minimum_claim_authority_signature_set_hash_binding: null
active_minimum_claim_checkpoint_hash_binding: null
acceptance_contract_template_hash_binding: null
canonical_schema_template_hash_binding: null
acceptance_contract_hash_algorithm_selection: null
canonicalization_algorithm_selection: null
signature_algorithm_selection: null
claim_envelope_template_hash_binding: null
authority_policy_template_hash_binding: null
run_code_commit_hash_binding: null
run_code_tree_hash_binding: null
run_code_release_package_hash_binding: null
evidence_schema_hash_binding: null
external_source_hash_binding: null
github_source_profile_hash_binding: null
hash_field_path_classification_registry_content_hash_binding: null
sampling_frame_commitment_hash_binding: null
machine_execution_policy_hash_binding: null
external_trust_policy_hash_binding: null
external_root_set_hash_binding: null
external_governance_anchor_hash_binding: null
protocol_timestamp_binding: null
release_control_canonicalization_algorithm_selection: null
release_control_hash_algorithm_selection: null
release_control_signature_algorithm_selection: null
eligibility_rule: null
eligibility_freeze_timestamp: null
planned_candidate_slots_per_target: null
planned_run_units_per_candidate: null
retry_mapping: null
result_independent_exclusion_rule: null
invalid_input_exclusion_reason_allowlist: null
invalid_input_exclusion_evidence_schema: null
terminal_state_table: null
itt_mapping: null
pipeline_delivery_rate_definition: null
expert_worth_reviewing_rate_itt_definition: null
expert_production_usable_rate_itt_definition: null
proportion_reporting_rule: null
candidate_content_fingerprint_algorithm: null
candidate_lineage_fingerprint_rule: null
candidate_equivalence_rule: null
candidate_duplicate_cluster_rule: null
candidate_required_label_view_object_set_rule: null
duplicate_cluster_label_aggregation_rule: null
expert_numerator_independence_rule: null
primary_endpoint_selection: null
pipeline_delivery_rate_itt_threshold: null
expert_label_rubric: null
expert_worth_reviewing_label_definition: null
expert_production_usable_label_definition: null
expert_worth_reviewing_rate_itt_threshold: null
expert_production_usable_rate_itt_threshold: null
expert_rater_identity_allowlist: null
expert_rater_count: null
expert_rater_combination_rule: null
expert_blinding_rule: null
tor_semantics: null
tor_units: null
tor_table_hash_selection: null
tor_monte_carlo_denominator: null
tor_compensator_policy: null
tor_aggregation_rule: null
tor_saturation_mapping: null
tor_compensation_failure_mapping: null
manufacturing_yield_threshold: null
confidence_method: null
cluster_method: null
confidence_level_threshold: null
repeat_policy: null
sampling_algorithm: null
sampling_frame_commitment_rule: null
sample_draw_count_rule: null
sample_draw_randomness_commitment_policy: null
holdout_protocol: null
holdout_custodian_identity: null
holdout_encryption_policy: null
holdout_acl_policy: null
holdout_access_audit_policy: null
holdout_protected_access_intent_and_terminal_receipt_policy: null
holdout_protected_action_capability_membership_proof_policy: null
holdout_audit_and_consumed_index_head_transition_policy: null
holdout_consumed_index_final_root_policy: null
holdout_pre_freeze_non_access_proof_policy: null
expert_review_time_definition: null
expert_review_time_threshold: null
productivity_baseline_definition: null
productivity_improvement_threshold: null
exit_code_table: null
analysis_plan: null
```

The expected active minimum-claim floor and current durable checkpoint hash/generation are supplied
independently to the verifier and must resolve to the canonical human-signed minimum-claim envelope/
signature-set/checkpoint chain. The external checkpoint store is append-only and advances by atomic
compare-and-swap; a stale valid floor, lower generation, fork or rollback rejects. Version lineage and
comparison are recomputed from registered bytes rather than accepted as opaque proof hashes. Every
successor must be equal or broader under the fixed comparator: scenario IDs stay exact under v0.1,
non-waivable endpoints may only expand; exclusions may only contract;
minimum counts and thresholds may not fall; specification ranges use explicit units and one of the
canonical comparator modes. Unknown, incomparable, or narrower scope is exploratory-only and cannot
become the active floor or satisfy A/F. The selected protocol claim must prove equal-or-broader against
that external active floor; a fresh narrow protocol plus a fresh holdout is still rejected.

The actual sample or holdout manifest hash is deliberately absent above: it does not exist until the
independent custodian performs the signed draw. The expected external-governance-anchor hash and its
bootstrap verification suite are supplied out of band before any protocol bytes; a protocol or signer
cannot select them. Protocol approvals are domain-separated message objects under
`$.protocol_role_approval_message_template`, each followed by a detached signature record. Their
ordered message/record members are closed into the separate
`$.protocol_authority_signature_set_content_template`, whose hash is external to its own preimage.
Custody is never a member of that set. The minimum protocol and activation role roster is claim, optical-expert,
manufacturing/statistics, and machine-execution authority, subject to the human-signed canonical
roster, quorum, and role-separation policy. The roster and quorum are registered immutable content
objects rather than opaque hashes. The selected within-role rule is exactly `AND` (every allowlisted
member required by that role) or `OR` (at least one allowlisted member required by that role); all
per-role and total minima are positive, and at least one valid human signature is mandatory.

The verifier also receives the expected canonical-schema-template hash and bootstrap
canonicalization/hash suite out of band. It recomputes
`H_bootstrap(UTF8(atelier.north-star.canonical-schema-template.v0.1) || 0x00 ||
CANONICALIZE_bootstrap(exact final schema-template JSON))` over the exact final parsed top-level
template, including literal runtime `null` placeholders. The external governance anchor, protocol
manifest binding, protocol package, sealed-sample manifest, activation manifest, and activation
package must all carry that same recomputed hash. Every registered object, nested content object,
and typed evidence leaf is parsed under that one schema. A recursive, missing, ambiguous,
signer-selected, package-selected, or unequal schema hash rejects; no object may splice a different
schema into an otherwise valid chain.

## Immutable dependency DAG

The finite DAG has two explicit external prerequisite events. X-00A is an operational predicate over
the already registered canonical external-governance anchor, its out-of-band expected hash/config,
and live official repository capability observations; it introduces no receipt or signer class. It
freezes the exact canonical schema bytes/hash, goal instance/genesis, immutable anchor machine-control
fields and release-governance profile. X-00B is the existing canonical floor/signature-set/current-
checkpoint tuple and activates the minimum-claim floor/checkpoint without a new object type.
Generic offline O/M implementation may proceed in parallel with X-00A, but machine-policy closure and
O-07 require X-00A. A missing event is `BLOCKED_WAIT_EXTERNAL`, never implicit success: the agent emits
one idempotent NEED keyed by `{goal_instance_id,event_id,canonical_schema_template_hash}`, continues
independent ready nodes, never self-signs or blindly retries, and re-evaluates only when an externally
controlled anchor/configuration/capability input or the X-00B canonical tuple changes.

0. **X-00A schema/anchor/authority freeze:** the external governance, machine-execution and
   repository-owner authorities supply the out-of-band expected schema/goal/anchor machine-control
   inputs; the verifier independently recomputes the final schema and canonical anchor bytes and
   compares them to those inputs,
   and an organization-owned GitHub source profile with authorized Enterprise Cloud audit-log, one
   out-of-band verified credential principal used by every exchange, full ruleset `bypass_actors`
   visibility, classic branch-protection 200/admin-read and merge-without-bypass authority. v0.1
   requires nonempty strict/up-to-date checks, direct merge commits allowed, merge queue absent, and
   no linear-history, merge-queue, Enterprise-parent or ruleset-workflow rule. Because GitHub's
   `mergePullRequest` has no expected-base or policy-snapshot CAS, the profile must additionally bind
   an independently trusted provider-side, fail-closed, irrevocable single-use lease that freezes both
   every policy-administration surface and every `refs/heads/main` update surface. Its signed sequence
   is acquisition before the policy window, snapshot binding after both policy/queue passes, exact-
   mutation admission after final CI/clientMutationId/body materialization and before send, then
   terminal closure after the bound merge; the merge request commits the snapshot and admission
   leaf, and the terminal leaf proves zero policy mutations, zero foreign main updates, and exactly one
   bound merge. Absence of this external primitive is `BLOCKED_WAIT_EXTERNAL`; strict checks,
   `expectedHeadOid`, stable polling, and post-merge audit cannot substitute. Post-merge main/push
   workflows come from a separate externally anchored release policy. The bound enterprise stream
   must prove enterprise→organization membership, configuration/destination/partition and a provider-
   backed event-time watermark. USER ownership, HTTP 403, plan unavailability, partial visibility,
   local-only high water or a missing provider watermark reject and are not an empty policy/audit.
   Actual machine-entry inventory,
   admission-boundary selection and enforcement are H-01/H-03/R-00 records, not X-00A assertions.
1. **X-00B minimum-claim floor:** after X-00A, the externally anchored minimum-claim authority signs the immutable floor
   through its own message, detached record and signature set. A successor becomes active only after
   complete deterministic lineage replay, the canonical equal-or-broader comparison pass, and one
   successful compare-and-swap of the external durable high-water checkpoint.
2. **Run-code release, then protocol convergence:** independently of when X-00B completes, O-07 freezes the reviewed PR-head tree, obtains three
   independent signed scope reviews, required PR CI, an expected-head compare-and-swap merge, matching
   main CI, and a post-merge attestation, then emits the canonical detached RUN_CODE_RELEASE package
   whose executable commit is the accepted main merge commit and whose tree is byte-identical to the
   reviewed PR-head tree. Only after all O/M verifier/importer code is released by that package may
   required authorities sign fixed approval messages over the exact protocol package and released
   run-code commit/tree; an
   explicit ordered signature-set object binds package, external governance anchor, roster, quorum,
   separation, common trust and every approval message/signature record before
   any confirmatory draw. H-01 and H-02 are independent signature chains over the same immutable
   protocol-package bytes; both must close.
3. **Draw:** the independent custodian applies the signed sampling frame/algorithm in isolation and
   creates the one canonical sealed-sample manifest only after validating the protocol package and
   signature set. It then produces unsigned draw content, a signer-identity-bearing signature message,
   a detached common-trust-verified signature record over that message hash, and an envelope. The
   content binds protocol/signature-set hashes, batch/draw IDs, source snapshot, randomness
   commitment/transcript, actual sealed-manifest hash, timestamp, and a non-self-referential audit
   transition. The draw content and resolved manifest must be byte-equal for ratification instance,
   confirmatory batch, draw event, protocol package/signature set, sampling frame/source/algorithm,
   entropy commitment, target distribution/count, and the recomputed sealed-manifest hash.
4. **Activation:** before any unseal, view, run, label, or export, required authorities sign a new
   activation package and explicit signature set binding the protocol signatures, draw envelope,
   actual manifest, initial custody-audit and consumed-capability roots, machine admission,
   activation ID/expiry, allowed action/object set, and membership-verifiable single-use capability
   root. The activation initial audit root equals the signed draw content's new audit root; its initial
   consumed root is the canonical activation/capability-set genesis. Every capability action/object/
   time scope must be a subset of the activation scope. The activation package must resolve the draw
   envelope through its unsigned content to that same manifest, then exactly match ratification,
   batch, protocol/signature set, draw envelope, manifest, target distribution, and target count.
   Cross-batch or cross-draw activation is rejected even when a referenced hash is otherwise valid.
   It does not mutate the protocol or draw object.
5. **Protected access:** a common-trust-verified custody broker proves capability membership,
   atomically compares both prior roots, consumes the nonce, and durably publishes a signed intent
   envelope with deterministic new audit/index roots before the action. It publishes a separately
   signed terminal envelope only after the result; the terminal prior roots must equal the intent new
   roots. Every envelope resolves one exact content/transition/message/record chain with matching
   instance, batch, event, signer and scope; A-content/B-signature splicing rejects. The first intent
   starts from the activation roots and each later intent starts from the current replayed roots. A
   signed intent without terminal remains provably consumed+incomplete; no nonce is reusable. After
   candidate production and before the first label intent, exactly one registered pre-label binding
   manifest describes every planned slot as available or permanently unavailable, along with actual
   candidate bytes, required label views, source/derivation lineage, and the globally recomputed unique
   equivalence partition. The manifest alone is not a freeze: a separately allowlisted custody broker
   must commit it through one accepted compare-and-swap receipt, a registered transition containing an
   inline audit-event payload, a detached signature message/record, and the one registered pre-label
   freeze envelope for the activation and batch. Each protected run intent is likewise joined by an
   exact per-attempt link to its launch
   ticket, durable machine intent, machine receipt, and protected terminal envelope, or to one retained
   consumed-incomplete disposition.
6. **Release and final decision:** after A–E, build and validate a release-evidence package with no
   final-decision bytes; that valid detached package closes only `F_release_evidence_complete`. The
   final-GO authority then signs a separate decision statement through canonical per-signer signature-
   message, signature-record and signature-set objects over that package hash. Gate F remains the
   release-evidence predicate; only a valid quorum-approved `GO` additionally completes the Goal.

### v0.1 change and migration semantics

The minimum-claim floor is run-code-independent only after X-00A freezes the exact schema, external
anchor, goal instance and genesis. A code/tree-only change with all of those bytes and the active
floor unchanged may retain the current floor/checkpoint, but requires fresh O-07, H-01, H-02, H-03
and every downstream object. Any schema, anchor or goal-instance byte change invalidates the floor,
minimum-claim signature set, checkpoint, protocol, draw, activation and all descendants and requires
a new goal genesis, anchor, floor and checkpoint genesis. v0.1 has no in-place schema migration or
anchor rotation. Any invalidating change after draw permanently makes that draw exploratory and
requires a new never-observed sealed holdout.

## Frozen identity schema

After the custodian draw, the sealed manifest must atomically assign the opaque target, seed, patent,
candidate-slot, run, and attempt identities and parent mappings before any unseal, view, run, outcome,
or label is visible. Before protocol signature and draw, only the sampling frame, eligibility rule,
population counts and allocation rules are frozen. Byte-derived candidate identity is a separate
post-production/pre-label freeze and is never self-declared by an expert label:

- `target_id`: one eligible target in the representative distribution.
- `seed_cluster_id`: the preregistered dependence cluster for seeds related by prescription,
  provenance, or derivation.
- `patent_family_id`: the externally sourced family identity used by the independence rule.
- `planned_candidate_slot_id`: the sole identifier for one planned candidate slot under exactly one
  target and seed cluster; `candidate_id` is not an accepted alias.
- `candidate_content_fingerprint`: the pre-label manifest's protocol-hash recomputation from the exact
  inline semantic-content set. Its nonempty, contiguous semantic components are deterministically
  extracted from actual candidate artifact bytes under the signed fingerprint algorithm and canonical
  candidate-representation schema; the candidate-byte-set root remains a separate binding.
- `candidate_lineage_fingerprint`: the pre-label manifest's recomputation from the planned slot,
  target/seed/patent parents, source run/attempt/machine evidence, and derivation graph.
- `candidate_equivalence_cluster_id`: the deterministic hash of the complete equivalence class,
  recomputed once over all available candidates under the preregistered equivalence and duplicate rules.
- `run_id`: one planned denominator run unit under exactly one candidate; it is not owned by an attempt.
- `attempt_id`: one immutable initial or retry attempt under exactly one `run_id`, with a unique
  monotonic sequence fixed by the sealed-manifest retry mapping.

The canonical `protocol_manifest_hard_invariants` are bound by the schema hash and cannot be weakened
by a non-null human selection. The 26-key sealed manifest carries both the exact inline
`planned_identity_mapping_content` and its paired `planned_identity_mapping_content_hash` over the
typed target, candidate-slot, run, and attempt member arrays. Its unique domain is
`atelier.north-star.planned-identity-mapping-content.v0.1`; its formula is the protocol hash of the
domain, separator byte, and canonical exact content excluding `domain_tag`. Targets are ordered by
contiguous zero-based draw ordinal; candidates by resolved target order then contiguous slot ordinal;
runs by resolved candidate order then contiguous run ordinal; and attempts by resolved run order then
contiguous attempt sequence. Counts must equal array lengths and signed allocation counts. Identifier
lexical order is never a fallback.

The same manifest carries the exact inline `eligibility_decision_set_content` beside its paired
`eligibility_decision_set_content_hash`. The set has domain
`atelier.north-star.eligibility-decision-set-content.v0.1`, the same explicit hash formula, and exactly
one typed decision per target in resolved target order. Every decision member also carries its exact
inline `eligibility_input_content` and derived content hash; the verifier executes the signed rule over
that immutable source input rather than accepting a submitted eligibility result. Its eligibility-rule
hash is itself uniquely derived from the exact selected protocol rule under
`atelier.north-star.eligibility-rule-content.v0.1`. Both nested contents exactly match the sealed
manifest and draw chain for goal, ratification, batch, draw, protocol, and signature set; opaque roots,
wrong ordering, missing bytes, or cross-batch content reject. IDs are never renumbered, recycled,
merged, or dropped after results. Missing or conflicting identity is an ITT not-passed unit, not an
exclusion.

After candidate production, exactly one immutable
`candidate_prelabel_binding_manifest` covers the full planned candidate-slot set as duplicate-free,
disjoint available and unavailable sets in planned order. An unavailable slot can never later become
available or contribute to an expert numerator. For each available slot the manifest binds and
recomputes target/seed/patent parents, artifact membership, actual candidate-byte root, the nonempty
required label-view object set and membership proofs, source run/attempt/machine evidence, derivation,
the exact inline semantic-content and lineage-fingerprint contents, their derived fingerprints, and
the deterministic equivalence-cluster ID. Semantic components must be nonempty, ordinal-contiguous,
and extracted from actual candidate bytes; their preimage excludes slot/batch IDs, paths, timestamps,
hosts, receipts, labels, outcomes, and thresholds. The mandatory equivalence floor joins candidates
with the same candidate-byte-set root **or** the same semantic content fingerprint. Human-selected
equivalence and duplicate rules may only add edges; the verifier takes the equivalence closure and
recomputes one unique, complete, pairwise-disjoint partition over every available slot. Clusters are
ordered by their minimum resolved slot order, not by an ID or hash, and each cluster ID is the hash of
its complete cluster content without the ID in its own preimage. No producer-submitted partition or
cluster assignment is trusted.

The one freeze is an atomic custody-broker transition after every run intent is terminal or retained
consumed-incomplete and every planned run unit has a frozen terminal state. The accepted CAS receipt
must match the transition's expected/committed audit sequences, heads, consumed root, manifest, link
set, store, and operation; the audit sequence advances exactly one while the consumed-capability root
is unchanged. The broker's detached signature is common-trust and allowlist verified, cannot predate
the CAS commit, and every label intent must bind the resulting freeze envelope and follow its signed
timestamp. A second freeze, a run after freeze, an unsigned transition, an unaccepted CAS, or an
overwrite/extension/repair rejects.

## ITT denominator and terminal semantics

Candidate slots and run units are two distinct frozen analysis populations and are never arithmetically
combined into one heterogeneous denominator. Every planned member of each population is retained:

- `pipeline_delivery_rate` = delivered planned run units / all preregistered planned run units.
- `expert_worth_reviewing_rate_itt` = independent candidate-equivalence clusters with a valid
  authorized signed worth-reviewing pass / all preregistered planned candidate slots.
- `expert_production_usable_rate_itt` = independent candidate-equivalence clusters with a valid
  authorized signed production-usable pass / all preregistered planned candidate slots.
- `manufacturing_yield_qualified` uses only the separately ratified TOR units, Monte Carlo denominator,
  compensator policy, aggregation rule, saturation mapping, compensation-failure mapping, and
  threshold; otherwise it is unavailable.

Every duplicate slot remains in both expert-rate denominators, while one equivalence cluster may
contribute at most one independent numerator under the human-ratified aggregation rule. Missing,
undelivered, or unlabelled candidate slots have numerator contribution zero in both expert rates.
The ratified expert-rater allowlist is a nonempty duplicate-free ordered array of identity / identity-
proof-hash / public-key-fingerprint tuples, its bootstrap hash must equal the external anchor,
`expert_rater_count` is an integer at least one and equals that array length, and every counted label
signature tuple must match exactly one member of that same array while carrying the same anchored
allowlist hash. Both expert-rate thresholds are strictly greater than zero and at most one. Gate D
additionally requires at least one candidate whose distinct valid envelope signer set equals the
complete protocol rater tuple array and whose two dimensions are recomputed under the signed
combination rule. Missing, extra, duplicate, outside-allowlist or cross-candidate envelopes force
that candidate to zero in both expert ITT numerators. Each valid envelope carries
both independent label dimensions in the same signed content and envelope. Zero raters, a zero
threshold, or an empty valid-label set therefore forces D false even when an arithmetic rate would
equal its threshold.
Retry attempts map to the original planned run unit and never create denominator members. Attempt
records are immutable and never reused, reparented or moved across runs. The run's trusted terminal
state is written once only after the frozen retry/aggregation rule has consumed all required attempt
records; a contaminated attempt remains preserved and cannot rewrite an attempt or finalized run. Every
reported proportion must carry its raw numerator, denominator, enumerated exclusions with evidence
hashes, dependence cluster, duplicate-cluster membership, raw-slot view, independent-cluster view,
and confidence interval. The human-ratified primary endpoint
may combine pass conditions logically, but it cannot add unlike populations or hide any component
rate. Terminal states within each population are mutually exclusive. The following mapping is
mandatory when the human-owned ITT table is ratified:

| Observed unit condition | Mandatory main-analysis treatment |
|---|---|
| blocked | stays in denominator; not passed |
| degraded | stays in denominator; not passed |
| failed | stays in denominator; not passed |
| non-converged | stays in denominator; not passed |
| missing | stays in denominator; not passed |
| unlabelled | stays in denominator; not passed |
| undelivered | stays in denominator; not passed |
| saturated | stays in denominator; not passed; manufacturing metric unavailable where the TOR contract requires it |
| compensation-failed | stays in denominator; not passed |
| contaminated attempt | immutable attempt and raw evidence stay retained; excluded from trusted execution evidence, while its original planned run unit stays in ITT and is not passed unless the frozen retry mapping later supplies a trusted terminal result |

No runtime status, successful delivery, parseable artifact, or machine metric is an expert label.
Every retry points back to its original planned unit; it neither creates a new denominator nor
erases earlier attempts. An exclusion is permitted only when all four conditions hold: its reason
was enumerated before contract signature; it is result-independent; independently hashed raw evidence
proves the immutable input itself invalid; and a frozen rule plus bound official machine receipt
recomputes `INVALID_INPUT` before outcome access. The registered domain-separated exclusion record
binds goal, active checkpoint/floor, protocol package, batch, sealed manifest, planned-membership root,
scope/member ID, reason allowlist, evidence schema, immutable input/raw evidence, the protected input-
validation terminal envelope, automatic rule input/output, machine receipt, current pre-outcome audit
head, evaluation time and fixed decision. Cross-batch or cross-protocol replay rejects; all four conditions are
mandatory and are not human-overridable. Missing, ambiguous, unavailable, or
conflicting exclusion evidence keeps the unit in ITT as not passed. Conditional-on-delivered,
complete-case, and per-success rates are diagnostics only and can never satisfy a north-star gate.

## Endpoints, labels, TOR, and analysis

The contract must ratify endpoint units and directionality, the two independent label dimensions
`expert_worth_reviewing` and `expert_production_usable`, the authorized human-rater count,
blinding/combination policy, label rubric, disagreement treatment, `tor_semantics`, `tor_units`,
`tor_table_hash_selection`, `tor_monte_carlo_denominator`, `tor_compensator_policy`,
`tor_aggregation_rule`, `tor_saturation_mapping`, `tor_compensation_failure_mapping`, repeat
aggregation, cluster-aware confidence method, sealed-holdout
analysis, expert review time, and productivity baseline. Every
actual label record must come from an externally authenticated, allowlisted optical expert and bind
the unique pre-label manifest, planned slot, candidate artifact and byte-set roots, required label-
view set, content/lineage fingerprints, equivalence-cluster ID, rubric bytes, label
dimension, timestamp, protected label intent/terminal, and signature. The human-owned
`candidate_required_label_view_object_set_rule` remains null until external ratification. Once
ratified, the label intent must request exactly the frozen candidate-specific required-view set plus
the protocol-fixed rubric/support objects, and the terminal must prove all were accessed by the same
final expert signer. The label cannot declare, replace, or repair candidate bytes, lineage, or cluster
identity. The duplicate-cluster aggregation rule must prevent one
equivalent candidate from contributing more than one independent numerator while preserving every
planned slot in the denominator. The contract—not this
template—must decide whether one or multiple raters are required and how multiple ratings combine.

Before that intent, its exact inline prior-exposure history must replay every same-rater `unseal`,
`view`, `export`, and `label` event that intersects the candidate's required views or any cluster-peer
object, from activation genesis through the audit cutoff. Missing terminal evidence or a retained
consumed-incomplete prior exposure is unknown exposure and invalidates the confirmatory label. The
signed pre-label freeze must precede the rater's first candidate exposure, and every earlier object
must be expressly permitted by the signed blinding rule. The same intent also carries an inline blank-
form attestation bound to the request/event/intent, slot, rater, view root, rubric, entry session,
trusted surface identity and binary, and form schema; both label dimensions are `UNSET` and the system-
suggestion root is the canonical empty-set root. System or AI prefilled outcome/recommendation bytes in
that attested surface reject, while no claim is made about unverifiable external human cognition.

Required label views and rubric support are then recorded once each as durable, timestamped access
events in protocol order, with no omitted, extra, or cross-candidate object. A separate inline human-
entry event binds the same session, surface, slot, intent, rater, view/rubric evidence and both entered
values; its actor must equal the requester and common-trust-verified expert signer. The verifier enforces
the exact timeline `freeze signed_timestamp < blank-form created_at <= label-intent written_timestamp <
review_started_timestamp <= every required accessed_at <= human-entry event_timestamp <=
review_completed_timestamp <= expert-signature signed_timestamp <= label-terminal timestamp <=
terminal-transition and broker-signature timestamps`. Missing or reordered evidence contributes zero
to both ITT expert numerators.

Review time begins and ends only at ratified auditable events; missing timestamps are unavailable,
not zero. The productivity comparison uses the ratified baseline population and the same non-waivable
quality endpoints. Faster review or more delivered artifacts cannot compensate for an endpoint,
label, TOR, or ITT failure.

The exit-code table must reserve mutually exclusive meanings for success, ITT not-passed,
invalid protocol, missing authority, custody violation, and machine conflict. Until the table anchor
is ratified, every confirmatory launcher must refuse to start.

## Holdout custody and protected access

At minimum, the holdout custodian is independent of every development, tuning, and execution role,
including the author, target selector, analyst, and launcher operator. Any additional separation
from claim authorities, expert raters, or the final-GO signer is a human-owned
`role_separation_policy` choice; this template does not select a rater count or add an unsigned
authority rule. After the protocol signatures exist, the custodian applies the signed sampling
algorithm in an isolated out-of-workspace system, immediately seals the drawn manifest and holdout
under encryption and explicit ACL, and signs the draw receipt. An append-only access audit starts
before the draw. Before authorized activation, the execution agent may receive only the target
distribution, count, protocol/draw receipt hashes, and sealed-manifest hash—never target identities,
seed identities, prescriptions, or result-bearing content. No holdout or confirmatory sample is
drawn, opened, inspected, labelled, or created by this task.

Every unseal, view, run, label, or export is a protected action and requires a distinct capability
authorized by the activation package. Its leaf hash, action/requester/expiry/object scope and
membership proof must verify against the signed activation capability root. The custody broker must
atomically compare the prior custody-audit head and consumed-capability-index root, prove the
capability absent from the prior consumed index, consume the one-time nonce, and durably publish a
signed intent envelope before granting access. The literal `nonce_consumed=true` intent contains
deterministically derived new audit and consumed-index roots. The signed terminal envelope follows
the action and binds the matching intent, requester, action/object set, pre/post hashes, result,
sequence and another deterministic transition; both terminal prior roots equal the intent new roots.
A crash after a signed intent leaves that envelope in the final consumed-index root as permanently
`consumed+incomplete`; it cannot be success and neither failure nor crash permits nonce reuse.
Duplicate request/event/intent/receipt IDs, non-monotonic sequence, head/root mismatch, or terminal-
without-intent rejects the batch. Any unrecorded access, required role overlap, ACL ambiguity,
decryption outside the approved
environment, replay, or mismatch invalidates the affected confirmatory batch. If the environment
cannot technically prove that the holdout was unreadable before freeze, it is exploratory only and
a NEED-human package is required; no policy prose or retrospective statement can promote it to
confirmatory.

Run and label actions use exact domain-separated action/phase hash sets rather than opaque generic
roots. A run intent freezes run/attempt, host, canonical launcher, lease broker/instance, complete
command, input set, and toolchain pins; its terminal freezes ticket, durable intent, machine receipt,
terminal artifact manifest, monitor snapshot, and zero-state proof. A label intent freezes the unique
pre-label manifest, planned slot, artifact manifest, candidate-byte root, required-view root, and
rubric. Missing, extra, cross-slot, cross-machine, or wrong-phase members reject.

## Pre-draw custody and trusted review clocks

The custody genesis is fixed by the external governance anchor before draw and is committed by one
closed-world atomic durable store initialization receipt. Its store attester has a distinct externally
anchored allowlist and common-trust signature class; it is not implicitly a custody broker. The genesis
content cannot depend on the later commit leaf, while the commit leaf binds the genesis and a signed
pre-draw trusted-clock leaf. There is no opaque detached durability proof: the raw initialization
request, raw atomic receipt, parser profile, store attester proof, signature, wall time and monotonic
counter are the recomputable source.

Both pre-draw and review clocks carry raw attestation bytes, parser profile, policy, clock instance,
validity interval, attester identity/proof/fingerprint/allowlist, a uniquely domain-separated message
hash, detached signature, and one unambiguous signed-record hash. START and COMPLETE review boundary
time leaves use their own allowlisted source attester, bind exact acyclic event subjects and raw event
bytes, and must resolve the same signed review clock. Store, clock and event-time attesters are checked
under the common external trust roots, expiry, revocation, key-use and proof-of-possession rules; none
may be substituted by the expert rater.

## Machine execution and terminal-order invariant

The selected `machine_execution` object must have exactly the canonical 19 keys, in schema order,
with no aliases or extra keys. Its snapshot subjects must be exactly `runner`, `codev`, `codevm`,
`p18_owner`, `global_owner`, `per_call_owner`, `launched_subtree`, and `unknown_carrier`; phases must
be exactly `pre_launch`, `during_run`, and `post_run`. Both arrays preserve order and contain no
duplicates. `post_run_snapshot_and_monitor` means the completed post-run snapshot plus
conflict-monitor result.

Each of the 19 selected values must validate against the canonical typed value template and fixed
constants. The non-waivable minimum covers one canonical launcher for every discovered entry,
machine-wide atomic lease, single-use content-bound default-deny ticket, bypass/direct-spawn rejection,
official executable/macro/version/input pins, durable pre-spawn intent, continuous conflict monitor,
signed pure-offline allowlist, owned-subtree-only termination, immutable contaminated-attempt raw/log
retention, and receipt-last zero-state release. `machine_execution_policy_hash` has the unique domain
`atelier.north-star.machine-execution-policy.v0.1` and is computed over the exact selected 19-key
subobject before the protocol-manifest hash; missing, null, alias, extra or weaker values reject.

Within those 19 policy values, `launch_ticket_policy.required_ticket_binding_set` has exactly 27
ordered members, `durable_intent_policy.required_intent_binding_set` has exactly 27, and
`receipt_last_policy.required_receipt_binding_set` has exactly 48. The receipt policy additionally
has an exact 33-member ACTIVE-status-CAS binding set. The `27/27/48` shape is not a
replacement for the 19-key machine-policy shape: it is the exact nested tuple coverage for ticket,
pre-spawn durable intent, and terminal receipt. The ticket binds batch/activation/signatures,
capability/proof/protected intent, host/launcher/lease/broker, run/attempt, command/input/pins,
execution-tuple hash, validity interval and nonce; the intent adds the ticket hash/nonce/expiry,
durable-store root and write timestamp; the receipt adds process ownership and timing, snapshots,
terminal artifacts/state, audit/index transitions, durable pre-spawn/process-start receipts and zero-
state proof. Missing, reordered, aliased, or count-drifted membership rejects before any success use.

The machine lease is held by an externally anchored durable transactional lease/journal authority and
an attested canonical broker that is not one of the zero-state subjects. The authority exclusively owns
lease state, release-operation state, and the durable journal. Its root, store identity, native receipt-
attester allowlist, acquisition/journal/barrier/atomic-receipt parsers, atomic receipt schema, and
journal-store policy are fixed in the external governance anchor and must byte-equal the selected
19-key machine policy and every runtime leaf. A Global named mutex or `ProgramData` ACL is only optional
defense in depth and cannot replace that authority.
Every barrier post-state root and per-operation terminal lease-state root uses the explicit
transition/accumulator-root reference class. The verifier resolves the anchor-pinned authority-state
accumulator policy and independently recomputes the root from the complete proof inside the raw
native barrier response; a signature, partial query projection, equality between two opaque root
fields, or parser assertion is insufficient.
Every native atomic-acquisition, OS-acquisition, barrier, journal-store, atomic-release, and OS-release
response carries an authority signature over its exact source-specific acyclic semantic projection.
That projection covers its batch/activation/protected-run tuple, run/attempt, host/broker/lease and
source-specific operation/transaction, roots, outcome and linearization. Acquisition covers its
pre-acquisition barrier; the barrier signs its complete ordered authority-wide operation members with
their transition and prepared/committed references; each journal/atomic/OS projection signs its own
transition, operation, transaction, roots, prior journal, raw-entry, and OS-result/time bindings. Only
the canonical per-source self-container, signature/control,
parser/schema/identity and genuinely later fields are excluded. A `_leaf_hash` suffix is never an
exclusion rule. Each raw request/content hash is committed by its named signed response, and every raw
authority or OS response field resolves exactly one signature projection.
The six raw-response source kinds use six distinct versioned signature domains. Verification input is
exactly `UTF8(source-domain) || 0x00 || CANONICALIZE_protocol(ordered required projection)`, with the
source key selecting the same required/excluded/schema/domain maps; cross-source or cross-version replay
rejects even when two projections happen to carry identical values.
`runner` means a run child or competing runner, while `global_owner` and `per_call_owner` are run or
legacy owner carriers, not the lease broker. The same `lease_instance_id` remains held by exactly one
broker through zero-state proof and durable receipt. The only valid terminal order is:

`terminal_artifacts → post_run_snapshot_and_monitor → zero_state_proof → ACTIVE status CAS →
durable_machine_terminal_receipt → protected_access_terminal_envelope → lease_release_transition →
PREPARED release journal → OS release + OS_RELEASE_COMMITTED journal as one atomic lease-authority
transaction → RELEASED status CAS →
durable_lease_release_receipt`.

The first seven subjects must be zero or absent and `unknown_carrier` must be absent before receipt.
Unknown, unreadable, duplicate, reordered, missing, weaker, or aliased state retains the lease and
fails closed. A terminal artifact or monitored-subject change after zero proof and before ACTIVE CAS
invalidates the proof and requires a fresh monitor/zero pair. The same change after ACTIVE CAS but
before the full receipt must abort under `ACTIVE_CAS_ONLY`, recover, abandon the ACTIVE status,
safety-release, and remain consumed-incomplete; it cannot rewrite the pre-status payload or emit a
normal receipt. Receipt invalidation followed by monitor/zero remains the
`FULL_RECEIPT_INVALIDATED` frontier and cannot alias the no-status frontier.
The external machine-receipt status index must atomically replay ABSENT→ACTIVE and, on the normal
release path, ACTIVE→RELEASED only after the durable OS-release journal. Crash recovery uses immutable
attempts, explicit generation/predecessor markers, typed monitor and zero-state wrappers, exact
wrapper/payload/evidence/time-leaf identity equality, and never upgrades consumed-incomplete evidence
to success. The final receipt binds both journal leaves and the atomic release-status CAS before the
broker may complete release.
A `PRE_LEASE` crash has one unique pre-chain intent anchor: last lifecycle state is
`INTENT_CONSUMED`, last sequence is literal `-1`, last kind is
`PROTECTED_ACCESS_INTENT_ENVELOPE`, and its selected last-member source is the same crash record's
exact-type protected intent-envelope hash. Last-member sources use three fixed, non-union paths: the
existing intent-envelope path is selectable only for `PROTECTED_ACCESS_INTENT_ENVELOPE`; the terminal-
envelope-or-marker path has exact expected type `protected_access_terminal_envelope` and is real only
for `PROTECTED_ACCESS_TERMINAL_ENVELOPE`; the typed-evidence/proof-or-marker path is real for every
other last-member kind. PRE_LEASE uses `NO_PROTECTED_TERMINAL_LAST_MEMBER` plus
`NO_TYPED_LEAF_LAST_MEMBER`; PROTECTED_TERMINAL uses the resolved terminal envelope plus
`NO_TYPED_LEAF_LAST_MEMBER`; every other frontier uses `NO_PROTECTED_TERMINAL_LAST_MEMBER` plus the
last replayed typed leaf. No fixed path may conditionally change object type or reference class.
Machine partial-chain members use the same discipline: the protected-terminal carrier has one exact
registered object type, the typed carrier has one typed-evidence/proof reference class, exactly one is
real by member kind, and the other equals `NO_PROTECTED_TERMINAL_PARTIAL_CHAIN_MEMBER` or
`NO_TYPED_LEAF_PARTIAL_CHAIN_MEMBER`. Thus a PROTECTED_TERMINAL crash replays the registered terminal
carrier without passing through a field named or classified as a typed leaf. Each of the other 24
member kinds resolves through one exhaustive kind-keyed canonical typed template or signed policy
schema/domain/phase entry; the resolved object must repeat the same batch, activation, execution tuple,
run, attempt, host, broker, lease and transition-specific bindings. `POST_RUN_SNAPSHOT_AND_MONITOR` and
`ZERO_STATE_PROOF` select disjoint normal/reproof versus post-crash recovery schemas from the replayed
from-state. A real leaf from any other member kind rejects even when it belongs to the same broad
typed-evidence/proof reference class and all self-reported kind/state/frontier labels agree. The PRE_LEASE anchor is
not a machine-chain member. The crash record itself is the first and
only prefix member at creation, at sequence `0`, replaying
`INTENT_CONSUMED -> CRASH_CONSUMED_INCOMPLETE`; null, zero, any other negative or positive anchor
sequence, or any claimed prior machine member rejects.
The selected lease authority must atomically compare/release the lease and append the durable
`OS_RELEASE_COMMITTED` journal entry under one operation ID, or commit neither. On restart a PREPARED
operation may advance only if the same authority atomically terminalizes that exact operation as
irrevocable `ABORTED_FINAL` with the lease still `HELD`, or proves it was already `COMMITTED` with the
exact journal durable. A transient `NOT_COMMITTED`, pending, unknown, partial, unqueryable, or released-
but-unjournalled result keeps machine admission closed. Every new acquisition consumes a complete
authority-wide, cross-batch/host/broker barrier proving zero unresolved PREPARED operations in the same
atomic authority transaction that inserts the new lease; an earlier empty observation is not evidence.

Machine execution is not valid merely because those machine artifacts agree with each other. Before
spawn, the launch ticket and durable machine intent must resolve the already signed protected `run`
intent and carry its activation package/signature set, capability, membership proof, run, attempt,
host, launcher, broker, lease, command, input, and pin tuple exactly. The machine terminal receipt and
protected terminal envelope must preserve the same tuple. A registered
`protected_run_machine_attempt_link_set_manifest` then orders every run attempt by planned run order
and attempt sequence and proves a complete forward-and-reverse bijection: every protected run intent
has exactly one terminal chain or retained `CONSUMED_INCOMPLETE` member, and every machine receipt is
linked exactly once. An orphan, duplicate, cross-capability, cross-attempt, or cross-batch machine
chain cannot contribute delivery, optical, repeat, manufacturing, or any other success evidence.

## Confirmatory invalidation rule

A substantive change to the contract, claim envelope, code commit/tree, rubric, TOR, eligibility,
denominator, threshold, evidence schema, retry mapping, exclusion rule, or analysis plan invalidates
the affected confirmatory batch. It requires a new preregistration, new bindings, and a new sealed
holdout before confirmatory work may resume. A patch, retrospective explanation, ledger edit, or
downstream approval cannot repair the invalidated batch in place.

## Detached object and hash rule

The null anchors above are mirror keys and are never filled in this file. The canonical schema uses
exactly 66 registered, ordered, separate immutable closed-world object types. The pre-label manifest
and its freeze transition, signature message, signature record, and envelope are distinct objects;
none can stand in for another. Each object has its own version, domain tag, canonicalization and hash
rule; a later stage can bind only a prior object's hash. Appending fields to an already
hashed object, including future draw, activation, access, release, or GO fields, is rejected.

Minimum-claim, protocol and activation approvals are ordered domain-separated messages. Every
signature uses only `UTF8(atelier.north-star.detached-signature-input.v0.1) || 0x00 ||
HEX_TO_BYTES(signature_message_hash)`; raw message-hash bytes alone are not a complete signature input.
Each detached signature record is hashed only after the signature exists, so no
record hash signs itself. Separate signature-set objects bind stage, package, ratification/batch
identity, external governance anchor, trusted policy/root hashes, roster, quorum, separation policy,
algorithm selections and ordered message/record members. The verifier deterministically recomputes
signature validity, allowlist membership, quorum and separation; no self-asserted boolean or opaque
verification-record hash is accepted. Missing, extra, duplicate, out-of-order or cross-stage members
reject. The verifier resolves each member record back through its exact message and signed object and
requires all envelope/set identity, role, instance, batch, event and package hashes to match. The exact
24 signer classes, in canonical order, are `minimum_claim_role_approval`, `protocol_role_approval`,
`activation_role_approval`, `draw_custodian`, `candidate_prelabel_freeze_custody_broker`,
`protected_access_intent_custody_broker`, `protected_access_terminal_custody_broker`,
`pre_draw_custody_store_attester`, `pre_draw_custody_control_source_attester`,
`pre_draw_trusted_clock_attester`, `trusted_review_clock_attester`,
`trusted_review_event_time_source_attester`, `trusted_review_event_store_attester`,
`machine_event_time_source_attester`, `machine_trusted_clock_attester`,
`machine_cross_clock_order_attester`, `machine_receipt_status_store_attester`,
`github_transport_capture_attester`, `github_audit_stream_attester`,
`repository_base_and_policy_mutation_freeze_attester`, `release_independent_reviewer`,
`post_merge_release_attester`, `expert_label_rater`, and `final_go_authority`. The external governance-anchor hash is fixed outside
signer control; trust/root/allowlist/roster/quorum/separation hashes match it exactly and selected
algorithms must belong to its anchored allowlists. Certificate chain, expiry, revocation, key usage
and proof of possession must verify. Custodian draw, pre-label freeze, and protected-access signatures
remain separate custody chains.

The evidence bundle is an exact 32-key closed-world membership manifest and excludes the release-
evidence package and its hash, every final decision statement/signature-message/signature-record/
signature-set/outer-receipt object and hash, and post-GO archival records. It binds every capability,
intent and terminal envelope set plus the replayed final custody-audit and consumed-capability-index
roots; a signed intent without terminal remains visible as consumed+incomplete. It also binds the
unique pre-label candidate manifest, its broker-signed CAS freeze envelope, and the complete protected-
run/machine attempt-link manifest, then independently recomputes their slot coverage, actual bytes,
semantic/lineage contents, required views, unique duplicate partition, label provenance, and forward/
reverse attempt bijection. The release-evidence package is an exact 43-key object. Its exact 25-member
shared-binding intersection with the evidence bundle—including the candidate manifest, freeze
envelope, machine link set, final audit/consumed roots, and A–E recomputation—must be byte-equal; the
declared intersection is dynamically recomputed from both templates, not trusted. The release package
binds those shared values plus protocol/draw/activation, sealed sample manifest, run and release code
commit/tree, evidence bundle, registered A–E recomputation, a three-scope review-envelope set, PR API,
required checks, merge commit/tree, source-bound raw bytes, and matching main CI.

PR and main-CI proof is source-specific GitHub evidence, not a generic API summary. One exact inline
release Git/CI container binds the signed GitHub source profile, its fixed merge and merge-queue
GraphQL query bytes, the
exhaustive digest-path registry, and a closed raw-member set. Every raw request/response/header/body,
Git object, workflow, review-scope file, tracked release artifact, identity proof, and provenance byte
hash resolves to exactly one inline Base64 member whose byte length, media/record kind, owning runtime
path, selected digest algorithm, and exact digest formula are recomputed. Secret credential bytes and
length are excluded, while one nonsecret credential handle, principal, kind, installation/user marker,
permission attestation, and validity interval are bound identically to every transport receipt.
The profile fixes both API origins to `https://api.github.com`, GraphQL to
`https://api.github.com/graphql`, an externally anchored TLS server-authentication policy, and
`REJECT_ALL` redirects. All fourteen request-bearing kinds (within fifteen GitHub source-leaf
templates; the merge response shares its request exchange) must match their exact method plus
official endpoint path/query template; alternate authorities, rewritten targets, cross-origin
pagination, query drift, userinfo/fragments, and noncanonical encodings reject.

Before a merge request exists, exactly three common-trust-valid, pairwise-distinct reviewers cover
`GOVERNANCE`, `MACHINE`, and `RELEASE_GIT_CI` from independent read-only checkouts of one commit/tree.
Their resolved principals, accounts, public keys, and identities are mutually distinct and disjoint
from the complete externally anchored development/tuning/execution actor-roster union. Any finding or
tree change invalidates all three reviews. Before those signatures, a pre-review actor set replays
every rebased base-to-head commit and parent edge from raw Git objects, binds each author/committer
and the final PR author to that roster union, and rejects any non-base boundary. A separate post-merge
set binds the unique merge-audit actor and both actor identities from every selected required Actions
run before the post-merge attestation. Before policy pass 1, an external provider atomically grants an
irrevocable single-use lease after comparing `refs/heads/main` to the frozen base; it rejects every
policy mutation and every other main-ref update. Under that active lease the two policy/queue passes
run, then the same authority signs a snapshot leaf binding the complete page set, resource/version
commitments, queue observations, base/head, and session. The raw GraphQL `POST` uses
`merge_method=MERGE` and an `expected_head_oid`; its `clientMutationId` commits the reviewed head,
complete three-review set, final PR and pre-merge main-ref observations, required-policy snapshots,
terminal-success pre-merge CI, and that snapshot leaf. An out-of-band ARMED admission leaf then binds
the exact target, raw body/header hashes, PR/head, preconditions, and clientMutationId and atomically
limits lease consumption to that one mutation; its hash is a request-leaf gate reference but is not
part of clientMutationId, avoiding a cycle. After acceptance, a terminal leaf for the same
lease proves zero policy mutations, zero foreign main updates, one bound merge, and no early release or
fail-open before the post-merge attestation.
The request body's unique JSON `query` string is strictly unescaped to UTF-8 and must byte-equal the
source profile's strict-Base64-decoded fixed query; its digest must equal both the request leaf and
profile query hashes. A semantically equivalent but byte-different, duplicated, re-encoded, missing,
or profile-detached query rejects before send. Its closed-world AST has exactly one named mutation,
one unaliased `mergePullRequest(input: …)` root field, and exactly four non-null declarations whose
`pullRequestId`, `mergeMethod`, `expectedHeadOid`, and `clientMutationId` variables map directly once
each to the same-named input fields. Fragments, directives, defaults, literals, unused variables,
additional roots/arguments, and any bypass path reject. `pullRequestId` equals the node ID reparsed
from the same final raw PR observation; `expectedHeadOid` equals the reviewed head and is therefore an
executable CAS input, not a detached body claim. The fixed unaliased response selection is exactly
`clientMutationId` plus `pullRequest { id number merged mergedAt mergeCommit { oid } }`; the strict raw
response projection byte-equals those response-leaf fields and echoes the exact correlation value.

The exact 15-field PR API record is recomputed from those source leaves and the Git object database.
It proves the freshly fetched `origin/main` base equals the clean-worktree base, final head commit/tree,
and an accepted merge-commit compare-and-swap whose expected head equals that reviewed head and whose
parents are the observed base and head. `expectedHeadOid` and strict checks alone do not provide an
exact-base CAS; exact base safety also requires the acquisition→snapshot→admission→terminal external lease
sequence above. If that primitive is unavailable, merge is blocked before send. A base change forces
fetch/rebase/static validation/rereview.
The RUN_CODE_RELEASE package executes the accepted main merge commit; its merge tree must be byte-
identical to the reviewed PR-head tree. EVIDENCE_RELEASE separately records its reviewed PR head while
retaining the earlier released run-code commit/tree bindings.

The required PR check set is nonempty and recomputed from its bound policy snapshot. A raw policy rule
is `(ordinal, name/context, provider constraint kind, required integration ID or ANY marker, scope,
rule id, source leaf)`, never a result kind. Complete current check-run and commit-status populations
expand each rule to every present result kind; both are required when both exist. A provider-specific
rule accepts only its exact app/integration, while any-source never backfills provider identity. The
dedicated classic status-check endpoint is authoritative for `strict` and any provider detail; its
two passes and the common `contexts` exposed by full branch protection must all agree, and full branch
protection must separately prove admin enforcement. A separately anchored post-merge workflow-policy
snapshot plus the reviewed tree and raw workflow blobs yields a nonempty required-main-workflow
identity set. Every member of both sets must be terminal with conclusion `success`. Each required main-
CI member is an exact typed 20-field record whose `event` is `push`, derived `head_ref` is
`refs/heads/main`, raw `head_branch` is `main`, and `head_sha` equals both the observed main-ref OID and
accepted merge commit. Workflow identity/ref/path/blob and trigger semantics must resolve to
`refs/heads/main` and the reviewed release tree. Completion is the maximum terminal job completion from
the complete, unique, no-next-page job set, not an asserted run timestamp. After every per-workflow
listing is complete, a single unconditional repository run listing filtered only by main/push/merge
SHA must contain at most 100 rows, have no next page, bind every required workflow's unique successful
maximum attempt, and expose no second run or higher/pending attempt. The unique closure response and
every prerequisite HTTP source leaf are ordered only by raw GitHub server `Date` and server event times;
hash dependencies prove construction order. Local capture/fetch/sent timestamps are signed audit
metadata only and cannot establish freshness, completeness, causality, or certificate validity without
a separately anchored same-clock attestation. `pull_request`, `workflow_dispatch`, tags, schedules,
pre-merge runs, alternate refs, generic status summaries, incomplete pagination, or a same-SHA different
workflow blob cannot substitute.

Merge audit is four complete REST chains (repository and organization, two passes each) reconciled
against one enterprise-scoped signed stream. Raw `@timestamp` and `created_at` must be integer epoch-ms
for the registered API version and parse to the same UTC instant. Page-set hashes are the exact
concatenation of all four chain summaries; the organization common universe plus disjoint stream-only
events equals the stream high-water population, while the repository view is a nonadditive filter.
Completeness requires a provider-backed event-time watermark covering the query end; a collector
signature, dwell, stable repeat, or post-hoc audit cannot prove completeness. If GitHub or the stream
provider cannot supply that watermark, the release remains `BLOCKED_WAIT_EXTERNAL`.

Its actual package bytes and
hash are detached from the bound release tree and every upstream preimage. The registered outer
release-evidence package uses verified `H_protocol/CANONICALIZE_protocol`; its inline release-control,
typed-source, and raw-member evidence uses `H_release/CANONICALIZE_release` byte-equal to the external
anchor and signed protocol mirror. It contains neither its own
hash nor any final decision. This closes only `F_release_evidence_complete`. The final-GO human(s)
then sign a separate domain-separated decision statement; the canonical final signature set binds
the signed roster, quorum and role separation over the already-fixed release package hash. All final decision artifacts remain detached
from the bound release tree; a tracked post-GO write requires a new complete release cycle.

## Authority semantics

The minimum-claim floor has its own externally anchored human roster/quorum. The minimum protocol and activation roster is `claim_authority AND optical_expert_authority AND
manufacturing_statistics_authority AND machine_execution_authority`; each stage has a distinct
canonical signature set, and the human-owned roster,
quorum, within-role rule, and role-separation selection remain null until externally ratified. Within
one role, the human-selected rule is exactly `AND` or `OR`: `AND` requires every allowlisted member
required by that role, while `OR` requires at least one allowlisted member. Both rules are evaluated
against the registered nonempty roster and positive quorum; empty rosters, empty allowlists, empty
signature sets, zero quorums, and vacuous truth reject. The two expert label
dimensions are an additional AND under the ratified rater-count/blinding/combination policy. A
separately allowlisted final-GO roster acts only after A–E and `F_release_evidence_complete` are
independently recomputed. Its human-owned quorum and role-separation rules are frozen in the protocol.
Only A–E, `F_release_evidence_complete`, and a common-trust-verified final signature set whose
statement has `decision=GO` complete the north-star Goal. That final set must resolve to the
registered nonempty final roster and positive quorum and contain at least one valid human signature.
Final-decision objects do not change F.
`NO_GO` is not
completion; `STOP`, `CANCEL`, or `SUPERSEDE` require an explicit human disposition and never become
GO. Every human-owned binding remains null; therefore this contract is UNRATIFIED and unusable for
confirmatory work.
