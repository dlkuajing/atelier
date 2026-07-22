# Family 97520240 exact-source audit

## Identity and lineage

The retained classification source is the exact official USPTO A1 HTML for
`US-20260110880-A1` (application `19/209987`, Family ID `97520240`). It names
Seon Ho Ryu, Hag Chul Kim and Byung Hyun Kim as inventors and Samsung
Electro-Mechanics Co., Ltd. as both applicant and assignee. The header and
paragraph `[0001]` directly identify Korean application `10-2024-0145051`, filed
2024-10-22, as the sole printed priority record. The US application was filed
2025-05-16 and published 2026-04-23. No unprinted continuation, counterpart or
numeric disclosure was inferred or borrowed.

## Complete source denominator

The exact A1 contains 24 Background/Summary paragraphs (`[0001]-[0024]`), ten
brief-drawing paragraphs (`[0025]-[0034]`), 95 detailed-description paragraphs
(`[0035]-[0129]`), 19 claims, 17 flattened tables, 25 MathML objects, 22
`figref` tags and nine declared figures/drawing sheets. Claims 1 and 11 are the
independent claims; claims 10 and 19 are electronic-device claims that expressly
depend on claims 1 and 11. The HTML contains no native `table` element: all 17
source tables are flattened text blocks owned by paragraphs `[0096]`, `[0105]`,
`[0114]`, `[0123]` and `[0124]`.

The detailed disclosure resolves to exactly five disjoint source items:

1. First imaging-lens-system embodiment 100: `[0087]-[0096]`, FIGS. 1-2,
   TABLES 1-3.
2. Second imaging-lens-system embodiment 200: `[0097]-[0105]`, FIGS. 3-4,
   TABLES 4-6.
3. Third imaging-lens-system embodiment 300: `[0106]-[0114]`, FIGS. 5-6,
   TABLES 7-9.
4. Fourth imaging-lens-system embodiment 400: `[0115]-[0123]`, FIGS. 7-8,
   TABLES 10-12.
5. Electronic-device/camera-module wrapper: `[0126]-[0127]`, FIG. 9. It may
   contain any of systems 100-400 but publishes no additional prescription.

Paragraphs `[0035]-[0086]` are shared terminology, conditional expressions,
asphere convention and system architecture. Paragraphs `[0124]-[0125]` publish
shared system values and conditions for the four optical items; `[0128]-[0129]`
are closing paragraphs. None is an additional source item.

## Prescription content and missing metadata

TABLES 1, 4, 7 and 10 each directly publish ordered rows S1-S20. S1-S3 form
the first prism/lens and reflective path, S4-S17 form the remaining seven lens
elements, S18-S19 are the filter and S20 is the imaging plane. S8 is directly
labelled `(Stop)` in all four surface tables. TABLES 2, 5, 8 and 11 bind `K`
plus rows `A-H/J/L-P` to sixteen surfaces S1, S3-S17. TABLES 3, 6, 9 and 12
publish the two source-labelled Telephoto/wide D1 and D2 states. The four
optical items therefore contain 80 ordered surface rows, 64 asphere surfaces,
960 directly published conic-plus-coefficient cells and eight directly
published axial states.

TABLE 13 directly publishes, per embodiment, TTL, focal length, f number and
ImgHT. The four direct focal lengths are all `22.474` mm; the direct f numbers
are `2.157`, `2.175`, `2.145` and `2.107`; the direct image heights are all
`5.720` mm. These strings are retained exactly from the official HTML and are
not recomputed.

The exact text contains no `field of view`, `FOV`, `HFOV`, `angle of view`,
`angular field` or `field angle` occurrence and publishes no numeric angular
field for any embodiment. No field is derived from focal length and ImgHT.
Thus embodiments 1-3 terminate as
`metadata_unpublished.system_angular_field_absent`.

TABLE 10 additionally leaves the Thickness/Distance cells for S18, S19 and S20
blank. The official original page 22 confirms those are printed blank cells;
no raster value is transcribed and no value is copied from TABLES 1, 4 or 7.
The fourth item therefore terminates more precisely as
`metadata_unpublished.system_angular_field_and_final_axial_distances_absent`.
The wrapper terminates as
`confirmed_no_prescription.electronic_device_wrapper_only`.

## Official PDF audit

Two independent official downloads are both 1,246,229 bytes but have distinct
container SHA-256 values. Each has 24 pages, one 1-bit raster per page and no
text layer. All 24 decoded page rasters are identical across both downloads and
the pinned first download; their ordered raster-set SHA-256 is
`6fafdb8ce988060a913ef4770ca29db5f6768d33990e4e6fc9fed0c840b404ca`.
Pages 13-16 are 2550x3300; all other pages are 2560x3300.

The cover is page 1, drawings FIGS. 1-9 are pages 2-10 and the specification is
pages 11-24, with claims on page 24. The retained PNGs are lossless RGB
expansions whose pixels equal the decoded embedded page samples. A contact
sheet was used only for navigation. Original pages 17, 22, 23 and 24 were
reviewed for surface/asphere-table, printed-blank, shared-table/wrapper and
claim boundaries. No enhancement, OCR, OCR repair, drawing measurement, plot
sampling, raster inference or numeric transcription was used.

## Source-bound outcome

The reversible exact-source boundary is four metadata-unpublished optical
items plus one confirmed-no-prescription wrapper. No conversion worker,
request, receipt, prescription fingerprint, candidate ZMX, staging ZMX, formal
intake or CODE V call is authorized by this source audit.

The exact classifier now enforces the raw and normalized source hashes,
bibliography and lineage, all section and paragraph-span hashes, figure/table/
MathML/claim denominators, the four S1-S20 surface-table payloads, the four
S1/S3-S17 asphere-table payloads, all D1/D2 state rows, direct TABLE 13 values,
the printed blank TABLE 10 S18-S20 axial cells, angular-field phrase absence and
the pinned PDF raster set. Any exact-source drift closes all five items with
`PatentParseError`; no generic heuristic, score, physical gate or protected
redline changed.

Append-only attempts 2 and 3 are business-semantics identical at
`5ed70937f280ab62db85c98e0602c03bdc0f2fed41e02bfa3a2066d4f2ad73c9`.
Strict replay remains 619/619 with no missing or corrupt result, generic residual
falls from 28 to 27, and the new result set is
`843699ac02589c748683ce5202fda6c78e0669b4cc2a568c3c39e33f1c337c6e`.
The two after censuses are byte-identical at
`dcf3b26e23e841ba5275abdfbc6d6d40935ce10ecf3712eec7c7d499b5d2d3e9`.
Stable ordering selects Family 86539672 / US-20240352227-A1 next; global
saturation remains incomplete.
