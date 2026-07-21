# Family 95563451 exact-source audit

## Identity and lineage

The retained classification source is the official USPTO A1 HTML for
`US-20250264785-A1` (application `19/049057`, Family ID `95563451`). It names
Lin-An Chang, Te-Sheng Tseng, Wen-Hung Hsu and Ming-Ta Chou as inventors and
Largan Digital Co., Ltd. as applicant. The retained header has no assignee field.
The header and paragraph `[0001]` directly identify only U.S. provisional
application `63/555469`, filed 2024-02-20, as priority. No unprinted continuation,
counterpart or numeric disclosure was inferred or borrowed.

## Complete source denominator

The exact A1 contains eight Background/Summary paragraphs (`[0001]-[0008]`),
29 brief-drawing paragraphs (`[0009]-[0037]`), 72 detailed-description
paragraphs (`[0038]-[0109]`), 27 claims, six tagged tables, 12 MathML objects,
161 `figref` tags and 28 declared figure panels. Claims 1, 14 and 22 are the only
claims that do not refer to an earlier claim. Claims 13 and 27 begin with an
electronic device but expressly depend on claims 1 and 22, respectively.

The 28 declared panels are `1A-1I`, `2-6`, `7A-7E`, `8A-8E`, `9` and
`10A-10C`. They map one-to-one to the 28 official drawing pages, PDF pages 2-29.
The six formal tables appear on PDF pages 35-37. Claims appear on pages 40-41.

The detailed disclosure resolves to exactly ten source items:

1. Six examples inside the first embodiment (`[0066]-[0087]`), each bound to
   one table and its corresponding figures.
2. The second folded-camera-module embodiment (`[0088]-[0091]`).
3. The third and fourth smartphone wrapper embodiments (`[0092]-[0104]`).
4. The fifth vehicle-camera wrapper embodiment (`[0105]-[0108]`).

Paragraph `[0109]` is a closing paragraph and is not another source item.
Paragraph `[0087]` prints “5th example” while paragraph `[0086]`, FIG. 6 and
TABLE 6 identify the same `120e` configuration as the sixth example. The source
conflict is retained verbatim; no repair or selection was applied.

## Tables and optical content

Tables 1-6 contain only six millimetre-valued opto-mechanical variables:
`H`, `Dim`, `Lf`, `Le`, `Ls` and `S`. They describe reflecting-element height,
focus travel and module placement distances. The first embodiment states only
that its first lens assembly can contain two lens elements, one glass and one
plastic. It does not publish their ordered surfaces or numerical materials.

Across all ten items, the exact A1 publishes no ordered optical surface sequence,
surface radii, axial optical spacings, numerical index/dispersion data, asphere
coefficients, aperture-stop coordinate, numeric focal length, image height,
F-number or lens field metadata. Paragraph `[0100]` says only “various focal
lengths” without values. Paragraph `[0106]` gives `40 degrees < theta < 90
degrees` for vehicle coverage; this is not field metadata bound to a constituent
lens prescription.

Therefore the six mechanical examples terminate as
`confirmed_no_prescription.light_folded_camera_mechanical_dimensions_only`, the
second embodiment as
`confirmed_no_prescription.light_folded_camera_module_architecture_only`, the
two smartphone embodiments as
`confirmed_no_prescription.electronic_device_wrapper_only`, and the vehicle
wrapper as
`confirmed_no_prescription.vehicle_camera_coverage_wrapper_only`.

## Official PDF audit

Two independent official downloads are both 1,909,074 bytes but have distinct
container SHA-256 values. Each has 41 pages, one 1-bit raster per page and no
text layer. All 41 decoded page rasters are identical across both downloads and
the pinned first download; the ordered raster-set SHA-256 is
`9bea8f943b9e0f8dd1de494e85f1949f5508704a66294feeb821242ea94517d6`.

The retained PNGs are lossless RGB serializations whose three channels exactly
equal the decoded embedded page samples. The contact sheet was used only for
navigation. Original pages 35-41 were reviewed for table, embodiment, closing
paragraph and claim boundaries. No enhancement, OCR repair, drawing
measurement, plot sampling, raster inference or numeric transcription was used.

## Replay outcome

Append-only attempts 2 and 3 each retain ten terminal items and have identical
business semantics after removing only `result_attempt`; semantic SHA-256 is
`76044d78ccc02c30627ee7c5edba256c359d2a4c9ba11f65df01e868e236f9e9`.
No conversion worker, request, receipt, prescription fingerprint, candidate ZMX,
staging ZMX, formal intake or CODE V call was created. The strict replay audit is
619/619 with zero missing and zero corrupt results. The generic residual moves
from 46 to 45 roots/items.
