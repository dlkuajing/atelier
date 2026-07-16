# Family 75759822 source audit

## Scope and publication relationship

- The two frozen roots are `US-20220244497-A1` and `US-12216247-B2`, both titled
  `OPTICAL IMAGING LENS ASSEMBLY AND FINGERPRINT IDENTIFICATION DEVICE` and both bound to
  Family ID `75759822` and application `17/575671`.
- The grant's official Prior Publication Data names `US-20220244497-A1`. No title or family
  similarity is used to move values between applications; these are two publications of the
  same exact application and both independently contain the complete five-embodiment tables.

## Exact official HTML sources

| Publication | Raw SHA-256 | Normalized-text SHA-256 |
|---|---|---|
| `US-12216247-B2` | `52c751834233443040bbd188c77c584a5e9a38a3ac5e99cc30a8ec7ecf8dee2b` | `491a61d9331cb197685dd764a095c0ab3a5b6049352cc3e073373a6aeeae1039` |
| `US-20220244497-A1` | `f19c4e1fdb2e65940f9c998688aab0aa50cadddd2d5370973045788dba408cd0` | `e1e1bdcf7c26956d4fd3dda9088ff3f0576b039185b680f028ac05ff0b98d40b` |

The complete disclosure denominator is five numbered embodiments, five surface tables
(`TABLE 1/3/5/7/9`), five matching even-order asphere tables (`TABLE 2/4/6/8/10`), and one
five-column conditional-expression table (`TABLE 11`). The ledger therefore creates exactly
five items per publication. There are no omitted, merged, or excluded formal embodiments.

Each prescription has the same ordered 12-row topology after the non-surface `OBJ` row is
excluded: glass-screen surfaces `S01/S02`, lens-one surfaces `S1/S2`, `STO`, lens-two surfaces
`S3/S4`, lens-three surfaces `S5/S6`, optical-filter surfaces `S7/S8`, and image surface `S9`.
`S1-S6` are aspheric. Each matching coefficient table publishes exactly A4 through A20, nine
coefficients per aspheric surface. The surface tables independently publish the conic coefficient.
Complete per-embodiment optical-cell digests bind every row label, radius, distance, refractive
index, Abbe number, surface type, conic, and A4-A20 coefficient.

The source formula defines curvature as `c=1/R`, identifies `k` as the conic coefficient, and
identifies `Ai` as the correction coefficient of order `i`. It publishes refractive-index/Abbe
pairs but no explicit wavelength token. Conversion therefore retains the repository's existing
immutable patent reference-wavelength default (0.5876 µm); this is not represented as a
source-published wavelength.

## Exact system metadata and field transform

| Embodiment | f (mm) | TTL (mm) | ImgH (mm) | Full FOV (deg) | f/EPD | Stored HFOV (deg) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.26 | 2.62 | 1.01 | 149.9 | 1.40 | 74.95 |
| 2 | 0.30 | 2.58 | 0.96 | 145.7 | 1.36 | 72.85 |
| 3 | 0.27 | 2.75 | 0.96 | 142.9 | 1.38 | 71.45 |
| 4 | 0.29 | 2.82 | 1.04 | 141.4 | 1.48 | 70.70 |
| 5 | 0.29 | 2.81 | 1.03 | 144.0 | 1.49 | 72.00 |

The abstract, detailed description, and claims explicitly define FOV as the maximum/full field.
The per-embodiment paragraphs then publish the numeric FOV values. Division by two is therefore a
source-defined unit transform into the half-field field stored by `PatentPrescription`; no image
height is used to infer a field. `f/EPD` comes directly from the cardinality-bound `TABLE 11` row.
TTL and published ImgH are source-locked reconciliation values, not substitutes for a missing
surface distance or for `f*tan(HFOV)`.

## Official PDF and drawing reconciliation

| Publication | Official PDF SHA-256 | Google PDF SHA-256 | Pages | Drawing pages | Decoded-raster set SHA-256 |
|---|---|---|---:|---|---|
| `US-12216247-B2` | `e0cf5dcdd3dc15f2cc0b36e890ba4d3bf43e809a5b28a367198e98798117e666` | `6e13bad522f81bfb3fb2ed0a6d7ca9321a4d4b152ca0b04ea566e83e4ba19b18` | 20 | 2-9 | `5d81b74de30e98312c9282ff07b7c8b71f6f121331492ec715c938b02a5d404a` |
| `US-20220244497-A1` | `b2a324c63222af6ed23b09736ba776e2a1743d94bb9ad0224ccbc78320a2e525` | `1ba50de9428e6ca874a8b83af565d93f92ffeb3ee28c6ea942ef68e554b591c0` | 20 | 2-9 | `17684830548930fa5598967e6926a0722e375ef4ee2aa7e7e227f3ca7f12c56a` |

Each page contains exactly one embedded source image. After OpenCV unchanged-mode decoding, every
official image has the same shape, dtype, and pixels as the corresponding Google PDF image in both
publications. The set hash is canonical JSON over the 20 ordered per-page hashes produced by the
repository's `decoded-page-raster-v1` domain. PDF page-render bytes are not compared because the
Google container adds a text overlay. The eight drawing sheets contain the declared FIGS. 1,
2A-2B, 3, 4A-4B, 5,
6A-6B, 7, 8A-8B, 9, and 10A-10B: five axial lens diagrams plus astigmatism and distortion plots.
Both retained contact sheets were visually inspected. They show no fold mirror, decenter, tilt,
coordinate break, image-only prescription cell, or additional embodiment. The contact-sheet
SHA-256 values are `b05fffc86cc24666653f6c78f34d1dcea46d564dd0b3b2ff790cf4f852f36c7b`
for the B2 and `9d80c40637d49f5b2b84538986a8f57056b2024bd7fb1eeb7278b4dcc9faa67a`
for the A1.

## Replay boundary

Both publications independently recover the same five prescription fingerprints:
`49bac5303aeebcea`, `d8f042c1b2c3a55e`, `64a36b2afe0001f8`,
`9b5f2449551c89d2`, and `55b063230f9e7c27`. All ten publication/embodiment items pass the
process-isolated worker and remain `converted_pending_intake`; none is formally intaken.

The worker's edge-field traced image heights are 0.502, 0.476, 0.666, 0.769, and 0.665 mm,
whereas the exact source publishes ImgH 1.01, 0.96, 0.96, 1.04, and 1.03 mm. The discrepancy is
preserved explicitly: it is neither repaired nor used to overwrite a source value, and it means
these staging candidates still require the existing real-IMH, physical-quality, duplicate, and
route/intake gates. This shovel makes no optical-quality or production-acceptance claim.
