# Family 95157884 source audit

## Identity, family scope, and frozen-cohort boundary

- The frozen root is `US-20250216652`, publication `US-20250216652-A1`, application
  `18/973352`, title `OPTICAL PHOTOGRAPHING LENS ASSEMBLY, IMAGING APPARATUS AND ELECTRONIC
  DEVICE`, and Family ID `95157884`. The publication was filed on 2024-12-09, published on
  2025-07-03, and claims priority from Taiwan application `113100162` filed on 2024-01-02.
  Largan Precision Co Ltd is applicant/assignee; the named inventors are Yeh Kuan-Ting, Chen
  I-Chieh, and Tsai Cheng-Yu.
- Google's narrow Family Applications table contains only US application `18/973352`. Its
  country-status and Also Published As metadata directly identify `CN120255132A`,
  `DE202024107550U1`, and `TW202528789A`; the priority-application link identifies later grant
  `TWI916734B`. None is a frozen US root. All four are retained in
  `family-95157884-external-family-members.json` and are not silently counted as complete here.
- The retained official PPUBS HTML SHA-256 is
  `a8ce8130d4420c435c79dffde20989df9035f1e32f2b2b19d01bb140ac55a018`; its parser-normalized
  SHA-256 is `70233e3a4c941838d0b20a08066a14a88b19cfe2e17c1c16ba47494736723c79`.
  The exact 39-table digests and all published mode metadata are in
  `family-95157884-source-evidence.json`.

## Complete source denominator

Embodiments 1-10 each disclose two optical states: a first, infinity-object mode and a second,
finite-object macro mode. They therefore map to ledger items 1-20 in alternating infinity/macro
order. Embodiment 11 is an imaging-apparatus wrapper; embodiments 12-15 are electronic-device or
smartphone wrappers. They map to items 21-25. The complete denominator is therefore 25 items, not
ten surface tables and not 15 headings.

The source contains exactly 39 suffixed tables:

- embodiment 1 has 1A/1B/1C;
- embodiments 2-10 each have A/B/C/D;
- A tables publish surfaces, B tables publish asphere coefficients, C tables publish both moving
  distances, and D tables publish both modes' `f`, F-number, HFOV, and FOV metadata;
- table 1C also carries embodiment 1 metadata, so no table 1D is absent from the source inventory.

The source-locked profile preserves every published number. It uses official raster pages only to
bind blank-cell occupancy in flattened B tables; numeric coefficient values come exclusively from
the retained PPUBS HTML. The official table 3C caption's literal `3th Embodiment` typo is likewise
bound rather than corrected.

## Official PDF denominator and source defect

Both independently fetched official wrappers contain 106 image-only pages with one image per page.
Their wrapper SHA-256 values differ—
`296ae37a3c8300df42b26beb249705d462acffcc2f1cd1fc6212e3c918d2b6da` and
`6609671cd8bca2612fb9e3386f6bccb44740f8392b7b7e69f634d5628892ea3e`—but all 106 decoded page
rasters are identical. The stable raster-set SHA-256 is
`5772b3fb3ab4f2ae7b433749e988084a9ca8aab854420ca3e4d0744d72dd9cba`.

Pages 2-63 are 62 drawing sheets. They disclose 64 panels: FIGS. 1-20 A/B; 21-23 A/B; 24;
25A/B/C; 26; 27; 28A/B; 29A/B/C; 30A/B; 31A/B/C; and 32A/B. Description begins on page 64.
The 39 source tables occupy 26 distinct wrapper pages from 73 through 100, with the exact
table-to-page mapping in `family-95157884-raster-audit.json`. OCR was used only to locate labels
and bind page numbers; no OCR-derived number enters a prescription.

Official wrapper page 96 proves TABLE 9A itself is malformed. Surface 17 Stop has a blank
curvature-radius cell, Filter back repeats surface number 20, and Image is numbered 21 even though
the fifth inserted stop requires a nonoverlapping 0-22 sequence. The source does not establish
whether the blank radius is plano or another value and does not establish a unique corrected
surface sequence. Both states of embodiment 9 therefore terminate as
`metadata_unpublished.surface_sequence_and_stop_radius_conflict`; no numeric repair is made.

## Fail-closed parsing and replay outcome

For embodiments 1-8 and 10, the published signed moving distances can place dummy stop rows out of
physical object-to-image order. The parser accumulates the exact published axial coordinates,
requires nonoverlap, sorts by physical coordinate, and splits a material span when a dummy stop
falls inside it. It never changes a published radius, distance, refractive index, Abbe number, or
asphere coefficient. Any source/hash/table/occupancy drift reopens all 25 items for parser review.

The nine intact infinity states enter the infinity-conjugate replay worker. Items 3, 5, 7, 11, 15,
and 19 produce staging-only ZMX files with respectively 2/5, 3/5, 3/5, 3/5, 4/5, and 4/5 finite
final rays. Items 1, 9, and 13 terminate from process receipts because full-field real rays do not
reach the image. These are replay/trace outcomes, not expert production-validity judgments.

The nine intact macro states remain nonterminal parser-review items because the current replay
tracer models an infinity conjugate and cannot validate their explicitly published finite object
distances. Embodiment 9's two states are the source-defect terminals above. Embodiment 11 terminates
as `confirmed_no_prescription.imaging_apparatus_wrapper_only`; embodiments 12-15 terminate as
`confirmed_no_prescription.electronic_device_wrapper_only`.

Two append-only replay results have different receipt-identity bytes but the same canonical
semantic SHA-256,
`1f471dffb3d8ac3ee707eb3fcd7efad086f42897441507f64c1185e2e474b64c`. Exact excluded retry fields,
per-receipt semantic hashes, request hashes, worker-response hashes, staging hashes, and both raw
result hashes are pinned in `family-95157884-replay-determinism.json`.
