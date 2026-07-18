# Family 21816074 source audit

## Identity and source closure

- Root `US-4249805`, publication `US-4249805-A`, application `06/023591`,
  Family `21816074`, assignee Magicam, Inc.
- Classification truth is the retained USPTO Patent Public Search HTML at raw SHA-256
  `25b5e668414a45ca2afcd5251205e28833c0c09fa1808779a96cc11fdd16cdb1`
  plus the official 22-page image PDF at container SHA-256
  `bf50e985949b792dbff17d239823a1555bb8fb64d1b60077d3b0ca92d292185d`.
- The HTML contains 20 numbered Background/Summary paragraphs, 61 numbered
  Description paragraphs, 25 declared figures, 54 claims with independent claims 1,
  17 and 39, zero tagged tables, zero MathML objects and zero image tags. Six optical
  tables are flattened into Description paragraphs 34, 39, 45, 50, 55 and 59. All
  section boundaries, paragraph spans and table payloads are hash-bound.
- The PDF has 22 image-only pages, one 2320x3408 raster per page and no text layer.
  Pages 2-8 are the seven drawing sheets, pages 13-17 carry Tables 1-6, pages 18-21
  carry the claims, and page 22 is the July 21, 1981 Certificate of Correction. The
  decoded raster-set SHA-256 is
  `d665607f33310bce89d9af0681f6d6a6aeb2de373d22f72ad07c9d0aac5b5687`.

## Complete source-item denominator

The source discloses six ordered prescription tables but eight lens modes because
Tables 3 and 4 each publish both wide-angle and narrow-angle modes. It also discloses
one coordinated composite-photography system wrapper. The denominator is therefore
nine source items:

| Item | Source mode | Table | EFL (in) | F/# | half-field (deg) |
|---:|---|---:|---:|---:|---:|
| 1 | television foreground narrow | 1 | 2.184 | 2.8 | 10.89 |
| 2 | television foreground wide | 2 | 0.728 | 2.8 | 30.0 |
| 3 | television background wide | 3 | 0.728 | 11.0 | 30.0 |
| 4 | television background narrow | 3 | 2.184 | 11.0 | 10.89 |
| 5 | movie background wide | 4 | 1.061 | 11.0 | 30.0 |
| 6 | movie background narrow | 4 | 3.165 | 11.0 | 10.89 |
| 7 | movie foreground narrow | 5 | 3.165 | 2.8 | 10.89 |
| 8 | movie foreground wide | 6 | 1.06 | 2.8 | 30.0 |
| 9 | coordinated camera/control wrapper | — | — | — | — |

The Certificate of Correction deletes the Table 3 stop parenthesis, supplies Table 4
`C=.00441495` and `D=.000174108`, changes column 15 line 62 to `+/-1.6%`, corrects
Table 6 L7 from `1.487/40.4` to `1.487/70.4`, and inserts the claim 22 asphere-formula
parenthesis. These corrections are bound to the source profile and do not add an
absolute image height.

## Fail-closed representability finding

Each of the eight lens modes directly publishes ordered radii, axial spacings,
refractive-index/Abbe data, an aperture stop, effective focal length, F-number and
half-field. Neither the official HTML nor the correction-certified official PDF
directly publishes an absolute image height for any mode. The lone phrase “image
height” describes a zoom ratio and does not supply a prescription-specific absolute
value. Nominal television and 35 mm motion-picture format language is not an absolute
image-height disclosure. Deriving image height from focal length and field would create
a value not printed by the source, so no such derivation is permitted.

Items 1-8 therefore retain:

`metadata_unpublished.absolute_image_height_absent`

FIG. 1 and independent claims 1, 17 and 39 disclose the coordinated registered-matte
camera/control system. Its optical prescriptions are exactly the eight modes already
mapped above; it publishes no ninth distinct ordered lens prescription. Item 9 therefore
retains:

`confirmed_no_prescription.composite_photography_system_wrapper_only`

No raster numeric transcription, drawing measurement, image enhancement, coordinate
synthesis or related-family numeric borrowing was used. No worker request,
prescription fingerprint, candidate ZMX, staging ZMX, intake record or CODE V call was
created.

## Replay and queue

Append-only attempts 2 and 3 are semantically identical after removing only
`result_attempt`; their canonical semantic SHA-256 is
`ed1c985871e8600f00fe2f88b76efdf13ee107d8c47063e0fb757c994d37c981`.
The strict replay remains 619/619 roots with no missing or corrupt result. Two independent
generic residual censuses agree at 78 roots/items and result-set SHA-256
`a5ba3123a2b21e649aec69ea2a1316a9446bc340bcc172717e6b8d1fd4d56501`.
The deterministic next exact group is Family `78471711`, root `US-12169351`,
publication `US-12169351-B2`. Global saturation remains incomplete.
