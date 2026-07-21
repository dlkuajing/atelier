# Family 89511297 exact-source audit

## Authority and identity

The classification authority is retained official USPTO PPUBS grant
`US-11874478-B1` at
`data/patent-lake/uspto-ppubs-html/USPAT/7a46e890a5a2713a/US-11874478-B1.html`.
The 148,686-byte HTML hashes to
`7a46e890a5a2713a0cb2ab07a112563e4239cdf3d9848abe43b08e2f08786340`;
its normalized 76,837-character text hashes to
`63076754a04f37d98317f754ab6a1081660143c0e205b99a0c99b1425e978eb1`.
It directly binds application `16/990939`, Family ID `89511297`, inventor Jason D.
Mudge, Golden Gate Light Optimization LLC as applicant and assignee, and provisional
application `63/048,548` dated 2020-07-06. The exact B1 lists no parent or pre-grant
publication; no external family member supplies classification data.

## Complete source denominator

- Nineteen numbered Background/Summary payloads: the cross-reference paragraph and
  Technical Field both print `(1)`, followed by printed paragraphs `(2)`-`(18)`.
- Seventy-nine Description paragraphs: twelve drawing declarations `(1)`-`(12)` and
  detailed disclosure `(13)`-`(79)`.
- Twenty claims, with claims 1, 10 and 16 independent.
- One `TABLE-US` symbol dictionary, 22 MathML objects, 20 unique numbered equations,
  78 `figref` tags, FIGS. 1-12 and ten official drawing sheets.
- Exactly eleven source items: three independent claimed lens/system/method groups,
  four structural embodiment groups tied to FIGS. 1-5, and four numerical first-order
  radiometric configurations tied to FIGS. 7-12. FIG. 6 validates the method and the
  paragraph `(77)` array variants remain dependent on the claimed system, so neither
  is double-counted as another prescription.

## Published data and terminal boundary

TABLE 1 defines only `fi`, `fo`, `Di`, `Do`, mounting-member radial thickness `t` and
detector characteristic dimension. Paragraph `(67)` publishes those six first-order
values for the short-range example. Paragraph `(72)` publishes them for a long-range
example; paragraphs `(74)` and `(76)` publish a relaxed focal-length variant and a
neutral-density example. None of the text, table, claims or drawings publishes an
ordered surface sequence, surface radii, center thicknesses, numerical glass/index
and dispersion, stop coordinate, or surface-by-surface prescription.

The long-range source is internally inconsistent. Paragraph `(72)` directly prints
`fo=0.6 m` for FIGS. 9-10, while paragraph `(74)` says the FIGS. 9-10 outer focal
length changes from `0.5 m` to `0.6 m` for FIG. 11. Official PDF page 22 prints both
tokens on the same page. The plots label curves and axes only; they neither resolve
that conflict nor add prescription coordinates. No value is selected, repaired or
derived.

All eleven items therefore close as exact-source `confirmed_no_prescription`
outcomes. No worker, conversion request, receipt, prescription fingerprint, candidate
ZMX, staging ZMX, formal intake record, expert verdict or CODE V call is created.

## Official raster audit

The official 24-page PDF endpoint was downloaded twice. The 1,466,086-byte wrappers
have distinct container hashes, while all 24 decoded page rasters agree in order at
canonical raster-set SHA-256
`a8205b2aff3b203f189141ceed21519357b6e15439bf9c1993e6a433c94bd3e6`.
Every page has exactly one raster and no text layer. Pages 15-17 and 19 are
2550x3300; all others are 2560x3300. The complete contact sheet and original pages
7, 9-12, 22 and 23 were reviewed. Figures 7-12 contain only curve labels and axes;
page 22 preserves the conflicting long-range focal-length statements.

Only lossless decoding and contact-sheet downscaling were used. There was no image
enhancement, OCR repair, drawing measurement, numeric transcription, plot sampling,
coordinate inference or related-publication borrowing.
