# Family 71123577 source audit

## Identity and publication boundary

- The frozen cohort contains root `US-11137579`, publication `US-11137579-B2`,
  application `16/675251`, and Family ID `71123577`. The exact B2 identifies AAC
  Optics Solutions Pte. Ltd. and Chinese priorities `201811614499.X` and
  `201811616005.1`, both dated 2018-12-27.
- `US-20200209559-A1` is the same-application prior publication but is outside the
  frozen 619-root cohort. JP, WO, and the Chinese priority publications/grants are
  also queued outside the cohort. Their metadata and rasters are cross-check evidence
  only; no external numeric value is borrowed into the B2 parser.

## Complete B2 source denominator

The exact raw and normalized hashes bind Background paragraphs 1-2,
drawing-description paragraphs 1-13, detailed-description paragraphs 14-94,
claims 1-19, FIGS. 1-12, one inline formula lead/tail pair, zero MathML elements,
and TABLES 1-13. There are exactly three seven-lens prescriptions and no separate
device-wrapper source item.

TABLES 1/5/9 contain Stop plus R1-R16, TABLES 2/6/10 contain fourteen conic plus
A4-A16 rows, TABLES 3/7/11 contain inflexion-point data, TABLES 4/8/12 contain
arrest-point data, and TABLE 13 contains the direct system and condition values.
Each parser model has 18 ordered surfaces after adding the image row; each source
table itself publishes 17 rows. Across the three embodiments this is 51 published
rows, 54 modeled surfaces, 42 asphere surfaces, and 336 coefficient cells.

The direct `(EFL, FNO, full FOV, entrance pupil, image height)` tuples are
`(4.065, 1.78, 75.99, 2.88, 4.000)`,
`(3.872, 1.78, 82.89, 2.175, 3.715)`, and
`(3.720, 1.78, 85.18, 2.090, 3.715)`. Full FOV is halved only for the parser's
explicit HFOV field. The published Stop distances `-0.330`, `-0.295`, and
`-0.224` mm are retained with their signs. The d1-d16 sums `5.760`, `5.635`, and
`5.699` mm are derived validation checks only: the B2 publishes TTL bounds, not
an exact TTL value, so those sums are never promoted to direct metadata.

## Frozen source anomalies

- TABLE 1 prints the fourth-lens Abbe marker as Latin `v`; all other material rows
  use Greek `ν`. The exact parser preserves that one-token distinction.
- TABLE 13 visually splits `(R13 + R14)/(R13 - R14)` around the three numeric
  values. The parser follows the source order instead of repairing the layout.
- Detailed paragraph 47 says that the seventh-lens focal length is `P`, while the
  immediately following condition uses `f7/f`. The typo is locked as source evidence
  and is not repaired.
- The direct material sequence is Plastic, Plastic, Plastic, Plastic, Plastic,
  Glass, Plastic, then filter GF. All refractive indices are explicitly d-line `nd`
  values.

## PDF closure

Two independent USPTO B2 downloads and the Google B2 wrapper contain 16 pages.
Their container hashes differ, but all 16 decoded page rasters agree. Page 1 is the
cover, pages 2-8 are seven drawing sheets containing FIGS. 1-12, and pages 9-16 are
specification sheets. Tables occupy PDF pages 11-15; B2 claims 1-19 begin on page 15
and end on page 16.

The same-application A1 official and Google wrappers contain 17 pages and agree on
all 17 decoded rasters. Its tables occupy pages 11-15 and its 20 claims occupy pages
15-17. B2 and A1 have zero equal same-position rasters across the first 16 pages,
so page or value borrowing between publication wrappers is expressly prohibited.
Review used only the original decoded rasters: no enhancement, OCR repair, drawing
measurement, raster inference, or numeric transcription was used.

## Replay outcome

The source-locked parser recovers all three prescriptions with complete surface,
material, and asphere coverage. Two append-only process-isolated replays under the
180-second worker and 1,500-second patent budgets are semantically identical at
`961f0a409e5eddde096c826c0bfc475df8da53ed761003bbf8d03bd68d9c0af4`.
Requests, responses, candidate ZMX files, stdout/stderr, and staging ZMX files are
byte-identical between retries. The three items remain `converted_pending_intake`;
no formal intake or CODE V operation occurred. This is a reproducible conversion
result, not an expert optical-quality or production-acceptance judgment.
