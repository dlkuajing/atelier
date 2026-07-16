# Family 74187659 source audit

## Identity lock

- Family ID: `74187659`.
- Application: `16/883126`, filed 2020-05-26, claiming priority to
  `TW108125965` (2019-07-23).
- Title: `Optical lens`.
- Applicant/assignee: Ability Enterprise Co., Ltd.; inventor: Yen-Chen Chiang.
- `US-20210026108-A1` is the application publication; `US-11719909-B2` names
  that A1 in Prior Publication Data. They are two publications of the same
  application and three optical designs, not six independent designs.
- Official HTML source locks:
  - B2 raw SHA-256
    `f43a4a419a082df67f60af279a3053069903b81eac017ba14d55359904840987`,
    recovery-normalized SHA-256
    `9a41a01aeb9a626685aa3a7939d2c34c3dd442573accf78a2de062fb73b72910`.
  - A1 raw SHA-256
    `a94cba4e581ebdb5b65798212ca6211170174ac43d60e539cce2152cf9d6c8de`,
    recovery-normalized SHA-256
    `49c30c4ae4049648ef33fd99bc6a5eb0f00c4da7f6e9c97949f5f1dc041e68d1`.

## Complete source denominator

Both official PDFs have 13/13 pages, exactly one decoded `3300 x 2560` image
per page, seven drawing sheets on PDF pages 2-8, and ten declared figure labels:
FIGS. 1-3, 4A/4B, 5A/5B, 6A/6B, and 7. Official HTML contains no table nodes;
the numerical tables are drawing images.

For B2, two live USPTO wrappers and the Google-hosted wrapper have different
container hashes but identical decoded rasters on 13/13 pages; all three have
no text layer. For A1, two live USPTO wrappers and the Google-hosted wrapper
also agree on 13/13 decoded rasters; only the Google wrapper has an OCR overlay.
Recovery accepts the overlay solely after pixel equality with every official
decoded raster. B2's all-blank overlay-page set and A1's empty blank-page set
are source-locked independently.

The complete ordered per-page raster hashes, all six wrapper hashes, image
counts, decoded shapes/dtypes, text-layer counts, contact-sheet hashes, and
retained full-resolution pages are recorded in
`family-74187659-raster-audit.json`. Recovery additionally pins the full ordered
13-page raster tuple in executable source profiles, not only the four key pages.

| PDF page | Drawing content | Reviewed denominator |
|---:|---|---|
| 5 | FIG. 4A / 4B | OL1 surface table plus S5-S10 K/A2/A4-A16 table |
| 6 | FIG. 5A / 5B | OL2 surface table plus S5-S10 K/A2/A4-A16 table |
| 7 | FIG. 6A / 6B | OL3 surface table plus S5-S10 K/A2/A4-A16 table |
| 8 | FIG. 7 | OL1-OL3 EFL/Fno/TTL/component and shape metadata |

## Optical-system audit

Each of OL1, OL2, and OL3 is a five-lens prescription. FIGS. 4A, 5A, and 6A
publish S1-S4, stop `St`, S5-S10, cover plate S11/S12, and image `I`, including
curvature, axial thickness, refractive index, and Abbe number. Their paired B
figures publish K, zero A2, and A4-A16 for S5-S10.

FIG. 7 publishes these direct whole-system values:

| Design | EFL (mm) | Fno | TTL (mm) |
|---|---:|---:|---:|
| OL1 | 2.42 | 2.11 | 6.78 |
| OL2 | 2.48 | 2.08 | 6.68 |
| OL3 | 2.44 | 2.15 | 6.60 |

It also publishes F1-F5, F345, F2/F345, TTL/EFL, h, H, h/H, and R1-R4.
Official HTML and every reviewed raster expose zero `FOV`, `HFOV`, `field of
view`, `viewing angle`, `angle of view`, or `image height` labels. The prose
defines lowercase h as the distance from the fifth-lens inflection point to the
optical axis and uppercase H as the fifth image-side surface outer-edge distance
to the optical axis. They are lens-shape coordinates and are not substituted for
image height or angular field.

The source also contains an internal OL2 contradiction. FIG. 5A publishes the
S1 curvature radius as `-17.90` mm, while FIG. 7 publishes OL2 R1 as `+17.90`
mm. Both signs are high-confidence OCR tokens on exact source-locked rasters and
are visually present in both publications. The sign is neither selected nor
repaired.

## Fail-closed disposition

Each publication expands to three source terminals and creates no trace worker,
request, receipt, fingerprint, candidate, or ZMX:

| Optical lens | Terminal reason |
|---|---|
| OL1 | `metadata_unpublished.prescription_specific_angular_field_absent` |
| OL2 | `metadata_unpublished.prescription_specific_angular_field_absent_and_r1_sign_conflicted` |
| OL3 | `metadata_unpublished.prescription_specific_angular_field_absent` |

Any drift in raw or normalized HTML, family/application identity, the complete
13-page raster tuple, page count, overlay blank-page set, figure/table labels,
angular-field absence, h/H definitions, or the OL2 sign evidence reopens parser
review. No FOV is derived from EFL, focal-length ratios, h/H, or drawing geometry,
and no numeric cell is inferred, interpolated, repaired, or borrowed from the
other publication.
