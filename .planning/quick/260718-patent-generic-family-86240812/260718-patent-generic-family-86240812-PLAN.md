# Quick Plan: Patent generic family 86240812 / US-20260129276-A1

**Status:** Complete shovel — family closed; parent saturation remains incomplete
**Date:** 2026-07-18
**Parent:** Global patent saturation ledger (incomplete)

## Entry facts

- Family ID: `86240812`
- Distinct root / publication: `US-20260129276` / `US-20260129276-A1`
- Application: `19/439370`
- Title: `COMPACT DOUBLE FOLDED TELE CAMERAS`
- First inventor: `Goldenberg; Ephraim`
- Applicant/assignee identity: `Corephotonics Ltd.`
- Raw HTML: `data/patent-lake/uspto-ppubs-html/US-PGPUB/6ba8e50cc7143544/US-20260129276-A1.html`
- Raw bytes / SHA-256: `92723` / `6ba8e50cc7143544b238cab4cb0aa74be777228a2795532b4d1be529aacba0fb`
- Normalized characters / SHA-256: `73487` / `cb7ae6ada4fc16336ff8e5fe0429455e4d016d3db4fa581e6beb944032964c43`
- Layout signature: `66e3492e7c1eca35e349bfca7afb05c37ed6dedd620ac31ec71e736faad49155`
- Existing replay attempt: `attempt-0001`, root state `parser_review_required`, item reason `parser_review_required.deterministic_parser_rejected`, detail `PatentParseError: embodiment f/Fno/HFOV line not found`; no conversion artifact.
- Entry marker scan: EFL=62, embodiment=1, example=5, F-number=27, full-field=7, half-field=10, queue table count=13. Marker counts and the generic-parser rejection are routing signals only, not proof that any source item is complete or representable.
- Frozen pre-change generic residual: 77 roots/items, result set `12c3080c61c9de456501a0c92126a2bee874fda912582d4bf991156cc1103a01`; the frozen census will be copied verbatim from the preceding committed after-census.

## Objective

Independently reconcile the retained official publication, continuation/PCT/provisional lineage, every folded-camera architecture and every disclosed lens prescription; bind each source item to its own exact surface/material/asphere/system-metadata tables and folded-path semantics; encode only source-complete deterministic conversions or precise terminal/nonterminal states; and close the family with append-only replay and full-ledger audit evidence while preserving all global saturation invariants.

## Work plan

- [x] Open this GSD quick before any family edit and record the exact entry snapshot.
- [x] Freeze the current 77-family generic residual census byte-for-byte.
- [x] Reconcile bibliographic identity, related applications, section/paragraph/claim denominators, declared figures, table objects, equations and every source-disclosed camera/lens item from retained official sources.
- [x] Establish the complete document/page/figure/table/example/item denominator without using “recognized prescriptions” as the denominator.
- [x] Bind every numerical lens only to its directly published ordered surface rows, materials, aspheres, stop, EFL, F-number, field and image height; preserve signed folded-path data exactly and never synthesize a coordinate transform or repair a source value.
- [x] Inspect official PDF/original raster evidence only where needed to resolve layout or printed-token ambiguity; never enhance, measure drawing geometry or infer a numeric cell.
- [x] Add the narrowest exact parser/classifier support and focused regression tests only after source reconciliation; do not change generic heuristics, scoring or redline criteria.
- [x] Replay append-only twice under the frozen 180-second worker / 1,500-second patent budgets, compare canonical business semantics under only explicit runtime normalization, audit all 619 roots and rebuild the after generic census twice.
- [x] Refresh only live shared-ledger pointers required by deterministic tests while preserving historical snapshots.
- [x] Run focused/full patent tests, guard tests, compile/Ruff, JSON/evidence/output/contamination audits, strict corruption audit, CODE V inventory, primary-repository cleanliness and diff review.
- [x] Update STATE and decisions evidence, mark this quick complete, and commit this family shovel atomically before selecting the next residual family.

## Closure evidence

- Exact official `US-20260129276-A1` reconciles application `19/439370`, Family ID
  `86240812`, paragraphs 1-194, claims 1-21 in two independent groups, 22 declared
  figure panels, 13 flattened tables, eight MathML objects and seven disclosed lens
  systems (`300`, `320`, `350`, `400`, `500`, `600`, `700`). All paragraph, claim,
  figure, table, equation and item denominators close with zero unmapped objects.
- Systems 300/320/350/400/500/700 bind exact published surface/material/asphere rows,
  direct EFL/F-number/HFOV metadata and deterministic stop ordering. Their six staging
  ZMX candidates remain pending intake only. System 600 publishes Q0-Q7 values but
  defines only Q0-Q5, so it closes precisely as
  `metadata_unpublished.qcon_q6_q7_basis_definitions_absent`. TABLE 1 conflicts for
  systems 400/500 remain disclosed and unrepaired; directional cut apertures are not
  synthesized into the axisymmetric ZMX representation.
- The retained 1,788,858-byte official PDF has 29 image-only pages, 13 drawing sheets,
  eight table pages and two claim pages. All 29 original decoded rasters reconcile at
  set hash `b57c80f63456407146f29885f970c95fecb0c4efcb42ab7558e7607ec725d9c5`;
  page 21's exact 2550×3300 exception is preserved. Contact and
  original-page review used no enhancement, drawing measurement or numeric inference.
- Append-only attempts 2/3 are business-semantic-equal at
  `c6fcde14a6e59fab93d97fd52f543ee28fb70983e7bb88e0705457d8b61d6061`;
  all request, response, candidate, stdout, stderr and final ZMX hashes agree. Generic
  residual falls 77→76 and both after censuses are byte-identical at
  `2895f26d21f9b32fec366f82707599ae0fb651cef970191d5be81c9043a6d2fc`.
  Strict replay is 619/619 with missing=0, corrupt=0 and result set
  `2fd10d202f3eff06d47e99656510d7eb0035c61a0afd161b788247a450a649a4`.
- Focused tests pass 9/9; complete `tests/test_patent_to_zmx.py` passes 730/730;
  the remaining patent suite passes 94/94 and the offline launch guard passes 5/5.
  The complete offline repository set passes 3,479 tests with one skip and ten
  `real_machine` deselections. One earlier unfiltered sweep was invalid as an offline
  gate: its only six failures were `real_machine` tests rejected by the stale-lock
  guard before engine startup; the corrected `not real_machine` sweep passed and CODE V
  inventory remained zero.
- Compile and Ruff pass; 96 changed/active JSON files parse; 76 source-evidence
  manifests rehash 1,012 path/SHA references including 861 complete path/byte/hash
  triples. Forty-six prior manifests refresh 92 shared summary/report records, and
  three explicitly live result-set fields align while historical frozen facts remain
  unchanged. Formal-output contamination and scorer/redline changes are zero; scoped
  non-ZMX `git diff --check` passes. The generated candidate/staging ZMX blobs retain
  their writer-emitted trailing blanks byte-for-byte because receipts and evidence hash
  those exact artifacts. The primary repository is clean. Source-evidence SHA-256 is
  `7c8fa33865c450fcf47ddfc0c66f2808b0b310407848ac3c06223c30aa114258`.
- Stable queue ordering selects Family `78957411`, root `US-20250130396`, publication
  `US-20250130396-A1` next. Global saturation remains incomplete.

## Safety constraints

- Never start, control or terminate CODE V; inventory must remain zero.
- Original retained source only. No drawing measurement, image enhancement, coordinate synthesis, convention repair or related-family numeric borrowing.
- Folded-path signs, mirrors and OPFE placement are source facts, not an authorization for an AI-generated coordinate transform.
- F-number, field, image height and stop position are prescription-specific required metadata; do not derive a missing value from another published quantity.
- The global patent saturation goal remains incomplete after this family closes.
