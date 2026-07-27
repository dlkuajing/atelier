# Family 66534470 source audit

The exact retained official publication is `US-20190154987-A1`, application
`16/101628`, Family ID `66534470`, titled *Camera Optical Lens*. The official HTML
is the sole content authority. It contains 108 consecutively numbered paragraphs,
12 flattened tables, eight declared figure panels and ten actual claims numbered
`1, 2, 4, 5, 6, 7, 8, 9, 10, 11`. Claim number 3 is absent in both the HTML and
the original official page raster and is intentionally not repaired.

## Source-item reconciliation

The document publishes exactly two optical items. Embodiment 1 occupies paragraphs
13-66 and Tables 1-6; Embodiment 2 occupies paragraphs 67-107 and Tables 7-12.
Paragraph 12 is the detailed-description preamble and paragraph 108 is closing
boilerplate. Each embodiment has an aperture, five lenses, a filter, an image
surface, a complete ordered radius/spacing/material table, ten eight-term asphere
rows, ten inflexion rows, ten arrest rows, a direct focal-length row and a condition
table. No wrapper or third prescription is disclosed.

The source directly publishes EFL, entrance-pupil diameter, image height and diagonal
field angle for both prescriptions. It publishes only the inequality “aperture F
number ... less than or equal to 1.8,” once in the detailed text and once in claim 10.
It does not publish either prescription's exact F-number. Dividing EFL by entrance-
pupil diameter would create a derived value and is therefore forbidden. Both items
terminate as `metadata_unpublished.system_f_number_absent`; no conversion request,
receipt, fingerprint, candidate ZMX or formal intake may be created.

## Original-raster audit

Two consecutive official endpoint downloads have different container hashes but the
same 11 decoded page rasters. A Google wrapper adds an OCR text layer but decodes to
the identical raster set. All 11 original 2560x3300 page rasters were reviewed without
enhancement: page 1 is the cover and representative drawing; pages 2-5 are four drawing
sheets containing FIGS. 1-8; pages 6-11 are specification pages; Tables 1-12 occupy
pages 7-10; claims begin on page 10 and end on page 11. The raster confirms layout,
the F-number upper-bound wording and the missing claim number only. No raster numeric
cell was transcribed and no drawing geometry was measured.

Exact hashes, page roles and source boundaries are recorded in
`family-66534470-source-availability.json`, `family-66534470-source-facts.json` and
`family-66534470-raster-audit.json`.

## Validation

Attempts 2 and 3 are semantically identical after removing only `result_attempt` at
`0e4932819abe0466e1f3f97eee9fe6718f7e7d600a6ebb7c73593e5aefa91557`.
The generic residual falls from 70 to 69 roots/items and two independent census builds
are byte-identical at `ed916acad71d10dfe3b20cd05f3a25317304c01bd70fdf0cd93ab5d018938631`.
The strict replay audit covers 619/619 roots with no missing or corrupt result. The
complete offline repository suite passes 3528 tests with one skip and ten explicitly
deselected real-machine tests; the five saturation guards, focused source/raster/replay
tests, Ruff and compilation also pass. Changed-JSON, all historical evidence references,
formal-output, contamination, protected-path, diff, primary-repository and read-only
CODE V inventory audits pass. The sealed aggregate evidence manifest is rehashed by a
separate post-seal regression test.
