# Family 94531539 source audit

## Identity and publication boundary

- The frozen cohort root is `US-20250189695`, publication `US-20250189695-A1`, application
  `18/964621`, Family ID `94531539`, owned by Largan Industrial Optics Co., Ltd.
- The official source names U.S. provisional `63/606632` dated 2023-12-06 and Taiwan application
  `113139408` dated 2024-10-16. JP3250120U, KR20250000908U, CN120111342A, and priority
  publication TWI919493B are outside the frozen cohort and remain queued.
- Only the retained USPTO PPUBS HTML supplies classification truth. Google Patents supplies an
  independent PDF wrapper and family/country-status cross-check; no external numeric value is
  borrowed into the US publication.

## Complete source denominator

The exact raw and normalized source hashes bind Related Applications paragraph 1, Background
paragraphs 2-4, Summary paragraphs 5-7, drawing paragraphs 8-61, detailed-description paragraphs
62-189, and claims 1-29. Nine explicit embodiment headings are present. Embodiment 1 has seven
structural examples, Embodiment 2 has six, Embodiments 3-4 are camera/image-sensor module
architectures, and Embodiments 5-9 are smartphone, unmanned-aircraft, vehicle, computer, and
wearable-device wrappers. This yields twenty explicit terminal items rather than one document-level
item.

Drawing paragraphs 9-61 declare 53 panels. The HTML conversion prints panel `1I` as `11` and panel
`2I` as `21`; official drawing sheets on PDF pages 10 and 34 visibly preserve `FIG. 1I` and
`FIG. 2I`. Both representations are retained and hash-bound rather than silently normalizing the
HTML source.

Two PPUBS tables are present:

1. TABLE 1 publishes 70 alternating high/low refractive-index coating layers and thicknesses,
   split into two coating groups.
2. TABLE 2 publishes R50 values for Samples a-h: 661, 670, 682, 692, 701, 664, 672, and 681 nm.

Whole-block and formal-table digests bind every value. The tables describe optical multilayer
deposition and filter response; they do not order lens surfaces.

## Optical boundary and terminal decision

The source describes folded paths, prisms or mirrors, nano-rough sensor surfaces, filter/coating
placement, image sensors, lens-set placement, and device packaging. Its ten `aspheric surface`
mentions apply to prism/reflecting-element surface options and publish no radius, conic, or
coefficient. Six `refractive index` mentions concern high/low coating groups. The single `focal
lengths` occurrence says that a device may combine camera modules with different focal lengths;
it gives no number or prescription.

Across the complete source there are zero Abbe, radius-of-curvature, curvature-radius, ordered
surface-number, optical/lens/surface-prescription, EFL, TTL, F-number/FNO, field-of-view/FOV,
angle-of-view, or numerical-aperture markers. Accordingly, the first fifteen items become exact
`folded_image_sensor_filter_and_nano_rough_surface_architecture_only` terminals and the five
device wrappers become `camera_module_device_architecture_only` terminals. No worker, conversion
request, receipt, prescription fingerprint, candidate, or ZMX is created. Any source, identity,
section, paragraph, claim, embodiment/example, figure, table, layer, R50, phrase, or
prescription-marker drift fails closed for all twenty items.

## PDF closure

Two independent official downloads and the Google wrapper each contain 68 image-only pages. Their
PDF-container SHA-256 values differ, but all 68 decoded page rasters agree across all three
wrappers; the raster-set SHA-256 is
`4c1174383971efd5e85d9f3f428a429fb89e1ae865329f4ba8e43688beb2df53`.

PDF page 1 is the cover, pages 2-54 are 53 drawing sheets, and pages 55-68 are internal
specification pages 1-14. TABLE 1 appears on PDF page 60, TABLE 2 on page 62, and claims 1-29 begin
on the shared description/claims boundary at PDF page 66 and end on page 68. Four full-range
contact sheets plus high-resolution table and claims-boundary sheets were visually inspected; no
hidden optical prescription table appears.
