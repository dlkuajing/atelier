# Family 64459548 source audit

## Identity and publication boundary

- The frozen cohort contains root `US-20210373283`, publication `US-20210373283-A1`,
  application `17/344651`, and Family ID `64459548`. The retained USPTO HTML identifies
  Kantatsu Co., Ltd., Nobuyuki Kasama, the 2017-06-02 and 2018-04-27 Japanese priorities, and
  parent application `15/996142`.
- `US-20180348479-A1` is the parent-application publication and lies outside the frozen 619-root
  cohort. `CN-108983383-A` and the Japanese priority lineage are also outside the cohort. Their
  metadata and rasters are cross-check evidence only; no numeric value is borrowed into the
  classification of `US-20210373283-A1`.

## Complete source denominator

The exact raw and normalized hashes bind all 190 consecutive description paragraphs, claims
1-14, 11 drawing declarations expanded to 23 panels, and zero PPUBS tables. The first embodiment
occupies paragraphs 28-117. The second embodiment begins at paragraph 118, reuses the same
five-lens assembly, changes the barrel/rear annular fixing-member architecture, and concludes at
paragraph 152; paragraphs 153-190 are the reference-sign list.

The first embodiment qualitatively states the signs of the five lens elements: biconvex L1,
object-convex/image-concave L2, axis-near biconcave aspherical L3, object-concave/image-convex L4,
and object-convex/image-concave aspherical L5. It does not publish radii, spacings, materials or
optical indices, Abbe numbers, conics/asphere coefficients, an ordered surface prescription, EFL,
F-number, or angular field. The second embodiment adds no prescription. Its novelty disclosure is
the resin barrel/contact/coating geometry, vacuum-ultraviolet surface modification, press fitting,
heating, and manufacturing sequence.

## PDF closure

Two independent USPTO downloads and the Google wrapper for `US-20210373283-A1` contain 21 pages.
Their container hashes differ while all 21 decoded page rasters agree. Page 1 is the cover, pages
2-12 are 11 drawing sheets, and pages 13-21 are specification pages. Claims 1-14 begin on page 20
and end on page 21. Visual inspection of every page, the higher-resolution drawing contact sheet,
and the claims boundary found no table or image-only optical prescription.

The independently downloaded official and Google wrappers for parent publication
`US-20180348479-A1` also contain 21 mutually agreeing rasters and the same page-role denominator.
The two publications have zero equal same-position raster hashes across 21 pages, so publication
pages are never treated as interchangeable source truth.

## Replay outcome

The exact-source classifier emits one source-proven `confirmed_no_prescription` terminal item for
each explicit embodiment. Attempts 2 and 3 are semantically identical after removing only
`result_attempt`; neither invokes the conversion worker nor emits a candidate or staging ZMX. The
strict 619-root audit remains complete with zero corrupt result, and the generic residual census
falls deterministically from 140 roots/items to 139 roots/items.
