# Quick Plan: Patent generic family 75907839 / US-12554102-B2

**Status:** Complete — family shovel closed; parent saturation remains incomplete
**Date:** 2026-07-18
**Parent:** Global patent saturation ledger (incomplete)

## Entry facts

- Family ID: `75907839`
- Distinct root / publication: `US-12554102` / `US-12554102-B2`
- Application: `18/460957`
- Prior publication: `US-20240004164-A1`
- Title: `Imaging lens system`
- First inventor: `Son; Ju Hwa`
- Applicant / assignee: `SAMSUNG ELECTRO-MECHANICS CO., LTD.`
- Raw HTML: `data/patent-lake/uspto-ppubs-html/USPAT/03f007e37ed2e5c5/US-12554102-B2.html`
- Raw bytes / SHA-256: `70522` / `03f007e37ed2e5c5c084d2f9caede96ec14592a23210cef7f61eb98d52e382c1`
- Layout signature: `65e7c81fcc86ef80c27964ce0ad0b130d49758908f927a1e90865d67c560f659`
- Existing replay attempt: `attempt-0001`, root state `parser_review_required`, item reason `parser_review_required.deterministic_parser_rejected`, detail `PatentParseError: embodiment f/Fno/HFOV line not found`; no conversion artifact.
- Entry marker scan: EFL=0, embodiment=0, example=0, F-number=4, full-field=8, half-field=0, 12 HTML tables. Marker counts are routing signals only, not a representability conclusion.
- Frozen pre-change generic residual: 80 roots/items, result set `ae553b4e9a655f7e2143a67d762b008e8b46eae3a169acffc1f4578269a4159e`; the frozen census will be copied verbatim from the preceding committed after-census.

## Objective

Independently reconcile the retained official grant source, its prior publication lineage and every disclosed optical design/item for this family, determine whether the 12 tables contain exact reconstructible prescriptions and directly published prescription-specific EFL, F-number, field, image-height and stop metadata, encode only evidence-supported conversions or terminal states, and close the family with deterministic replay/audit evidence while preserving all global saturation-ledger invariants.

## Work plan

- [x] Freeze the current 80-family generic residual census and record the exact entry snapshot.
- [x] Reconcile bibliographic identity, continuation/priority lineage, claims, sections, equations, figures, all 12 tagged tables and every disclosed embodiment directly from retained official sources.
- [x] Establish the complete document-item denominator and distinguish independent optical prescriptions from device/module wrappers without collapsing source items.
- [x] Map any prescription only to its own directly published ordered surfaces, materials, aspheres, stop, EFL, F-number, field and image-height metadata; do not derive, repair or borrow missing values.
- [x] Inspect official PDF/original raster evidence only where needed to resolve source layout or printed-token ambiguity; never enhance, measure geometry or repair a numeric cell.
- [x] Add the narrowest exact parser/classifier support and focused regression tests only after full source reconciliation; do not change generic heuristics or scoring/redline criteria.
- [x] Replay append-only twice, compare canonical semantics under only explicitly permitted runtime normalization, audit all 619 roots and rebuild the after generic census twice.
- [x] Refresh only live shared-ledger pointers required by deterministic tests while preserving historical snapshots.
- [x] Run focused/full patent tests, guard tests, compile/Ruff, JSON/evidence/output/contamination audits, corruption audit, CODE V process inventory, primary-repository cleanliness and diff review.
- [x] Update STATE and decisions evidence, mark this quick complete, and commit this family shovel atomically before selecting the next residual family.

## Closure evidence

- The exact source denominator is five optical prescriptions, description paragraphs 1-75, claims 1-5 with claim 1 independent, FIGS. 1-10, TABLES 1-12 and one MathML object. Each prescription publishes S1-S19, nine material rows, S1-S16 K/A-J aspheres, and direct per-example `f`, F-number, IMGHT, full FOV and TTL metadata.
- Example 1 prints an unnumbered standalone stop marker between S6 and S7 without a radius, thickness or published axial split, so it closes as `metadata_unpublished`. Examples 2-5 print the stop directly in S5 and are exactly reconstructed without coordinate synthesis or source repair.
- Under identical 180-second worker and 1,500-second patent budgets, examples 2/3 are receipt-backed `trace_timeout`, example 4 produces one staging candidate pending intake, and example 5 is receipt-backed `trace_failed`. Source IMGHT remains distinct from traced/sanity values; formal intake remains zero.
- The retained 912,850-byte official PDF has 20 image-only pages, ten drawing sheets and five table pages; all page rasters reconcile at `60e5e5276326d245f3c45d5ad0614a7a8510e0a479120aea91f965aa65eaa97e`. No enhancement, geometry measurement or raster numeric transcription occurred.
- Append-only attempts 2/3 are business-semantic-equal at `353f276808ab14acfb8cd9e4b81e4521eb6d496cfe4283d0ad4db59965d46340`. Requests, responses, candidate/partial ZMX and stdout are byte-identical; example 3's second timeout stderr contains one additional duplicated warning pair and the runtime PID evidence naturally differs, both explicitly retained as diagnostic-only differences.
- Strict replay is 619/619 with missing=0 and corrupt=0. Generic residual is 80→79 roots/items; both after-census files are byte-identical at `fc6daa2a90d18aa62bba2a7f2c8afb57fe50a37fe3ae32a484ddd740b3c77276`, and the result set is `95b6f817d78a357f8c1c7bbfbb627117fc7bd81773dd947d440a2f0c42606702`.
- Focused tests pass 7/7, complete `tests/test_patent_to_zmx.py` passes 705/705, the remaining patent suite passes 94/94 and combined guard suite passes 16/16. Compile and Ruff pass.
- All 76 changed/current-worker JSON files parse; 73 source-evidence manifests rehash 800 complete path/byte/hash references; 62 worker/result evidence files rehash; the deterministic result pair retains six null conversion fields and two empty coverage maps. Four-scope formal contamination, diff checks and CODE V inventory are zero; the primary repository is clean.
- Forty-three prior source-evidence files refresh 86 shared summary/report records; three explicit live result-set pointers are aligned while historical census/replay snapshots remain fixed. Stable queue ordering selects Family `21816074`, root `US-4249805`, publication `US-4249805-A` next; global saturation remains incomplete.

## Safety constraints

- Never start, control or terminate CODE V; inventory must remain zero.
- Original retained source only. No drawing measurement, image enhancement, coordinate synthesis, convention repair or related-family numeric borrowing.
- F-number, field, image height and stop position are prescription-specific required metadata; do not derive a missing value from another published quantity.
- The global patent saturation goal remains incomplete after this family closes.
