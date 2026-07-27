# Quick Plan: Patent generic family 94658603 / US-20260118635-A1

**Status:** Complete — family shovel closed; parent saturation remains incomplete
**Date:** 2026-07-18
**Parent:** Global patent saturation ledger (incomplete)

## Entry facts

- Family ID: `94658603`
- Distinct root / publication: `US-20260118635` / `US-20260118635-A1`
- Application: `19/281010`
- Title: `OPTICAL LENS, IMAGE MODULE, AND TERMINAL DEVICE`
- First inventor: `LAN; Binli`
- Applicant: `Jiangxi OFLM Optical Co., Ltd.`
- Raw HTML: `data/patent-lake/uspto-ppubs-html/US-PGPUB/3fe547f20905b87a/US-20260118635-A1.html`
- Raw bytes / SHA-256: `131770` / `3fe547f20905b87a7b338b6c45437edcfe8bf5649d00e3e8bb28a2174fff9c60`
- Layout signature: `65033b8cec3386b0d135f137768209b81b14acd9e8c842c24f0f53c0d7c16652`
- Existing replay attempt: `attempt-0001`, root state `parser_review_required`, item reason `parser_review_required.deterministic_parser_rejected`, detail `PatentParseError: embodiment f/Fno/HFOV line not found`; no conversion artifact.
- Entry marker scan: EFL=76, embodiment=88, example=0, F-number=17, full-field=79, half-field=0, 13 HTML tables. Marker counts are routing signals only, not a representability conclusion.
- Frozen pre-change generic residual: 81 roots/items, result set `3b091362a87c21e0dc156f49c39c140e034b0775772ae9f288a730aba55dd518`; frozen census is copied verbatim from the preceding committed after-census.

## Objective

Independently reconcile the retained official publication source and every disclosed optical design/item for this family, determine whether the 13 tables contain exact reconstructible prescriptions and whether each prescription has directly published EFL, F-number, field, image-height and stop metadata, encode only evidence-supported conversions or terminal states, and close the family with deterministic replay/audit evidence while preserving all global saturation-ledger invariants.

## Work plan

- [x] Freeze the current 81-family generic residual census and record the exact entry snapshot.
- [x] Reconcile bibliographic identity, priority lineage, claims, sections, equations, figures, all 13 tagged tables and every disclosed embodiment directly from the retained source.
- [x] Establish the complete document-item denominator and distinguish independent optical prescriptions from image-module and terminal-device wrappers without collapsing source items.
- [x] Map any prescription only to its own directly published ordered surfaces, materials, aspheres, stop, EFL, F-number, field and image-height metadata; do not derive, repair or borrow missing values.
- [x] Inspect official PDF/original raster evidence only where needed to resolve source layout or printed-token ambiguity; never enhance, measure geometry or repair a numeric cell.
- [x] Add the narrowest exact parser/classifier support and focused regression tests only after full source reconciliation; do not change generic heuristics or scoring/redline criteria.
- [x] Replay append-only twice, compare canonical semantics under only explicitly permitted runtime normalization, audit all 619 roots and rebuild the after generic census twice.
- [x] Refresh only live shared-ledger pointers required by deterministic tests while preserving historical snapshots.
- [x] Run focused/full patent tests, guard tests, compile/Ruff, JSON/evidence/output/contamination audits, corruption audit, CODE V process inventory, primary-repository cleanliness and diff review.
- [x] Update STATE and decisions evidence, mark this quick complete, and commit this family shovel atomically before selecting the next residual family.

## Closure evidence

- The exact source denominator is 115 consecutive numbered paragraphs, 20 claims in three independent families, 14 declared figures, 13 tagged tables, 23 MathML objects and eight ledger items: six seven-lens prescriptions plus image-module and terminal-device wrappers.
- Each prescription publishes 19 ordered surface rows, stop placement, glass indices/Abbe values, S13/S14 K/A4-A16 coefficients, EFL, F-number and full FOV. Neither the official HTML nor all-page PDF raster denominator directly publishes absolute image height; TABLE 7 publishes ratios only, and none is used to derive the missing value. The six prescriptions therefore close as `metadata_unpublished`; the two wrappers close as `confirmed_no_prescription`.
- TABLE 3a's direct fourth-lens `nd=1.437`, `Vd=1.95` is retained verbatim under a distinct reason code despite lying outside the repository physical range. The malformed official asphere expression and paragraph-38 inequality are recorded without repair or numeric inference.
- The retained 2,006,772-byte official PDF has 28 image-only pages, seven drawing sheets, seven table pages and a decoded-raster-set SHA-256 of `84466d371fda110f132af84bc0ebc13fcef54cb6bed6782bafccb6a012b13651`; every page raster is retained at original resolution, with no enhancement, geometry measurement or raster numeric transcription.
- Append-only attempts 2/3 are semantic-equal after removing only `result_attempt`, at `207037f94bbba8c40f5a64c3c5ec4c810ee190609b815d8ecf23d58a49e23d18`. Conversion requests, receipts, fingerprints, staging ZMX and formal outputs remain zero.
- Strict replay is 619/619 with missing=0 and corrupt=0. Generic residual is 81→80 roots/items; the two after-census files are byte-identical at `534c7fab56f3223fbee4dcc9df22a8d6fb3f1fd5f8e35fec30ddc13fe690bd0c`, and the final result set is `ae553b4e9a655f7e2143a67d762b008e8b46eae3a169acffc1f4578269a4159e`.
- Focused tests pass 8/8, the complete `tests/test_patent_to_zmx.py` sweep passes 698/698, the remaining patent suite passes 94/94 and the no-real-CODE-V guard passes 5/5. Compile and Ruff pass.
- All 55 changed JSON files parse; 72 source-evidence manifests rehash 784 complete path/byte/hash references; the deterministic pair retains 48 null formal fields and 16 empty coverage maps; four-scope formal contamination, diff checks and CODE V inventory are zero; the primary repository is clean.
- Forty-two prior shared summary/report references and five explicit live result-set pointers were refreshed without changing historical census/replay snapshots. Stable queue ordering selects Family `75907839`, root `US-12554102`, publication `US-12554102-B2` next; global saturation remains incomplete.

## Safety constraints

- Never start, control or terminate CODE V; inventory must remain zero.
- Original retained source only. No drawing measurement, image enhancement, coordinate synthesis, convention repair or related-family numeric borrowing.
- F-number, field, image height and stop position are prescription-specific required metadata; do not derive a missing value from another published quantity.
- The global patent saturation goal remains incomplete after this family closes.
