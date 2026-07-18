# Family 78471711 source audit

## Identity and source closure

- Root `US-12169351`, grant `US-12169351-B2`, application `17/405071`, prior
  publication `US-20220100057-A1`, Family `78471711`, assignee LARGAN PRECISION
  CO., LTD.
- Classification truth is the retained USPTO B2 HTML at raw SHA-256
  `86c15343d390d69dbb9fef7209d6b0852ea0b89ec4d1eac71a67e06d44e2b5f4`
  plus the official 36-page B2 image PDF at container SHA-256
  `d50dff1009a33c0a6a093145b36cbf82c0cd752db58acb19c33eec3f4e780ef7`.
  The official 35-page A1 PDF is retained only to bind the prior-publication
  lineage; no numeric value is borrowed from it.
- The B2 HTML contains one Related Applications paragraph, two Background
  paragraphs, three Summary paragraphs, 27 Brief Description paragraphs, 61
  Detailed Description paragraphs and ten claims, with independent claims 1, 9
  and 10. Every section, paragraph span, table payload and claim is hash-bound.
- Brief Description paragraph 1 is the drawing introduction and paragraphs 2-27
  declare 26 figure panels. The B2 has exactly 26 drawing sheets on pages 3-28,
  one for each panel. The HTML token `FIG. 10` in paragraph 4 disagrees with the
  visible official page-5 label `Fig. 1C`; the discrepancy has no numeric effect
  and was recorded without repair or inference.
- The HTML contains zero tagged tables, zero MathML objects and zero image tags.
  Three flattened mechanical tables occur in Detailed Description paragraphs
  56, 69 and 82 and on official B2 pages 32, 33 and 35. They contain only a
  mechanical air gap, two outer diameters and their ratio.

## Complete source-item denominator

The document discloses three concrete imaging-lens-assembly mechanical
architectures, one image-capturing-apparatus wrapper and one electronic-device
wrapper. The denominator is therefore five source items:

| Item | Source scope | Paragraphs / claim | Figures | Table |
|---:|---|---|---|---:|
| 1 | first barrel/retainer/glue/void assembly | detailed 44-56 / claims 1-8 | 1A-1G | 1 |
| 2 | second barrel/retainer/glue/void assembly | detailed 57-69 / claims 1-8 | 2A-2G | 2 |
| 3 | third barrel/retainer/glue/void assembly | detailed 70-82 / claims 1-8 | 3A-3H | 3 |
| 4 | image-capturing-apparatus wrapper | summary 4, detailed 41 / claim 9 | inherited | — |
| 5 | electronic-device wrapper | summary 5, detailed 42 and 83-87 / claim 10 | 4A-4D | — |

Each of the first three embodiments labels five plastic lens elements in order
and describes their barrel, retaining member, glue, void and image-surface
architecture. The source expressly leaves lens amount, lens structures, surface
shapes and additional optical elements to imaging demand. Tables 1-3 are fully
mapped: Table 1 has `d=20 um`, `phi_i=5.35 mm`, `phi_1=4.82 mm` and ratio 1.11;
Tables 2 and 3 each have `d=20 um`, `phi_i=4.95 mm`, `phi_1=4.3 mm` and ratio
1.15. These values describe mechanical separation and outer diameters, not an
ordered optical prescription.

## Confirmed-no-prescription finding

The complete normalized B2 contains no occurrence of “radius of curvature”,
“refractive index”, “Abbe”, “aspheric”, “aperture stop”, “effective focal
length”, “F-number”, “field of view” or “image height”. The four occurrences of
“focal length” are qualitative statements about thermal-expansion influence on
overall focal length. No source item publishes ordered surface radii, numeric
optical axial spacings, optical material/index/Abbe data, conics/aspheres, an
aperture stop, or direct numeric EFL, F-number, field and absolute image height.

Items 1-3 therefore retain:

`confirmed_no_prescription.lens_barrel_retaining_glue_void_architecture_only`

Item 4 only wraps one of the mapped assemblies in an image-capturing apparatus
and retains:

`confirmed_no_prescription.image_capturing_apparatus_wrapper_only`

Item 5 only wraps that apparatus and an image sensor in an electronic device and
retains:

`confirmed_no_prescription.electronic_device_wrapper_only`

No raster numeric transcription, drawing measurement, image enhancement,
coordinate synthesis or related-publication numeric borrowing was used. No
worker request, prescription fingerprint, candidate ZMX, staging ZMX, intake
record or CODE V call was created.

## Replay and queue

Append-only attempts 2 and 3 are semantically identical after removing only
`result_attempt`; their canonical semantic SHA-256 is
`1ee284d27b916c2826368d92eafcf59375ca3766a2ea17b227fd8aa5461e0189`.
The strict replay remains 619/619 roots with no missing or corrupt result. Two
independent generic residual censuses agree at 77 roots/items and result-set
SHA-256 `12c3080c61c9de456501a0c92126a2bee874fda912582d4bf991156cc1103a01`.
The deterministic next exact group is Family `86240812`, root
`US-20260129276`, publication `US-20260129276-A1`. Global saturation remains
incomplete.
