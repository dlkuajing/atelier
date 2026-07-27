# Quick: Patent generic Family 74060373

**Status:** complete-shovel-saturation-incomplete
**Parent:** patent saturation engineering (active / incomplete)
**Started:** 2026-07-15
**Entry evidence:** strict 619/619 replay result set
`3d12a5b3ea27617286578ab122d3ee1f9a19f2720b3c8e097f538d90ca83beb6`, with
`generic_summary_metadata_missing` at 192 items/192 roots and no corrupt result.

## Objective

Resolve the tied-largest three-root official Family ID 74060373 using only retained source facts.
Audit the complete text and every drawing/table reference before choosing parser expansion,
source-proven terminal classification, or continued parser review. Never infer no-prescription
status from the current zero-table census alone.

## Plan

1. Freeze the 192-item generic census and identify the exact three official publications.
2. Audit title, application/family bindings, formal embodiments, drawings, tables, architecture
   counts, and every optical surface-prescription marker per publication.
3. Implement only an exact-source, fail-closed parser/classifier supported by the full disclosure;
   preserve any figure-only, missing, or ambiguous prescription as structured parser review.
4. Replay all selected roots append-only twice, compare canonical semantics excluding only retry
   identity, audit all 619 roots, and rebuild the after census twice.
5. Run explicit parser/replay/census/process/saturation tests, Ruff, and `git diff --check` with
   `PYTHONUTF8=1` and CODE V inventory zero.
6. Update STATE, decisions, and this plan with exact hashes and the next measured bucket. Parent
   saturation remains incomplete.

## Completion evidence

- Full official-source audit: `family-74060373-source-audit.md`.
- `US-12092800-B2` is exact-source terminal
  `confirmed_no_prescription.panoramic_opto_mechanical_architecture_only`; the complete 28-entry
  drawing sequence and 56-page image PDF contain architecture only.
- `US-12313825-B2` and `US-20250284103-A1` each retain one explicit FIG. 8C seven-lens parser
  item. Their 66-page official PDFs expose zero table-region numeric OCR tokens at the unchanged
  0.99 gate, so no numeric value or ZMX is accepted.
- Attempts 2/3 are semantic-equal for all three roots after excluding only `result_attempt`; see
  `family-74060373-replay-determinism.json`.
- Replay result set: `e0b098b9b622c5ce6033889b93690aa18e5691a869309198a680c8f3ed74c180`.
  Full audit: 619/619, missing=0, corrupt=0.
- Generic census: 192→189 items/roots. Two after-census builds are byte-identical at
  `d638c3c548ac5bca9bbc088a9dc5aaf06e204beea004e00373f70d7932f81db5`.
- Verification: 197 complete patent-parser tests + 54 replay/census/saturation/CODE V guard tests
  passed; Ruff and `git diff --check` passed; CODE V inventory was zero before every sweep.
- Next measured generic family tie: `44121309` and `46327306`, three roots each. Continue with
  `44121309` because its official text explicitly points to FIGS. 14A/14B prescriptions and thus
  requires the higher-risk exact-raster recovery path rather than a no-prescription inference.

Parent patent saturation and formal intake remain incomplete.
