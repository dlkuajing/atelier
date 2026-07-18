# Quick Plan: Patent generic family 78471711 / US-12169351-B2

**Status:** Complete — family shovel closed; parent saturation remains incomplete
**Date:** 2026-07-18
**Parent:** Global patent saturation ledger (incomplete)

## Entry facts

- Family ID: `78471711`
- Distinct root / publication: `US-12169351` / `US-12169351-B2`
- Application: `17/405071`
- Prior publication: `US-20220100057-A1`
- Title: `Imaging lens assembly, image capturing apparatus and electronic device`
- First inventor: `Su; Heng-Yi`
- Assignee: `LARGAN PRECISION CO., LTD.`
- Raw HTML: `data/patent-lake/uspto-ppubs-html/USPAT/86c15343d390d69d/US-12169351-B2.html`
- Raw bytes / SHA-256: `82117` / `86c15343d390d69dbb9fef7209d6b0852ea0b89ec4d1eac71a67e06d44e2b5f4`
- Normalized characters / SHA-256: `58575` / `66b6a725ff77dad6684caf9ac4170ec0309392c836d7ce831d996e71448361a9`
- Layout signature: `669c74453c256b9c8b70aacf6e499b3b25f467446459a157baa5754adea100cb`
- Existing replay attempt: `attempt-0001`, root state `parser_review_required`, item reason `parser_review_required.deterministic_parser_rejected`, detail `PatentParseError: embodiment f/Fno/HFOV line not found`; no conversion artifact.
- Entry marker scan: EFL=0, embodiment=84, example=0, F-number=0, full-field=0, half-field=0, queue table count=3. Marker counts and the generic-parser rejection are routing signals only, not a prescription or terminal conclusion.
- Frozen pre-change generic residual: 78 roots/items, result set `a5ba3123a2b21e649aec69ea2a1316a9446bc340bcc172717e6b8d1fd4d56501`; the frozen census will be copied verbatim from the preceding committed after-census.

## Objective

Independently reconcile the retained official grant source, prior-publication/priority lineage and every disclosed imaging-lens assembly, image-capturing apparatus or electronic-device item; determine whether the flattened prose/tables publish any exact reconstructible optical prescription and all required prescription-specific metadata; encode only evidence-supported conversions or terminal states; and close the family with deterministic replay/audit evidence while preserving all global saturation-ledger invariants.

## Work plan

- [x] Open this GSD quick before any family edit and record the exact entry snapshot.
- [x] Freeze the current 78-family generic residual census.
- [x] Reconcile bibliographic identity, related/priority lineage, claims, sections, formulas, figures, all table payloads and every disclosed source item directly from retained official sources.
- [x] Establish the complete document-item denominator and distinguish numerical optical prescriptions from lens-barrel, retaining, glue/void, module and device wrappers without collapsing source items.
- [x] Map any prescription only to its own directly published ordered surfaces, materials, aspheres, stop, EFL, F-number, field and image-height metadata; do not derive, repair or borrow missing values.
- [x] Inspect official PDF/original raster evidence only where needed to resolve layout or printed-token ambiguity; never enhance, measure geometry or repair a numeric cell.
- [x] Add the narrowest exact parser/classifier support and focused regression tests only after full source reconciliation; do not change generic heuristics or scoring/redline criteria.
- [x] Replay append-only twice, compare canonical semantics under only explicitly permitted runtime normalization, audit all 619 roots and rebuild the after generic census twice.
- [x] Refresh only live shared-ledger pointers required by deterministic tests while preserving historical snapshots.
- [x] Run focused/full patent tests, guard tests, compile/Ruff, JSON/evidence/output/contamination audits, corruption audit, CODE V process inventory, primary-repository cleanliness and diff review.
- [x] Update STATE and decisions evidence, mark this quick complete, and commit this family shovel atomically before selecting the next residual family.

## Closure evidence

- Exact official B2 source binds application `17/405071`, Family `78471711`, prior
  publication `US-20220100057-A1`, one Related Applications paragraph, two
  Background paragraphs, three Summary paragraphs, 27 Brief Description paragraphs,
  61 Detailed Description paragraphs, claims 1-10 with independent claims 1/9/10,
  26 declared figure panels, three flattened tables and five source items.
- Items 1-3 each disclose five plastic lens-element labels plus barrel, retainer,
  glue, void and image-surface mechanics. Tables 1-3 publish only a 20 um air gap,
  outer diameters and a ratio; the source expressly leaves lens amount, structures,
  surface shapes and other optical elements to imaging demand. Items 4/5 are the
  image-capturing-apparatus and electronic-device wrappers.
- The complete source has no radius-of-curvature, refractive-index, Abbe, asphere,
  aperture-stop, effective-focal-length, F-number, field-of-view or image-height
  disclosure. All five items therefore close as exact `confirmed_no_prescription`
  terminals under three evidence-specific reason codes; no worker, fingerprint, ZMX
  or formal intake is created.
- The retained B2/A1 PDFs have 36/35 image-only pages and decoded raster sets
  `4fd9f14d...648a7b` / `69425fbf...534e2`; they share no decoded raster. The B2
  has 26 drawing sheets, table pages 32/33/35 and claim pages 35/36. The HTML
  `FIG. 10` versus official page-5 `Fig. 1C` discrepancy is retained without repair.
  Contact/original review used no enhancement, geometry measurement or raster numeric
  transcription.
- Append-only attempts 2/3 are semantic-equal after removing only `result_attempt`,
  at `1ee284d27b916c2826368d92eafcf59375ca3766a2ea17b227fd8aa5461e0189`.
  Generic residual is 78→77 roots/items; both after censuses are byte-identical at
  `f176ad775ecc2b5ae6aa370a483a3f33d542192621a3e29f2d51731fbef02071`,
  and result set is `12c3080c61c9de456501a0c92126a2bee874fda912582d4bf991156cc1103a01`.
- Focused tests pass 8/8, complete `tests/test_patent_to_zmx.py` passes 721/721,
  the remaining patent suite passes 94/94 and the offline launch guard passes 5/5.
  Compile and Ruff pass; 58 changed JSON files parse; 75 source-evidence manifests
  rehash 983 path-hash references including 833 complete path/byte/hash triples;
  all 37 retained visual artifacts rehash through the raster regression.
- Forty-five prior manifests refresh 90 shared summary/report live records while
  preserving their formatting and historical snapshots; three test-proven live
  result-set fields are aligned. Terminal null/coverage invariants, formal-output
  contamination, scorer/redline changes and `git diff --check` are zero; the primary
  repository is clean and CODE V inventory is zero. Source-evidence SHA-256 is
  `90a502f88ad178cc0600c6d95adbbef9dcbf54a5c883ab2809aa0192399bbdf8`.
- Stable queue ordering selects Family `86240812`, root `US-20260129276`,
  publication `US-20260129276-A1` next. Global saturation remains incomplete.

## Safety constraints

- Never start, control or terminate CODE V; inventory must remain zero.
- Original retained source only. No drawing measurement, image enhancement, coordinate synthesis, convention repair or related-family numeric borrowing.
- F-number, field, image height and stop position are prescription-specific required metadata; do not derive a missing value from another published quantity.
- The global patent saturation goal remains incomplete after this family closes.
