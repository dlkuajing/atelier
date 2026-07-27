---
quick_id: 260715-patent-sunny-metadata-parser
status: complete
owner: Codex
base: 1523abd
---

# Sunny metadata parser census and deterministic expansion

## Goal

Reduce the largest measured frozen-pool parser signature,
`sunny_embodiment_metadata_missing` (299 items), by inspecting every affected retained official
USPTO PPUBS HTML document, grouping exact published metadata layouts, and implementing only
deterministic extraction rules supported by those documents.

This quick does not infer or repair optical values, promote staging ZMX to the formal library,
change quality/scoring thresholds, or claim patent saturation.

## Evidence contract

1. Recompute the affected root/item set from the latest strict replay results; do not select
   samples from historical prose or chat memory.
2. Bind the census to the frozen cohort SHA and pre-change result-set SHA. Retain publication,
   root, embodiment, missing-field tuple, raw-document path/hash, and normalized layout signature.
3. Every implemented format family must have retained official examples and regression fixtures
   that preserve the published numeric tokens. No LLM-generated or midpoint-filled number is
   permitted.
4. Ambiguous, damaged, or unbound metadata remains an explicit parser-review item; fail closed.

## Implementation contract

1. Audit all 299 affected items and separate parser gaps from documents that truly omit one or
   more required published fields.
2. Add the smallest deterministic Sunny metadata rules covering the largest homogeneous evidence
   groups. Bind values to the correct embodiment through explicit example labels or table position.
3. Add a replay selector for exact parser signatures if needed, so append-only retries touch only
   affected roots and preserve prior attempts.
4. Re-run affected roots through the existing process-isolated converter and cumulative patent
   budget. Successful output remains `converted_pending_intake`.
5. Recompute the complete 619-root summary/report and record exact before/after counts and hashes.

## Safety and verification

- Set `PYTHONUTF8=1` for all Windows tests and replay commands.
- Confirm no CODE V process before and after replay; do not start CODE V/codevm.
- Run focused parser/replay tests, the patent regression set, Ruff, strict replay audit, and
  `git diff --check`.
- Do not modify route scorers, redline criteria, forbidden paths, or physical thresholds.
- Leave unresolved layouts in structured non-terminal buckets with retained source evidence.

## Completion condition

The quick is complete only when the full affected census is reproducible, every implemented rule
has exact-source tests, the targeted append-only replay and complete summary audit pass, and the
next largest measured failure bucket is recorded in STATE and decisions. Parent patent saturation
remains incomplete.

## Final runtime result (2026-07-15)

- The strict before census contains all 299 matching items across 64 roots and is bound to result
  set `3bc0bbee88906ff3b6c40e276addbb6bd3336e0dc73dd987706f5b90393776df`.
  Missing-field counts were `f=77`, `Fno=246`, and `Semi-FOV=206`; artifact SHA-256 is
  `dbf3c9887b5d010ea189de05ab38fdb05d34de7060ca648933212439c989f5aa`.
- Implemented exact-cardinality grouped rows for shuffled Sunny condition/parameter headers,
  explicit maximum/full-FOV to half-angle conversion, compound-expression rejection, and an exact
  duplicate-pair collapse for published two-state columns. Differing state pairs remain rejected.
- All 64 census roots were replayed append-only. The CLI default limit split the first pass at 25;
  an explicit frozen 39-root remainder list completed the cohort without replaying those 25. A
  five-root regression replay closed the compound-EFL and duplicate-state findings.
- The strict after census contains 199 matching items across 53 roots: 100 items left the Sunny
  metadata bucket. Missing-field counts are `f=77`, `Fno=154`, and `Semi-FOV=155`, so no field
  regressed relative to the before census. After-census SHA-256 is
  `c20a350e4fc932396442f28b62eb7e9468cda8f8472ba3f434b431ad9adb1dca`.
- Full current result-set SHA-256 is
  `2e0a9ceb2e8b930393168dc7f9cda50c1659aebeacab6afe98f0b96dfea5d506`;
  summary file SHA-256 is
  `56700a7baea5228a7d07d84243e762f8fb6b6536dde65c972b87009c22ee4772`.
  Strict audit reports 619/619 roots, zero missing, and zero corrupt external evidence.
- Current items are parser review 1288, converted-pending-intake 429, terminal receipt 649, and
  conversion retry 28. None of the staging successes were promoted to the formal library.
- `PYTHONUTF8=1` patent regression passed 95 tests; Ruff and `git diff --check` passed. CODE V
  inventory was zero before and after every replay segment.
- The next largest measured parser signature is `generic_summary_metadata_missing=294`, followed
  by Sunny metadata 199 and AAC Raytech metadata 174. Parent patent saturation remains incomplete.
