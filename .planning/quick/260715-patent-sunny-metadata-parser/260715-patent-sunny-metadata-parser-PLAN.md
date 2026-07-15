---
quick_id: 260715-patent-sunny-metadata-parser
status: active
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
