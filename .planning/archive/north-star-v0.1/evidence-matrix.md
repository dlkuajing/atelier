# North-star evidence matrix — ACTIVE / all gates false

This matrix is a recomputation map, not an approval surface. Gate truth must be derived from the
listed raw evidence classes. `.planning/north-star/gap-ledger.json` is only an index/cache and is
never cited as gate proof. No confirmatory sample or holdout was drawn, opened, inspected, created,
or labelled by this task; CODE V was not started.

For Gate A, the 66-type registry includes canonical authority-roster, authority-quorum-rule, machine-
entry-inventory and machine-admission-receipt content. Every stage-bound roster/allowlist must be
nonempty, every per-role and total quorum minimum
must be positive, and every accepted stage set must contain at least one valid allowlisted human
signature. Every counted identity/proof/key/allowlist tuple exactly matches one same-role registered
roster member; `AND` equals the roster tuple set and `OR` is only a nonempty duplicate-free subset.
Empty or vacuous authorization is false. For Gate D, the nonempty protocol rater tuple array must
bootstrap-hash to the external anchor, every counted signature tuple must match one unique member of
that same array, `expert_rater_count` must be an integer at least one and equal its length, both
expert-rate thresholds must lie in `(0, 1]`, and at least one valid human expert-label envelope must
participate in a complete per-candidate signer set equal to the protocol array, with both dimensions
recomputed under the signed combination rule. Incomplete or mismatched signer sets contribute zero
to both numerators. Those are raw-evidence requirements, not values selected by this matrix.

| Gate | Present truth | Raw evidence required to recompute | Currently available evidence and limitation |
|---|---|---|---|
| A — contract and permissions | **false** | Exact fail-closed schema: 66 registered object types including canonical authority-roster, authority-quorum-rule, machine-entry-inventory and machine-admission-receipt content, 24 common-trust signer classes, ten closed hash-reference classes plus an exhaustive signed runtime-path registry and no self-hash or unclassified alias; out-of-band governance/schema anchors; active human-signed minimum-claim floor plus durable anti-rollback checkpoint; canonical RUN_CODE_RELEASE before protocol signatures and draw; externally anchored custody genesis and atomic durable commit receipt; separately allowlisted store/clock/event-time/release attesters; draw↔sealed-manifest↔activation equality; non-overridable ITT/exclusion/cluster rules and fully resolved capability/intent/terminal chains | Only `UNRATIFIED` templates exist. All minimum-claim and other human-owned choices are null. No external anchor, active floor/checkpoint, trust roots, protocol/activation/final signature set, custody genesis receipt, signed clock source, draw, activation or final decision exists. All twelve recorded fixed trees were rejected; dirty-tree checks are not gate proof. 主公's optical-expert qualification remains unset; Git/CI/AI authorship is not a human signature. |
| B — multi-target same-source production chain | **false** | Preregistered representative exact targets and all ITT run units; requirement→seed→Stage B→Stage C→candidate→XLSX/ZIP/ZMX/reproduction; source/forward/reverse hashes; each protected run linked bijectively through the exact `terminal_artifacts → post_run_snapshot_and_monitor → zero_state_proof → ACTIVE status CAS → durable_machine_terminal_receipt → protected terminal → lease_release_transition → PREPARED journal → atomic OS release + OS_RELEASE_COMMITTED journal → RELEASED status CAS → durable release receipt` chain; nonterminal intents retained as exact contiguous `CONSUMED_INCOMPLETE`; immutable crash generations and cross-attempt-safe monitor/zero-state wrappers; structured failure ledger and frozen exit/repeat semantics | Loop2 remains exploratory: P18 `29/21`, Stage B `8/8`, Stage C `2/46` and `6/48`, and one exact-target chain do not prove representative multi-target capability. No north-star link set, closed FSM/status replay, or full forward/reverse population exists. |
| C — evidence completeness | **false; manufacturing unavailable** | Ratified thresholds and same-source raw evidence for optical quality, RI, CRA, distortion, Stage B/C, repeat, TOR and manufacturability; exact eight-field TOR semantics; official executable/macro/version/parameters; raw/derived forward and reverse hashes; machine receipts and status/journal replay; every proxy/degraded/sentinel/missing/unavailable ITT unit retained | Only 6/48 exploratory Stage C runs had usable spot/WFE metrics. RI/CRA/distortion/manufacturability are not a complete same-source confirmatory set; all TOR choices are unratified and saturation occurred. `manufacturing_yield_qualified` is unavailable. |
| D — human expert validation | **false; [EXPERT] and both rates unavailable** | Ratified rubric/rater/view policy with a nonempty allowlist, integer `expert_rater_count >= 1`, both expert-rate thresholds in `(0, 1]`, and at least one valid human expert-label envelope carrying both dimensions; one immutable pre-label manifest and accepted signed CAS freeze; complete actual-byte/content/lineage/cluster partition; protected blank form→intent→signed-clock START→required access→raw human entry→signed-clock COMPLETE→expert signature→terminal chain; store, clock and boundary-time attesters externally trusted and disjoint from rater; two separate ITT numerators, cluster rule, CI, verifier-derived review time and productivity baseline | No human selections, nonempty rater allowlist, positive rater count/thresholds, pre-label freeze, protected review timeline, signed clock/store evidence, human-signed labels, review-time series, ITT thresholds or productivity comparison exists. Machine/export status cannot substitute; `[EXPERT]` and both rates are unavailable. |
| E — independent holdout | **false** | Custodian disjoint from development/tuning/execution; externally anchored genesis-to-current audit prefix and five raw control leaves cover the draw CAS; fixed-code protocol signatures before draw; sealed manifest/activation equality; all capabilities, run-machine links and pre-label freeze replay; R-00 full population, R-01 optical/TOR closure, R-02 protected labels, then independent R-03 raw A–E recomputation; crash remains consumed-incomplete | No custodian, sealed draw, custody/clock source evidence, activation, protected link/freeze/access chain, independent confirmatory population or R-03 recomputation exists. No holdout was accessed. |
| F — release evidence | **false; F_release_evidence_complete=false; final_GO=false** | Fresh clean `origin/main`; exact 32-field evidence bundle and 43-field release/authority mirror with 25 shared bindings; one commit/tree covered by three pairwise-distinct, author-disjoint scope reviews; final PR head checks; accepted `expected_head_oid` head CAS through a fixed single-mutation closed-world AST whose direct variable→input mapping includes all four fixed mutation variables and the final raw PR node ID; an independent provider acquisition→snapshot→merge-admission→terminal lease that freezes exact base and all policy/main-ref mutation surfaces; direct TLS-authenticated official GitHub API endpoint templates with no redirects/alternate targets; exact unaliased `clientMutationId` + `pullRequest{id,number,merged,mergedAt,mergeCommit{oid}}` raw response projection; Git-derived merge/tree/workflow proofs; exhaustive signed digest registry and source-bound inline raw bytes; complete raw jobs/listings; a separately externally anchored nonempty post-merge main/push workflow policy; final one-response repository Actions closure (`<=100`, no next, no second/higher attempt) ordered by GitHub server time; matching successful post-merge main/push CI; tracked writeback and detached release package | This control-plane work is not the future north-star release package and cannot make F true. A–E and F remain false; no qualifying final evidence or post-merge attestation exists. A separately authorized common-trust `decision=GO` is additionally required for Goal completion and never changes F. |

## Machine-execution incident boundary feeding Gates B, C, and F

Read-only inspection anchors the low-level launch path at
`app/core/engines/codev_batch.py::run_codev_process_bytes -> _popen_codev ->
subprocess.Popen`. The default lock root is `%USERPROFILE%\.atelier\codev-execution-lock`, and a
caller may supply `lock_root`; this protects only cooperating calls in that user-scoped namespace.
It is not a machine-wide seat lease. The Stage C `CreateFileW` share-deny protection is an
executable-TOCTOU control, not a seat lease.

`.planning/loop/p13-smoke-2026-07-11/freeze_smoke.py:70` is a tracked direct `Popen` bypass.
Other launch-capable surfaces that must be closed behind the same canonical launcher and default-
deny launch ticket include Web `POST /candidates`, C1 CLI, P18 real mode, P13/P14/P15 and probe
tools, Stage B, Stage C, and ordinary `real_machine` tests. These findings are incident evidence,
not permission to run or modify the launcher in this task.

Before any future real-machine work, the raw evidence chain must show: one canonical launcher; a
signed inventory of repository, Task Scheduler, service, startup, other-worktree, external-script,
and manual entry points; a human-approved OS admission boundary or unique broker that forces all
   callers through that launcher; one externally anchored durable transactional machine lease/journal
   authority selected by authorized humans, with Global named mutex/`ProgramData` ACL permitted only
   as defense in depth; durable intent; exact `pre_launch`/`during_run`/`post_run`
snapshots for `runner`, `codev`, `codevm`, `p18_owner`, `global_owner`, `per_call_owner`,
`launched_subtree`, and `unknown_carrier`; official executable/macro/version/sequence pins; default-deny launch
tickets for every surface; denial of non-allowlisted shell/test/import/runner activity while the
lease is held; conflict handling that kills only the provably owned subtree, permanently retains the
contaminated attempt and raw logs, and never kills unknown processes; a receipt binding host, PID,
batch/run/attempt IDs, one-time ticket/nonce, owner, start/end, full command, toolchain/input hashes,
pre/during/post snapshots, terminal state, artifact hashes, and audit heads; and append-only consumed-
ticket rejection. The canonical lease broker is distinct from the eight snapshot/zero-state subjects;
`runner` is a run child or competitor, and global/per-call owner carriers are not the lease owner. One
attested broker must retain the same `lease_instance_id` through zero proof and durable receipt. The
only valid order is `terminal_artifacts → post_run_snapshot_and_monitor → zero_state_proof → ACTIVE
status CAS → durable_machine_terminal_receipt → protected terminal → lease_release_transition →
PREPARED journal → OS release + OS_RELEASE_COMMITTED journal as one atomic authority transaction →
RELEASED status CAS → durable release receipt`; the receipt binds all prior hashes plus broker and
lease identity. Lease release occurs only after `runner`, `codev`, `codevm`, `p18_owner`,
`global_owner`, `per_call_owner`, and `launched_subtree` are all proven zero/absent and
`unknown_carrier` absent. Cooperative repository checks cannot attest
the machine admission boundary. Unknown process, owner, or lease state fails closed without killing
or clearing it. ACL or AppLocker changes are high-impact external decisions and are not made here.
The selected external lease authority must atomically commit both release and the committed journal
entry, or neither. A PREPARED operation may advance only when that authority atomically terminalizes
the exact operation as irrevocable `ABORTED_FINAL` with its lease still held, or proves an existing
`COMMITTED` result with the exact journal durable. Transient `NOT_COMMITTED`, pending, unknown,
partial, unqueryable, or released-but-unjournalled outcomes keep admission closed. Every new
acquisition must consume a complete authority-wide cross-batch/host/broker barrier proving zero
unresolved PREPARED operations in the same atomic transaction that inserts the new lease.
Native atomic-acquisition, OS-acquisition, barrier, journal-store, atomic-release, and OS-release
responses each verify an exact source-specific acyclic signature projection. The signed semantics cover
batch/activation/run context, host/broker/lease and source-specific operation/transaction/roots/outcome.
Barrier post-state and per-operation terminal lease-state roots additionally use the explicit
accumulator-root class and are independently recomputed from a complete raw native proof under the
anchor-pinned authority-state accumulator policy; signed opaque-root equality is not evidence.
Acquisition signs its barrier, the barrier signs all ordered operation members, and journal/atomic/OS
sources sign their own transition, prior-journal, result, and time bindings. Raw caller
request/content hashes are committed by their named signed response; only enumerated self-container,
control, and genuinely later fields are excluded, never every `_leaf_hash`.

Immediately before spawn, the 64-field durable pre-spawn receipt must be one atomic, single-use native
gate transaction: its raw receipt and parser-membership proof must derive the complete current ordered
inventory under the exact member template, while the verifier recomputes its root/count and checks the
same launcher, admission boundary, lease policy, zero drift, zero uncovered entries, zero bypass paths,
and active enforcement. Its external OS attester algorithm is part of the signed preimage and must be
allowed by the anchored signature suite. The 36-field process-start receipt repeats the same transaction,
attestation-record hash, clock and valid-through monotonic counter; mutation, expiry, reuse or a competing
start rejects spawn and requires a new inventory/admission/activation chain.

For each protected `run`, the signed protected-access intent must exist before launch. The launch
ticket, durable machine intent, and machine terminal receipt policies expose exactly 27, 27, and 48
required bindings respectively, plus a 33-binding ACTIVE-status CAS. Each terminal member also resolves the durable pre-spawn commit and process-
start receipts, and all objects byte-agree on activation, capability/proof, batch/run/attempt, host,
launcher, broker, lease, complete command, inputs, and toolchain pins. A canonical ordered link-set
has one and only one member per protected run intent and one and only one member per valid
confirmatory terminal receipt.

A run intent without a valid terminal has one exact tagged `CONSUMED_INCOMPLETE` member. Its retained
chain is either `INTENT_ONLY`, with a closed-world proof that no machine leaf exists, or a contiguous
`PREFIX` that exactly equals every typed leaf reached in lifecycle order (ticket → durable intent →
pre-spawn commit → process start, followed only by reached later stages). Every ticket, durable intent,
pre-spawn receipt, and process-start receipt has exactly one forward and reverse terminal or partial
link; every terminal receipt has exactly one terminal link. A valid terminal forbids partial evidence,
and partial evidence supplies no success. Missing, extra, duplicate, aliased, orphaned, cross-run,
cross-attempt, or cross-batch links fail closed.

All machine requirements above are canonical typed minimum invariants, not merely prose: each of the
19 selected values must match its exact value template and fixed constants, and the derived machine-
policy hash uses the unique closed-world 19-key preimage before protocol hashing.

## Recalculation invariants

These are mirrors of `protocol_manifest_hard_invariants`; selected human policy may be stricter but
cannot override or weaken them.

- Every planned non-passing slot/run stays in the frozen ITT denominator and counts as not passed.
- Protocol signatures freeze the frame, eligibility rule and allocation/count rules; the custodian
  draw then atomically assigns actual IDs/mappings and eligibility in the sealed manifest before
  access. The verifier reconstructs the exact domain-separated ordered planned-identity-mapping and
  eligibility-decision-set hash preimages; opaque roots, ID fallback ordering, or missing/duplicate/
  gapped members reject.
- A run belongs to one candidate; immutable initial/retry attempts belong to one run and never create
  denominator units. The final run state is derived once under the frozen retry/aggregation rule.
- Planned run units and planned candidate slots remain separate denominators: delivery uses all run
  units, while each expert rate uses all candidate slots. Every ratio reports raw numerator,
  denominator, enumerated exclusions with evidence hashes, dependence cluster, and confidence interval.
- After all runs are terminal or consumed-incomplete and before any label access, one unique pre-label
  manifest partitions every planned candidate slot into available or permanently unavailable and a
  custody broker signs an accepted CAS freeze that advances the audit head once while preserving the
  consumed-capability root. The manifest embeds the verifier-recomputed unique, complete, pairwise-
  disjoint available-slot partition: the mandatory same-byte-root or same-content-fingerprint floor
  plus signed-rule closure, ordered by minimum planned slot order with deterministic full-cluster IDs.
  Every available member binds actual candidate bytes, the human-selected required view set,
  verifier-recomputed content/lineage fingerprints, and terminal source machine evidence. Every
  duplicate slot stays in the denominator and one cluster contributes at most one independent
  numerator.
- Label evidence follows the signed freeze and proves the exact blank-form (`UNSET`, no suggestion) →
  durable intent → review start → required-view/rubric-support access events → raw human entry →
  review completion → common-trust-verified expert signature → terminal chain. Prefill, missing or
  reordered exposure/entry evidence, wrong candidate/view/session/rater, or producer-declared cluster
  identity rejects.
- Blocked, degraded, failed, non-converged, missing, unlabelled, undelivered, saturated, and
  compensation-failed units are never silently excluded.
- An exclusion requires all four: preregistered reason, result independence, independent raw evidence
  proving the immutable input itself invalid, and a frozen automatic rule plus bound machine receipt
  before outcome access. Its registered record binds goal/floor/protocol/batch/manifest/member/audit head;
  cross-batch or cross-protocol replay rejects.
- A contaminated attempt remains immutable and outside trusted execution evidence, but its planned
  run unit remains in ITT as not passed unless the frozen retry map later supplies trusted evidence.
- Conditional-on-delivered and complete-case rates are diagnostic only.
- A ledger row, status string, artifact presence, PR merge, CI success, or AI review never supplies
  a missing human signature.
- A substantive contract/code/rubric/eligibility/denominator/threshold/analysis change invalidates
  the affected confirmatory batch and requires a new sealed holdout.
