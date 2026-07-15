---
quick_id: 260715-patent-generic-summary-metadata-parser
status: active
owner: Codex
base: c3f7af8
---

# Generic summary metadata parser census and deterministic expansion

## Goal

Reduce the largest current frozen-pool parser signature,
`generic_summary_metadata_missing` (294 items), by auditing every affected latest replay item and
its retained official USPTO PPUBS HTML, grouping the exact published metadata layouts, and adding
only deterministic embodiment-bound extraction rules.

This quick does not infer optical values, promote staging candidates, change quality/scoring
thresholds, or claim patent saturation.

## Evidence contract

1. Build a strict before census from the latest 619-root result set, bound to cohort and result-set
   hashes. Retain root, publication, item, embodiment, raw HTML path/hash, and normalized layout
   signature for all 294 matching items.
2. Inspect the complete census before choosing a format family. Historical parser names and
   assignee assumptions are not evidence.
3. Every accepted EFL, F-number, and half-field value must be an exact published token or an
   explicitly defined deterministic transform such as full-field divided by two.
4. Metadata without a provable embodiment binding, damaged OCR, or ambiguous multiple candidates
   remains a structured parser-review item.

## Implementation and replay contract

1. Rank exact layout groups by affected item/root count and implement the largest homogeneous
   source-proven group first.
2. Preserve existing family-specific parsers; do not make the generic parser permissive enough to
   steal or cross-bind another family's tables.
3. Add exact-source regression fixtures for every layout and negative tests for ambiguity and
   cross-embodiment leakage.
4. Replay affected roots append-only through the existing process-isolated converter and 180-second
   root budget. Successful output remains `converted_pending_intake`.
5. Recompute the full summary, strict external-evidence audit, and before/after census. Record the
   next largest measured bucket.

## Safety and verification

- Use `PYTHONUTF8=1` on Windows and `uv` only.
- Confirm CODE V inventory is zero before and after replay; do not start CODE V/codevm.
- Run focused parser/replay tests, the patent regression set, Ruff, strict audit, and
  `git diff --check`.
- Do not modify scorers, redlines, forbidden paths, or physical thresholds.

## Runtime census checkpoint (2026-07-15)

- Strict before census: 294 document-scoped items / 294 roots, bound to result set
  `2e0a9ceb2e8b930393168dc7f9cda50c1659aebeacab6afe98f0b96dfea5d506`.
- Optional alphanumeric table suffixes (`1A`, `1B`) are included in layout segmentation. The
  census has 179 exact normalized signatures; artifact SHA-256 is
  `fa145da695c2e9d2dbff1fe8d9c5144ceb84773e1fa1e2edf70d6af211da82c4`.
- The first source-proven family is 8 roots / 58 disclosed embodiments with exact published
  `f=... mm, Fno=..., HFOV=...` headers. Deterministic dry-run yields 52 complete prescriptions
  and 6 structured physical/OCR rejections. The two related exemplary tables with a different
  `S.sub.i` structure remain outside this implementation.

## Completion condition

The quick is complete only when the 294-item before census is reproducible, implemented layouts
are source-proven and regression-tested, targeted replay and full audit pass, no metadata field
regresses, and the next largest measured failure bucket is recorded. Parent saturation remains
incomplete.
