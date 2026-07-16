# Family 88236580 source audit

## Identity, relationship, and current scope

- `US-12631860-B2` and `US-20260153717-A1` share Family ID `88236580`, title
  `IMAGING LENS ASSEMBLY MODULE, CAMERA MODULE AND ELECTRONIC DEVICE`, and Largan ownership.
  They are not the same application: B2 is application `18/474353`; A1 is continuation
  application `19/460417` and explicitly names `18/474353` as its parent.
- B2 Prior Publication Data names `US-20240111139-A1`, the publication of application
  `18/474353`. That root is not in the frozen 619-root cohort. It is retained in
  `family-88236580-external-family-members.json` for the post-frozen external queue and is not
  silently counted as complete by this shovel.
- Retained official HTML SHA-256 values are
  `053e22371b8427c36702a98d7d4992c0ff86771fb8fa5391c04103982d8ee9f5` (B2) and
  `0c6ae9d0c0d4606ebc29235e993f71ce459bf04a875f586c00eda9869c356990` (A1).
  Parser-normalized text hashes are
  `f5340d3edabdf94df8663b8b12514b77abe50380786603baef9b1f7401e6a16a` and
  `57f16c924738b6790604ef5cdc3a08f9e1a70b3c6e3e93cac0c8ccfb721a062a`.

## Source denominator and item mapping

Each publication contains exactly seven section headings, from 1st through 7th Embodiment, and
exactly six subordinate thin-film examples in the first four embodiments:

| Ledger item | Source example/embodiment | Thin-film table | System table |
|---:|---|---|---|
| 1 | 1st example, 1st embodiment | 1A | 1B |
| 2 | 1st example, 2nd embodiment | 2A | 2B |
| 3 | 1st example, 3rd embodiment | 3A | 3D |
| 4 | 2nd example, 3rd embodiment | 3B | 3D |
| 5 | 3rd example, 3rd embodiment | 3C | 3D |
| 6 | 1st example, 4th embodiment | 4A | 4B |
| 7 | 5th embodiment smartphone/multi-camera architecture | none | none |
| 8 | 6th embodiment smartphone/TOF/folded-light architecture | none | none |
| 9 | 7th embodiment vehicle camera architecture | none | none |

Embodiments 1-4 are represented by their six declared subordinate examples and are not counted a
second time as duplicate parent items. Thus the denominator is nine ledger items per publication,
18 for the two frozen roots.

The ten PPUBS tables are exactly 1A, 1B, 2A, 2B, 3A, 3B, 3C, 3D, 4A, and 4B; every normalized
table block is independently hash-bound in the exact source profile. Tables 1A/2A/3A/3B/3C/4A
publish light-eliminating thin-film materials and refractive indices. They are coating stacks, not
ordered lens surfaces. The four system rows are:

| Embodiment | D (mm) | FNO | FOV (degrees) |
|---|---:|---:|---:|
| 1 | 3.05 | 1.82 | 19.1 |
| 2 | 3.05 | 1.82 | 19.1 |
| 3 | 2.49 | 2.2 | 16.5 |
| 4 | 2.49 | 2.2 | 16.5 |

`D` is explicitly the distance between the first and second relying surfaces. Neither source
publishes an ordered optical-surface sequence, radius of curvature, curvature radius, surface
number, Abbe number, effective focal length, numeric focal-length assignment, asphere coefficient,
or axial lens spacing. Three generic `aspheric`/`aspherical` occurrences state only that optical
surfaces may be aspheric. The single plural `focal lengths` occurrence belongs to the fifth
embodiment's multi-camera zoom narrative. The seventh embodiment's `40 degrees < theta < 90
degrees` is a vehicle coverage angle and is not converted into a lens prescription.

## Figures and official raster denominator

Both sources declare the exact 18-panel sequence 1A-1E, 2, 3, 4A-4B, 5A-5E, 6, and 7A-7C.
The brief drawing descriptions contain zero table, prescription, optical-data, lens-data, radius,
Abbe, FNO, or FOV references.

Both official PDFs have 30 pages and exactly one raster image per page. B2 drawing sheets 1-18 are
pages 3-20; A1 drawing sheets 1-18 are pages 2-19. All-page contact sheets were visually audited:
they show only catadioptric/module/device layouts, exploded views, a nano-ridge micrograph, captured
scene/device drawings, and vehicle placement drawings. No hidden prescription table or numeric
surface annotation is present.

| Publication | Retained official PDF SHA-256 | Retained recheck wrapper SHA-256 | Stable raster-set SHA-256 | Contact SHA-256 |
|---|---|---|---|---|
| B2 | `27bf0829f9a6af3b80da766965e38534df92b218fdb41da61a402d71a9dee434` | `447605c3930757066bb0870ec5911dbed0665a2df08c889aab666a6b47886ed8` | `214c3a9795732ab980f6a77ac2ecbe3e2bd8a7cdaf0599fe05bc9ca1e230cb67` | `b7d85a443e2256520d332e86ac78d260fc76e24ecf5ee3b35aea96ddb9e06afe` |
| A1 | `e6a256a30cf8a960313494a5e2ec12dd405b8d6dc3b4492c44e6f025f172a00f` | `e179169bec01b07251d41f64ff5c607370ba59cf3ff3845ab87a1a949a3e301c` | `ee10741181934680cc3c1ce831bae1aae75e06a0093b832f0b7e6da15372a446` | `0fc99410accfa5faabf55ce54a80fe288f9f9d3a53000a0d3bca856f44bb9570` |

The official PDF wrapper bytes varied across two retained fetches, while all 30 decoded
page-raster hashes remained identical for each publication. Therefore live wrapper equality is not
claimed; both wrappers and the stable decoded-raster set are retained separately. Google
citation pages were unavailable (404), so no mirror supplies optical truth. Full structured page
and drawing roles are in `family-88236580-raster-audit.json` and rehash in the test suite.

## Fail-closed outcome

Profile selection requires an exact publication ID and raw/normalized official HTML hashes.
Application/family relationships, seven headings, six example pairs, ten ordered table keys and
digests, four system rows, 18 drawing declarations, allowed generic marker counts, and absence of
surface-prescription markers are independently checked. Any drift returns all nine items to parser
review. The six thin-film examples terminate as
`confirmed_no_prescription.catadioptric_thin_film_and_module_architecture_only`; embodiments 5-7
terminate as `confirmed_no_prescription.camera_module_device_architecture_only`. No trace worker,
conversion receipt, request fingerprint, formal candidate, or ZMX is created.
