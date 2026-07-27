# North-star minimum claim envelope v0.1 — UNRATIFIED

status: UNRATIFIED
document_role: human-ratifiable-template
claim_version: v0.1-draft

current_truth: `A=false; B=false; C=false; D=false; E=false; F=false; [EXPERT] unavailable`

> **Fail closed.** This file is an AI-authored proposal, not a claim, approval, signature,
> expert judgement, manufacturing verdict, yield statement, or GO decision. It cannot validate
> itself. No downstream batch may call this template ratified. Silence, a Git commit, CI success,
> an AI review, or a reviewer name written by the author selects no value below.

## Minimum claim boundary

This document is a non-authoritative human-readable mirror of
`.planning/north-star/preregistration-manifest-schema-unratified-v0.1.json` at
`$.minimum_claim_envelope_template` and the selected `$.protocol_manifest_template.claim`. This
Markdown is never signed as an independent payload; the canonical minimum-claim envelope, its
separate human signature set, and the external verifier's append-only atomic-CAS high-water
checkpoint are the authority. Every protocol must bind the current checkpoint and resolved active
floor and deterministically prove its selected claim equal or broader. Any missing, extra, duplicate, narrower,
or conflicting mirror field rejects confirmatory use. A supported scenario must have a result-independent
target distribution, specification ranges with units, independence rules, non-waivable endpoints,
and explicit external-tool exclusions. Unlisted scenarios, ranges, endpoints, or tools stay outside
the claim.

The current canonical schema shape is exact and fail-closed: 66 ordered registered object types; 24
ordered common-verification signer classes; ten exhaustive digest-reference classes; 26 sealed-
sample-manifest keys; 19 selected machine-policy keys with exact launch-ticket/durable-intent/receipt
binding-set counts of `27/27/48` plus a separate 33-member ACTIVE-status-CAS set; 32 evidence-bundle
keys; 43 release-package keys; a 25-member
release/evidence shared-binding intersection; 20 protocol bindings; and 109 human-owned choice
positions in the authority mirror, all currently null. Template-key counts include `domain_tag` where
present; the `27/27/48` and 33-member binding sets count exact array members and contain no `domain_tag`.
These byte-shape facts are neither human selections nor evidence that any gate passed; any schema
change requires a new synchronized mirror.

The 66-type registry includes canonical `authority_role_roster_content`,
`authority_quorum_rule_content`, `machine_entry_inventory_content`, and
`machine_admission_receipt` objects. Every minimum-claim, protocol, activation, and final-GO
stage resolves its roster/quorum hashes to these registered immutable objects. Each roster and
allowlist is nonempty, every per-role and total quorum minimum is a positive integer, and every
accepted stage signature set contains at least one valid allowlisted human signature. Empty or zero
configurations and vacuous-truth evaluations reject.
Every counted signer tuple—identity, identity-proof hash, public-key fingerprint, and allowlist
hash—must exactly match one same-role registered roster member. `AND` requires the full roster tuple
set; `OR` permits only a nonempty duplicate-free subset, never an external-allowlist-only identity.

In v0.1, the floor is independent of run-code bytes only after X-00A has frozen the exact schema,
external anchor, goal instance and genesis. A code/tree-only change that preserves those bytes may
reuse the active floor, but it invalidates O-07, H-01, H-02, H-03 and every downstream run/release
object. Any schema, anchor or goal-instance byte change invalidates the floor, its signature set and
checkpoint as well as protocol, draw, activation and all descendants; it requires a new goal genesis,
anchor, minimum-claim floor and checkpoint genesis. v0.1 supports no in-place schema migration or
anchor rotation. If either class of invalidating change happens after draw, that draw is permanently
exploratory and confirmatory work requires a new never-observed sealed holdout.

Before any protocol can be approved, the registered `RUN_CODE_RELEASE` chain must resolve exactly
three independent scope-review chains of four objects each, one inline source-bound Git/CI container, four post-merge
attestation objects, and the canonical `run_code_release_package`. That package distinguishes the
reviewed final PR-head commit from the accepted `main` merge commit, requires an identical reviewed
tree, a raw-DAG-derived pre-review actor set, a raw audit/Actions-derived post-merge actor set,
provider-specific terminal-success PR CI, compare-and-swap merge, and matching post-merge main/push CI. It binds
the executable merge commit/tree used by protocol, activation, machine attempts, A–E recomputation,
and evidence. O-07 is a prerequisite only: it cannot make A–F or human GO true.

```text
north_star_goal_instance_id: null
minimum_claim_version: null
generation: null
predecessor_kind: null
predecessor_hash: null
external_governance_anchor_hash: null
claim_statement: null
supported_scenarios: null
specification_ranges: null
representative_target_distribution: null
minimum_independent_target_count: null
minimum_independent_seed_cluster_count: null
minimum_sealed_holdout_count: null
patent_family_independence_rule: null
non_waivable_endpoints: null
excluded_external_tool_walls: null
expert_worth_reviewing_rate_itt_threshold: null
expert_production_usable_rate_itt_threshold: null
pipeline_delivery_rate_itt_threshold: null
manufacturing_yield_threshold: null
productivity_threshold: null
confidence_threshold: null
primary_endpoint_selection: null
```

The comparator policy is fixed canonically as
`atelier.north-star.minimum-claim-equal-or-broader.v0.1`: scenario IDs stay exact in v0.1,
non-waivable endpoints may only expand, exclusions may only contract, minimum counts/thresholds may not fall, exact fields stay
exact, and specification ranges use unit-bound direction-aware comparators. Every successor replays
to the externally anchored goal genesis and advances the durable checkpoint exactly once. A changed
scenario set, incomparable or narrower version, stale generation, fork, or rollback is exploratory-only
and can never replace the active floor, even with a new protocol or new sealed holdout.

Role approvals are domain-separated message→detached-signature-record pairs defined only by the
canonical schema. This
mirror contains no approval, signature, timestamp, trust-root, or signature-set field.

The final GO decision is not a protocol field. After A–E, the exact 43-key closed-world release-
evidence package binds the prior `run_code_release_package`, protocol, same-batch
draw/manifest/activation chain, custody, run/release
trees, access-envelope sets and final audit/consumed roots, unique candidate pre-label manifest and
broker-signed CAS freeze envelope, protected-run/machine attempt-link bijection, the exact 32-key
evidence bundle, review, source-specific GitHub PR/merge proof, and typed post-merge `push` CI on
`refs/heads/main`. Its exact 32-key evidence bundle and 25 shared bindings are dynamically recomputed from the
two templates and must be byte-equal. Validating that detached package closes
`F_release_evidence_complete`. Its bytes
and hash are absent from the bound release tree and every upstream preimage. The authorized final-GO
roster then signs separate domain-separated per-signer messages over a decision statement; a
canonical final signature set enforces externally anchored quorum and separation over that package
hash. The registered final roster is nonempty, its quorum is positive, and the accepted set contains
at least one valid allowlisted human signature. The evidence bundle excludes the release package,
every final statement/signature-message/
signature-record/signature-set/outer-receipt object and hash, and
post-GO archival records, so the graph cannot self-reference.

The external-tool wall must explicitly dispose of strict stray-light/ghost analysis and AR
waveguide validation; neither is silently included through an adjacent scenario. Patent-family
independence is evaluated before results are known and prevents related family members from being
counted as independent targets or seed clusters.

## Authority boundary

The externally anchored minimum-claim authority owns approval of the floor and equal-or-broader
successors. The protocol claim authority owns selected wording and product scope within that floor.
Neither role confers optical-expert
authority. Whether 主公 is independently qualified and allowlisted for an optical-expert role is a
human-owned choice in the authority policy and remains unset. Optical acceptance requires both
independent label dimensions, `expert_worth_reviewing` and `expert_production_usable`, produced
only by authorized human expert(s) under a human-ratified rater-count, blinding, and combination
policy. This template does not select one rater, two raters, or any other count. Manufacturing and
statistical claims require the separate manufacturing/statistics authority. Machine admission,
entry inventory, OS boundary, lease, launch-ticket, and receipt policy require the separate
machine-execution authority. The overall
ratification rule is the AND of all required role approvals. Within one role the human-selected rule
is exactly `AND` (every required allowlisted identity) or `OR` (at least one allowlisted identity),
always against a registered nonempty roster and positive quorum. The expert-rater allowlist is a
nonempty, duplicate-free ordered array of identity / identity-proof-hash / public-key-fingerprint
tuples whose bootstrap hash equals the external anchor; `expert_rater_count` is an integer at least
one and equals that array length. Every expert-label signature counted for D must match exactly one
member tuple in that same protocol array and carry the same anchored allowlist hash. Both expert-rate
thresholds are strictly greater than zero and at most one. A candidate contributes to either expert
numerator only when its distinct envelope signer set equals the complete protocol rater tuple array
and both dimensions are recomputed under the signed combination rule; otherwise both contributions
are zero. D requires at least one such complete human-labelled candidate set. The expected external-governance-anchor hash and
bootstrap algorithm suite are supplied to the verifier outside signer and protocol control. The
verifier likewise receives and recomputes the expected canonical-schema-template hash over the exact
final schema template, including literal runtime `null` placeholders. The external anchor, protocol
binding/package, sealed manifest, and activation manifest/package must all equal that same hash; every
registered object, nested content, and typed leaf is parsed under it. Trust,
root, allowlist, roster, quorum and separation hashes must match it, while selected algorithms must
belong to its anchored allowlists. A separately allowlisted final-GO roster acts
only after A–E and `F_release_evidence_complete` are independently recomputed; its quorum and role-
separation rules are human-owned. Claim ownership or prior contract approval does not
implicitly grant final-GO authority.

The 24 common-verification signer classes are exactly, in order,
`minimum_claim_role_approval`, `protocol_role_approval`, `activation_role_approval`,
`draw_custodian`, `candidate_prelabel_freeze_custody_broker`,
`protected_access_intent_custody_broker`, `protected_access_terminal_custody_broker`,
`pre_draw_custody_store_attester`, `pre_draw_custody_control_source_attester`,
`pre_draw_trusted_clock_attester`, `trusted_review_clock_attester`,
`trusted_review_event_time_source_attester`, `trusted_review_event_store_attester`,
`machine_event_time_source_attester`, `machine_trusted_clock_attester`,
`machine_cross_clock_order_attester`, `machine_receipt_status_store_attester`,
`github_transport_capture_attester`, `github_audit_stream_attester`,
`repository_base_and_policy_mutation_freeze_attester`, `release_independent_reviewer`,
`post_merge_release_attester`,
`expert_label_rater`, and `final_go_authority`. The pre-label freeze broker is therefore a distinct
allowlisted signer; a producer-authored manifest or unsigned storage write cannot create the freeze.

## Detached ratification and hash rule

The null anchors in this mirror are never filled in place. The canonical schema defines exactly 66
ordered, distinct immutable object types—external governance anchor; authority-role-roster content;
authority-quorum-rule content; minimum-claim envelope, role-
approval messages/records,
signature set and active high-water checkpoint; protocol package, role-approval messages/records and
signature set; canonical sealed sample manifest with exact inline identity-mapping and eligibility-
decision contents beside their derived hashes; draw content/message/record/envelope; pre-activation
capability leaves and set manifest; activation package, role-approval messages/records and signature
set; membership proofs; signed access intent/terminal messages, records and envelopes; the unique
candidate pre-label binding manifest plus its separate CAS transition, signature message, signature
record, and freeze envelope; the protected-run/machine attempt-link manifest; expert-label
content/message/record/envelope; batch-bound invalid-input exclusion record; evidence bundle;
three-scope four-object fixed-tree review chains and a four-object post-merge attestation chain shared by both release
stages; the pre-protocol `run_code_release_package`; registered raw A–E recomputation;
release-evidence package; and detached final
statement/message/record/signature-set/outer receipt. Every object hash
is external to its own preimage; a later stage may bind only a prior object's hash. Protocol and
minimum-claim, protocol and activation signature sets bind package/envelope, external anchor, roster, quorum, separation and ordered
message/record members; the verifier deterministically recomputes common-trust, allowlist, signature,
quorum and separation results rather than accepting self-asserted booleans. The same verifier-
pretrusted policy covers minimum claim, protocol, activation, custodian,
broker, expert-rater and final-GO signers; no signer may select its own root. Expiry, revocation, key
usage and proof of possession must verify. Every signature uses the one canonical detached input
formula; each record/message/envelope or set chain is fully resolved and cross-object splicing
rejects. No
detached manifest or human signature is created by this task.

## Canonical evidence constraints

The claim remains unavailable unless all of the following canonical verifier constraints hold. These
are fixed schema invariants, not new claim thresholds or AI approvals:

1. The exact 26-key sealed manifest carries `planned_identity_mapping_content` and
   `eligibility_decision_set_content` inline beside their separately derived content hashes. The latter
   has exactly one decision per target in resolved target order, and each member carries its immutable
   `eligibility_input_content` inline beside its hash. The verifier executes the signed rule over that
   content. Targets are ordered by contiguous draw ordinal; candidates, runs, and attempts by resolved
   parent order then contiguous local ordinal or attempt sequence. Declared counts, signed allocations,
   parents, goal, ratification, batch, draw, protocol, and signature-set bindings must all agree; an
   opaque root, submitted-only decision, or identifier-order fallback rejects.
2. The verifier recomputes the canonical-schema-template hash from the exact final template using the
   out-of-band bootstrap suite. External anchor, protocol binding/package, sealed manifest, activation
   manifest/package, every registered object, nested content, and typed leaf must resolve that same
   schema. Signers and packages cannot select or override it.
3. The draw envelope resolves through its unsigned content to the registered sealed manifest, and
   draw and manifest are byte-equal for ratification, batch, draw event, protocol/signature set,
   sampling frame/source/algorithm, entropy commitment, target distribution/count, and manifest hash.
   Activation resolves that exact chain and repeats the same batch/protocol/manifest/distribution/count
   values before any protected action. A valid hash from another batch or draw cannot be spliced in.
4. After candidate production, exactly one immutable pre-label manifest covers every planned slot as
   available or permanently unavailable. Each available member carries actual byte membership plus
   inline source, view-set, semantic-content, lineage-content, and partition contents with their
   derived hashes. Semantic components are nonempty, contiguous, and deterministically extracted from
   actual bytes without slot/batch/path/time/host/receipt/label/outcome/threshold inputs. Same byte-set
   root **or** same semantic fingerprint is a mandatory duplicate edge; signed human rules may only
   add edges. The verifier computes one unique complete pairwise-disjoint equivalence partition and
   deterministic cluster IDs over every available slot. Then a separately allowlisted custody broker
   commits that manifest and the complete machine-link set through one accepted CAS receipt, audit
   transition, detached signature message/record, and freeze envelope. Audit sequence advances one,
   consumed root stays unchanged, and no run or second freeze may follow.
5. Before each label intent, the inline prior-exposure history replays every same-rater unseal/view/
   export/label event touching the required views or cluster peers from activation genesis. The freeze
   precedes first candidate exposure; unknown, consumed-incomplete, or blinding-forbidden exposure
   invalidates the label. An inline blank-form attestation binds one trusted session/surface/binary/form
   with both dimensions `UNSET` and an empty system-suggestion root. Durable access events exactly cover
   required views plus rubric support once each; a separate human-entry event binds the same rater,
   session, surface, slot, intent, evidence and both values. The enforced order is `freeze signature <
   blank form <= label intent < review start <= every access <= human entry <= review completion <=
   expert signature <= label terminal <= terminal transition/broker signature`. AI/system prefill
   rejects; authority comes only from the final verified human signature, not inferred cognition.
6. The machine policy remains exactly 19 top-level selected keys. Its exact nested required binding-set
   counts are 27 for the launch ticket, 27 for the durable pre-spawn intent, and 48 for the receipt-last
   terminal receipt. Every protected `run` intent freezes the tuple before spawn; ticket, intent,
   receipt, and protected terminal preserve it. The registered per-attempt link manifest proves a
   complete forward/reverse bijection between every run intent and exactly one terminal chain or
   retained `CONSUMED_INCOMPLETE` member, and between every machine receipt and one run intent. Orphan,
   duplicate, cross-capability, cross-attempt, and cross-batch evidence is not success. The normal
   terminal chain is exactly `terminal artifacts → post-run monitor → zero-state proof → ACTIVE status
   CAS → durable machine receipt → protected terminal → release transition → PREPARED journal → OS
   release + OS_RELEASE_COMMITTED journal as one atomic transactional-authority operation → RELEASED
   status CAS → durable release receipt`. PREPARED recovery accepts only an authority-atomic irrevocable
   `ABORTED_FINAL`/lease-held terminalization or an existing `COMMITTED`/durable-journal result; every
   new acquisition atomically consumes a global zero-unresolved barrier. Crash monitor and recovery-
   zero wrapper/payload/evidence/time fields match exactly; cross-attempt/generation splicing rejects.
   Native authority and OS responses use exact per-source acyclic signed projections that bind the
   batch/activation/protected-run tuple, run/attempt, host/broker/lease and source-specific operations,
   transactions, roots and outcomes. Acquisition signs its barrier; the barrier signs its full ordered
   operation members; journal/atomic/OS sources sign their own transition and prior-journal/result/time
   bindings. Each raw
   request/content hash is committed by its named signed response; only enumerated self-container/control
   and genuinely later fields are excluded, never every field containing `_leaf_hash`.
7. Every digest/OID/SHA field reachable from a runtime template is covered exactly once by the signed,
   exhaustive path-classification registry and one of ten reference classes, including immutable raw
   member bytes and native Git object OIDs. PR/main-CI evidence uses exactly fifteen source-specific
   GitHub leaf templates (fourteen request-bearing; merge response shares the merge request exchange)
   in one inline release Git/CI container, with one signed source profile bound through
   the external governance anchor and protocol `external_source_hash`, normalized nonsecret headers,
   direct TLS-authenticated `https://api.github.com` method/endpoint-template matches with GraphQL fixed
   at `/graphql`, and redirects, alternate hosts, target rewriting, or cross-origin pagination rejected,
   raw bodies, request IDs/times, PR and main-ref observations, fixed merge and merge-queue GraphQL
   query bytes, HTTP `POST` GraphQL request/response with `merge_method=MERGE`, Git object and
   workflow-blob proofs, raw Actions run leaves; the transmitted request's strictly unescaped JSON
   `query` bytes and digest must byte-equal the bound profile's fixed decoded query bytes and digest;
   its closed-world AST has exactly one `mergePullRequest(input: …)` mutation and directly maps the
   exact `pullRequestId`, `mergeMethod`, `expectedHeadOid`, and `clientMutationId` variables once each,
   with the PR node ID bound to the final raw PR observation and no alias/fragment/bypass path; its
   exact unaliased response projection is `clientMutationId` plus
   `pullRequest { id number merged mergedAt mergeCommit { oid } }`, strictly reparsed with the echo,
   and complete paginated job pages. Because public `mergePullRequest` has no expected-base or
   policy-snapshot CAS, an external provider-side acquisition→snapshot→admission→terminal lease must freeze both
   every policy mutation and every `refs/heads/main` update, atomically compare the frozen base, bind
   the complete two-pass policy/queue snapshot, arm only the exact finalized request body/clientMutationId
   before send, and prove after merge zero policy changes,
   zero foreign main updates, one bound merge and no early-release/fail-open. The request correlation
   commits the snapshot leaf; absent this primitive the path is `BLOCKED_WAIT_EXTERNAL`.
   Required-check rules keep policy provider constraints separate from result kind and expand over the
   complete current check-run/status populations; dedicated classic `strict` and full-protection
   contexts must agree. Required post-merge workflows come from a separate external policy; applicable
   ruleset-workflow rules block v0.1. The exact 15-field PR record and every exact 20-field main-CI run
   record are recomputed, not self-asserted. Each required workflow is a unique post-merge `push` with
   `head_ref=refs/heads/main`, raw `head_branch=main`, merge SHA, reviewed workflow blob, complete
   terminal jobs, and `success`. Raw `merged_at` precedes Actions creation/start/jobs completion and
   post-merge ref observation; Actions creation need not wait for merge-response capture. Generic API
   summaries, incomplete pagination, alternate events/refs/blobs, and pre-merge runs reject. A final
   one-page repository-wide Actions closure response must be complete at `<=100` rows, have no next
   page, prove no second or higher attempt, and supply the exact GitHub server Date projected into the
   main-CI record under that profile; local capture timestamps are audit-only. Four audit REST chains
   reconcile with an enterprise stream whose raw time fields agree and whose provider event-time
   watermark covers the query end; a local collector signature or stable polling cannot substitute.
   Only the eight exact terminal
   pagination `derived_next_request_target_or_null` paths may carry JSON null; every nonterminal path
   is reparsed from raw `Link rel=next`, and every other runtime placeholder is nonnull.
8. Pre-draw custody starts from an externally anchored genesis and one raw atomic durable
   initialization receipt signed by a separately allowlisted store attester. The genesis cannot depend
   on its later commit leaf. Pre-draw and review clocks each carry raw bytes/parser, policy, validity,
   attester proof/fingerprint/allowlist, message hash, detached signature and one unique signed-record
   hash. Review START/COMPLETE time leaves have their own allowlisted source-attester signatures and
   bind exact acyclic subjects, raw boundary bytes, session and entry surface; no rater or AI can
   substitute for those external trust proofs.

## Non-promotable evidence boundary

Loop2 observations, including P18 orchestration states, Stage B input closure, Stage C
delivered/blocked outcomes, and the single exact-target reproduction/export chain, remain
`exploratory_reusable_component` or `incident_evidence`. This task cannot promote any of them to a
confirmatory sample, expert rate, manufacturing yield, or evidence for a claim threshold.

Every planned candidate slot and run unit that is not passing remains in the frozen ITT main
denominator and counts as not passed. A conditional-on-delivered rate is diagnostic only and can
never satisfy a north-star gate. Any north-star statement remains unavailable until this envelope,
the acceptance contract, the authority policy, and all required external signatures are bound to
the same immutable evidence set.
