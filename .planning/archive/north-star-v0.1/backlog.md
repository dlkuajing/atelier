# North-star staged backlog — ACTIVE / UNRATIFIED

This is a finite dependency DAG over repository work nodes plus the explicit external prerequisite
events X-00A/X-00B below. A missing external event is `BLOCKED_WAIT_EXTERNAL`, never implicit
success. This DAG neither authorizes a confirmatory sample nor schedules a real machine. Gates A–F
remain false. Safe offline work may proceed without human ratification, but no
confirmatory draw, expert disposition, threshold, holdout unseal, CODE V launch, or final GO may
cross its named external gate.

All twelve recorded fixed trees (`57c305f/2b3c73d`, `a5ea60e/930767a`,
`ff76ae0/4317805`, `d9e0e75/00c7af0`, `bd2e1cf/cf9c6f3`, `aca7241/53c2455`, and
`ead809c/b140543`, `8acb078/5856f8d`, `0915ccf/7e004a0`, `2c74a54/5784bac`, and
`02f9d17/7abf1b6`, and `ab7ce4d/f2ff988`) were rejected by independent read-only
review and cannot be published. The fourth tree exposed empty-roster/zero-quorum vacuous
authorization, zero-rater/zero-threshold expert closure, and three runtime digest-selector
omissions. The fifth tree left the GET PR-observation request-body carrier simultaneously typed as
a mandatory digest and required to equal the no-body protocol marker, making release unsatisfiable.
The sixth tree left inventory/admission schema hashes and activation references opaque: it lacked
closed-world typed inventory/admission objects, raw externally attested OS evidence, exact selected-
policy equality, and propagation through the real spawn/receipt chain; both same-tree PASS scopes were
invalidated by that MACHINE P1.
The seventh tree still excluded each inventory/admission `signature_algorithm` from its signed
message and lacked an external allowed-suite/trust-root contract; its durable pre-spawn receipt also
had no fresh raw native inventory/boundary evidence, parser membership, external attester record,
single-use atomic gate transaction, or validity bound repeated through process start. Its two P1s
and the tracked STATE count P2 invalidate all same-tree results.
The eighth tree used the unregistered `registered_object_hash` alias for two content-hash
classification rules, made the DURABLE_COMMIT event subject depend on an attestation record whose
signed source object contains that same event-time leaf, and retained contradictory `25/25/46` and
`27/27/48` machine-binding counts in the acceptance mirror. Its GOVERNANCE and MACHINE P1s
invalidate the same-tree release PASS.
The ninth tree left both STATE entry summaries stale and made PRE_LEASE crash replay
unconstructible: it required the last-durable tuple to resolve a replayed partial-chain transition
while naming a protected intent envelope that is not a machine-chain member and defining no pre-chain
sequence sentinel. Its GOVERNANCE/RELEASE P2 and MACHINE P1 invalidate the tree.
The tenth tree made the PRE_LEASE anchor locally replayable but reused one
`last_durable_member_hash` path for a registered intent-envelope object and ordinary machine typed
leaves, violating the exhaustive registry's one-path/one-reference-class rule. Its MACHINE P1
invalidates the same-tree GOVERNANCE and RELEASE passes.
The eleventh tree split the crash record but left `machine_partial_chain_member_template.typed_leaf_hash`
mixing ordinary typed leaves with the registered protected-terminal envelope, and its new crash
registered path conditionally carried two exact object types even though registry metadata has one
expected-object-type slot. PLAN/SUMMARY/VERIFICATION also retained `2054/2061` while the fixed schema
recomputed `2055/2062`. These GOVERNANCE/MACHINE P1s and MACHINE/RELEASE P2 reject the tree.
The twelfth tree correctly split the carrier classes and exact crash-object types, but its exact
kind-to-template resolution covered only eleven recovery member kinds. Thirteen ordinary typed
member kinds remained unmapped, so same-class cross-kind substitution could pass, including a real
lease-acquisition receipt claimed as `PRE_LAUNCH_SNAPSHOT`. Its MACHINE P1 invalidates the same-tree
GOVERNANCE and RELEASE passes.
Dirty-tree specialist prechecks and author-side PowerShell checks are diagnostic only; a new fixed
commit/tree and three fresh fixed-tree scope reviews remain pending. The current schema target is
exactly 66 registered object types, including canonical authority-roster, authority-quorum-rule,
machine-entry-inventory and machine-admission-receipt
content; 24 detached-signer classes; ten closed hash-reference classes,
26 sealed-manifest fields, 27/27/48 exact launch-ticket/durable-intent/terminal-receipt bindings plus
33 ACTIVE-status-CAS bindings, 33/39-field initial inventory/admission templates, a 64-field durable
pre-spawn receipt, a 36-field process-start receipt, 29 machine typed leaves, 32 evidence-bundle
fields, 43 release/authority-mirror fields, 25 dynamic shared bindings, 64 release Git/CI typed
templates, and 109 null human-owned choices. A–F
and valid human GO
remain false until their external raw evidence exists.

Every item has the same hard budget: **1 implementation + at most 2 evidence-driven fix-forward**.
If that budget is exhausted, the item stops with evidence; there is no unbounded retry. All future
Python checks use `PYTHONUTF8=1`, and all CODE V control checks are fake/offline with both explicit
`-k "not real"` and `-m "not real_machine"` filters. A future test slice must also assert a zero
real-process spawn count; filter names alone are never seat-safety evidence.

## Dependency order

```text
H-00 non-binding human discussion/options (no signature, no gate; may run in parallel)
X-00A SCHEMA_ANCHOR_MACHINE_AND_RELEASE_AUTHORITY_FROZEN
  └─ X-00B ACTIVE_MINIMUM_CLAIM_FLOOR_CHECKPOINT
O-01 preregistration/ITT kernel
  ├─ O-02 C1 exit semantics ─ O-03 namespaces ─ O-04 multi-target reproduction ─ O-05 diagnostics
  │                                                        ├─ O-06 signed two-dimension expert-label import
  │                                                        ├─ O-08 signed TOR import
  └─ M-01 canonical launcher ─ M-02 machine-wide lease ─ M-03 intent/monitor/pins
                                                 ─ M-04 ticket+bypass closure
                                                 ─ M-05 receipt-last+zero-state release
                                                 ─ M-06 fake/offline closure proof

offline O/M implementation may proceed in parallel with X-00A, but machine-policy closure requires X-00A
O-01..O-06 + O-08 + M-01..M-06 + X-00A ─ O-07 fixed run-code review/PR/CAS/main-CI release
O-07 + X-00B ─ final H-01 protocol/authority signature
O-07 + X-00B ─ final H-02 TOR signature
O-07 + H-01 + H-02 ─ H-03 pre-draw custody/draw/activation
H-03 ─ R-00 confirmatory machine population + prelabel freeze
R-00 ─ R-01 post-run optical/repeat/TOR/manufacturing closure
R-01 ─ R-02 protected human-label collection
R-01 + R-02 ─ R-03 independent A–E recomputation
R-03 ─ O-09 final evidence/handoff release ─ H-04 final human decision.
```

## External prerequisite event lane

### X-00A — schema, anchor, machine authority, and release-governance freeze

- **Stable event ID:** `X-00A_SCHEMA_ANCHOR_MACHINE_AND_RELEASE_AUTHORITY_FROZEN`.
- **External owners:** governance-anchor authority, machine-execution authority, and repository
  owner/administrator. This is an operational predicate over the already registered canonical
  `external_governance_anchor`, its out-of-band expected hash/configuration, and live official
  repository capability observations—not a new receipt or signer class. The agent may prepare the
  idempotent NEED and re-evaluate changed external inputs; it may not choose, approve, sign, transfer the repository, change a paid plan, or weaken
  any endpoint requirement.
- **Dependencies:** exact final canonical-schema bytes and their recomputed template hash. Offline
  generic/fake implementation may continue in parallel, but this event cannot close while schema
  bytes are changing.
- **Predicate inputs:** one immutable goal instance/genesis and out-of-band anchor hash; every anchor
  component, including the durable lease/journal authority root, store, native attester/parser/schema/policy controls; status-store,
  trusted-time, cross-clock and OS-evidence controls; and the GitHub source profile. The GitHub
  profile must name an `ORGANIZATION` owner with authorized GitHub Enterprise Cloud audit-log
  visibility and one out-of-band verified nonsecret credential handle/principal used by every
  exchange. That principal must have repository/organization ruleset detail visibility including an
  explicitly present full `bypass_actors` field, classic branch-protection admin-read, merge authority,
  and no applicable bypass. v0.1 additionally requires classic branch protection to return 200,
  nonempty strict/up-to-date required checks, `mergeCommitAllowed=true`, `main` merge queue absent,
  no applicable linear-history, merge-queue, Enterprise-parent, or ruleset-workflow rule, and an
  independently anchored nonempty post-merge `main`/`push` workflow policy. Since
  `mergePullRequest` exposes no expected-base or policy-snapshot CAS, the profile must also bind an
  independent provider-side, fail-closed, irrevocable single-use lease over both every policy-
  administration surface and every `refs/heads/main` update surface. Its acquisition receipt precedes
  policy pass 1; its snapshot receipt binds the complete two-pass policy/queue snapshot; after final
  required checks and request-byte materialization, its one-shot ARMED admission receipt binds the
  exact target, body, normalized headers, principal, preconditions and `clientMutationId` before any
  send; and its terminal receipt proves zero policy changes, zero foreign main updates, exactly one
  bound merge, and no early release/fail-open. The snapshot hash, but not the later admission hash,
  enters `clientMutationId`, avoiding a hash cycle while the request leaf binds both. If that
  external acquisition→snapshot→admission→request→response→terminal primitive is unavailable, v0.1 is
  `BLOCKED_WAIT_EXTERNAL`; `strict`, `expectedHeadOid`, stable reads, and post-hoc audit do not replace
  it. The enterprise audit
  stream must be provider-configured and bind enterprise→organization membership, stream ID,
  destination and partition, plus a provider-backed event-time watermark that closes the audit query
  window; a local collector signature, stable polling or dwell is insufficient. The current
  `dlkuajing/atelier` USER ownership, observed HTTP 403 policy endpoints, or absence of such a provider
  watermark do not satisfy this event and may never be interpreted as an empty policy or audit.
- **Exit criteria:** the verifier recomputes the registered anchor object hash and canonical schema
  hash under the bootstrap suite and both equal the out-of-band expected inputs; its exact
  `goal_instance_id`, genesis and selected controls also equal those expected
  inputs; and the live repository capability observations satisfy the release profile. Actual
  machine-entry inventory/admission-boundary selection remains a later H-01 protocol choice and its
  enforcement evidence remains H-03/R-00; X-00A does not attest either. v0.1 has no anchor rotation or migration.
- **Wait/resume protocol:** unsatisfied predicate => persist `BLOCKED_WAIT_EXTERNAL` and emit at most
  one NEED keyed by `{goal_instance_id,event_id,canonical_schema_template_hash}`. No blind polling or
  retry. Re-evaluate only after at least one externally controlled anchor/configuration/capability
  observation byte sequence changes; retain invalid inputs and rejection evidence.
- **Retry budget:** one evaluation per distinct external input tuple; identical bytes are never retried.

### X-00B — active minimum-claim floor and checkpoint

- **Stable event ID:** `X-00B_ACTIVE_MINIMUM_CLAIM_FLOOR_CHECKPOINT`.
- **External owner:** minimum-claim authority and the separately approved append-only atomic-CAS
  checkpoint-store authority. The agent may prepare and verify, never sign or advance the store.
- **Dependencies:** X-00A exact goal instance, schema bytes/hash, genesis and immutable anchor.
- **Event identity:** the canonical tuple `{minimum_claim_envelope_hash,
  minimum_claim_authority_signature_set_hash,current_checkpoint_hash,current_checkpoint_generation}`;
  no new receipt type is introduced.
- **Bindings:** minimum-claim envelope, human signature set, comparator/lineage, checkpoint
  store policy, accepted CAS current-head hash and generation. A genesis floor must descend from the
  X-00A goal genesis; a successor must descend from the current active checkpoint and be deterministically
  equal or broader.
- **Exit criteria:** the complete signature and lineage chain verifies and one durable accepted CAS
  head is current. The floor is run-code-release-independent only because the schema and every anchor
  component are already frozen by X-00A.
- **Wait/resume protocol:** the same idempotent NEED and `BLOCKED_WAIT_EXTERNAL` rules as X-00A;
  verify when dependency X-00A first transitions to satisfied, or re-evaluate when this four-member
  canonical tuple changes. An identical tuple under an unchanged satisfied X-00A is never retried;
  the scheduler cache key scopes to `{goal_instance_id,canonical_schema_template_hash,
  X00A_input_digest,event_tuple}` and is not a gate object or receipt.
- **Retry budget:** one verification attempt per distinct scoped scheduler cache key; the same event
  tuple may be verified once after a genuinely changed X-00A input digest, but never retried under an
  unchanged key.

## Offline implementation lane

### O-01 — strict preregistration and ITT protocol kernel (first code slice)

- **Gates:** A, C, D, E.
- **Dependencies:** the canonical schema plus three v0.1-draft UNRATIFIED mirrors; no human decision is required to
  implement null/default-deny schemas.
- **Exit criteria:** the protocol freezes sampling frame, eligibility rule, population counts and
  allocation rules. `planned_identity_mapping_content_hash` and
  `eligibility_decision_set_content_hash` are separate domain-separated, verifier-recomputed hashes
  over exact closed-world member templates and explicit formulas: targets follow contiguous
  `draw_ordinal`; candidates follow resolved target order plus contiguous `candidate_slot_ordinal`;
  runs follow resolved candidate order plus contiguous `run_ordinal`; attempts follow resolved run
  order plus contiguous `attempt_sequence`; eligibility has exactly one decision per target in that
  same target order. Every derived nested hash has one declared runtime source path, inline exact
  content or exact sealed-content container, value template, unique domain and formula; a hash-only
  detached value without uniquely locatable bytes rejects. `planned_candidate_slot_id` is the single
  candidate-slot identifier throughout mapping, run parentage, source evidence, views, clusters,
  intents and labels. Missing, extra, duplicate, gapped, reordered, aliased, opaque-root, missing-source,
  or ID-fallback forms reject. The post-draw/pre-access sealed manifest atomically assigns actual target/seed-
  cluster/patent-family/candidate/run/attempt IDs and eligibility. A run belongs to one candidate;
  immutable monotonic initial/retry attempts belong to one run and never create denominator units;
  the run terminal is derived once by the frozen retry/aggregation rule. Mutually exclusive terminal
  states and retry mapping are closed. Exclusions require a registered domain-separated record binding
  goal, active checkpoint/floor, protocol, batch, manifest, member, reason/evidence policy, current
  pre-outcome audit head, independent raw evidence, protected validation terminal, frozen automatic
  rule input/output, and official machine receipt; distinct planned run-unit and candidate-slot
  ITT populations; exact `pipeline_delivery_rate`, `expert_worth_reviewing_rate_itt`, and
  `expert_production_usable_rate_itt` formulas; raw numerator/denominator/exclusion/cluster/CI report
  tuple; contaminated attempts retained and mapped without shrinking ITT; conditional rates marked
  diagnostic only; unknown/unsigned input rejected. The single closed-world schema implements
  separate immutable minimum-claim/protocol/activation/final signature sets. The verifier recomputes
  `canonical_schema_template_hash` from the exact final schema bytes under the out-of-band
  bootstrap suite and requires equality with the external governance anchor, protocol manifest
  binding, protocol package, sealed manifest, activation manifest, and activation package; an
  internally self-consistent foreign schema or any one-object splice rejects. The active floor has
  a durable append-only atomic-CAS high-water checkpoint and deterministic anti-rollback lineage/
  equal-or-broader verification with scenario IDs exact in v0.1; every signer uses unsigned message→
  detached signature record→envelope/set with no self-hash; protocol and activation approval message
  types are distinct; one out-of-band governance anchor covers protocol, activation, custodian, broker, expert and
  final-GO signers; protocol→draw→activation ordering; membership-proved single-use access
  capabilities whose signed intents advance both audit and consumed-index roots before
  unseal/view/run/label/export and whose terminals chain from those roots. Before the first label
  intent/view/outcome, one immutable `candidate_prelabel_binding_manifest` partitions every planned candidate slot into
  one duplicate-free, disjoint, exhaustive available/unavailable partition and binds each available
  slot to actual artifact bytes and membership, required label-view objects, content/lineage
  fingerprints, deterministic equivalence/duplicate-cluster membership, and source machine evidence.
  A separate custody-broker-signed four-object freeze chain — transition, signature message, detached
  signature record, and envelope — commits that manifest through an attested atomic CAS over the
  current audit and consumed-index roots. It requires `new_sequence == prior_sequence + 1`, carries
  the consumed root forward unchanged, binds the complete protected-run/machine link set and store
  receipt, and precedes every label intent or exposure. Every source run/attempt must already be
  terminal or consumed-incomplete, and no run intent may be signed after freeze; labels cannot
  self-declare, expose early, mutate, promote unavailable slots, or swap any bound value.
  All-slot denominators and at-most-one independent numerator per cluster remain fixed. Canonical hard
  invariants reject non-null but weaker ITT, retry, exclusion, conditional-rate, cluster or label
  policies; positive/negative vectors cover stale/forked floor rollback, changed scenario set,
  pre-draw actual-ID assignment, reversed run/attempt parentage, cross-batch exclusion/draw/activation
  replay, mapping/eligibility reorder or opaque roots, missing/ambiguous nested-content source paths,
  canonical-schema-hash splice, `candidate_id`/`planned_candidate_slot_id` aliasing, source run mapped
  to another slot, candidate-byte/label-view/manifest swap, label or view before signed CAS freeze,
  duplicate/overlapping/incomplete partition, same-byte-root split, same-semantic-fingerprint split,
  producer-selected partition, second freeze, prior candidate/cluster-peer exposure, a nonblank or
  suggestion-bearing entry form, expert signature before required access or raw human entry,
  duplicate-cluster split, orphan or
  cross-paired protected run/machine attempts, incomplete-attempt success, an orphan ticket or durable
  intent hidden behind an opaque retained-chain hash, and non-main/non-push/foreign-workflow/pre-merge
  main CI. The schema uses a per-instance dependency DAG: template registration order is not accepted
  as object creation order, every direct and typed-leaf-transitive registered hash edge resolves to
  one expected type, and unresolved, ambiguous, cyclic, or forward-self-created instance graphs reject.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_north_star_protocol.py tests/test_north_star_itt.py -q -k "not real" -m "not real_machine"`
  and `$env:PYTHONUTF8='1'; uv run ruff check app/core/north_star tests/test_north_star_protocol.py tests/test_north_star_itt.py`.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### O-02 — C1 EFL + IMH with derived-FOV exit semantics

- **Gates:** B, C.
- **Dependencies:** O-01.
- **Exit criteria:** C1 distinguishes EFL convergence, IMH machine-achieved evidence, and FOV
  derived from same-source EFL/IMH; missing explicit FOV cannot silently flip a successful machine
  unit to a contradictory outer exit; non-converged/missing/blocked units map to ITT not-passed;
  no IMH/FOV promotion into optimizer `CONVERGED_FIELDS`.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_c1_exit_semantics.py tests/test_stagec_contract.py -q -k "not real" -m "not real_machine"`
  and `$env:PYTHONUTF8='1'; uv run ruff check app/core/orchestration tests/test_c1_exit_semantics.py`.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### O-03 — per-requirement artifact namespaces

- **Gates:** B, C.
- **Dependencies:** O-01, O-02.
- **Exit criteria:** every requirement/target/candidate/attempt/run has a collision-resistant,
  deterministic artifact namespace; retries cannot overwrite prior bytes; manifests bind all paths
  and hashes; the known C1 multi-requirement artifact-key collision has a fail-closed regression.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_artifact_namespace.py tests/test_candidate_persistence.py -q -k "not real" -m "not real_machine"`
  and `$env:PYTHONUTF8='1'; uv run ruff check app/core/orchestration tests/test_artifact_namespace.py`.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### O-04 — multi-target exports and deterministic reproduction

- **Gates:** B, C.
- **Dependencies:** O-01, O-02, O-03.
- **Exit criteria:** more than one independent target can be exported and restored without
  namespace collision; bundle/workbook/manifest/candidate bytes share target and source hashes and
  resolve to the same `candidate_prelabel_binding_manifest` member, actual byte-set root, artifact-membership manifest,
  content/lineage fingerprints, equivalence cluster, and required label-view object-set root;
  reproduction checks the frozen code/evidence schema and refuses missing/foreign/swapped artifacts
  or a self-consistent manifest that points at different bytes; no single-target observation is
  generalized into a rate.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_multi_target_exports.py tests/test_reproduction_bundle.py -q -k "not real" -m "not real_machine"`
  and `$env:PYTHONUTF8='1'; uv run ruff check app tests/test_multi_target_exports.py tests/test_reproduction_bundle.py`.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### O-05 — evidence diagnostics without gate promotion

- **Gates:** C, D.
- **Dependencies:** O-01, O-04.
- **Exit criteria:** diagnostics expose blocked/degraded/failed/non-converged/missing/unlabelled/
  undelivered/saturated/compensation-failed counts; C's manufacturing output remains unavailable
  without signed TOR and D's expert metrics remain unavailable without authorized signed labels;
  conditional-on-delivered views are visibly diagnostic and cannot set a gate;
  ledger recomputation consumes raw receipts/hashes rather than trusting cached booleans. It
  independently rederives exact mapping/eligibility content hashes, the
  `candidate_prelabel_binding_manifest` available/unavailable partition and duplicate clusters, and
  the `protected_run_machine_attempt_link_set_manifest` bijection; orphan,
  cross-paired, reused, or consumed-incomplete chains remain visible and never count as success. It
  also replays the unique broker-signed prelabel CAS envelope, proves the partition existed before
  every label/view exposure, proves no run followed freeze, and rejects any source receipt whose
  attempt→run→planned-slot reverse mapping differs from the candidate member.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_north_star_diagnostics.py tests/test_evidence_recompute.py -q -k "not real" -m "not real_machine"`
  and `$env:PYTHONUTF8='1'; uv run ruff check app/core/north_star tests/test_north_star_diagnostics.py`.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### O-06 — externally signed two-dimension expert-label import

- **Gates:** D.
- **Dependencies:** O-01, O-04, O-05; only explicit UNRATIFIED/test-root fixtures, never a real H-01
  signature or holdout, are used while implementing the importer.
- **Exit criteria:** import only; both `expert_worth_reviewing` and
  `expert_production_usable` label dimensions come from allowlisted external human expert(s) under
  the ratified rater-count/blinding/combination policy. Each label intent, completed access terminal,
  and signed label resolves one immutable `candidate_prelabel_binding_manifest` member plus its unique
  custody-broker-signed CAS freeze envelope and exactly matches its planned
  slot, candidate artifact-membership manifest, actual byte-set root, required label-view object-set
  root, content/lineage fingerprints, deterministic equivalence-cluster ID, rubric, timestamps, and
  signatures; the terminal proves all required view objects were accessed. Duplicate slots
  stay in the denominator while one equivalence cluster contributes at most one independent
  numerator under the signed aggregation rule; missing, duplicate, author-generated, self-declared,
  or mismatched labels remain unavailable; manifest swaps, labels over different candidate bytes,
  self-declared fingerprint/lineage/cluster values, label/view exposure before freeze, source evidence
  from a different planned slot, unavailable-to-available promotion, second freeze, and duplicate-
  cluster splitting reject. The label
  uses canonical content→detached signature→envelope objects and the common external trust verifier;
  no AI verdict path.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_signed_expert_label_import.py -q -k "not real" -m "not real_machine"`
  and `$env:PYTHONUTF8='1'; uv run ruff check app/core/north_star tests/test_signed_expert_label_import.py`.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### O-07 — pre-run code review / PR / CI commit-and-tree binding

- **Gates:** none; prerequisite-only. This registered RUN_CODE_RELEASE package cannot close A–F.
- **Dependencies:** O-01 through O-06, O-08, and M-01 through M-06.
- **Exit criteria:** exactly three external common-trust review chains cover `GOVERNANCE`, `MACHINE`,
  and `RELEASE_GIT_CI`; their resolved principals/accounts/keys/identities are mutually distinct and
  disjoint from the anchored development/tuning/execution rosters. Each binds the same exact commit
  and tree from an independent read-only checkout. Before review, raw Git replay binds every rebased
  base-to-head parent edge, commit author/committer, and PR author; after merge, raw audit/Actions
  evidence binds the merge actor and every selected run actor/triggering actor. PR API proves reviewed tree equals final head tree and every required check targets that head
  and is terminal with conclusion `success`; merge uses an accepted compare-and-swap whose
  `expectedHeadOid` equals that reviewed head; merge attestation proves the merge tree equals the
  reviewed head tree apart from commit-parent packaging. The raw merge request `clientMutationId`
  commits the three-review set, final-PR and premerge-main observations, policy snapshots, and required
  PR CI before the expected-head CAS. It also commits the signed snapshot receipt in a provider-side
  acquisition→snapshot→admission→terminal lease that freezes both policy and `refs/heads/main`; without this
  external exact-base primitive, the request is never sent. Required-check policy identity contains
  name/context, provider constraint, scope/rule/source and ordinal but no result kind; complete current
  check-run/status populations expand the required result kinds, so a same-name wrong-provider success
  rejects and both kinds are required when both are present. The dedicated classic endpoint supplies
  `strict`/provider detail while its contexts must agree with full branch protection in both passes. The
  transmitted merge request's unique JSON `query` string, after strict unescaping to UTF-8, must
  byte-equal the bound source profile's strict-Base64-decoded fixed query and share its exact digest;
  its closed-world AST must contain exactly one `mergePullRequest(input: …)` mutation and directly map
  the exact `pullRequestId`, `mergeMethod`, `expectedHeadOid`, and `clientMutationId` variables once
  each, with the node ID reparsed from the same final PR observation. Alias, fragment, unused variable,
  literal indirection, byte-different re-encoding, or a detached query rejects before send. Every required main workflow is proven from
  raw API evidence to be a post-merge run with `event == push`, `head_ref == refs/heads/main`,
  `head_branch == main`, and `head_sha == main_ref_oid_at_observation == merge commit hash`, using
  the reviewed `workflow_file_path`, `workflow_ref`, `workflow_file_git_blob_oid`,
  `workflow_file_raw_bytes_hash`, and `workflow_blob_proof_leaf_hash`; GitHub server
  `Date` and event times establish the post-merge closure, while local capture/fetch/sent timestamps
  are audit-only. A
  workflow-dispatch, non-main ref, foreign workflow blob, pre-merge run, or empty coverage rejects;
  any finding or
  tracked write invalidates the pre-merge binding and requires a new commit, static checks, and
  independent review; no tracked post-freeze review artifact mutates the reviewed tree. The
  post-merge attestation is external and binds PR head, required checks, the terminal freeze receipt,
  merge commit/tree, and main CI record. The canonical RUN_CODE_RELEASE package executes the accepted main merge commit and the
  byte-identical reviewed tree. This closes only the frozen run-code release used by R-00; it cannot stand in for the
  later evidence/handoff release after confirmatory execution.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_review_tree_binding.py -q -k "not real" -m "not real_machine"`
  and `git diff --check` before commit, followed by read-only equality checks against the external
  review/PR/CI record after commit and the external post-merge attestation after merge.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### O-08 — externally signed TOR contract import

- **Gates:** C.
- **Dependencies:** O-01, O-04, O-05; only explicit UNRATIFIED/test-root fixtures, never a real H-02
  signature or confirmatory result, are used while implementing the importer.
- **Exit criteria:** import verifies external manufacturing/statistics authority and the exact eight
  fields `tor_semantics`, `tor_units`, `tor_table_hash_selection`, `tor_monte_carlo_denominator`, `tor_compensator_policy`,
  `tor_aggregation_rule`, `tor_saturation_mapping`, `tor_compensation_failure_mapping`, thresholds,
  confidence/cluster method, and signatures;
  each named field must be non-null and hash-consistent or manufacturing metrics remain unavailable.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_signed_tor_import.py tests/test_tor_itt_mapping.py -q -k "not real" -m "not real_machine"`
  and `$env:PYTHONUTF8='1'; uv run ruff check app/core/north_star tests/test_signed_tor_import.py`.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

## P0 CODE V machine-authority lane — mandatory before every future real-machine task

### M-01 — one canonical launcher

- **Gates:** B, C, F.
- **Dependencies:** O-01; read-only inventory of every launch-capable surface. The node before O-07
  is only generic/fake implementation readiness; X-00A/H-01/H-03/R-00 close later external policy and
  enforcement evidence.
- **Offline exit criteria for O-07 (does not close B/C/F):** exactly one production subprocess creation seam owns CODE V; Web
  `POST /candidates`, C1 CLI, P18 real, P13/P14/P15/probes, Stage B, Stage C, and ordinary
  `real_machine` tests cannot launch around it; retained direct-Popen tools default deny. The later
  H-01/H-03 machine-entry inventory must also cover Task Scheduler, services, startup entries, other worktrees,
  external scripts, and manual entry points. A cooperative repository lock alone cannot close this
  gate: one human-approved OS admission boundary or unique broker must make noncanonical execution
  impossible; absent that enforcement, M-01 stays false.
- **Exact offline checks:**
  `rg -n "subprocess\.Popen|run_codev_process_bytes|codev\.exe|codevm" app scripts tests .planning/loop`
  plus `$env:PYTHONUTF8='1'; uv run pytest tests/test_codev_canonical_launcher.py -q -k "not real" -m "not real_machine"`;
  the later machine-entry inventory/admission receipt is a human-approved external gate, not
  something these repository checks may self-attest.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### M-02 — machine-wide OS lease

- **Gates:** B, C, F.
- **Dependencies:** M-01 for generic/fake implementation. The exact external transactional machine
  lease/journal authority is selected only in final H-01 after O-07 and enforced/attested only in
  H-03/R-00. A Global named mutex and/or controlled `ProgramData` ACL may be
  optional defense in depth only and cannot implement or replace the lease/journal authority.
- **Offline exit criteria for O-07 (does not close B/C/F):** the implementation can enforce a lease that is machine-wide across users/worktrees; public caller cannot redirect the
  authority root; owner metadata is diagnostic only; unknown owner/lease state fails closed without
  deletion, killing, recovery guessing, or fallback to the current user-scoped lock. The approved
  OS admission boundary requires every allowed launcher, including manual and external callers, to
  acquire through this same authority; otherwise the gate remains false. The external anchor fixes
  its root, store identity, native receipt-attester allowlist, acquisition/journal/barrier/atomic-
  receipt parsers, atomic receipt schema, and release-journal store policy.
  Native atomic-acquisition, OS-acquisition, barrier, journal-store, atomic-release, and OS-release
  responses must each resolve their exact source-specific acyclic signed projection. Batch/activation/
  run context, host/broker/lease and source-specific operation/transaction/roots/outcome are signed.
  Acquisition signs its barrier, the barrier signs all ordered operation members, journal and atomic
  release sources sign their own transition, prior-journal raw request/entry, result, and time
  bindings, while OS release signs only its exact 24-field OS semantic projection without raw journal
  request/entry. Only enumerated self-container/control/
  later fields are excluded, never every `_leaf_hash`. Caller request and journal-entry hashes are
  committed by their named signed responses, with closed-world raw-source coverage.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_codev_machine_wide_lease.py -q -k "not real" -m "not real_machine"`
  including two-user/redirect/permission/unknown-owner fake cases; no CODE V executable is invoked.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### M-03 — durable intent, conflict monitor, and official pins

- **Gates:** B, C, F.
- **Dependencies:** M-01, M-02.
- **Exit criteria:** durable intent precedes process creation; exact `pre_launch`/`during_run`/
  `post_run` snapshots cover `runner`, `codev`, `codevm`, `p18_owner`, `global_owner`,
  `per_call_owner`, `launched_subtree`, and `unknown_carrier`; official executable, macro, version,
  the subject and phase arrays have exact canonical order/length with no duplicate or alias; the
  selected machine policy has exactly the canonical 19 keys and no weaker replacement; the durable
  machine intent has exactly the canonical 25 bindings with no alias, extra, null, or omitted field;
  and sequence hashes are pinned before launch. The durable intent resolves the signed protected
  `run` access intent and exactly carries its activation package/signature set, capability,
  membership proof, run/attempt/host/launcher/broker/lease, complete command, input set, and toolchain
  pins; a same-batch but different protected intent cannot be substituted. Missing/unreadable/conflicting state fails closed and
  does not kill or clear anything. On a detected conflict, the launcher terminates only a subtree it
  can cryptographically/process-parentage prove it owns, marks the current attempt `contaminated`,
  immutably preserves raw artifacts and logs, leaves unknown processes untouched, and emits a NEED
  record; the planned run unit remains in ITT under the frozen retry mapping.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_codev_launch_intent.py tests/test_codev_conflict_monitor.py tests/test_codev_toolchain_pins.py -q -k "not real" -m "not real_machine"`.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### M-04 — launch ticket and bypass closure

- **Gates:** B, C, F.
- **Dependencies:** M-01, M-02, M-03.
- **Exit criteria:** content-hash-bound, single-use launch ticket is issued only after authority,
  lease, intent, monitoring, and pins pass; every Web/CLI/batch/probe/test surface defaults deny
  without it. The launch ticket has exactly the canonical 25 bindings. The ticket, durable machine
  intent, terminal receipt, and protected terminal all resolve
  the exact same protected run intent/capability/member and run/attempt/machine tuple; ticket reuse,
  scope drift, cross-pairing, unknown caller, or direct `Popen` is rejected before spawn.
  While the lease is held, every shell, test, import, or runner that is not on the signed pure-offline
  allowlist is denied, including a second runner. Machine-entry inventory drift or missing OS
  admission evidence also rejects before spawn.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_codev_launch_ticket.py tests/test_codev_bypass_closure.py -q -k "not real" -m "not real_machine"`
  and the M-01 `rg` inventory must show no unapproved spawn seam.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### M-05 — receipt-last persistence and zero-state release

- **Gates:** B, C, F.
- **Dependencies:** M-01 through M-04.
- **Exit criteria:** the lease-owning canonical broker is separate from every zero-state subject;
  `runner` means a run child or competitor and global/per-call owner carriers are not the lease owner.
  Exactly one attested broker retains the same `lease_instance_id` through the complete fixed order
  `terminal_artifacts → post_run_snapshot_and_monitor → zero_state_proof →
  active_machine_receipt_status_cas_receipt → durable_machine_terminal_receipt →
  protected_access_terminal_envelope → lease_release_transition →
  durable_broker_release_journal_prepared → OS_release +
  durable_broker_release_journal_os_release_committed as one atomic authority transaction → durable_release_status_cas_receipt →
  durable_lease_release_receipt`. The receipt binds batch/run/attempt IDs, host,
  PID, broker/lease identity, owner, start/end, complete command, single-use launch
  ticket/nonce, intent/toolchain/input hashes, pre/during/post process snapshots, terminal state,
  every raw/derived artifact hash, and prior/new audit-chain heads. An append-only consumed-ticket
  index rejects replay. The terminal receipt has exactly the canonical 46 bindings. One closed-world
  ordered `protected_run_machine_attempt_link_set_manifest` gives every
  protected run intent exactly one member: either a complete ticket→machine-intent→machine-receipt→
  protected-terminal chain or an explicit `consumed-incomplete` chain that cannot emit success. All
  consumed-incomplete members use an exact tagged crash-frontier schema that enumerates every extant
  launch ticket and durable intent rather than an opaque retained-chain hash. Every run intent,
  launch ticket, durable intent, receipt and terminal has complete forward-and-reverse coverage; all
  hashes are unique. Missing, extra, duplicate, reused, orphaned, or
  cross-paired objects and any run/attempt/host/broker/lease/command/input/pin mismatch reject. A terminal artifact or monitored-subject change after zero proof invalidates
  the proof before ACTIVE CAS and forces a new monitor/zero proof. A monitored change after ACTIVE
  CAS but before the full receipt must abort into the `ACTIVE_CAS_ONLY` recovery path, abandon that
  status, safety-release, and remain consumed-incomplete; it may not rewrite the pre-status payload
  or emit a normal receipt. Every status, protected-terminal,
  transition and journal write above must persist in order. The selected external lease authority
  must atomically commit both OS release and the durable `OS_RELEASE_COMMITTED` journal entry, or
  neither, under one operation ID. After restart, a PREPARED operation must be atomically terminalized
  by that authority as irrevocable `ABORTED_FINAL` with its lease still held, or proven already
  `COMMITTED` with the exact durable journal. Transient `NOT_COMMITTED`, pending, unknown, partial,
  unqueryable, or released-without-journal state keeps machine admission closed. Every new acquisition
  must consume a complete authority-wide cross-batch/host/broker barrier with zero unresolved PREPARED
  operations in the same atomic transaction as lease insertion.
  After the OS-release-committed journal, one
  atomic external status CAS changes `ACTIVE` to `RELEASED` before the final release receipt. A crash before terminal
  state cannot emit success; lease release occurs only after `runner`, `codev`, `codevm`, `p18_owner`,
  `global_owner`, `per_call_owner`, and `launched_subtree` are proven zero/absent and
  `unknown_carrier` is absent; unreadable or unknown state retains the lease and fails closed
  without destructive cleanup.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_codev_receipt_last.py tests/test_codev_zero_state_release.py -q -k "not real" -m "not real_machine"`.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### M-06 — pure-fake offline closure proof

- **Gates:** B, C, F.
- **Dependencies:** M-01 through M-05.
- **Exit criteria:** fake process matrix proves mutual exclusion, ticket denial, bypass denial,
  intent ordering, pin mismatch, unknown carrier, owned-subtree-only termination, permanent
  contaminated-attempt/raw-log preservation, lease-held shell/test/import/second-runner denial,
  machine-entry inventory/admission failure, crash boundaries, full receipt bindings, the exact
  broker-held `zero-proof → ACTIVE-CAS → receipt → protected-terminal → release transition →
  PREPARED journal → OS release + OS_RELEASE_COMMITTED journal as one atomic authority transaction →
  RELEASED-CAS → durable-release-receipt` order,
  plus the invalidated-receipt monitor/zero crash frontier, ACTIVE-CAS-only abort path, atomic
  OS-release/journal operation, PREPARED-operation irrevocable ABORTED_FINAL-or-COMMITTED resolution,
  same-transaction pre-acquisition global barrier, and exact pre/during/post
  snapshots plus zero-state release for `runner`, `codev`, `codevm`,
  `p18_owner`, `global_owner`, `per_call_owner`, `launched_subtree`, and `unknown_carrier` across all
  launch surfaces; unknown/unreadable state retains the fake lease, and instrumentation proves no
  `codev`/`codevm` process started. Negative cases cover missing/extra/duplicate/reordered subject and
  phase entries, aliases including `CODE V`, old `zero_owner_release_policy`, wrong terminal order,
  changed/multiple broker identity and unknown carrier not absent. They also cover protected run intent
  paired to another machine receipt, every orphan class including ticket-only and durable-intent-without-
  receipt crash frontiers, an opaque retained-chain substitute, duplicate/reused chain hashes, any
  27/27/48/33 binding-count or field mismatch, and consumed-incomplete counted as success. Fake tests
  cannot replace the signed machine admission/inventory receipt.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_codev_authority_matrix.py -q -k "not real" -m "not real_machine"`
  followed by `git diff --check` and independent non-author review of the exact commit/tree.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

## External human gates — minimum-claim floor may close after X-00A; protocol/TOR signatures follow frozen code

### H-00 — non-binding human discussion and option design

- **Gates:** none.
- **Dependencies:** none.
- **Exit criteria:** humans may discuss scope, floor lineage, rubric, TOR and machine mechanisms and
  return draft choices; no canonical signature, active-floor update, draw, threshold, gate or
  confirmatory authority is created. Silence selects nothing.
- **Exact offline checks:** response is visibly `DRAFT`/`UNRATIFIED` and absent from every signature
  set, active-floor input and confirmatory evidence bundle.
- **Retry budget:** 1 package + at most 2 evidence-driven clarification revisions.

### H-01 — verified active minimum-claim plus final protocol, authority, rubric, and sample-design ratification

- **Gates:** A, D.
- **Dependencies:** O-07, O-06, O-08, H-00 option work, and X-00B's valid externally signed active
  minimum-claim floor/current anti-rollback checkpoint. The floor chain is run-code-release-independent
  only after X-00A freezes the exact schema bytes/hash, goal instance and every anchor component; it
  may then be signed and activated before O-07 and does not claim to bind run code. Final protocol
  signatures must follow O-07 and bind its exact fixed run-code commit/tree and the same immutable
  protocol-package bytes consumed independently by H-02.
- **Exit criteria:** minimum-claim/claim/optical/manufacturing-statistics authorities, immutable allowlists,
  machine-execution authority, externally pretrusted trust policy/root set, registered stage-specific
  nonempty roster/quorum content, exact human-selected within-role `AND`/`OR` and role-separation
  rules, final-GO nonempty roster/positive quorum, common trust coverage for all 24
  signer classes including independent custody store/pre-draw clock/review clock/review event-time,
  machine time/status, GitHub transport/audit and repository-freeze attesters, 主公 qualification choice, claim
  scope, independence/sample choices, rubric, thresholds, all content/hash bindings, and external
  minimum-claim floor signature set, deterministic equal-or-broader lineage and current durable
  high-water checkpoint verify from the anchored goal genesis without opaque proof hashes or rollback;
  protocol signatures verify through the active checkpoint/floor → protocol-package →
  domain-separated approval-message → detached signature-record → canonical signature-set DAG
  before any draw; every per-role and total quorum minimum is positive, every accepted stage set has
  at least one valid allowlisted human signature, and the verifier rejects empty/vacuous membership,
  quorum, or separation while silence selects nothing. Every counted signature's identity/proof/key/
  allowlist tuple must exactly match one same-role registered roster member; `AND` equals the roster
  tuple set and `OR` is only a nonempty duplicate-free subset. The actual sealed-manifest hash,
  draw/activation/access records, and post-evidence final-GO
  decision/signature/evidence-bundle fields are explicitly not H-01 prerequisites and remain null.
- **Exact offline checks:** external signature verifier plus schema/property checks proving every
  protocol-required field is non-null, satisfies every canonical hard invariant, and is bound to the same active floor/claim/contract/policy/run-code
  commit/tree/evidence schema/sampling frame/trust policy, while actual manifest and every later-stage
  field remain unavailable;
  the exact verifier command must be added by the ratified signature-algorithm decision before use.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### H-02 — manufacturing/statistics TOR ratification

- **Gates:** C.
- **Dependencies:** O-07, O-08, H-00, X-00B/current checkpoint, and authorized manufacturing/
  statistics and optical-expert authorities. H-02 and H-01 independently sign the same immutable
  final protocol-package bytes; neither signature chain depends on the other, and both must close
  before H-03.
- **Exit criteria:** the exact keys `tor_semantics`, `tor_units`, `tor_table_hash_selection`,
  `tor_monte_carlo_denominator`, `tor_compensator_policy`, `tor_aggregation_rule`,
  `tor_saturation_mapping`, `tor_compensation_failure_mapping`, confidence/cluster method,
  thresholds, and signatures are hash-bound;
  no value is inferred from current exploratory saturation evidence.
- **Exact offline checks:** the ratified external signature-verifier command plus O-08 tests; no
  machine execution is part of ratification.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### H-03 — holdout draw, activation, and protected-access authority

- **Gates:** E.
- **Dependencies:** O-07, final H-01, final H-02; an independent external custodian and approved
  out-of-workspace system. It cannot proceed in parallel with code/schema work.
- **Exit criteria:** after protocol signatures, the custodian applies the signed sampling algorithm
  only after the external governance anchor fixes exact development/tuning/execution actor rosters,
  the custodian allowlist is disjoint from all three by principal and account, and the externally
  anchored custody-audit genesis, durable atomic-CAS current head, store policy/identity, and
  pre-draw evidence schema verify. The complete genesis-to-current audit prefix and five distinct
  raw control leaves (encryption, ACL, non-access, source-pool isolation, role separation) must cover
  the draw CAS time; any intervening control or access change advances the same compared head.
  The custodian then applies the signed sampling algorithm
  and produces one sealed manifest plus draw content→signature message→detached signature record→
  envelope binding protocol/signature set, batch/draw IDs, source snapshot,
  randomness commitment/transcript, actual sealed manifest, identity, timestamp, and pre/post audit
  heads. The draw resolves the sealed manifest and exactly agrees on ratification, batch, draw,
  protocol package/signature set, manifest hash, sampling frame/source/algorithm/entropy commitment, target
  distribution, and target count. Activation resolves that same draw and sealed manifest and repeats
  the same values exactly; a batch-A draw/manifest cannot activate batch-B, and activation cannot
  precede draw. Activation initial audit root must equal the signed draw new root and its consumed root must
  equal the canonical activation/capability-set genesis. Required authorities then sign activation
  before any unseal/view/run/label/export. Every capability action/object/time scope is a subset of
  activation; every
  protected action proves capability membership, atomically consumes one nonce and publishes a signed
  intent envelope with new audit/consumed-index roots before action plus a signed terminal envelope
  afterward whose prior roots equal the intent new roots; crash remains provably consumed+incomplete
  in the final root, replay and head mismatch reject.
  Encryption/ACL, technical pre-freeze non-access proof, append-only audit, and role separation all
  verify. Inability to prove non-access forces exploratory-only plus NEED. This backlog performs no
  draw, activation, or access.
- **Exact offline checks:** the ratified custody verifier validates manifest commitment, ACL/audit
  export, draw and activation bindings, role separation, capability membership, signed intent/
  terminal envelopes, replayed audit/consumed-index roots,
  and custody signatures without exposing holdout content to the workspace. Negative vectors swap
  batch, protocol/signature set, manifest, distribution/count, or draw time one field at a time; its exact command is
  part of the signed holdout protocol.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

## Future real-machine barrier

### R-00 — confirmatory real-machine population and prelabel freeze (not authorized or scheduled)

- **Gates:** B, E; produces raw inputs for C and D but cannot close either alone.
- **Dependencies:** O-01 through O-08, M-01 through M-06, H-01 through H-03, a new sealed holdout,
  exact fixed commit/tree, independent non-author review, and proof that no substantive post-seal
  change invalidated the batch.
- **Exit criteria:** only the ratified protocol may define and authorize the actual run. Every
  preregistered run unit and permitted attempt is actually driven to one frozen terminal or
  consumed-incomplete state; no slot or attempt is omitted because of outcome. Canonical launch ticket,
  machine-wide broker-held lease, intent/monitor/pins, exact pre/during/post snapshots of `runner`,
  `codev`, `codevm`, `p18_owner`, `global_owner`, `per_call_owner`, `launched_subtree`, and
  `unknown_carrier`, plus the fixed order
  `terminal_artifacts → post_run_snapshot_and_monitor → zero_state_proof →
  active_machine_receipt_status_cas_receipt → durable_machine_terminal_receipt →
  protected_access_terminal_envelope → lease_release_transition →
  durable_broker_release_journal_prepared → OS_release +
  durable_broker_release_journal_os_release_committed as one atomic authority transaction → durable_release_status_cas_receipt →
  durable_lease_release_receipt` all emit raw evidence.
  Trusted event-time source leaves, status-index ACTIVE/INVALIDATED/SUPERSEDED/RELEASED CAS replay,
  invalidation/supersession sets, post-release current-head observation, and the closed FSM must all
  verify. Completion requires an
  exact `protected_run_machine_attempt_link_set_manifest` with no orphan, reuse, cross-pair, or false success from
  consumed-incomplete attempts, plus the immutable `candidate_prelabel_binding_manifest` over actual bytes,
  views, fingerprints, lineage, cluster membership, and source machine evidence and its unique
  broker-signed atomic-CAS freeze envelope. The freeze must follow the complete run/link population,
  precede every label/view exposure, carry audit/consumed roots exactly, and permanently bar later
  runs or unavailable-slot promotion; every ITT unit is retained. Until H-03 and all machine gates
  are valid, this node is blocked and no command is authorized. Once authorized, the exact launcher
  command, bounded population and expected receipt set come only from the signed protocol.
- **Exact checks:** all O/M checks green on the fixed tree, external signature/custody verification
  green, exact population/ITT reconciliation, machine FSM/status-root replay, final prelabel freeze
  verification, `git diff --check`, and read-only review bound to that commit/tree. Before authority,
  only the offline checks exist; afterward the signed protocol supplies the one real command.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### R-01 — post-run optical, repeat, TOR and manufacturing evidence closure

- **Gates:** B, C, E.
- **Dependencies:** R-00 complete machine population and immutable prelabel freeze; H-02 TOR semantics;
  no result-driven protocol, threshold, eligibility, denominator or exclusion change.
- **Exit criteria:** every planned run and candidate slot is reconciled to source-bound optical,
  Stage B, Stage C, RI/CRA/distortion, repeat, TOR Monte Carlo, compensator, saturation,
  compensation-failure and manufacturability records. Official macro/executable/version, all
  parameters, raw/derived artifacts, forward/reverse hashes, time-source leaves and machine receipts
  resolve for every asserted value. Missing/proxy/degraded/blocked/non-converged/unavailable remain
  explicit ITT failures; only the human-ratified TOR table and aggregation rule can produce
  `manufacturing_yield_qualified`.
- **Exact checks:** closed-world artifact membership and reverse-hash replay; planned-run/candidate
  reconciliation; repeat tolerance recomputation; TOR Monte Carlo denominator/compensator/saturation
  replay; raw numerator/denominator/exclusion/cluster/CI reports; no conditional-on-delivered metric
  is used as a gate.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward; a substantive repair
  invalidates this confirmatory batch rather than rewriting its evidence.

### R-02 — protected human expert-label collection and productivity evidence

- **Gates:** D, E.
- **Dependencies:** R-00 signed prelabel freeze, R-01 evidence views, H-01 ratified rubric/rater
  allowlist/blinding and the externally anchored trusted review store/clock controls.
- **Exit criteria:** for every planned candidate slot, each authorized rater follows one protected
  chain: current audit-head observation and complete prior-exposure replay → blank form → signed label
  intent → durable START append → exact required accesses → raw human entry → durable COMPLETE append
  → detached expert signature → protected terminal. START/COMPLETE store and clock attestations are
  externally trusted and disjoint from the rater. Review duration is verifier-derived only from the
  same monotonic clock. Missing, unavailable or unsigned labels contribute zero to both separate ITT
  numerators; productivity uses the ratified human baseline and threshold without AI imputation.
  The ratified rater allowlist is a nonempty duplicate-free ordered identity / identity-proof-hash /
  public-key-fingerprint tuple array whose bootstrap hash equals the external anchor;
  `expert_rater_count` is an integer at least one and equals its length; every counted label signature
  tuple matches one unique member of that same array and carries the same anchored hash; both expert-
  rate thresholds are strictly greater than zero and at most one; and D requires at least one valid
  human-labelled candidate whose distinct valid envelope signer set equals the full protocol tuple
  array and whose two dimensions are recomputed under the signed combination rule. Any incomplete,
  extra, duplicate, outside-allowlist or cross-candidate set contributes zero to both numerators. Zero
  raters, zero thresholds, or an empty valid-label set force D false.
- **Exact checks:** signature/allowlist verification; three-way cutoff equality; full audit-prefix
  replay; one-of consumed-incomplete exposure representation; START/COMPLETE content and CAS receipt
  reconstruction; exact access-set coverage; two independent label numerators with raw denominator,
  exclusions, clusters and confidence intervals; review-time and productivity recomputation.
- **Retry budget:** 1 collection attempt plus at most 2 evidence-driven transport corrections that
  never alter a human value; substantive rubric/schema/timing changes require a new sealed holdout.

### R-03 — independent raw-evidence A–E recomputation

- **Gates:** A, B, C, D, E.
- **Dependencies:** R-01 and R-02 complete; fixed raw evidence bytes and no author-written gate cache
  accepted as proof.
- **Exit criteria:** an independent, non-author, read-only verifier starts from the external governance
  anchor, minimum-claim checkpoint, human signatures, sealed manifest, custody/machine/access logs,
  artifacts and expert labels and recomputes each A–E predicate, all ITT numerators/denominators,
  exclusions, clusters, confidence intervals, TOR yield, repeatability, review time and productivity.
  It emits one canonical `a_e_recomputation_hash`; unknown or missing evidence leaves the affected gate
  false/unavailable. No ledger or author summary can substitute.
- **Exact checks:** deterministic clean-checkout verifier command fixed by the signed protocol;
  independent source inventory and hash replay; negative vectors for missing, forked, stale, duplicate,
  cross-batch and post-outcome inputs; signed read-only review bound to the evidence bytes and verifier
  commit/tree.
- **Retry budget:** 1 recomputation + at most 2 evidence-driven verifier fix-forward; any evidence or
  verifier tree change invalidates the previous result and requires a fresh independent run.

## Post-execution release lane

### O-09 — final evidence and handoff release binding

- **Gates:** F.
- **Dependencies:** R-03 canonical independent A–E recomputation; no direct dependency shortcut from
  R-00 or an author-written ledger is allowed.
- **Exit criteria:** every predictable tracked manifest/handoff/runbook/evidence-index/memory/decision/
  GSD-verification/review-scope write is inside one fixed release tree; three pairwise-distinct,
  author-disjoint scope reviewers validate that exact commit/tree from independent read-only checkouts;
  PR required checks target the exact head and are all terminal `success`; merge
  uses the exact raw GraphQL `expectedHeadOid` compare-and-swap equal to that head through the fixed
  single-mutation AST's direct variable→`mergePullRequest(input: …)` mapping, with `pullRequestId`
  equal to the final raw PR observation node ID and no alias/unused/bypass path. Independently, the
  same provider acquisition→snapshot→merge-admission→terminal lease freezes exact base plus every
  policy/main-ref mutation surface through the one bound mutation; absence is
  `BLOCKED_WAIT_EXTERNAL`. The merge tree
  equals reviewed tree. All required main workflows are terminal `success`. Source-specific leaves
  preserve and recompute: post-merge PR-GET raw bytes supply server-side `merged_at` and merge SHA;
  Actions-run raw bytes supply `event == push`, `head_branch == main`, `head_sha`, `path`,
  `workflow_id`, `run_attempt`, status/conclusion and API timestamps; a refs-API raw response supplies
  `refs/heads/main` and its OID; and Git object bytes recompute the workflow blob from merge tree plus
  path. Any derived full ref, workflow identity/ref, or completion timestamp has one explicit formula
  from those real fields; an absent API field may not be filled by assertion. The main-ref OID and run
  head SHA equal the accepted merge commit, workflow path/blob equal the reviewed tree, and server-side
  GitHub server times are monotonic from `merged_at` through the bounded repository closure; local
  capture times are audit-only. Post-merge
  PR/CI facts remain in a detached attestation. If any of those
  facts must be written into tracked files, a second full review→PR CI→merge→main CI cycle is required
  and the later clean tree becomes authoritative. The closed-world evidence bundle excludes the
  release package/hash and every final-decision object. Evidence/release bind the active minimum-
  claim floor/signature-set/current durable checkpoint. The PR base equals the freshly fetched
  `origin/main` commit/tree and clean-worktree record; a base change triggers fetch/rebase/revalidation/
  rereview. Required PR checks and the separately externally anchored post-merge main-workflow policy
  are both nonempty; applicable ruleset workflow rules block v0.1 rather than defining that set. The
  actual package/hash is detached from the
  reviewed release tree and every upstream preimage; `release_code_tree_hash == reviewed tree ==
  final PR head tree == merge_tree_hash`, required CI binds that head, main CI binds the merge commit,
  main push ref/event/workflow blob/time chain,
  and run-code bindings equal protocol/activation. Every raw source byte, Git object, workflow,
  tracked artifact, and review scope resolves through the signed source profile and exhaustive digest
  registry into the inline raw-member set. All fourteen request-bearing GitHub kinds within the exact
  fifteen source-leaf templates must use the fixed
  direct TLS-authenticated official API origin and exact method/path/query templates with redirects,
  alternate hosts, target rewriting, and cross-origin pagination rejected. The fixed GraphQL response
  selection and strict raw projection are exactly `clientMutationId` plus
  `pullRequest { id number merged mergedAt mergeCommit { oid } }`. A valid package closes only
  `F_release_evidence_complete`; it contains neither a GO nor proof of its own hash.
- **Exact offline checks:**
  `$env:PYTHONUTF8='1'; uv run pytest tests/test_release_evidence_package.py tests/test_review_tree_binding.py -q -k "not real" -m "not real_machine"`
  plus `git diff --check`, exact Git object/tree equality, and external PR/CI API verification.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

### H-04 — final integrated GO

- **Gates:** Goal completion after A–F; this decision does not change F.
- **Dependencies:** R-03 recomputed A–E true from raw evidence; O-09 release-evidence
  package and detached post-merge attestation complete; final custody audit and all role signatures agree.
- **Exit criteria:** the separately authorized final-GO roster signs domain-separated per-signer
  messages over a decision statement through canonical signature-record/signature-set objects that satisfy the externally anchored
  common trust, roster, quorum, ordering and role-separation rules over the fixed release-evidence-
  package hash. The roster and quorum resolve to the registered canonical content objects, are
  nonempty/positive, and the accepted set contains at least one valid allowlisted human signature;
  empty or vacuous authorization rejects. That package binds protocol, draw,
  activation, access audit, sealed sample manifest, exact mapping/eligibility hashes, immutable
  `candidate_prelabel_binding_manifest`, `protected_run_machine_attempt_link_set_manifest`, run/release trees, evidence bundle, A–E recomputation,
  non-author review, PR head/checks, merge tree, and matching post-merge main-push CI ref/event/
  workflow-blob/time evidence. The evidence bundle excludes
  the release package/hash, every final statement/message/record/set/outer-receipt object and hash,
  and post-GO archival records. F remains the release-evidence predicate. Only A–E, F-release, and a
  valid final signature set with `decision=GO` complete the Goal; absent, `NO_GO`, `STOP`,
  `CANCEL`, or `SUPERSEDE` is never GO. AI, ledger, Git, or CI cannot issue it.
- **Exact offline checks:** ratified signature verifier plus independent recomputation from frozen
  contracts, signatures, sealed manifest, machine receipts, artifact hashes, Git/PR/CI, and holdout
  access logs; the exact command must be fixed before confirmatory execution.
- **Retry budget:** 1 implementation + at most 2 evidence-driven fix-forward.

Any finding, tracked write, contract/code/rubric/eligibility/denominator/threshold/analysis change,
or holdout access mismatch invalidates the affected binding. The new tree must rerun static checks
and independent review, and a substantive confirmatory change requires a new sealed holdout.
