# Quick Plan: Patent generic family 84322717 / US-12656584-B2

**Status:** Complete — family shovel closed; parent saturation remains incomplete
**Date:** 2026-07-18
**Parent:** Global patent saturation ledger (incomplete)

## Entry facts

- Family ID: `84322717`
- Distinct root / publication: `US-12656584` / `US-12656584-B2`
- Application: `18/526988`
- Title: `Imaging lens assembly, camera module and imaging device`
- First inventor: `Katsuragi; Daigo`
- Applicant: `GUANGDONG OPPO MOBILE TELECOMMUNICATIONS CORP., LTD.`
- Assignee: `GUANGDONG OPPO MOBILE TELECOMMUNICATION CORP., LTD.`
- Raw HTML:
  `data/patent-lake/uspto-ppubs-html/USPAT/4c49c1f0f7b88434/US-12656584-B2.html`
- Raw bytes / SHA-256: `134814` /
  `4c49c1f0f7b88434639b5ffddd557efe1333044a14517a802bf2d0388e6a38a5`
- Runtime `normalize_patent_text` characters / SHA-256: `113014` /
  `a769839300a2b2fa29467f2b6b308a0df1bc8743b54c4373d7480cbfeeb984a0`
- Layout signature:
  `6973e2ab4c8f6c7c0cdb8c11973deb0a1908fbf623deac3167e58eb0e1b1573a`
- Existing replay attempt: `attempt-0001`, root state `parser_review_required`, item
  reason `parser_review_required.deterministic_parser_rejected`, detail
  `PatentParseError: embodiment f/Fno/HFOV line not found`; no conversion artifact.
- Entry marker scan: EFL=0, embodiment=0, example=0, F-number=14, full-field=0,
  half-field=0, queue table count=45. These counts and the generic-parser rejection are
  routing observations only, not proof of a prescription or terminal outcome.
- Frozen pre-change generic residual: 75 roots/items, result set
  `0f8b7b951a365edc65a324ce5ab9349c5645e6d89b62a81d94406ff2025a0d8b`;
  the before census must be copied byte-for-byte from the committed Family 78957411
  after census.

## Objective

Independently reconcile the exact retained official publication, its application/family
lineage, every disclosed imaging-lens assembly, camera-module and imaging-device item,
all 45 table objects, formulas, claims, figures and source metadata; establish whether
each item publishes a complete ordered optical prescription and required system values;
encode only source-proven conversions or precise terminal/nonterminal states; then close
the family with append-only deterministic replay and full-ledger evidence while
preserving all global saturation invariants.

## Work plan

- [x] Open this GSD quick before any family edit and record the exact entry snapshot.
- [x] Freeze the current 75-family generic residual census byte-for-byte and record the
  single frozen root.
- [x] Reconcile bibliographic identity, application/family lineage, section/paragraph/
  claim denominators, declared figures, all 45 table objects, formulas and every
  source-disclosed assembly/module/device item from retained official sources.
- [x] Establish the complete document/page/figure/table/embodiment/item denominator
  without using “recognized prescriptions” or generic marker counts as the denominator.
- [x] Bind numerical surfaces, spacings, optical materials, aspheres and system metadata
  only to their directly published item; never infer missing values from drawings,
  ratios, product categories, related publications or general lens terminology.
- [x] Inspect official PDF/original raster evidence only where needed to resolve layout
  or printed-token ambiguity; never enhance, measure drawing geometry or infer a numeric
  cell.
- [x] Add the narrowest exact parser/classifier support and focused regression tests only
  after source reconciliation; do not change generic heuristics, scoring or redline
  criteria.
- [x] Replay append-only twice under the frozen 180-second worker / 1,500-second patent
  budgets, compare canonical business semantics under only explicit runtime
  normalization, audit all 619 roots and rebuild the after generic census twice.
- [x] Refresh only live shared-ledger pointers required by deterministic tests while
  preserving historical snapshots.
- [x] Run focused/full offline tests, guard tests, compile/Ruff, JSON/evidence/output/
  contamination audits, strict corruption audit, CODE V inventory, primary-repository
  cleanliness and staged diff review.
- [x] Update STATE and decisions evidence, mark this quick complete, and commit this
  family shovel atomically before selecting the next residual family.

## Closure evidence

- Exact B2 source reconciles application `18/526988`, prior publication
  `US-20240134168-A1`, PCT lineage, 170 numbered paragraphs, claims 1-13 in three
  independent families, 22 figure panels, 45 flattened tables, 31 inline formula
  pairs and five paired short/long examples: ten complete optical prescriptions.
- The ten prescriptions retain 138 ordered sequential surfaces, 88 asphere surfaces,
  directly published focal length, F-number, full field and 2.35 mm image height.
  Source `K=0` maps exactly to the repository/Zemax convention `K=-1`; all published
  odd A3-A19 coefficients remain zero. Mirrors stay material-free, and the published
  `Image Plane` row is represented as filter exit plus its terminal air gap and an
  appended zero-thickness image surface. No mirror aperture, 3-D coordinate or missing
  metadata is synthesized.
- Two source exceptions remain explicit and narrow: TABLE 32's surface-distance sum
  `38.457` differs from TABLE 34's rounded `ΣTd=38.56` by `0.103`, so the ordered
  surface distances are retained; Example 4's rounded rear radii in TABLES 28/32 have
  opposite signs from exact TABLES 31/35, so the exact coefficient-table radii govern
  only that allowlisted group. No source number is repaired arithmetically.
- The retained official B2/A1 PDFs contain 45/46 pages. All 45 primary original page
  rasters are retained at decoded-raster-set SHA-256
  `6d8c500d0d743a6f020b43e3cccef62176f681ca44fe00d8c20ce904276a72c7`;
  review used original resolution only, without enhancement, drawing measurement or
  raster numeric transcription.
- Append-only attempts 2/3 are semantic-equal at
  `b1ea4876a77ee4679565ae163eabd60a6da9411cb07a3d36dbe0f7869004acdc`
  after only recorded attempt identity/path/receipt-runtime normalization. All ten
  request, response, candidate ZMX, staging ZMX and empty stdout/stderr payloads are
  byte-equal. The root is `converted_pending_intake` with ten receipt-backed staging
  candidates and zero formal intake, expert-backed item or CODE V call.
- Strict replay is 619/619 with missing=0 and corrupt=0. Generic residual is 75→74
  roots/items; both after censuses are byte-identical at
  `b0b1599a256dfabd9dbc1aacebde31d946c1554ad904d2b518321cbdca4f5be8`,
  and result set is
  `ed561776087212b38801f262b725409b314ccf1b9cb1c2be86195ca58f1b21bb`.
- Focused Family 843 tests pass 8/8; the complete parser file passes 745/745; all other
  patent tests pass 94/94; the no-real-CODE-V guard passes 5/5. A non-overlapping full
  offline split covers the complete `not real_machine` collection at 3494 passed and
  one skipped, with ten `real_machine` tests deselected. Compile, Ruff and diff checks
  pass.
- All 61 changed JSON files parse; 78 source-evidence manifests rehash 1127 path/SHA
  references including 974 complete path/byte/SHA triples. Forty-nine live summary and
  forty-nine live report references align. Ten converted-output contracts, four-scope
  formal contamination, protected scorer/redline paths and primary-repository checks
  pass; CODE V inventory is zero.
- Stable queue ordering selects Family `63165840`, root `US-10197774`, publication
  `US-10197774-B1`, application `15/864483` next. Global saturation remains incomplete.

## Safety constraints

- Never start, control or terminate CODE V; inventory must remain zero. All repository
  sweeps must explicitly deselect `real_machine` tests.
- Original retained source only. No drawing measurement, image enhancement, numeric
  repair, derived prescription metadata or related-family borrowing.
- Table count, F-number markers and generic lens-assembly wording are not substitutes
  for a source-proven item denominator or complete ordered prescription.
- The global patent saturation goal remains incomplete after this family closes.
