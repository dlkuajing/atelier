# Family 60048601 exact-source audit

## Authority and identity

The classification authority is the retained official USPTO PPUBS B2 HTML at
`data/patent-lake/uspto-ppubs-html/USPAT/783b3621e11c5f08/US-11086108-B2.html`.
It is 60,819 bytes at SHA-256
`783b3621e11c5f081cc9fc317921f18b75d2841b2711af260ffba363080a2f42`;
its normalized 41,789-character text is
`e1cbb30deffaba7272f02a78b62960ee88f1b52e97a81cfac634001fa7e8b8b6`.
The document directly binds US application `16/748874`, Family ID `60048601`,
inventors Cheng-Feng Lin, I-Wei Lai and Ming-Ta Chou, and Largan Precision as
applicant and assignee. It identifies same-application publication
`US-20200158996-A1`, Taiwan priority `TW 105114303` dated 2016-05-09, parent
application `16/251320` / grant `US-10578839`, and earlier parent application
`15/201668` / grant `US-10234658`.

Google Patents was used only as an external lineage cross-check. It independently
lists the same three US family applications, the same Taiwan priority and Family ID
60048601. No external family text, number, conclusion or optical value is imported
into the classifier or terminal outcomes.

## Complete source denominator

- Four Background paragraphs `(1)`-`(4)` and four Summary paragraphs `(5)`-`(8)`.
- Twenty brief-drawing paragraphs `(1)`-`(20)` declaring exactly FIGS. `1A`-`1G`,
  `2A`-`2E`, `3A`-`3E`, `4`, `5` and `6`.
- Fifty-seven detailed-description paragraphs `(21)`-`(77)`.
- Six claims, of which claims 1 and 6 are independent.
- Three tagged `TABLE-US` blocks, zero MathML objects and 90 `figref` tags.
- Twenty official drawing sheets and exactly six source items.

Background paragraphs apply to the document. Summary paragraphs 5 and 7 describe
the two common dual-molded imaging-lens-assembly aspects; paragraphs 6 and 8 add the
corresponding electronic-device aspects. Claims 1-5 cover the common assembly,
coating, placement, glue and lens-count architecture represented by items 1-3;
claim 6 covers the device wrapper represented by items 4-6. They add no separately
parameterized optical prescription.

| Item | Exact detailed span | Figures | Table | Source outcome |
|---|---:|---|---:|---|
| 1 | `(21)`-`(49)` | `1A`-`1G` | 1 | six-lens dual-molded light-absorbing architecture only |
| 2 | `(50)`-`(61)` | `2A`-`2E` | 2 | five-lens dual-molded light-absorbing architecture only |
| 3 | `(62)`-`(73)` | `3A`-`3E` | 3 | six-lens dual-molded light-absorbing architecture only |
| 4 | `(74)` | `4` | none | smartphone electronic-device wrapper only |
| 5 | `(75)` | `5` | none | tablet electronic-device wrapper only |
| 6 | `(76)` | `6` | none | wearable electronic-device wrapper only |

Paragraph `(77)` is document-closing boilerplate and does not create a seventh
item. Each item has a distinct label; no embodiment is merged or double counted.

## Tables and prescription boundary

TABLES 1-3 publish mechanical molding and light-blocking quantities: the number of
opening sides `m`, number of lens elements `N`, opening/outer diameters, recess depth
`t`, recess width `w`, and ratios among those mechanical dimensions. They do not
publish a sequential optical prescription. The prose allows an effective optical
section to be planar or aspheric with arbitrary curvature, and later describes
selected image-side sections as aspheric/concave with an inflection point, but gives
no radii, conics or coefficients.

Across the exact B2, source phrase counts are zero for `F-number`, `FNO`, focal
length, image height, radius of curvature, curvature radius, aspheric/aspherical
coefficient, refractive index, Abbe number, aperture stop and surface prescription.
There is no ordered radius/spacing/material sequence, stop coordinate, focal length,
absolute image height, angular field or F-number to convert. Drawing geometry is not
measured and no coordinate or metadata is derived.

Items 1-3 therefore close as
`confirmed_no_prescription.dual_molded_lens_light_absorbing_architecture_only`.
Items 4-6 close as
`confirmed_no_prescription.electronic_device_wrapper_only`. These exact source
terminals do not launch a worker or create a request, receipt, fingerprint, candidate
ZMX, staging ZMX, formal intake record, expert verdict or CODE V call.

## Official raster audit

The official B2 endpoint was downloaded twice. The two 1,279,888-byte containers
have different wrapper hashes because their creation metadata differs, but all 28
decoded page rasters are equal in order at raster-set SHA-256
`72c3232c42cff9d1f0e088493cfc6b0529d45018cab90f6252613c522407c4d3`.
Every page has exactly one 2560x3300 bitonal raster and no text layer. B2 pages 3-22
are the twenty drawing sheets; TABLE 1 is on page 26, TABLES 2-3 are on page 27, and
claims 1-6 are on page 28.

The same-application A1 has 27 image-only pages with raster-set SHA-256
`43a34054676a52dc794d79791bb750a902789211d1316ac196ea3192fe73b2c4`.
Its twenty drawing sheets are pages 2-21. Zero of 27 same-position A1/B2 pages are
pixel-equal and the two publications share zero page rasters anywhere. The A1 is
lineage/layout evidence only; its seven as-published claims are not substituted for
the six allowed B2 claims.

Both complete contact sheets and original-resolution B2 pages 1, 3, 22, 23, 26, 27,
28 plus A1 pages 1, 2, 21, 22, 25, 26, 27 were reviewed. Only lossless format
conversion and contact-sheet downscaling were used. There was no enhancement, OCR
repair, drawing measurement, numeric transcription, raster inference or related-
publication numeric borrowing.
