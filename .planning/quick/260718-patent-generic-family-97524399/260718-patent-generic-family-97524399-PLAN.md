# Quick Plan: Patent generic family 97524399 / US-20260147219-A1

**Status:** Complete — family shovel closed; parent saturation remains incomplete
**Date:** 2026-07-18
**Parent:** Global patent saturation ledger (incomplete)

## Entry facts

- Family ID: `97524399`
- Distinct root / publication: `US-20260147219` / `US-20260147219-A1`
- Application: `19/052311`
- Title: `OPTICAL LENS ASSEMBLY AND ELECTRONIC DEVICE`
- Applicant: `NEWMAX TECHNOLOGY CO., LTD.`
- First inventor in normalized source front matter: `HUANG; Ching-Yun`
- Queue assignee field: `null`; assignee identity, if any, must be reconciled from the retained source rather than inferred from applicant identity.
- Raw HTML: `data/patent-lake/uspto-ppubs-html/US-PGPUB/08078faa3d16975e/US-20260147219-A1.html`
- Raw SHA-256: `08078faa3d16975e12990aad5bcfbd922e0d95b0263040261b19a2e6d06abf72`
- Layout signature: `5cd8602188b9adf5b9fa961372643148bc385ce0e8bea064d788c91b283bc75a`
- Existing replay attempt: `attempt-0001`, root state `parser_review_required`, item reason `parser_review_required.deterministic_parser_rejected`, detail `PatentParseError: embodiment f/Fno/HFOV line not found`; no conversion artifact.
- Entry marker scan: EFL=6, embodiment=69, F-number=0, full-field=32, half-field=0, 24 HTML tables. Marker counts are routing signals only, not a terminal classification.

## Objective

Independently reconcile the retained official publication source and every disclosed optical design/item for this family, determine whether the 24 tables contain exact reconstructible prescriptions and whether required metadata is directly published, encode only evidence-supported conversions or terminal states, and close the family with deterministic replay/audit evidence while preserving all global saturation-ledger invariants.

## Work plan

- [x] Freeze the current 84-family generic residual census and record the exact entry snapshot.
- [x] Reconcile bibliographic identity, application/priority lineage, claims, sections, equations, figures, all 24 tagged tables and every disclosed embodiment directly from the retained source.
- [x] Establish the complete document-item denominator and map each prescription/table pair to its own directly published EFL, F-number, field and image-height/stop metadata without deriving or borrowing values.
- [x] Inspect official PDF/original raster evidence only where needed to resolve source layout or printed-token ambiguity; never enhance, measure geometry or repair a numeric cell.
- [x] Add the narrowest exact parser/classifier support and focused regression tests only after full source reconciliation; do not change generic heuristics or scoring/redline criteria.
- [x] Replay append-only twice, compare canonical semantics under only explicitly permitted runtime normalization, audit all 619 roots and rebuild the after generic census twice.
- [x] Refresh only live shared-ledger pointers required by deterministic tests while preserving historical snapshots.
- [x] Run focused/full patent tests, guard tests, compile/Ruff, JSON/evidence/terminal/converted-output/contamination audits, corruption audit, CODE V process inventory, primary-repository cleanliness and diff review.
- [x] Update STATE and decisions evidence, mark this quick complete, and commit this family shovel atomically before selecting the next residual family.

## Closure evidence

- Six exact folded three-lens prescriptions terminate as `metadata_unpublished.system_f_number_absent`; the electronic-device wrapper terminates as `confirmed_no_prescription.electronic_device_wrapper_only`.
- Append-only attempts 2/3 are semantically equal after removing only `result_attempt`, at `d13a65dcb22383deb47631f61e3443d892fc8f9d1c2a3adf82da9d46856176a3`.
- Strict replay is 619/619 with missing=0 and corrupt=0; generic residual is deterministically 83 roots/items and `saturation_complete=false`.
- Focused/file sweep passed 676/676; remaining patent suite passed 94/94; saturation guard passed 10/10; compile and Ruff passed.
- 52 changed JSON files parse; 69 evidence manifests rehash 881 path/hash references; terminal invariants are 42 null formal fields and 14 empty coverage maps; formal contamination and CODE V inventory are zero; the primary repository is clean.

## Safety constraints

- Never start, control or terminate CODE V; inventory must remain zero.
- Original retained source only. No drawing measurement, image enhancement, coordinate synthesis, convention repair or related-family numeric borrowing.
- F-number, field, image height and stop position are prescription-specific required metadata; do not derive a missing value from another published quantity.
- The global patent saturation goal remains incomplete after this family closes.
