# NEED: human ratification and external authority package v0.1 — UNRATIFIED

status: UNRATIFIED
response_requirement: explicit-external-signature
no_response_effect: all fields remain null; all A-F gates remain false; no recommendation is selected

AI lacks legal, optical-expert, manufacturing/statistical, machine-execution, and holdout-custody authority. Git
authorship, CI, silence, a self-declared reviewer string, or this recommendation cannot supply it.
No confirmatory sample, holdout, expert label, threshold, scope, yield, or GO is created here.
`[EXPERT]`, both expert-rate numerators, manufacturing yield, and every A-F gate therefore remain
unavailable/false; this document does not sign or infer any of them.

The current canonical schema shape registers exactly 66 closed-world object templates and 24
detached-signer classes. It also fixes ten digest-reference classes, 26 sealed-manifest fields,
27/27/48 machine ticket/intent/terminal-receipt bindings plus 33 ACTIVE-status-CAS bindings, 32
evidence fields, 43 release fields and 25 shared
release/evidence bindings. Its minimum-claim envelope contains exactly 23 null template positions
(6 envelope positions plus 17 nested claim positions). These counts are structural facts only: all
23 positions remain null here, and none creates a signature, threshold, authority decision, or gate.

Two registered templates are the canonical authority-role-roster content and authority-quorum-rule
content objects. Every stage must bind those objects rather than an opaque roster/quorum hash. Human
ratification must supply a nonempty role roster and allowlist, an exact within-role `AND` or `OR`
choice, positive per-role and total quorum minima, and at least one valid allowlisted human signature.
Empty or zero choices and vacuous truth are rejected; this document does not fill any of them.
Each counted signature must resolve a message whose identity, identity-proof hash, public-key
fingerprint, and allowlist hash exactly match one same-role registered roster member. `AND` requires
the entire roster tuple set; `OR` permits only a nonempty duplicate-free subset. A signer that appears
only in the broader external role allowlist receives no stage quorum credit.

Two further registered templates are the closed-world machine-entry-inventory content and machine-
admission receipt. Human machine-execution ratification must supply the selected inventory and
admission schema/control values plus external OS-evidence policy, parser registry and attester
allowlist. Repository text cannot substitute for raw native inventory/boundary receipts or their
externally verified signatures, and no spawn is admissible without the same inventory/admission hashes
recomputed through activation and the complete machine attempt chain.

## Who must decide

1. **Minimum-claim authority (主公 or externally designated human roster):** signs the immutable
   north-star floor and only equal-or-broader successors under the externally anchored comparator;
   scenario IDs stay exact under comparator v0.1. A separately approved external append-only atomic-
   CAS checkpoint store prevents a stale, forked, or rolled-back floor from becoming active.
2. **Protocol claim authority:** claim wording, supported scope,
   external-tool walls, and whether 主公 separately qualifies as an optical expert. Claim ownership
   alone does not establish optical qualification.
3. **Optical-expert authority:** immutable identity allowlist, non-waivable endpoints, rubric, TOR
   interpretation, the two label dimensions (`expert_worth_reviewing` and
   `expert_production_usable`), and the rater-count/blinding/combination policy. This template does
   not choose one or multiple expert raters.
4. **Manufacturing/statistics authority:** independence, ITT, confidence/cluster method, TOR table,
   manufacturing and productivity analysis, thresholds, and statistical disposition.
5. **Machine-execution authority:** machine host and entry inventory, OS admission boundary,
   machine-wide lease, toolchain pins, launch-ticket/capability, monitoring, receipt, and release
   policy. It must externally approve the durable transactional lease/journal authority root, store
   identity, native receipt-attester allowlist, fixed acquisition/journal/barrier/atomic-receipt
   parsers, atomic receipt schema, and release-journal store policy. Repository checks cannot
   self-approve any of those controls, an ACL, AppLocker rule, broker, or equivalent OS enforcement.
6. **Independent holdout custodian:** out-of-workspace encrypted storage, ACL, draw receipt,
   activation custody head, protected-access capabilities, intents, terminal receipts, and audit.
   The human package must separately approve the custody-audit store policy/identity/genesis and
   store-attester allowlist, the pre-draw clock policy/attester allowlist, and the trusted review
   store, clock and event-time source-attester allowlists. These are external trust roles, not AI or
   rater assertions.
   This identity must at minimum be separated from every
   development, tuning, and execution role. Any additional separation from claim authorities,
   expert raters, or the GO signer is an explicit human-owned role-separation choice, not an AI
   default.
7. **Final-GO authority:** a separately allowlisted human signer who reviews independently
   recomputed A–E plus release evidence and signs the final GO or NO-GO. Earlier claim, rubric, TOR,
   or custody approval does not implicitly grant this role.

## Exact evidence presented for the decision

- `.planning/loop/prod-loop2-final-handoff-2026-07-13.md` records PR/main CI truth and the honesty
  boundary: P18 `29/21`, Stage B `8/8`, Stage C `2/46` plus `6/48`, and one exact target are not
  expert rates or manufacturing yield.
- `.planning/quick/260712-stagec-real-evidence/260712-stagec-real-evidence-PLAN.md` records the
  Stage B manifest hash, Stage C plan/state/report hashes, the single-target chain, and that the
  final executable share-deny patch was not followed by another real CODE V run.
- `.planning/loop/phase18-night-20260711-morning-audit.md` records P18 orchestration terminal states
  and retained contamination exclusions; it supplies no expert or manufacturing verdict.
- `app/core/engines/codev_batch.py` anchors the current launch chain and user-scoped default lock;
  `.planning/loop/p13-smoke-2026-07-11/freeze_smoke.py:70` anchors a direct `Popen` bypass.
- This GSD plan is based on Git commit `d35b3d07cead830396d24d2b10665199c73985e0` and Git-derived
  tree `5121336ca69bb0397de244550114aa3d8487498c`. The control-plane proposal's own commit/tree,
  independent review, PR, and CI status are external Git/GitHub records; this self-authored NEED
  package never asserts or substitutes those records.

A bounded read-only audit rehashed the designated retained Stage B, Stage C, and exact-target
runtime artifacts to verify the tracked hashes. That access makes no confirmatory claim: all
loop2 data were already observed and remain permanently `exploratory_reusable_component` or
`incident_evidence`. No artifact was modified, relabelled, or used to set a threshold.

## Quantified sample-design options — options only, never self-selecting

These illustrative packages size work; they are not statistical-power-qualified and none sets an
optical pass threshold, TOR table, manufacturing yield threshold, minimum claim envelope, or GO
rule. Counts mean independent targets after the ratified patent-family and seed-cluster rules;
holdout targets are additional to non-holdout targets. Planned run units include both groups.
“Label decisions” counts the two independent label dimensions once per planned candidate slot for
one authorized rater; actual review work scales by the human-ratified rater count and combination
rule. CODE V minutes and expert hours remain unavailable until a ratified cost model exists; no
runtime estimate is invented here.

| Option | Non-holdout independent targets | Seed clusters | Sealed holdout targets | Candidate slots per target | Planned repeats per slot | Planned run units | Label decisions at one rater | Trade-off |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| A — larger planning package | 60 | 30 | 20 | 2 | 3 | 480 | 320 | Broader dependence coverage and repeat evidence; highest machine and expert-review cost. |
| B — middle planning package | 36 | 18 | 12 | 2 | 2 | 192 | 192 | Moderate coverage and cost; recommended for initial human discussion, not selected. |
| C — smaller planning package | 18 | 9 | 6 | 1 | 2 | 48 | 48 | Lowest cost and widest uncertainty; below-envelope use is exploratory only. |

Recommendation: discuss Option B first, then have the manufacturing/statistics and optical-expert
authorities either sign a complete bound package or replace it. None of A/B/C may shrink a separate
human-signed minimum claim envelope: any package below that minimum is exploratory only and cannot
complete the Goal. **No response does not select the recommendation**; it leaves every anchor below
null and every gate false.

## Machine-wide CODE V control decision

Before any real-machine run, authorized humans must select and approve a single canonical launcher
and one durable transactional machine lease/journal authority. That authority is the only admissible
seat-lease mechanism: it exclusively owns the machine-wide lease state, release-operation state, and
durable release journal under an externally anchored root/store/attester/parser policy. A Windows
Global named mutex or controlled `ProgramData` ACL may be added only as defense in depth; neither,
alone or together, can substitute for the transactional authority. Cooperative local controls cannot
force an external manual launcher to participate. Completion
of the canonical-launcher gate therefore also requires a human-approved machine admission boundary
(for example one broker plus an approved OS execution policy) and an attested inventory of Task
Scheduler, services, startup entries, other worktrees, external scripts, and manual entry points.
Without an enforceable OS boundary the gate remains false. Every choice still requires durable
intent and exact `pre_launch`/`during_run`/`post_run` snapshots for `runner`, `codev`, `codevm`,
`p18_owner`, `global_owner`, `per_call_owner`, `launched_subtree`, and `unknown_carrier`, plus official
toolchain pins, default-deny launch tickets for Web/CLI/tests and all batch/probe surfaces, and
receipt-last persistence. The canonical lease broker is distinct from those zero-state subjects;
`runner` means a run child or competitor, while global/per-call owner carriers are not the current
lease owner. The same `lease_instance_id` remains held by exactly one attested broker through the
zero proof and receipt. The only valid terminal order is `terminal_artifacts →
post_run_snapshot_and_monitor → zero_state_proof → ACTIVE status CAS →
durable_machine_terminal_receipt → protected terminal → release transition → PREPARED journal →
OS release + OS_RELEASE_COMMITTED journal as one atomic external-authority transaction →
RELEASED status CAS → durable release receipt`. Lease release
requires every known subject proven zero/absent and unknown carrier
absent; unreadable, reordered, aliased, duplicate, weaker, or unknown state retains the lease and
fails closed. During the lease,
non-allowlisted shell/test/import/runner activity is denied.
On conflict, only the provably owned subtree may be terminated; the attempt becomes permanently
retained `contaminated` evidence, all raw artifacts/logs are preserved, and unknown processes are
never killed. The receipt binds host, PID, owner, start/end, full command, and artifact hashes.
The machine receipt also binds batch/run/attempt IDs, single-use ticket/nonce, durable intent,
official executable/macro/version/sequence/input hashes, pre/during/post snapshots, terminal state,
artifact hashes, and audit-chain heads; the consumed-ticket index rejects replay. Unknown
process/owner/lease state fails closed and is not killed or cleared. OS ACL or AppLocker
enforcement is high-impact and needs separate human approval; this task makes no system change.
The chosen authority must make release and durable committed-journal append one atomic
compare-and-update operation, or commit neither. After restart, a PREPARED operation may advance
only when the same authority transactionally terminalizes that exact operation ID as irrevocable
`ABORTED_FINAL` with the lease still `HELD` (so it can never commit later), or proves it was already
`COMMITTED` with the exact OS_RELEASE_COMMITTED journal durable. A transient `NOT_COMMITTED`,
pending, partial, unknown, unqueryable, or released-but-unjournalled result keeps admission closed.
Before every new acquisition, a complete authority-wide barrier must cover all prior operation IDs
across batches/hosts/brokers, prove zero unresolved PREPARED operations, and be consumed in the same
atomic authority transaction that inserts the new lease; a prior empty observation is insufficient.
The human-selected native receipt suite must sign the canonical exact per-source acyclic projections for
atomic acquisition, OS acquisition, barrier, journal-store, atomic release, and OS release. Those
projections bind batch/activation/protected-run context, run/attempt, host/broker/lease and their
source-specific operation/transaction, roots and outcomes. Acquisition signs its barrier; the barrier
signs its complete ordered operation members; journal/atomic/OS sources sign their own transition,
prior-journal, result, and time bindings. Each raw request/content hash is committed by its
named signed response. Only enumerated self-container/control and genuinely later fields are excluded;
`_leaf_hash` is never a blanket exclusion rule.
For every protected `run`, the signed protected-access intent must be resolved before launch. For a
terminal member, its activation, capability, membership proof, run/attempt, host, launcher, broker,
lease, complete command, input, and toolchain-pin bindings must equal the launch ticket, durable
machine intent, durable pre-spawn commit receipt, process-start receipt, machine terminal receipt,
and protected terminal envelope. The exact launch-ticket, durable-machine-intent, and terminal-
receipt policies have respectively 27, 27, and 48 exact required binding members; the ACTIVE-status
CAS has a separate exact 33-member binding set. A canonical ordered
per-attempt link-set manifest must cover every protected run intent exactly once and every valid
confirmatory machine terminal receipt exactly once. An intent without a valid terminal must instead
have one exact tagged `CONSUMED_INCOMPLETE` member whose retained machine-chain evidence validates,
remains explicit, and cannot contribute success. Its retained chain is either `INTENT_ONLY`, proven
by a closed-world scan with no machine leaf, or the exact contiguous `PREFIX` actually reached. A
prefix must preserve lifecycle order through ticket → durable intent → durable pre-spawn commit
receipt → process-start receipt, and its members must exactly equal every typed machine leaf for the
same intent and tuple. Conversely, every launch ticket, durable intent, pre-spawn receipt, and
process-start receipt must resolve to exactly one terminal or consumed-incomplete member; every
terminal receipt resolves to exactly one terminal member. A valid terminal receipt/envelope forbids
a partial chain. Duplicate, missing, aliased, orphaned, cross-run, cross-attempt, or cross-batch links
reject. This forward-and-reverse coverage is a verifier-derived fact, never a launcher or signer
assertion.
Crash recovery is never a success shortcut. Its generation/predecessor markers are exact; monitor and
zero-state wrapper, inline pre-time payload, raw evidence and trusted event-time leaf repeat the same
schema/batch/activation/tuple/run/attempt/host/broker/lease/crash/generation bindings. The selected
owned-subtree branch and zero→monitor hashes must resolve exactly; any cross-attempt or cross-generation
splice rejects. ACTIVE→RELEASED occurs once in the external status store after the durable OS-release
journal and before the final release receipt.
A monitored state change after zero proof but before ACTIVE CAS repeats monitor/zero first. The same
change after ACTIVE CAS but before the full receipt must use the `ACTIVE_CAS_ONLY` abort/recovery path,
abandon the status, safety-release, and remain consumed-incomplete; it cannot rewrite the committed
pre-status payload or emit a normal receipt. After receipt invalidation, later monitor/zero states
remain explicitly typed as `FULL_RECEIPT_INVALIDATED`, never aliased to the no-status frontier.
All 19 values are typed canonical objects with fixed minimum constants; a human may select concrete
identities/mechanisms/hashes but cannot weaken launcher coverage, ticket single-use/default-deny,
bypass closure, pins, intent, monitoring, contamination retention, or zero-state release. The policy
hash has one domain and exact 19-key preimage before protocol-manifest hashing.

## Non-authoritative response form for protocol selections

This form is only a convenience mirror of
`.planning/north-star/preregistration-manifest-schema-unratified-v0.1.json`. It is never signed as
an independent payload. The external ratifier must produce a closed-world canonical protocol
manifest under that schema; missing, extra, duplicate, or conflicting values reject. Every field
below remains null until an authorized human selects it.

Non-binding H-00 discussion may fill an option worksheet, but it creates no signature or gate. The
minimum-claim floor/signature/checkpoint chain is run-code-release-independent only after the exact
canonical schema bytes/hash, goal instance/genesis, and every out-of-band anchor component are frozen
and verified as X-00A. X-00B may then establish the active floor before O-07; it commits the durable
claim floor, not a run-code release. Actual protocol and TOR signatures must wait until all O/M
importer/verifier code has been fixed and O-07 has released the exact run-code commit/tree, then bind
both that release and the already verified active floor. H-01 and H-02 independently sign the same
immutable protocol-package bytes and both must precede H-03 draw/activation.

A code/commit/tree-only change may reuse the active floor only when every canonical schema byte,
expected schema hash, anchor component, and goal-instance byte is identical; it still requires fresh
O-07, protocol, TOR, and downstream signatures. Any canonical schema byte or anchor-component change
invalidates the prior floor, signature set, checkpoint, protocol, draw and activation. v0.1 supports
no rotation or migration: create a new goal instance, genesis, out-of-band anchor, floor chain and
checkpoint genesis, then replay the DAG. After draw, either kind of relevant change also permanently
invalidates that confirmatory batch and requires a new sealed holdout.

## Explicit external prerequisite events and wait protocol

- `X-00A_SCHEMA_ANCHOR_MACHINE_AND_RELEASE_AUTHORITY_FROZEN` is an operational predicate over the
  already registered canonical external-governance anchor, its out-of-band expected hash/config, and
  live official repository capability observations; it adds no receipt or signer class. External
  governance, machine-execution and repository-owner authorities supply those inputs. The predicate
  covers the exact schema/goal/anchor lease/journal/status/time/cross-clock/OS-evidence controls and
  GitHub source profile. The release profile requires an organization-owned repository, authorized
  Enterprise Cloud audit-log visibility, and one out-of-band verified credential principal used for
  every exchange with full private ruleset `bypass_actors` visibility, classic branch-protection
  200/admin-read, merge authority and no bypass. v0.1 also requires nonempty strict/up-to-date checks,
  `mergeCommitAllowed=true`, `main` merge queue absent, no applicable linear-history, merge-queue,
  Enterprise-parent or ruleset-workflow rule, plus a separately anchored nonempty post-merge
  main/push workflow policy. Public `mergePullRequest` has no expected-base or policy-snapshot CAS, so
  X-00A also requires an independent provider-side, fail-closed, irrevocable single-use lease over
  every policy-administration surface and every `refs/heads/main` update surface. A signed acquisition
  atomically compares the frozen base before policy pass 1; an ACTIVE-lease snapshot receipt binds both
  policy/queue passes; an ARMED admission receipt then binds the finalized request target/body/header
  hashes, preconditions, and clientMutationId before merge send; a terminal receipt proves zero policy mutations, zero foreign
  main updates, exactly one bound merge, and no early release/fail-open. If the provider cannot supply
  this acquisition→snapshot→admission→terminal primitive, the merge path is `BLOCKED_WAIT_EXTERNAL`; strict
  checks, `expectedHeadOid`, stable reads, and post-hoc audit are not substitutes. Its enterprise stream configuration must bind enterprise→organization
  membership, stream ID, destination and partition and expose a provider-backed event-time watermark;
  local high-water signatures, dwell or repeated stable reads cannot substitute. Current
  `dlkuajing/atelier` USER ownership, observed HTTP 403 policy endpoints, or the absence of such a
  provider watermark fail closed; none is evidence of an empty policy/audit.
- Actual machine-entry inventory/admission-boundary selection and enforcement remain H-01/H-03/R-00
  records; X-00A does not attest them.
- `X-00B_ACTIVE_MINIMUM_CLAIM_FLOOR_CHECKPOINT` depends on X-00A and is the existing canonical tuple
  `{minimum_claim_envelope_hash,minimum_claim_authority_signature_set_hash,current_checkpoint_hash,
  current_checkpoint_generation}` supplied by the external minimum-claim and checkpoint-store
  authorities. It adds no receipt type and binds the floor, human signature set, comparator/lineage,
  checkpoint-store policy and accepted CAS current head.
- The agent may prepare one idempotent NEED per
  `{goal_instance_id,event_id,canonical_schema_template_hash}` and verify changed external inputs. It cannot
  select, approve, sign, transfer the repository, alter a paid plan, advance a checkpoint, or treat
  silence as approval. Missing input persists as `BLOCKED_WAIT_EXTERNAL`; all independent ready nodes
  continue. There is no blind poll/retry. Re-evaluate only when an externally controlled X-00A input
  byte sequence or the X-00B canonical tuple changes; retain invalid bytes and rejection evidence,
  and verify each distinct input tuple at most once.

```text
selected_quantified_option: null
external_governance_anchor_hash: null
expected_active_minimum_claim_envelope_hash: null
minimum_claim_checkpoint_store_policy: null
expected_active_minimum_claim_checkpoint_hash_and_generation: null
north_star_goal_instance_and_genesis_commitment: null
minimum_claim_version_generation_and_predecessor: null
minimum_claim_authority_allowlist_identity_roster_and_quorum: null
minimum_claim_envelope_hash: null
minimum_claim_authority_signature_set_hash: null
claim_authority_allowlist_and_identity: null
optical_expert_authority_allowlist_and_identity: null
manufacturing_statistics_authority_allowlist_and_identity: null
machine_execution_authority_allowlist_and_identity: null
machine_lease_authority_root_hash: null
machine_lease_authority_store_identity_hash: null
machine_lease_authority_attester_allowlist_hash: null
machine_lease_authority_acquisition_attestation_parser_profile_hash: null
machine_lease_authority_release_journal_parser_profile_hash: null
machine_lease_authority_state_barrier_parser_profile_hash: null
machine_lease_authority_atomic_operation_receipt_schema_hash: null
machine_lease_authority_atomic_operation_receipt_parser_profile_hash: null
machine_release_journal_store_policy_hash: null
final_go_authority_allowlist_and_identity: null
expert_rater_identity_allowlist: null
holdout_custodian_allowlist_and_identity: null
custody_broker_allowlist_and_identity: null
custody_audit_store_policy_identity_genesis_and_store_attester_allowlist: null
pre_draw_trusted_clock_policy_and_attester_allowlist: null
trusted_review_event_store_policy_identity_and_store_attester_allowlist: null
trusted_review_clock_policy_and_attester_allowlist: null
trusted_review_event_time_source_attester_allowlist: null
protocol_required_role_roster_and_quorum: null
activation_required_role_roster_and_quorum: null
final_go_required_role_roster_and_quorum: null
within_role_identity_rule: null
role_separation_policy: null
duplicate_signature_and_statement_policy: null
principal_is_optical_expert: null
external_trust_policy_id_and_hash: null
external_root_set_hash: null
certificate_expiry_revocation_key_usage_and_proof_of_possession_policy: null
common_signer_verification_coverage: null
supported_scenarios_and_specification_ranges: null
representative_target_distribution: null
minimum_independent_target_seed_cluster_and_holdout_counts: null
patent_family_independence_rule: null
non_waivable_endpoints_and_external_tool_exclusions: null
eligibility_and_result_independent_exclusion_rule: null
invalid_input_exclusion_reason_allowlist_and_evidence_schema: null
planned_candidate_slots_and_run_units: null
retry_mapping_and_terminal_state_table: null
itt_mapping_and_primary_endpoint: null
pipeline_delivery_rate_definition_and_threshold: null
candidate_content_and_lineage_fingerprint_rules: null
candidate_equivalence_and_duplicate_cluster_rules: null
candidate_required_label_view_object_set_rule: null
duplicate_cluster_label_aggregation_and_expert_numerator_independence_rule: null
expert_label_rubric_and_two_dimension_definitions: null
expert_rate_thresholds: null
expert_rater_count_blinding_combination_and_disagreement_rule: null
tor_semantics: null
tor_units: null
tor_table_hash_selection: null
tor_monte_carlo_denominator: null
tor_compensator_policy: null
tor_aggregation_rule: null
tor_saturation_mapping: null
tor_compensation_failure_mapping: null
manufacturing_yield_threshold: null
confidence_cluster_and_level_rule: null
repeat_policy: null
sampling_algorithm_frame_count_and_randomness_commitment: null
holdout_encryption_acl_audit_and_non_access_policy: null
draw_receipt_policy: null
protected_action_capability_membership_intent_terminal_and_crash_policy: null
audit_and_consumed_capability_index_root_policy: null
expert_review_time_and_productivity_baseline_thresholds: null
exit_code_table_and_analysis_plan: null
machine_host_identity: null
machine_entry_inventory_policy: null
machine_admission_boundary_policy: null
machine_wide_lease_mechanism: null
os_acl_policy: null
applocker_policy: null
launch_ticket_policy: null
pure_offline_allowlist_policy: null
durable_intent_policy: null
conflict_monitor_policy: null
pre_during_post_snapshot_policy: null
required_snapshot_subject_set: null
required_snapshot_phase_set: null
unknown_carrier_policy: null
contaminated_attempt_policy: null
owned_subtree_termination_policy: null
receipt_last_policy: null
zero_state_release_policy: null
official_toolchain_pin_policy: null
canonicalization_hash_and_signature_algorithms: null
canonical_schema_claim_contract_authority_template_hashes: null
run_code_commit_and_tree_hashes: null
evidence_schema_external_source_and_sampling_frame_hashes: null
machine_execution_policy_hash: null
protocol_freeze_timestamp: null
```

The pre-draw protocol manifest cannot contain the actual sealed sample/holdout-manifest hash.

Human expert choices are also bounded by canonical non-vacuity invariants: the rater allowlist is a
nonempty duplicate-free ordered identity / identity-proof-hash / public-key-fingerprint tuple array
whose bootstrap hash equals the external anchor; `expert_rater_count` is an integer at least one and
equals its length; each counted label signature tuple matches one unique member of that same array
and carries the same anchored hash; both expert-rate thresholds are strictly greater than zero and at
most one; and Gate D requires at least one valid human expert-label envelope carrying both
dimensions as part of a complete per-candidate signer set equal to the protocol tuple array, with the
two results recomputed under the signed combination rule. Any incomplete or mismatched set
contributes zero to both numerators. Those bounds do not choose a rater, threshold, label, or
`[EXPERT]` value; all such human-owned fields above remain null.

The canonical ITT denominator types, terminal→not-pass map, retry non-expansion, four-condition
invalid-input exclusion record, conditional-metric diagnostic-only rule, duplicate-slot denominator
retention, per-cluster max-one numerator, and independent two-label calculations are hard invariants.
Human choices may be stricter but cannot replace them with weaker non-null text; the O-01 verifier
must reject a violating vector before any final H-01/H-02 signature is accepted.

The added `candidate_required_label_view_object_set_rule` is a human-owned protocol choice, not an
AI-selected default. Until it is signed, no candidate view is sufficient for an expert label. The
final canonical schema also requires verifier-recomputed, domain-separated exact content hashes for
the ordered planned identity mapping and ordered eligibility-decision set. Opaque set-root claims,
ID fallback ordering, missing/duplicate/gapped ordinals, or signer-controlled verification booleans
must reject.

## Required external record sequence

0. **X-00A schema/anchor/machine/release-governance predicate:** external authorities first supply
   the exact goal instance/genesis, final canonical schema hash and immutable anchor components,
   including lease/status/time/OS-evidence controls and the organization/Enterprise-visible GitHub
   source profile. The verifier checks the registered anchor plus live capability observations; no
   new receipt is created. This predicate is not A–F evidence and not permission to launch.
0. **Minimum-claim authority chain:** the floor envelope is bound to the externally anchored goal
   genesis, version lineage and fixed comparator. Its approval message→detached record→signature-set
   chain must verify, deterministic lineage/comparison replay must pass, and the external durable
   high-water checkpoint must advance once by compare-and-swap before the verifier exposes the floor.
   No opaque lineage/comparison proof hash, stale generation, fork, or rollback is accepted.
   Before parsing any signed object, the verifier must recompute the fixed canonical-schema-template
   hash from the exact final template bytes under the separately bootstrapped canonicalization/hash
   suite. That recomputation must equal the out-of-band pretrusted governance anchor and every
   protocol-manifest binding, protocol package, sealed manifest, activation manifest, and activation
   package schema-hash field. A mismatch, missing field, alternate schema, or cross-schema splice
   rejects before signature or quorum evaluation.
1. **Final-code protocol authority chain:** only after O-07 freezes/releases the exact run-code tree,
   claim, optical-expert, manufacturing/statistics, and
   machine-execution roles sign distinct domain-separated messages over the fixed protocol package.
   Each detached signature record points to its message hash. A separate canonical signature set
   binds the package, externally supplied governance-anchor hash, roster, quorum, separation policy,
   and ordered message/record members. Roster and quorum hashes resolve the registered canonical
   content objects; rosters/allowlists are nonempty, role and total minima are positive, and every
   accepted stage set contains at least one valid human signature. The verifier recomputes signature, allowlist, quorum and
   separation results; no signer-controlled boolean or opaque verification-record hash is accepted.
   Every signature uses the one canonical detached-input formula, and every member/envelope resolves
   through its exact message and signed object without cross-content splicing.
2. **Custodian draw chain:** only after protocol signatures, the custodian applies the signed
   sampling algorithm. Before draw, the externally anchored custody genesis must resolve one raw
   atomic durable initialization receipt signed by the separately allowlisted store attester and a
   signed pre-draw clock leaf. The genesis cannot depend on the later commit leaf; no opaque detached
   durability proof is accepted. The custodian then creates one canonical sealed-sample manifest and
   emits unsigned draw content,
   a signer-identity-bearing signature message, a detached common-trust-verified signature record,
   and an envelope. They bind protocol/signature set, batch/draw IDs, source snapshot, algorithm,
   randomness commitment/transcript, actual manifest hash, identity, timestamp, and an acyclic audit
   transition. The sealed manifest contains the exact domain-separated ordered planned-identity-
   mapping content hash and ordered eligibility-decision-set content hash; the verifier independently
   reconstructs both exact member lists, counts, ordinals, and hash preimages. The draw envelope must
   resolve that one sealed manifest and equal it on ratification, batch, draw, protocol package and
   signature set, sampling frame/source/algorithm/entropy commitment, target distribution/count, and
   manifest hash. No opaque membership root or cross-batch manifest reuse is accepted.
3. **Activation authority chain:** before any protected access, the required roles sign an activation
   package and separate signature set binding protocol, draw envelope, actual manifest, initial
   custody-audit and consumed-capability roots, machine admission, activation ID/expiry, action/object
   scope, and a membership-verifiable capability root. Activation must resolve its draw envelope all
   the way through unsigned draw content and sealed manifest, and must equal that chain on canonical
   schema, ratification, batch, draw, protocol package/signature set, manifest, target distribution,
   and target count. Its timestamp follows draw; cross-batch, cross-draw, cross-protocol, or manifest
   splicing rejects. The initial audit root equals the signed draw
   new root, the consumed root is the canonical activation/capability genesis, and every capability
   action/object/time scope is a subset of activation.
4. **Protected-access custody chain:** each unseal, view, run, label, or export proves capability
   membership and consumes one nonce. A signed intent envelope with literal `nonce_consumed=true`
   and deterministic new audit/index roots precedes action; a signed terminal envelope follows it,
   with both terminal prior roots equal to the intent new roots. Crash remains provably
   consumed+incomplete in the final index root. Each protected run also appears exactly once in the
   canonical per-attempt run↔machine link-set manifest described above; the evidence verifier
   recomputes complete forward/reverse coverage across intent, ticket, durable intent, pre-spawn
   commit, process start, terminal receipt/protected terminal, or the exact retained partial chain.
   Custody records never enter protocol or activation authority signature sets.
5. **Pre-label candidate freeze and human-entry chain:** after every protected run is terminal or
   consumed-incomplete, one append-only candidate pre-label binding manifest partitions every
   planned candidate slot into exactly one available or permanently unavailable member. Each
   available member binds the actual candidate artifact membership manifest and byte-set root, the
   human-selected required label-view object-set root, verifier-recomputed content and lineage
   fingerprints, its deterministic equivalence-cluster ID, and source run/attempt/machine evidence.
   The manifest contains the exact inline equivalence-partition content and hash. The verifier
   computes one unique, complete, pairwise-disjoint partition over every available slot from the
   mandatory floor (equal candidate byte-set root or equal content fingerprint) plus the closure of
   the signed equivalence and duplicate-cluster rules. Clusters are ordered by minimum resolved slot
   order and every member cluster ID is the hash of its complete cluster; producer-supplied partitions
   or identifiers are not trusted.

   The manifest alone is not the freeze. A custody-broker transition, detached signature message and
   record, and freeze envelope must bind it to an accepted store-attested compare-and-swap receipt.
   That receipt must advance the custody audit sequence exactly once, bind the prior/new audit heads,
   preserve the consumed-capability root byte-for-byte, and expose raw receipt bytes; the broker
   signature must not precede the committed timestamp. Exactly one valid signed freeze envelope may
   exist for the activation/batch, and every later label intent binds it. A second, unsigned, unaccepted,
   head-mismatched, cross-batch, or run-after-freeze transition rejects.

   The signed freeze precedes a blank label form whose two dimensions are `UNSET` and whose suggestion
   root contains no system or AI recommendation. The label intent is durable before review starts;
   required access events are durably written at access time and exactly cover the required view plus
   rubric-support union in protocol order. The raw human entry event follows those accesses, binds the
   same session/surface/form/rater/slot/intent/view/rubric, and byte-equals both signed label values.
   The exact order is freeze signature < blank-form creation ≤ label-intent write < review start ≤ all
   required accesses ≤ human entry ≤ review completion ≤ expert signature ≤ label terminal ≤ terminal
   transition/broker signature. START and COMPLETE use distinct raw boundary bytes and externally
   signed event-time leaves on one signed review clock; review duration is verifier-derived from that
   monotonic clock. Store/clock/event-time attesters are common-trust verified and disjoint from the
   rater. No successor, overwrite, self-declared cluster, wrong-candidate label,
   prefilling, or later admission of an unavailable slot is valid.

## Post-evidence release and final-decision records

After A–E, construct a closed-world evidence bundle and a separate release-evidence package binding
protocol/draw/activation, the candidate pre-label binding manifest and signed freeze envelope, the
protected-run machine-link manifest, access-envelope sets, final audit and consumed-capability roots,
sample manifest, run and release trees, evidence, review, PR/checks, merge tree, and matching main CI. The canonical evidence
bundle has 32 exact fields; the release package/authority mirror has 43 exact fields; all 25 shared
bindings must compare equal after independent reconstruction. Both evidence and release
bind the active minimum-claim envelope/signature-set/current durable checkpoint. PR evidence must prove
a freshly fetched `origin/main` base and clean worktree, the final head, accepted compare-and-swap with
`expected_head_oid` equal to that head, and a nonempty required-check set with every check terminal
`success`; a separately externally anchored post-merge workflow policy plus the reviewed release tree
must deterministically yield a nonempty required-main-workflow set, all terminal `success` on the merge
SHA. Applicable ruleset workflow rules block v0.1 rather than silently defining that set.

Each release stage requires exactly three signed independent read-only review chains covering
`GOVERNANCE`, `MACHINE`, and `RELEASE_GIT_CI`. Their resolved principals, accounts, public keys, and
identities are pairwise distinct and disjoint from the complete anchored development/tuning/execution
actor-roster union. The review set commits the exact repository, PR, commit/tree, actor-evidence set,
and scope manifest; any finding or tree change invalidates all three reviews. The pre-review actor set
replays every rebased base-to-head raw commit/parent edge and binds all commit authors/committers plus
the final PR author; the post-merge actor set binds the unique merge-audit actor and each selected
required workflow's Actions actor and triggering actor before attestation.

The Git/GitHub proof is source-specific, not a summary record: the closed-world evidence manifest
must retain raw response bodies, normalized non-secret headers and requests, Git objects, workflow
bytes, and every Actions jobs page. Typed leaves separately bind final and post-merge PR observations,
  the pre-merge `refs/heads/main` observation, the HTTP `POST` GraphQL request carrying
  `merge_method=MERGE` and `expected_head_oid`, whose strictly unescaped JSON `query` UTF-8 bytes and
  digest must exactly equal the bound source profile's strict-Base64-decoded query bytes and digest,
  with every request using the exact direct TLS-authenticated `https://api.github.com` method/endpoint
  template, GraphQL fixed at `/graphql`, and redirects plus alternate, rewritten, or cross-origin
  pagination targets rejected,
  and whose closed-world AST has exactly one `mergePullRequest(input: …)` mutation that directly maps
  the exact `pullRequestId`, `mergeMethod`, `expectedHeadOid`, and `clientMutationId` variables once
  each; the node ID is reparsed from the same final raw PR observation and alias/fragment/default/
  unused-variable/literal-indirection/bypass paths reject; the fixed response selection is exactly
  `clientMutationId` plus `pullRequest { id number merged mergedAt mergeCommit { oid } }` and the raw
  response must strictly project those fields and echo the correlation value,
  the raw merge response, and the post-merge main-ref
  observation. Before this request, the external base+policy freeze acquisition atomically compares
  the frozen main OID and blocks every other policy/ref update; after both policy/queue passes its
  snapshot leaf binds the complete page/resource/version set and is committed by `clientMutationId`.
  After final required checks and request-byte materialization, a one-shot ARMED admission leaf binds
  the exact request target, body hash, normalized-header hash, principal, preconditions and
  `clientMutationId` before send. The admission hash is deliberately excluded from `clientMutationId`
  to avoid a cycle, while the request leaf binds both snapshot and admission. After the response, the
  terminal leaf proves the same lease admitted no policy change, no foreign main update, exactly one
  bound merge, and no early release/fail-open. Missing any acquisition→snapshot→admission→request→
  response→terminal member is `BLOCKED_WAIT_EXTERNAL`; `expectedHeadOid` plus strict checks without
  this provider-side lease is not exact-base CAS and must fail before send. Git tree traversal must prove each required
workflow path, blob OID, raw-byte hash, parsed trigger semantics, and identity from the reviewed
release tree. A nonempty required-workflow identity set must then map one-to-one to raw Actions run
leaves and complete, uniquely paginated jobs-page sets; job completion is derived from the maximum
terminal job timestamp, not trusted from a summary boolean. Main-CI evidence must prove `push`, raw
`head_branch=main`, derived `head_ref=refs/heads/main`, reviewed workflow/ref/blob, and equality among
 the observed main-ref OID, every run head SHA, main-CI head SHA, and merge commit. Hash/OID edges and
the request `clientMutationId` prove that final PR/main-ref observations, reviews, policy snapshots,
and required CI precede the merge request. The GitHub-server order is required-check completion ≤ raw
`merged_at` ≤ Actions creation ≤ run start ≤ jobs-derived completion ≤ repository-closure `Date`;
merge-response, post-merge PR, main-ref, and audit server times each lie independently between
`merged_at` and closure `Date`. Local capture/fetch/sent times are audit-only. A
`workflow_dispatch`, other ref/branch, stale workflow blob, incomplete jobs pagination, pre-merge run,
or same-SHA cross-ref run cannot satisfy F. After all per-workflow captures, one unconditional
repository Actions listing filtered only by main/push/merge SHA must have `total_count <= 100`, one
page, no next link, and exactly one terminal-success maximum attempt for every required workflow.
Its raw leaf supplies the closure start/completion and server Date projected exactly into the closure
set and 15-field main-CI record. A second run, higher/pending attempt, self-asserted later closure time,
or mixed GitHub source profile rejects. The evidence bundle
must exclude the release package/hash, every final decision statement/signature-message/signature-
record/signature-set/outer-receipt object and hash, and post-GO archival records. The actual release
package bytes/hash are detached from the bound release tree and every upstream preimage. Required PR
policy identity contains ordinal/name-or-context/provider-constraint/scope/rule/source but no result
kind; complete current check-run/status populations expand the required result kinds, with dedicated
classic `strict` and provider detail cross-checked against full-protection contexts. Same-name output
from a different provider is invalid. The registered outer package uses verified `H_protocol` and
`CANONICALIZE_protocol`, while its inline release-control/raw evidence uses the mirrored `H_release`
and `CANONICALIZE_release` suite.

The valid package closes only `F_release_evidence_complete`. The final-GO roster then signs a
detached statement through canonical per-signer signature-message, signature-record and signature-set
objects over that package hash. Its registered roster is nonempty, its quorum is positive, and the
set contains at least one valid allowlisted human signature. F remains unchanged. Only A–E,
F-release, and a valid quorum-approved
`decision=GO` complete the Goal. `NO_GO`, `STOP`,
`CANCEL`, and `SUPERSEDE` are human decisions
but never GO. Any tracked post-GO write requires a new complete review/PR/merge/main-CI release
cycle; a detached archival receipt cannot silently mutate the bound release tree.

Until every required choice and stage record externally verifies, no launcher, batch, report,
ledger, downstream process, or reviewer may call the claim, contract, authority policy, sample,
threshold, manufacturing yield, expert metric, or GO ratified.
