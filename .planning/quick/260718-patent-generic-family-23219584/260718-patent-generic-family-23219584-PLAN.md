# Quick Task: Patent Generic Family 23219584

**Status:** complete-shovel-saturation-incomplete
**Parent:** patent saturation engineering (active / incomplete)
**Started:** 2026-07-18
**Entry evidence:** committed Family 85177416 shovel at `762cc36`; strict replay is
619/619 and `generic_summary_metadata_missing` remains the largest executable bucket at
95 items / 95 roots.

## Objective

Resolve deterministic next Family ID `23219584`, root `US-6292306`, publication
`US-6292306-B1`, application `09/314343`, title `Telecentric zoom lens system for video based
inspection system`, applicant `Optical Gaging Products, Inc.` Reconcile exact publication,
application and family identity plus every source-disclosed optical design or dependent variant.
Convert only complete, directly published optical prescriptions representable by the current
contract; retain incomplete, unsupported, source-conflicted or metadata-missing designs
fail-closed without drawing transcription, coordinate synthesis or related-family borrowing.

## Plan

1. [complete] Freeze the committed strict 619-root generic census; verify exact next-group
   selection and attempt-1 failure from repository/runtime facts.
2. [complete] Pin official source raw/normalized hashes, application/priority/publication/family identity,
   and complete section/paragraph/claim/figure/table/formula/disclosed-item denominators.
3. [complete] Reconcile every disclosed zoom/telecentric configuration, optical surface, motion group,
   aperture/stop, system parameter and dependent variant; inspect official PDF/raster evidence
   only where it closes a source gap, never to infer coordinates.
4. [complete] Test ordered surfaces, radius, spacing, material, stop and required system-metadata semantics
   against PatentSurfaceInput/ZMX representability before any worker runs.
5. [complete] Add one exact-source parser, terminal or nonterminal classifier only after the complete source
   denominator reconciles and each item state follows from source facts.
6. [complete] Replay append-only twice, compare canonical semantics under only permitted runtime identity
   normalization, audit all 619 roots and rebuild the after generic census twice.
7. [complete] Run focused and full offline patent tests, CODE V guard, Ruff, compile, JSON, strict audit,
   hash, contamination and diff checks with `PYTHONUTF8=1` and exact CODE V inventory zero.
8. [complete] Update STATE, decisions, source evidence and queue; commit the shovel without push, then
   remeasure every executable bucket. Parent saturation remains incomplete.

## Entry facts

- The committed queue selects layout signature
  `437fa2555cbad39206a20353ea2dc5e5c7dba01ccf65749ed1c49baa7cfdaa4b`, Family
  `23219584`, root `US-6292306` and publication `US-6292306-B1` next.
- Committed result set is
  `d6f7f079db46225c64cff3a464f42ae718627642a1d20b4eda8235b42cd34f17`;
  generic residual is 95 roots/items, ahead by root count of AAC Raytech 55 roots/174 items and
  Sunny 49 roots/177 items.
- Retained parser input is
  `data/patent-lake/uspto-ppubs-html/USPAT/79baca6bd83e0d39/US-6292306-B1.html`,
  raw SHA-256 `79baca6bd83e0d395aedfb916b7af7afa388706a6030b2706f6ef1c112430ba6`,
  with zero tagged tables and one F-number marker measured by the committed census.

## Result

- Exact B1 source binds application `09/314343`, Family ID `23219584`, Optical Gaging
  Products ownership, 29 numbered Background/Summary/Description paragraphs, claims 1-17,
  FIGS.1-5, two flattened optical tables, zero tagged tables and one four-state telecentric
  zoom system plus five qualitative dependent variants.
- The Lens Table publishes 27 radii and 17 glass-element thickness/material rows; the
  Magnification Table publishes stop diameter and X/Y/Z moving-group spacings at 0.8x, 1.8x,
  4.8x and 8.0x. It does not publish eight required fixed air gaps, S2 conic/asphere
  coefficients, system EFL, image height or angular field. The published image F/20 and
  0.8x F/25 through 8x F/2.5 notation do not close those gaps. The system therefore becomes
  one exact `metadata_unpublished` terminal without deriving coordinates or metadata, borrowing
  family values or creating formal output.
- The retained official PDF is a 478,406-byte, seven-page image-only wrapper with one
  2320x3408 raster per page, two drawing sheets and the optical tables on pages 5-6. Every
  raster plus the contact sheet and all page PNGs are hashed; pages 5-6 were visually reviewed
  at original detail without drawing measurement.
- Append-only attempts 2/3 are semantic-equal after excluding only `result_attempt`, at
  `0e5314f3793453d4414ed0551ec7d6c529c346a3174a615f708a5f64eabe737c`. Result-set SHA is
  `10baa7c069cf8619b947e5ccffaaee58299c09c52569659ed65ba7cba6ca0540`; summary/report SHAs
  are `c50619a1a83cae412725e50b2eccb96f49b5d8bf0efc04294f0c19ac18f35850` and
  `abe1c064e50a359842a399ab10a0106ee27f550accaeb2a4cd3dda5d5f5efc41`.
- Generic residual falls 95 -> 94 roots/items; both after censuses are byte-identical at
  `12eea380eb5c4838dd7412afe25697a1369f295d3c749c8e34c21aff6f21e797`. Strict replay audit
  is 619/619 with corrupt=0. Focused tests are 9/9, `test_patent_to_zmx.py` is 590/590,
  all 684 offline patent tests plus 5/5 CODE V guard tests pass; compile, Ruff, ten-JSON,
  58 evidence files/564 referenced hashes, 6-null/2-empty-coverage, four-scope formal-
  contamination and diff checks pass. One 304-second file regression attempt timed out without
  a verdict; the subsequent 720-second run passed in 309.61 seconds. CODE V stayed zero.
- All 28 prior evidence references to the changed global summary/report were mechanically
  refreshed; the current evidence makes 29 live shared references. Root-first queue keeps
  generic ahead of AAC Raytech 55 roots/174 items and Sunny 49 roots/177 items. Stable ordering
  selects Family `94819907`, root `US-20260189780`, publication `US-20260189780-A1`, next.
  Parent/global patent saturation remains active and incomplete.
