# Family 81258214 source audit

## Identity and publication boundary

- The frozen cohort contains root `US-20220128799`, publication `US-20220128799-A1`,
  application `17/364492`, Family ID `81258214`, title `Optical lens`, inventor
  `CHEN; Jung-Yao`, and applicant `ABILITY ENTERPRISE CO., LTD.` No assignee is published.
- The application was filed 2021-06-30 and published 2022-04-28. It claims Taiwan priority
  `109137408` dated 2020-10-28. No related publication supplies a numeric value to this parser.
- The exact retained PPUBS HTML is 51,919 bytes at raw SHA-256
  `d3357394...ba8962`. Both the recovery normalization (`aa900faf...a33c`, 42,792
  characters) and parser normalization (`3893832b...43288`, 42,711 characters) are recorded.

## Complete source denominator

The specification has 66 continuous numbered paragraphs, with paragraphs 1-8 covering priority,
technical field, background and summary, and paragraphs 9-66 covering drawings and detailed
description. Claims 1-20 form three independent claim families at claims 1, 8 and 14. Those claims
constrain the same disclosed optical-lens structures and do not introduce a fifth numerical
prescription.

The brief description declares eleven panels: FIGS.1, 2, 3A, 3B, 4A, 4B, 5, 6, 7, 8 and 9.
Seven panels are printed numerical tables. FIGS.3A/3B disclose OL1, FIGS.4A/4B disclose OL2,
FIG.7 discloses spherical OL3, FIG.8 discloses spherical OL4, and FIG.9 directly publishes the
four systems' F, TTL, Fno, image height, full FOV, R1/R2 and redundant ratios. HTML contains no
formal table or image payload, so the printed drawing sheets are the only numerical table source.
Paragraph 39 contains one MathML asphere equation; OL1 and OL2 publish K=A2=0 and nonzero A4-A12
only, which the current even-asphere contract represents without synthesis.

The four direct `(F mm, Fno, full FOV, image height mm)` tuples are
`(2.07, 2.08, 160, 2.90)`, `(2.09, 2.02, 160, 2.90)`,
`(2.14, 2.05, 160, 2.90)` and `(2.13, 1.99, 160, 2.90)`. Full FOV is divided by two only for the
parser's explicit HFOV field. OL1/OL2 each retain 26 ordered rows, including stop, filter, cover
and image plane; OL3/OL4 each retain 28 because the eleventh lens is inserted after the third lens.
Every printed radius, thickness, refractive index, Abbe number and asphere coefficient remains in
the canonical 104,254-byte OCR JSON; none is measured from lens geometry.

The per-surface thickness sums differ from FIG.9 TTL by 0.020, 0.125, 0.060 and 0.090 mm. This is
within the deterministic maximum accumulated error from 25 or 27 values printed to 0.01 mm. The
parser checks that explicit rounding bound, rather than replacing any printed thickness or TTL.
FIG.9's independently printed R1/R2 values exactly match the first two prescription rows, and all
four printed relation rows agree with their operands within displayed precision.

## PDF and OCR closure

The official USPTO PDF is 886,635 bytes at SHA-256 `5266c4f2...2d438`. It has 15 pages and exactly
one 2560×3300 raster per page, with no text layer. Seven drawing sheets occupy pages 2-8; printed
tables are on pages 3, 4, 6, 7 and 8. The Google OCR PDF is 1,334,320 bytes at SHA-256
`b28a4118...4692`. All 15 decoded rasters are pixel-equal to the official PDF, with raster-set
SHA-256 `9f00ea45...db5`; only then is its 50,152-character text layer admitted as a second OCR view.

RapidOCR retains 194, 194, 180, 180 and 63 tokens on the five key pages. Low-confidence cells are
limited to the printed infinity glyph (deterministically read as `8`) and some zero/material values.
The new exact-source profile accepts those only on the 15-page raster denominator and requires
every non-infinity numerical token to appear in the independent same-raster overlay. Original
pages 3, 4, 6, 7 and 8 plus the contact sheet were visually reviewed without enhancement or
geometry measurement.

## Replay outcome

All four prescriptions pass `PatentSurfaceInput`, material, asphere, deterministic trace and
process-isolated ZMX validation. Attempts 2/3 are append-only. Result receipts differ only in
retry identity/path and elapsed time; after the recorded receipt normalization and semantic-hash
replacement, both results have SHA-256 `f2b85fee...a9f0`. All four candidate and staged ZMX hashes
are identical within and across the two attempts.

The root becomes `converted_pending_intake` with four distinct evidence-complete items. Generic
residual moves 90→89 roots/items; strict replay remains 619/619 with corrupt=0. This is an
engineering conversion result, not an expert production-acceptance judgment.
