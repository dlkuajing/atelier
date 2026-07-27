# Quick Task: Patent Generic Family 81258214

**Status:** complete-shovel-saturation-incomplete
**Parent:** patent saturation engineering (active / incomplete)
**Started:** 2026-07-18
**Entry evidence:** committed Family 77292582 shovel at `2b37e98c`; strict replay is
619/619 and `generic_summary_metadata_missing` remains the largest executable bucket at
90 items / 90 roots.

## Objective

Resolve deterministic next Family ID `81258214`, root `US-20220128799`, publication
`US-20220128799-A1`, application `17/364492`, title `Optical lens` and applicant
`ABILITY ENTERPRISE CO., LTD.` Reconcile exact publication, application, priority/continuation
and family identity plus every source-disclosed prescription, optical system, embodiment, example,
variant, claim family, figure, table and formula. Convert only complete directly published optical
prescriptions representable by the current contract; retain incomplete, unsupported, conflicted or
metadata-missing designs fail-closed without drawing transcription, coordinate synthesis or values
borrowed from related applications.

## Plan

1. [completed] Freeze the committed strict 619-root generic census; verify exact next-group
   selection and attempt-1 failure from repository/runtime facts.
2. [completed] Pin official source raw/normalized hashes, application/priority/publication/family identity,
   and complete section/paragraph/claim/figure/table/formula/disclosed-item denominators.
3. [completed] Reconcile every disclosed prescription, optical system, embodiment, example and dependent
   variant; inspect official PDF/raster evidence only where it closes a source gap, never to infer
   coordinates.
4. [completed] Test every optical reference and numeric value against PatentSurfaceInput/ZMX representability
   before any worker runs.
5. [completed] Add one exact-source parser, terminal or nonterminal classifier only after the complete source
   denominator reconciles and each item state follows from independent source facts.
6. [completed] Replay append-only twice, compare canonical semantics under only permitted runtime identity
   normalization, audit all 619 roots and rebuild the after generic census twice.
7. [completed] Run focused and full offline patent tests, CODE V guard, Ruff, compile, JSON, strict audit,
   hash, contamination and diff checks with `PYTHONUTF8=1` and exact CODE V inventory zero.
8. [completed] Update STATE, decisions, source evidence and queue; commit the shovel without push, then
   remeasure every executable bucket. Parent saturation remains incomplete.

## Entry facts

- The committed queue selects layout signature
  `47e7cc4e752d976ce84eb570f2ad8f451a7ead80846f9db627cd1be1f6a5aa35`, Family
  `81258214`, root `US-20220128799` and publication `US-20220128799-A1` next.
- Committed result set is
  `9d5afa23ac6a0af7ad4a701c513c2eabde5d4ae5356e9682f0ec7a9f02235562`;
  generic residual is 90 roots/items, ahead by root count of AAC Raytech 55 roots/174 items and
  Sunny 49 roots/177 items.
- Retained parser input is
  `data/patent-lake/uspto-ppubs-html/US-PGPUB/d3357394ccefdb40/US-20220128799-A1.html`,
  raw SHA-256 `d3357394ccefdb4090c9d5b607403cd512476db65630c5c51e812b7dd8ba8962`,
  with zero tagged tables, 21 F-number markers and 32 full-field markers measured by the committed
  queue.
- Attempt 1 is the frozen starting failure; its exact state, detail and absence/presence of any
  conversion/formal artifact must be read from the committed result before classification.

## Result

Exact A1 source reconciles application `17/364492`, Taiwan priority `109137408`, Ability
Enterprise identity, 66 continuous numbered paragraphs, claims 1-20 in three independent claim
families, eleven declared figure panels, seven printed table panels, one MathML asphere equation
and exactly four disclosed prescriptions. FIGS.3A/3B and 4A/4B publish complete ten-lens OL1/OL2
surface and even-asphere tables; FIGS.7/8 publish complete spherical eleven-lens OL3/OL4 tables;
FIG.9 directly publishes each system's focal length, TTL, F-number, image height, full FOV, R1/R2
and redundant ratios. No fifth prescription is introduced by a dependent claim or prose variant.

The retained official PDF is 886,635 bytes with fifteen image-only 2560x3300 pages and one raster
per page. The 1,334,320-byte Google OCR wrapper has all fifteen decoded rasters pixel-identical to
the official wrapper at raster-set SHA-256 `9f00ea45...4db5`; only this exact-raster overlay is
admitted as a second OCR view. RapidOCR and overlay text independently agree on every finite
numeric cell. Original pages 3/4/6/7/8 and the contact sheet were reviewed without enhancement or
drawing-geometry measurement. OL1/OL2 retain 26 ordered rows and aspheres S19/S20; OL3/OL4 retain
28 spherical rows. Published thickness sums are checked against FIG.9 TTL using only the maximum
accumulated 0.01-mm printing-rounding bound, while R1/R2 and redundant rows cross-check exactly.

All four source-faithful prescriptions pass `PatentSurfaceInput`, deterministic trace and
process-isolated ZMX validation. Attempts 2/3 produce eight isolated worker receipts and four
distinct staging ZMX files; request/response/candidate payloads agree across retries. After the
recorded runtime identity/path/elapsed-time normalization and receipt semantic replacement, both
results equal SHA-256 `f2b85fee...a9f0`. The root becomes `converted_pending_intake` with four
evidence-complete items and no formal intake or CODE V call. Generic residual moves 90->89;
result set is `5a9124d1...615e`, summary `0a40be70...419e`, report `6b1f901a...80af`, and the two
after censuses are byte-identical at `56974bcf...cddec`. Strict audit is 619/619 with corrupt=0.

Focused tests pass 4/4, complete `tests/test_patent_to_zmx.py` passes 630/630, the remaining patent
suite passes 94/94, and the no-real-CODE-V guard passes 5/5. The first complete sweep passed
629/630 and exposed only Family 77292582's live summary result-set pointer; after that one pointer
was aligned, its targeted pair passed 2/2 and the second complete sweep passed. Ruff, compile,
72-JSON parsing, 63 evidence files/730 path-hash references, 66-null/22-empty-coverage terminal
invariants, current converted-output checks, four-scope formal-contamination and primary-repository
contamination checks pass; CODE V inventory is zero. All 33 prior shared summary/report references
were mechanically refreshed while historical result-set snapshots remain fixed except the prior
Family 77292582 evidence contract, whose test explicitly binds the live summary result set.
Root-first queue keeps generic ahead of AAC Raytech 55 roots/174 items and Sunny 49 roots/177
items; stable ordering selects Family `94732062`, root `US-20260181269`, publication
`US-20260181269-A1` next. Parent/global saturation remains active and incomplete.
