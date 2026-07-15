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
- Append-only replay completed all 8 roots. The generic document bucket changed 294→286; the 58
  disclosed embodiments produced 26 converted-pending-intake items, 26 terminal receipts, and 6
  structured parser rejections. No candidate was promoted. Result-set SHA-256 is
  `f0e4e3c1a0a0600fea49c276ce51cfe7a84558228d55bb0f404509bebe6f4dc8`; strict audit is
  619/619 with zero corrupt evidence. The after-first-layout census SHA-256 is
  `f165467dd70fe1ab98e529c61dbc95ef499e1f47523e854595ae1101f5673c35`.
- The second source-proven family is 3 roots / 21 disclosed folded-zoom states. Exact adjacent
  configuration tables bind EFL, F/#, HFOV, and every variable air gap by column. Twelve ASP
  states are deterministically recoverable. Six QTYP states retain the published duplicate `S7`
  / missing `S8` index failure; three index-complete QTYP states retain an explicit unsupported
  `QTYP/NR/A0-A6` rejection instead of translating a different polynomial basis as XASPHERE.
- Append-only replay completed all 3 roots. The 21 states produced 9 converted-pending-intake
  items, 3 terminal process receipts (`trace_timeout` after the 120-second worker hard limit), and
  9 structured parser rejections. No candidate was promoted. The generic document bucket changed
  286→283. Result-set SHA-256 is
  `3aab024784036d6f268f741deb0396d68438300226b20e9805f0c20f05d48bd6`; summary artifact
  SHA-256 is `80310958a437ab64a90f997035cfc065c7aa73a9ec399f4c56e56a8ed44dcb19`;
  strict audit is 619/619 with zero corrupt evidence. The after-second-layout census SHA-256 is
  `fb68b3362117a00506dcadbc34189b7a6222a3d4afbddeb9559295aabbdc4798`. The
  family-ownership scan matches exactly these 3 roots before replay and zero remaining roots after
  replay; 74 focused parser/census/replay/process tests and Ruff pass.

## Completion condition

The quick is complete only when the 294-item before census is reproducible, implemented layouts
are source-proven and regression-tested, targeted replay and full audit pass, no metadata field
regresses, and the next largest measured failure bucket is recorded. Parent saturation remains
incomplete.
