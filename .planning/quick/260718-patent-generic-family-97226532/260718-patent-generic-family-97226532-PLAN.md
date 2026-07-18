# Quick Plan: Patent generic family 97226532 / US-20260063870-A1

**Status:** Complete
**Date:** 2026-07-18
**Parent:** Global patent saturation ledger (incomplete)

## Entry facts

- Family ID: `97226532`
- Distinct root / publication: `US-20260063870` / `US-20260063870-A1`
- Application: `19/085529`
- Title: `IMAGING LENS SYSTEM`
- First inventor: `KIM; Hyuk Joo`
- Applicant / assignee: `Samsung Electro-Mechanics Co., Ltd.`
- Raw HTML: `data/patent-lake/uspto-ppubs-html/US-PGPUB/200d56a3a5dbf491/US-20260063870-A1.html`
- Raw bytes / SHA-256: `85686` / `200d56a3a5dbf4913e37af18d64f3ea90dbf8c9e738cd9fb93af19a316a16b34`
- Layout signature: `5f11500ac688fb1ba38deecf30caca4a22d401f4e9cca2a81c5795ec8dffcec0`
- Existing replay attempt: `attempt-0001`, root state `parser_review_required`, item reason `parser_review_required.deterministic_parser_rejected`, detail `PatentParseError: embodiment f/Fno/HFOV line not found`; no conversion artifact.
- Entry marker scan: EFL=0, embodiment=14, example=0, F-number=1, full-field=1, half-field=0, 17 HTML tables. Marker counts are routing signals only, not a terminal classification.

## Objective

Independently reconcile the retained official publication source and every disclosed optical design/item for this family, determine whether the 17 tables contain exact reconstructible prescriptions and whether required prescription-specific metadata is directly published, encode only evidence-supported conversions or terminal states, and close the family with deterministic replay/audit evidence while preserving all global saturation-ledger invariants.

## Work plan

- [x] Freeze the current 83-family generic residual census and record the exact entry snapshot.
- [x] Reconcile bibliographic identity, application/priority lineage, claims, sections, equations, figures, all 17 tagged tables and every disclosed embodiment directly from the retained source.
- [x] Establish the complete document-item denominator and map each prescription/table pair to its own directly published EFL, F-number, field, image-height and stop metadata without deriving or borrowing values.
- [x] Inspect official PDF/original raster evidence only where needed to resolve source layout or printed-token ambiguity; never enhance, measure geometry or repair a numeric cell.
- [x] Add the narrowest exact parser/classifier support and focused regression tests only after full source reconciliation; do not change generic heuristics or scoring/redline criteria.
- [x] Replay append-only twice, compare canonical semantics under only explicitly permitted runtime normalization, audit all 619 roots and rebuild the after generic census twice.
- [x] Refresh only live shared-ledger pointers required by deterministic tests while preserving historical snapshots.
- [x] Run focused/full patent tests, guard tests, compile/Ruff, JSON/evidence/output/contamination audits, corruption audit, CODE V process inventory, primary-repository cleanliness and diff review.
- [x] Update STATE and decisions evidence, mark this quick complete, and commit this family shovel atomically before selecting the next residual family.

## Safety constraints

- Never start, control or terminate CODE V; inventory must remain zero.
- Original retained source only. No drawing measurement, image enhancement, coordinate synthesis, convention repair or related-family numeric borrowing.
- F-number, field, image height and stop position are prescription-specific required metadata; do not derive a missing value from another published quantity.
- The global patent saturation goal remains incomplete after this family closes.
