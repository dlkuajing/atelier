# Quick Plan: Patent generic family 21816074 / US-4249805-A

**Status:** Complete — family shovel closed; parent saturation remains incomplete
**Date:** 2026-07-18
**Parent:** Global patent saturation ledger (incomplete)

## Entry facts

- Family ID: `21816074`
- Distinct root / publication: `US-4249805` / `US-4249805-A`
- Application: `06/023591`
- Title: `Composite photography system`
- First inventor: `Hilbert; Robert S.`
- Assignee: `Magicam, Inc.`
- Raw HTML: `data/patent-lake/uspto-ppubs-html/USPAT/25b5e668414a45ca/US-4249805-A.html`
- Raw bytes / SHA-256: `82047` / `25b5e668414a45ca2afcd5251205e28833c0c09fa1808779a96cc11fdd16cdb1`
- Layout signature: `65e82bf69eb4de7c2350051a1212f906c0e29435d901bf1e0e35a6e3cf634f74`
- Existing replay attempt: `attempt-0001`, root state `parser_review_required`, item reason `parser_review_required.deterministic_parser_rejected`, detail `PatentParseError: embodiment f/Fno/HFOV line not found`; no conversion artifact.
- Entry marker scan: EFL=8, embodiment=0, example=0, F-number=0, full-field=36, half-field=0, 0 HTML tables. Marker counts are routing signals only, not a representability conclusion.
- Frozen pre-change generic residual: 79 roots/items, result set `95b6f817d78a357f8c1c7bbfbb627117fc7bd81773dd947d440a2f0c42606702`; the frozen census will be copied verbatim from the preceding committed after-census.

## Objective

Independently reconcile the retained official grant source and every disclosed foreground/background optical design or system item, determine whether the prose-only source publishes exact reconstructible prescriptions and all prescription-specific required metadata, encode only evidence-supported conversions or terminal states, and close the family with deterministic replay/audit evidence while preserving all global saturation-ledger invariants.

## Work plan

- [x] Open this GSD quick before any family edit and record the exact entry snapshot.
- [x] Freeze the current 79-family generic residual census.
- [x] Reconcile bibliographic identity, priority/related lineage, claims, sections, equations, figures and every disclosed optical item directly from retained official sources.
- [x] Establish the complete document-item denominator and distinguish optical prescriptions from composite-system wrappers without collapsing source items.
- [x] Map any prescription only to its own directly published ordered surfaces, materials, stop, EFL, F-number, field and image-height metadata; do not derive, repair or borrow missing values.
- [x] Inspect official PDF/original raster evidence only where needed to resolve source layout or printed-token ambiguity; never enhance, measure geometry or repair a numeric cell.
- [x] Add the narrowest exact parser/classifier support and focused regression tests only after full source reconciliation; do not change generic heuristics or scoring/redline criteria.
- [x] Replay append-only twice, compare canonical semantics under only explicitly permitted runtime normalization, audit all 619 roots and rebuild the after generic census twice.
- [x] Refresh only live shared-ledger pointers required by deterministic tests while preserving historical snapshots.
- [x] Run focused/full patent tests, guard tests, compile/Ruff, JSON/evidence/output/contamination audits, corruption audit, CODE V process inventory, primary-repository cleanliness and diff review.
- [x] Update STATE and decisions evidence, mark this quick complete, and commit this family shovel atomically before selecting the next residual family.

## Closure evidence

- The exact source denominator is 20 Background/Summary paragraphs, 61 Description paragraphs, claims 1-54 with independent claims 1/17/39, FIGS. 1-25, six flattened optical tables, eight numerical lens modes and one coordinated composite-photography system wrapper.
- Tables 1-6 directly publish ordered radii, axial spacings, index/Abbe data, aperture stops, effective focal lengths, F-numbers and half-fields for all eight lens modes. Neither the official HTML nor the correction-certified PDF directly publishes a prescription-specific absolute image height; no value was derived from focal length/field or nominal television/35 mm format.
- Items 1-8 close as `metadata_unpublished.absolute_image_height_absent`. The wrapper contains exactly those eight modes and no ninth ordered prescription, so item 9 closes as `confirmed_no_prescription.composite_photography_system_wrapper_only`.
- The retained 1,468,403-byte official PDF has 22 image-only pages, seven drawing sheets, five table pages and a page-22 Certificate of Correction. All decoded rasters reconcile at `d665607f33310bce89d9af0681f6d6a6aeb2de373d22f72ad07c9d0aac5b5687`; contact/original review used no enhancement, measurement or raster numeric transcription.
- Append-only attempts 2/3 are semantic-equal after removing only `result_attempt`, at `ed1c985871e8600f00fe2f88b76efdf13ee107d8c47063e0fb757c994d37c981`. Both retain nine terminal items, 54 null conversion fields and 18 empty coverage maps, with no request, receipt, fingerprint, candidate, staging ZMX or formal intake.
- Strict replay is 619/619 with missing=0 and corrupt=0. Generic residual is 79→78 roots/items; the two after censuses are byte-identical at `31f7f635e081be3f4fdddce4f8dc9dcbf1dbc836c2c94c79346ce2d8ce0fde6a`, and the result set is `a5ba3123a2b21e649aec69ea2a1316a9446bc340bcc172717e6b8d1fd4d56501`.
- Focused tests pass 8/8, complete `tests/test_patent_to_zmx.py` passes 713/713, the remaining patent suite passes 94/94 and guards pass 16/16. Compile and Ruff pass; 57 changed JSON files parse; 74 source-evidence manifests rehash 816 complete references; 23 retained visual artifacts rehash.
- Forty-four prior source-evidence manifests refresh 88 summary/report live records while retaining their original formatting and historical snapshots; three test-proven live result-set fields are aligned. Formal-output contamination, scorer/redline changes and `git diff --check` are zero; the primary repository is clean and CODE V inventory is zero.
- Stable queue ordering selects Family `78471711`, root `US-12169351`, publication `US-12169351-B2` next. Global saturation remains incomplete.

## Safety constraints

- Never start, control or terminate CODE V; inventory must remain zero.
- Original retained source only. No drawing measurement, image enhancement, coordinate synthesis, convention repair or related-family numeric borrowing.
- F-number, field, image height and stop position are prescription-specific required metadata; do not derive a missing value from another published quantity.
- The global patent saturation goal remains incomplete after this family closes.
