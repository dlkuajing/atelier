# Quick 260713-n7x verification

status: ACTIVE_UNRATIFIED_EXTERNAL_RELEASE_EVIDENCE_REQUIRED

## Guardrail result

- This tracked file defines a verification procedure; it does not attest its own containing
  commit/tree, worktree state, reviewer result, PR, CI, merge, or main-CI outcome.
- The procedure forbids Python, `py`, `uv`, pytest, imports, runners, CODE V and `codevm`; it also
  forbids confirmatory-sample/holdout access, credentials, global configuration, scoring rulers and
  redline edits.
- Historical fixed commits `57c305f/2b3c73d`, `a5ea60e/930767a`, `ff76ae0/4317805`,
  `d9e0e75/00c7af0`, `bd2e1cf/cf9c6f3`, `aca7241/53c2455`, `ead809c/b140543`, and
  `8acb078/5856f8d`, `0915ccf/7e004a0`, `2c74a54/5784bac`, `02f9d17/7abf1b6`, and
  `ab7ce4d/f2ff988` were rejected. None may be
  published or treated as release evidence.

## Superseded design prechecks

Earlier dirty-tree specialists reported PASS on governance, machine and GitHub slices at a historical
schema byte hash. The later `a5ea60e/930767a` fixed-tree review superseded those observations with
`CHANGES_REQUIRED`, including source-attestation, pagination, digest registry, signed source profile,
canonical O-07 and tracked-document findings.

No dirty-tree or author-side result substitutes for fresh, non-author, read-only review of one
immutable fixed commit/tree.

## Permitted final static suite

The final suite uses only PowerShell `ConvertFrom-Json`, property access, literal/regex checks,
collection equality, `Get-FileHash`, protected-process inventory, and read-only Git commands including
`git diff --check`. Document text is never executed and `Invoke-Expression` is forbidden.

The suite must verify at least:

- all three JSON documents parse;
- 66 registered objects resolve one-to-one to templates and unique domains, including canonical
  authority-roster, authority-quorum-rule, machine-entry-inventory and machine-admission-receipt
  content objects;
- ten hash-reference classes plus the exhaustive signed path registry cover every hash/OID/SHA,
  digest-or-marker and fingerprint field exactly once;
- selector arithmetic is exactly 129 runtime roots, 2,056 automatic paths, ten exact additions,
  three bootstrap exclusions and 2,063 unique nonbootstrap paths; all inventory/admission and atomic
  pre-spawn revalidation evidence,
  the lease-state post-terminal hash
  and both optional merge-commit OID-or-protocol-marker leaves are explicitly selected;
- 24 common signer classes and all source/clock/release attester binding maps are exact;
- every stage roster/allowlist is nonempty, all per-role/total quorum minima are positive, within-role
  `AND`/`OR` semantics are exact, every accepted stage set has at least one valid human signature,
  and empty/zero/vacuous authorization rejects;
- every counted signature resolves one exact same-role registered roster identity/proof/key/allowlist
  tuple; `AND` equals the roster tuple set and `OR` is a nonempty duplicate-free subset, so an
  external-allowlist-only signer receives no quorum credit;
- the expert-rater protocol array is nonempty and duplicate-free, its exact tuple members bootstrap-
  hash to the external anchor, `expert_rater_count >= 1` equals its length, every counted expert-label
  signature tuple matches one unique member while carrying the same anchored hash, both expert-rate
  thresholds lie in `(0, 1]`, each candidate numerator requires the complete exact signer set and
  signed combination rule, incomplete or mismatched sets contribute zero to both numerators, and D
  requires at least one complete human two-dimension candidate set;
- custody genesis/commit/clock DAG, raw receipts, signatures and no opaque durability alias;
- signed review clock and START/COMPLETE event-time source bindings;
- 19 machine policy values, 27/27/48/33 binding sets, 29 typed leaves, 22 event kinds/formulas,
  35 lifecycle states, 43 transition rows and 10 unique crash variants;
- all 24 nonterminal partial-chain member kinds select exactly one canonical typed template or
  signed-policy schema/domain and exact transition context; the normal/recovery predecessor sets for
  `POST_RUN_SNAPSHOT_AND_MONITOR` and `ZERO_STATE_PROOF` are disjoint and exhaustive, and a same-class
  typed leaf from another kind rejects;
- two registered closed-world 33/39-field inventory/admission objects bind complete native machine/OS evidence,
  external OS-evidence attestation controls, selected inventory/admission schema/control equality,
  activation and the complete ticket/intent/pre-spawn/start/terminal chain; pre-spawn revalidation and
  drift-triggered new activation are mandatory;
- inventory/admission signature algorithms are inside their message preimages and validate under the
  fixed detached input, external trust roots, exact attester allowlist and anchored allowed suite;
- the 64-field durable pre-spawn receipt and 36-field process-start receipt bind one fresh raw native,
  externally attested, parser-verified, single-use atomic revalidation/commit transaction and the same
  unexpired monotonic validity bound; the machine OS source map has exactly five kinds;
- wrapper→payload→evidence→time equality, the exact 9-row lease anchor→policy, 19-row time/status/OS/gate
  anchor mapping, 16-row repeated-runtime-
  control equality and 20-row runtime-evidence→policy lease-authority maps, irrevocable PREPARED
  resolution, atomic admission barrier/insertion, and
  release-status CAS persistence;
- barrier post-state and per-operation terminal lease-state roots use the explicit accumulator-root
  class and independently recompute from the complete raw native proof under the anchor-pinned
  authority-state accumulator policy; opaque signed-root equality rejects;
- 32 evidence fields, 43 release/authority fields and 25 shared bindings;
- 64 release typed templates, 20 protocol bindings, 109 null human-owned choices, 20-field main-run
  member, 15-field main-CI record and bounded one-response
  repository Actions closure with exact capture-time projection and one source profile;
- exactly eight terminal-pagination JSON-null paths and fifteen GitHub source-leaf profile bindings;
- a pre-protocol anchor-only O-07 chain with exhaustive inline raw-member bytes, three distinct
  review scopes, complete content→message→record→envelope links, terminal PR CI, expected-head CAS,
  an independent provider acquisition→snapshot→merge-admission→terminal base/policy freeze, matching
  main/push CI, and distinct reviewed PR-head versus executable main-merge commit identity;
  its merge request must also prove the fixed query bytes and unique closed-world
  `mergePullRequest(input: …)` AST directly map all four fixed mutation variables with no bypass;
- 24 backlog nodes, H-00 plus prerequisite-only O-07 as the two `Gates: none` nodes, and reachability through
  `H-03 → R-00 → R-01 → R-02 → R-03 → O-09 → H-04`;
- every human-owned authority field remains null, A–F remain false, external human GO remains false,
  and expert/manufacturing outputs remain unavailable;
- zero protected CODE V/runner carriers and no real-machine command;
- `git diff --check` and stale-count/alias rejection.

## Historical static result — superseded

A prior author-side PowerShell run recorded `1,534/1,534` against older bytes. It was invalidated by
later tracked writes and the rejected `a5ea60e/930767a` fixed-tree findings; it is retained only as a
historical non-gate observation. A valid publication requires a new static receipt bound externally
to the exact immutable commit/tree. Passing author-side checks never creates a gate, human signature,
fixed-tree review, PR/CI record or north-star completion.

## Current author-side static observation — not gate proof

Pure PowerShell checks (`2994/2994`) on the current dirty bytes parse and duplicate-scan all three JSON files,
reject the escaped-key duplicate probe, recompute the structural and digest-selector counts, verify
machine/release semantics, and close the expert-rater external-anchor hash → signed protocol tuple
array → counted signature tuple → complete per-candidate signer-set chain. They also require the GET
PR-observation request-body carrier to be the exact no-body marker under the digest-or-marker class,
never a plain digest. The suite also proves both initial attestation algorithms are signed
under the external allowed suite and that the five-kind OS source map binds one externally attested
64-field atomic pre-spawn gate to the same unexpired transaction in the 36-field process-start receipt.
It validates all 116 non-null `reference_class` values against the exact ten-member enum, rejects the
obsolete registered-object alias, require the DURABLE_COMMIT subject to exclude the source-attestation
record that signs the same event-time leaf, retain final-receipt binding to both objects, and require the
acceptance mirror's machine counts to equal canonical `27/27/48`.
It constructs PRE_LEASE failure with the sole `INTENT_CONSUMED` pre-chain anchor at sequence `-1`,
the crash record as first partial-chain member at sequence `0`, rejection of every other anchor value
or claimed prior machine member, complete twelve-tree coverage in both STATE entry summaries, and
three exact-type/class last-member sources: the existing intent path, a terminal-or-marker path and a
typed-evidence/proof-or-marker path. It also requires partial-chain terminal and typed carriers to be
mutually exclusive, so PROTECTED_TERMINAL replay has no registered-object-through-typed-field alias and
the obsolete mixed field remains absent. It additionally resolves all 24 nonterminal member kinds
through the exhaustive exact template/policy schema/domain map, proves the two normal/recovery
context partitions are disjoint and exhaustive, and confirms the explicit same-class cross-kind
substitution rejection rule.
The staged canonical schema Git-blob SHA-256 is
`674e2e440c5ba671fe833308a12826dc3ab5a9ac0da916e7247665ab57db6c34`; the staged authority-policy
Git-blob SHA-256 is `485821144aa2bb2a11c6388da54d0048d3a5f8551220d96c95faefcfb5e41867`.

This is author-side dirty-byte evidence only. It is invalidated by later canonical/authority writes
and cannot substitute for a new immutable clean-parent commit/tree plus all three fresh reviews.

## External checks intentionally pending

- exact fixed commit/tree identity;
- three fresh non-author read-only PASS reviews on that same tree;
- PR CI, GitHub merge and matching main CI;
- human minimum-claim/protocol/TOR/custody/clock authority;
- sealed holdout draw/activation, confirmatory R-00 through R-03, expert labels and A–E evidence;
- future F release package and final external human `decision=GO`.
