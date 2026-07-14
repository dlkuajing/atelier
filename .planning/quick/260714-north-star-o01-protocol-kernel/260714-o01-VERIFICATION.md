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

## Strict protocol and freeze assertions

- Public raw payloads are copied in one recursive pass and accept only exact JSON primitives plus
  exact built-in dicts, lists, or tuples. Container subclasses, bytes, sets, frozensets, generators,
  non-string mapping keys, embedded models, and cyclic raw containers are rejected with
  `ProtocolViolation`.
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
- Pipeline run units and expert candidate slots have separate denominators. Missing verified expert
  evidence contributes zero; caller-submitted expert booleans are forbidden.
- Conditional-on-unverified-reported-delivery expert ratios are diagnostic only. Their dependence
  clusters are filtered to exactly their diagnostic denominator members and empty clusters are
  dropped.
- Candidate reported delivery uses the frozen
  `any_non_rejected_run_reported_delivered` aggregation rule. An explicit selection ledger records
  ordered selected candidate slots plus every rejected run/candidate exclusion hash considered during
  selection; both conditional ratios enumerate those hashes.
- Duplicate-cluster evidence and confidence intervals are explicitly unavailable. O-01 does not
  claim to implement the later pre-label duplicate verifier or a ratified confidence method.

## Commands and current results

```text
PYTHONUTF8=1 uv run pytest tests/test_north_star_protocol.py tests/test_north_star_itt.py -q -k "not real" -m "not real_machine"
91 passed in 0.35s

PYTHONUTF8=1 uv run ruff check app/core/north_star tests/test_north_star_protocol.py tests/test_north_star_itt.py
All checks passed!

PYTHONUTF8=1 uv run mypy app/core/north_star
Success: no issues found in 4 source files

git diff --check
exit 0 (Windows line-ending conversion warnings only)

PYTHONUTF8=1 uv run pytest -q -k "not real" -m "not real_machine"
2267 passed, 1 skipped, 545 deselected, 6154 warnings in 1208.91s
```

The first full-regression attempt on the old `7f53436d` base exposed two pre-existing Windows CRLF
hard-pin failures. They were isolated and released separately through PR #84; O-01 is based on
`42803f8d`. No real-machine test, runner, CODE V process, holdout, or expert-review surface is
selected by these commands.
