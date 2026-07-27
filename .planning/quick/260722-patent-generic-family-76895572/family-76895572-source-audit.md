# Family 76895572 exact-source audit

## Exact publication and lineage

- Root/publication: `US-12174451` / `US-12174451-B2`.
- Application: `18/504213`, filed 2023-11-08; prior publication
  `US-20240069305-A1`, published 2024-02-29; patent date 2024-12-24.
- Continuation parent: application `17/249182`, filed 2021-02-23 and granted as
  `US-11846826`; provisional priority: `63/027390`, filed 2020-05-20.
- Applicant/assignee: LARGAN PRECISION CO., LTD.; inventors Chang Lin-An,
  Chou Ming-Ta, Yang Shu-Yun and Lin Cheng-Feng.
- Retained PPUBS HTML:
  `data/patent-lake/uspto-ppubs-html/USPAT/cda8fd6d4eff9e12/US-12174451-B2.html`,
  112,474 bytes, SHA-256
  `cda8fd6d4eff9e1227beb39c5f6aa07183cf726e65f8864ec3bd6187c4e1cf8c`.
  The normalized 89,458-character text has SHA-256
  `63399ac52e9130c9427e712c356b072665f71b937ce0e0299267acceb55103a4`.

## Denominator and source-item boundary

The exact specification contains one Related Applications paragraph, six
Background/Summary paragraphs and 176 Description paragraphs. Description
paragraphs 1-43 declare 42 drawing panels; paragraphs 44-62 provide shared
definitions; paragraphs 63-175 contain eleven disjoint embodiments; paragraph
176 is closing boilerplate. The source items are:

1. paragraphs 63-73 / FIGS. 1A-1F / TABLE 1: first imaging-lens-assembly
   light-blocking-opening architecture;
2. paragraphs 74-84 / FIGS. 2A-2D / TABLE 2: second architecture;
3. paragraphs 85-94 / FIGS. 3A-3F / TABLE 3: third architecture;
4. paragraphs 95-104 / FIGS. 4A-4C / TABLE 4: fourth architecture;
5. paragraphs 105-114 / FIGS. 5A-5C / TABLE 5: fifth architecture;
6. paragraphs 115-124 / FIGS. 6A-6F / TABLE 6: sixth architecture;
7. paragraphs 125-137 / FIGS. 7A-7C / TABLE 7: first camera-module architecture;
8. paragraphs 138-150 / FIGS. 8A-8C / TABLE 8: second camera-module architecture;
9. paragraphs 151-158 / FIG. 9 / TABLE 9: ninth light-blocking-structure variant;
10. paragraphs 159-166 / FIG. 10 / TABLE 10: tenth light-blocking-structure variant;
11. paragraphs 167-175 / FIGS. 11A-11F: electronic-device multi-camera wrapper.

There are 14 claims. Claim 1 is the only independent claim; claims 2-12 depend
on claim 1, claim 13 expressly incorporates the claim-1 assembly into a camera
module, and claim 14 expressly incorporates claim 13 into an electronic device.
All claims map to the eleven-item denominator and create no additional source
item or prescription. The exact HTML has 198 figure-reference tags, 42 unique
panels, ten flattened `TABLE-US` blocks, five inline-formula lead/tail pairs,
and no HTML table, MathML or custom-character image tag.

## Table and formula boundary

TABLES 1-10 each contain only `D`, light-blocking-opening area `A`, first
curvature radius `R`, minimum opening distance `dmin`, the ratios
`A/[pi*(D/2)^2]`, `dmin/D` and `R/D`, lens-element count `N`, and maximum
deployment field `FOV`. The curvature is explicitly the arc portion of the
light-blocking opening, not an ordered lens-surface radius. The tables do not
publish surface numbers, axial order, intersurface spacing, glass/material,
index, dispersion, conic or asphere rows. Their ten normalized payloads have
ordered-set SHA-256
`b55e1051de80da325bb3ddf49a5bc474a58adaa06bbd5eff614aad0bd29f0ddc`.

The five formulae are only `0.01<R/D<3`, two `dmin/D` limits, `3<=N<=8`, and
`3 degrees<=FOV<=40 degrees`; their normalized ordered-set SHA-256 is
`db4a3e19d931f50b9b5608b5b5ffc8f69a1ac25fa676b2c158827b4fa374c9cc`.

## Prescription boundary and outcome

The exact text has zero occurrences of `radius of curvature`, `F-number`,
`image height`, `aspheric`, `refractive index`, `Abbe`, `dispersion`, `lens
group`, `optical power`, `wavelength`, `effective focal` and `entrance pupil`.
Its 85 `curvature radius` occurrences all describe the light-blocking opening;
the single `focal length` occurrence is qualitative multi-camera zoom language
in the electronic-device wrapper. `FOV` is a maximum module/deployment field in
the opening-geometry tables and conditions, not a field attached to an ordered
optical prescription.

No source item publishes an ordered optical surface-radius sequence, ordered
axial spacings, numerical optical materials/index/dispersion, surface-specific
conics/aspheres, a source-bound focal length and F-number, or absolute image
height. Lens counts, convex/concave labels, the light-blocking aperture, opening
geometry and deployment FOV cannot form a prescription without inventing the
missing coordinates. Therefore all eleven items close narrowly as
`confirmed_no_prescription`: six imaging-lens-assembly light-blocking
architectures, two camera-module light-blocking architectures, two isolated
light-blocking-structure variants and one electronic-device wrapper. No worker,
conversion request, receipt, fingerprint, ZMX, formal intake or CODE V use is
authorized.

## Official PDF/original-raster audit

Two independent official downloads are distinct 2,042,458-byte PDF containers.
Both contain 57 image-only pages, one 2560x3300 one-bit raster per page and zero
extractable text; decoded pages agree exactly at raster-set SHA-256
`e6d5d3b5d3ad8267e0fb408273502014585052eb8196b6de32f1939e7fc51bf7`.
Original PNG exports are pixel-equal to the embedded rasters.

Navigation and original-scale review establishes only page roles: wrapper page
1 is the cover, page 2 references, pages 3-44 the 42 drawing sheets, and pages
45-57 the paired specification pages 1-26; wrapper page 57 contains claims 1-14
and ends at claim 14. Original pages 45 and 48-57 visually confirm that TABLES
1-10 contain opening geometry rather than optical prescription rows. No OCR,
enhancement, repair, measurement, numeric raster transcription or raster
inference was used.

## Binding policy

- No derivation, interpolation, drawing measurement or printed-token repair.
- No PDF-raster numeric transcription or inference.
- No promotion of opening curvature, lens count, convex/concave labels,
  aperture-stop function or deployment FOV into an ordered prescription.
- No borrowing from the parent, prior publication, another family or a shared
  layout.
