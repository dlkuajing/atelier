# Quick Task: Patent Generic Family 90535253

**Status:** complete-shovel-saturation-incomplete
**Parent:** patent saturation engineering (active / incomplete)
**Started:** 2026-07-18
**Entry evidence:** committed Family 94732062 shovel at
`bdd68e9eee46c4cbde74a272b0cca983fb9342ed`; strict replay is 619/619 and
`generic_summary_metadata_missing` remains the largest executable bucket at 88 items / 88 roots.

## Objective

Resolve deterministic next Family ID `90535253`, root `US-20240118520`, publication
`US-20240118520-A1`, application `18/306676`, title `IMAGING LENS SYSTEM AND ELECTRONIC DEVICE
HAVING THE SAME`, first inventor `CHO; Yongsik` and applicant `SAMSUNG ELECTRONICS CO., LTD.`
Reconcile exact publication, application, priority/continuation and family identity plus every
source-disclosed imaging system, prescription, embodiment, example, variant, claim family, figure,
table and formula. Convert only complete directly published optical prescriptions representable by
the current contract; retain incomplete, unsupported, conflicted or metadata-missing designs
fail-closed without drawing transcription, coordinate synthesis or values borrowed from related
applications.

## Plan

1. [completed] Freeze the committed strict 619-root generic census; verify exact next-group
   selection and attempt-1 failure from repository/runtime facts.
2. [completed] Pin official source raw/normalized hashes, application/priority/publication/family identity,
   and complete section/paragraph/claim/figure/table/formula/disclosed-item denominators.
3. [completed] Reconcile all 21 tagged tables against every disclosed imaging-lens prescription and dependent
   variant; inspect exact official PDF/raster evidence only where it closes a source gap, never to
   infer coordinates or numeric cells.
4. [completed] Test every prescription against PatentSurfaceInput/ZMX representability, including ordered
   surfaces, stop, EFL, F-number, image height and angular field, before any worker runs.
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
  `50d77537d1a790ed464997f1b6f9d490417bc0b53440bfd788b44d48c66ebc91`, Family
  `90535253`, root `US-20240118520` and publication `US-20240118520-A1` next.
- Committed result set is
  `10b873228f5b8b9d5e64c8e435e17ffac4d71432eea96dff89270accbdab646c`;
  generic residual is 88 roots/items, ahead by root count of AAC Raytech 55 roots/174 items and
  Sunny 49 roots/177 items.
- Retained parser input is
  `data/patent-lake/uspto-ppubs-html/US-PGPUB/f72e752aba1ccbdb/US-20240118520-A1.html`,
  76,012 bytes, raw SHA-256
  `f72e752aba1ccbdb0fcc09e45ecd23dbea549b6d39f677ed0d466d21b2c7e96e`, with 21 tagged
  tables, ten effective-focal-length markers, five F-number markers, thirteen full-field markers
  and nineteen half-field markers measured by the committed queue.
- Attempt 1 is one document-level `parser_review_required.deterministic_parser_rejected` item
  with exact detail `PatentParseError: embodiment f/Fno/HFOV line not found`; no conversion
  attempt or formal output exists.

## Result

Exact `US-20240118520-A1` binds application `18/306676`, Family `90535253`, Samsung identity,
Korean priority `10-2022-0127936`, 100 consecutive numbered paragraphs, claims 1-20, nine
declared figures/ten panels, 21 numbered tables, one MathML object, three inline equations and
seven source items. Systems 100a-100d publish 66 ordered surface rows, 67 asphere rows and exact
EFL/Fno/HFOV/image-height metadata. Neither the HTML nor exact FIGS.1-5 publishes a stop or
diaphragm row, STO label or axial stop coordinate; Y Aperture is a per-surface effective aperture
and Fno does not determine a unique axial stop position. The four numerical items therefore become
metadata-unpublished. The generic seven-/eight-lens architectures and electronic-device/camera
wrapper become three confirmed-no-prescription terminals. No value is inferred from Fno, measured
from a raster, synthesized or borrowed from another family, and no formal output exists.

The retained 1,266,189-byte official PDF has 23 image-only pages, one raster per page and nine
drawing sheets on pages 2-10. All page rasters reconcile at
`1070dfce17cbf0502b108ea3a76235b467bd8d0fe37fd97bcff82a0712971429`; FIGS.1-5 and
representative table pages were reviewed at original resolution without enhancement. Attempts 2/3
are semantic-equal excluding only `result_attempt` at
`3c2aeb1c2c49f14ead9bec04a4c973e47833ae3577cf9fb502abb72e3187f38d`. Generic 88->87;
result set `1b9794864254687a10fc20b29307e6a071d1a3d0355c3674fd57c39911c73973`; summary
`68a05034a676e839c4211f6eb370af0e66a3b31775ac66d51bdf7d97feff7adb`; report
`e806c1dcefd155534ac5381a2dbce7fa3b130b6cfda3bfe89a0eb0cf6eaacd91`; after census
`367476a905eaca89aa388fff31ba060d742cb5490b0a966e177d82b5b4e7a670`. Strict audit is 619/619,
missing=0, corrupt=0.

Focused tests pass 9/9. The first full-file sweep passed 647/648 and exposed only Family 77292582's
single live-summary result-set pointer; targeted verification passed 2/2 after alignment and the
second full sweep passed 648/648. Remaining patent tests pass 94/94 and CODE V guard 5/5. Compile,
Ruff, 48 changed JSON, 65 evidence files/778 path-hash references, 42-null/14-empty-coverage and
four-scope formal-contamination checks pass; CODE V stays zero. All 35 prior shared summary/report
references were refreshed while historical result-set snapshots were preserved, except the one
explicit live pointer. Root-first ordering keeps generic ahead of AAC Raytech and Sunny and selects
Family `98695135`, `US-20260086429-A1`, next. Parent/global patent saturation remains active and
incomplete.
