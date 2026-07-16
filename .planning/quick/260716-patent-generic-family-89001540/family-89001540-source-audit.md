# Family 89001540 source audit

## Identity lock

- Family ID: `89001540`.
- Application: `18/402737`, filed 2024-01-03, claiming priority to
  `CN202311236718.6` (2023-09-22).
- Title: `Camera telecentric lens`.
- Applicant/assignee: Changzhou AAC Raytech Optronics Co., Ltd.; inventor:
  Takaaki Teranishi.
- `US-20250102782-A1` is the application publication; `US-12585096-B2` identifies
  that A1 as its prior publication. The two roots therefore form one exact family,
  not two independent optical designs.
- Official HTML source locks:
  - B2 raw SHA-256
    `5bd759cb65d3d9815f6218a79994b91201eb58bb399bea6891abb5673f453987`,
    parser-normalized SHA-256
    `50209f643a66dde1859ee71576e3558b832b9c47b12ff901ecb6db8acd11080c`.
  - A1 raw SHA-256
    `0d6559cf2668051684f43dc51245307286441d21d0c558ee66728d0d2f1c7625`,
    parser-normalized SHA-256
    `3b9bfd136910fe58e15feeb9dc1b35c750eb3ac3aafd1ba21888faae42840fae`.

## Complete source denominator

The official PDFs have no text layer and contain exactly one decoded bilevel page
image per page. The B2 denominator is 27/27 pages; the A1 denominator is 29/29
pages. Every page was decoded and hashed. The two B2 wrappers agree on all 27/27
decoded page rasters. Both live A1 wrappers and the Google-hosted A1 wrapper agree
on all 29/29 decoded page rasters. The wrapper byte hashes differ, so equivalence is
asserted only from decoded page evidence, not from container-byte equality.

Both publications declare FIGS. 1-28 across 14/14 drawing sheets (PDF pages 2-15).
Each of seven embodiments has four figures: optical layout, longitudinal aberration,
lateral color, and field-curvature/distortion evidence. The reviewed prescription
denominator is TABLES 1-8:

| Publication | Reviewed PDF pages | Table binding |
|---|---:|---|
| B2 | 21-26 | p21 T1; p22 T2; p23 T3/T4; p24 T5/T6; p25 T7; p26 T8 |
| A1 | 22-27 | p22 definitions/T1; p23 T2/T3; p24 T4; p25 T5/T6; p26 T7; p27 T8 |

The full per-page raster hashes, wrapper hashes, image counts, page sizes, retained
full-resolution table pages, and contact-sheet hashes are recorded in
`family-89001540-raster-audit.json`.

## Optical-system audit

TABLES 1-7 describe seven finite-object, object-space telecentric, nine-lens systems
with object/working-distance rows, G1-G9, R1-R18, thicknesses, lens refractive
indices/Abbe numbers, an aperture S1 between G6 and G7, and a beam-splitting prism.
TABLE 8 publishes whole-system and component focal lengths. The whole-system focal
lengths are `140.015`, `228.181`, `192.943`, `139.411`, `167.106`, `92.494`, and
`143.161` mm. Every embodiment publishes full-field image height `18.5` mm.

The source is insufficient for deterministic construction:

- It publishes beam-splitter thickness but no beam-splitter refractive index, Abbe
  number, or material identity.
- It publishes no F-number/FNO/F/# value. Numerical aperture and entrance-pupil
  diameter are not interchangeable with F-number for this finite-conjugate
  telecentric system and are not used to manufacture one.
- Embodiment 1 publishes `NA = 0.13` and entrance-pupil diameter `4633.628` but no
  numeric angular field. Embodiments 2-7 publish diagonal angular fields
  `0.01`, `0.03`, `0.02`, `0.00`, `0.03`, and `0.02` degrees.
- TABLE 7 visibly contains an extra chain before G4:
  `d6-BS`, `dBS`, `dBS-S1`, `dS1-7`. The prose defines the beam splitter between
  G6 and G7 and defines the later `d11-BS` chain. The extra chain is therefore an
  unresolved source identity/spacing contradiction, not an HTML extraction glitch.
  It appears in both official publication rasters (B2 p25 and A1 p26) and is not
  repaired.

## Fail-closed disposition

The exact source profiles retain all seven embodiments as terminal source outcomes;
they do not create a ZMX worker task:

| Embodiment | Terminal reason |
|---:|---|
| 1 | `metadata_unpublished.beam_splitter_material_f_number_and_angular_field_absent` |
| 2-6 | `metadata_unpublished.beam_splitter_material_and_f_number_absent` |
| 7 | `metadata_unpublished.beam_splitter_material_f_number_and_table7_spacing_identity_absent` |

Any drift in the raw source hash, parser-normalized hash, family/application
relationship, figure/table denominator, table digest, published metadata, or TABLE 7
spacing text reopens parser review. No source gap is filled by inference.
