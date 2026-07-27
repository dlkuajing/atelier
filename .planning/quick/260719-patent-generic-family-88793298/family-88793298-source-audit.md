# Family 88793298 source audit

## Identity and authority

The retained USPTO PPUBS publication is `US-20260153710-A1`, application
`19/424607`, Family ID `88793298`, titled *SLIM POP-OUT WIDE CAMERA LENSES
AND POP-OUT CAMERA ACTUATORS*. It names Goldenberg, Dror, Kowal, Grushka,
Boral and Goulinski as inventors and Corephotonics Ltd. as applicant. The
86,522-byte HTML is the content authority and is pinned at
`188dbb739fd8d71378d568a9d8d9d94dd06931b1c5ae9a0c7373836a4b31f36e`.
The application is a continuation of `19/117048`, which descends from
`PCT/IB2023/061327`; no numerical value was borrowed from a relative.

## Complete source denominator

The normalized publication contains paragraphs `[0001]` through `[0125]`
without a gap: 23 Background/Summary paragraphs, 25 drawing-description
paragraphs and 77 Detailed Description paragraphs. Claims are numbered 1-19,
with claim 1 the sole independent claim. Paragraphs 25-48 declare 24 panels:
FIGS. 1A-D, 2A-D, 3-7, 8A-C, 9A-C, 10A-B, 11A-B and 12. The HTML contains
11 `TABLE-US` objects and nine outer `<maths>` objects. Every section, item
span, table payload and MathML object is independently hashed in
`family-88793298-source-facts.json`.

The disclosed-item denominator is 11. It comprises generic one-group pop-out
lens system 250; five table-backed QT1 lens systems 300, 400, 500, 600 and
700; passive pop-out camera systems 800, 900, 1000 and 1100; and multiwire SMA
actuator 1200. Known-art camera 110 and known-art lens system 200 in
paragraphs 49-52 are mapped context, not inventions silently added to the
denominator. Paragraphs 57-59 and 121-125 are also mapped global/closing
context. Thus no paragraph, claim, figure, table, MathML object or disclosed
item is left unmapped.

## Prescription boundary

Tables 1/2, 3/4, 5/6, 7/8 and 9/10 publish five direct prescriptions. Together
they contain 101 ordered surface rows and 82 coefficient rows. Their direct
system metadata are respectively:

- system 300: EFL 11.58 mm, F/2.0, HFOV 41.35 degrees, explicit stop;
- system 400: EFL 11.51 mm, F/1.91, HFOV 43.91 degrees, explicit stop;
- system 500: EFL 11.53 mm, F/1.675, HFOV 41.862 degrees, explicit stop;
- system 600: EFL 11.256 mm, F/2.0, HFOV 42.9 degrees, explicit stop;
- system 700: EFL 8.78 mm, F/1.40, HFOV 38.33 degrees, no published stop row
  or stop coordinate.

Equation 1 and its following MathML objects define `Qcon` basis functions only
for Q0 through Q5. The coefficient tables publish non-zero terms through A9,
A10, A7, A11 and A7 respectively. No external Q-type convention is imported.
Tables 3/4 have a second independent defect: the source surface table itself
repeats printed surface indices 14/15 for lenses 8 and 9, so surface identity
cannot be repaired. System 700 also lacks a published system stop. These are
source metadata gaps, not generic parser limitations.

The resulting exact terminal classifications are:

- system 300: `metadata_unpublished.qcon_q6_q9_basis_definitions_absent`;
- system 400:
  `metadata_unpublished.qcon_q6_q10_basis_definitions_and_surface_index_mapping_absent`;
- system 500: `metadata_unpublished.qcon_q6_q7_basis_definitions_absent`;
- system 600: `metadata_unpublished.qcon_q6_q11_basis_definitions_absent`;
- system 700:
  `metadata_unpublished.qcon_q6_q7_basis_definitions_and_system_stop_absent`.

System 250 publishes a one-group pop-out architecture but no ordered radii,
spacings, materials or coefficients. Systems 800-1200 publish spring,
magnetic, gear, mirror and SMA actuator/camera packaging only. These six items
therefore receive their precise `confirmed_no_prescription` outcomes. No
conversion request, receipt, prescription fingerprint, candidate ZMX, staging
ZMX or formal intake item is created.

## Original-raster corroboration

Two official PDF fetches contain 1,827,604 bytes each but have distinct
container hashes. Each has 30 pages, one raster per page and no text layer;
all 30 decoded page records match exactly at
`00a8525f4a7e8dbac1d7c4da476e5377b121803772c046b27ba723809552721a`.
Pages 2-17 are drawing sheets, pages 18-30 are specification/claims, pages
21-27 contain the tables and page 30 contains the claims. Original retained
rasters for pages 1, 18, 20-27 and 30 were visually inspected. They corroborate
the layout, the Q0-Q5 definition boundary, the printed high-order columns, the
repeated Table 3 indices and the absent Table 9 stop. No enhancement,
measurement, OCR repair or numerical transcription was used; HTML remains
content authority. Exact records are in `family-88793298-raster-audit.json`.

## Replay and residual queue

Append-only attempts 2 and 3 each produce 11 terminal items and are
business-semantically identical after removing only `result_attempt`, at
`8c662b8973efcf734ab8d8aa126a661cd860c6e14d13f512a3af0318b5f2161a`.
Strict audit is 619/619 roots with zero missing or corrupt results. The generic
residual falls from 68 to 67 roots/items and both after censuses are byte
identical. Stable ordering selects Family `100208972`, root `US-12663617`,
publication `US-12663617-B2` next. Global patent saturation remains incomplete.
