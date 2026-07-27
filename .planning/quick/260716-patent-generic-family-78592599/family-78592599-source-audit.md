# Family 78592599 source audit

## Identity and relationship

- `US-11832791-B2` and `US-20230091208-A1` share Family ID `78592599`, application
  `17/477544`, title `OPTICAL IMAGING LENS ASSEMBLY AND ENDOSCOPIC OPTICAL DEVICE`, and
  Altek Biotechnology ownership. B2 Prior Publication Data explicitly names A1 with publication
  date March 23, 2023.
- Retained official HTML SHA-256 values are
  `2ef9a1fbb3aad09317228a9db6d30d1b9fad67059b7fae25e21655d96301451f` (B2) and
  `0ba2fa9864b8a3fc1b2b60af0dfc241eb55b0dcb953ea4f6cafeb3a0a34e475a` (A1).
  Parser-normalized text hashes are
  `8d5d3edad4daa9845193bdd0e7d0e4d6a530c04a0ee9f334011c319fd7d3c699` and
  `78b1cb4de4dc2a7a82e7e19e7c34e0c40725b05d9a17c32ea2ef7fed6c3a47eb`.

## Source denominator and item mapping

Each publication declares 11 figures, nine numbered tables, and three table-bound optical imaging
lens assembly embodiments:

| Ledger item | Optical embodiment | Layout / performance figures | System / surface / asphere tables |
|---:|---|---|---|
| 1 | first | 3 / 4 / 5 | 1 / 2 / 3 |
| 2 | second | 6 / 7 / 8 | 4 / 5 / 6 |
| 3 | third | 9 / 10 / 11 | 7 / 8 / 9 |

FIGS. 1 and 2 are two endoscopic-device functional-block variants. They contain no independent
optical prescription, example table, or system row and both reference the same optical imaging
lens assembly component. They are reconciled as device-wrapper figures and excluded from the
prescription-item denominator rather than duplicated as optical designs. There is no fourth
optical embodiment and no example anchor.

For every optical embodiment, the system table publishes EFL, f1/f2/f3, HFOV, and five ratios;
the surface table publishes the object, six lens surfaces, aperture stop, filter, and image plane
with radius, thickness/air gap, refractive index, and Abbe number; and the asphere table publishes
K plus A4/A6/A8/A10/A12 for all six lens surfaces. All nine normalized table blocks are
independently hash-bound by publication in the exact source profile.

The direct system values are:

| Embodiment | EFL | f1 | f2 | f3 | HFOV |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.43 | -0.35 | 0.60 | 0.59 | 60.00 |
| 2 | 0.43 | -0.34 | 0.60 | 0.60 | 60.00 |
| 3 | 0.42 | -0.33 | 0.60 | 0.59 | 60.00 |

Neither official HTML record contains `F-number`, `FNO`, a numeric `F/#` assignment, `aperture
number`, or `numerical aperture`. The aperture-stop rows publish position/thickness and infinite
curvature, not an entrance-pupil diameter or system F-number. No ratio or stop value is used to
derive the missing field.

## Official raster denominator

Both official PDFs have 15 single-image pages and no text layer. B2 drawing sheets 1-7 are pages
3-9; A1 drawing sheets 1-7 are pages 2-8. The seven sheets contain the complete FIG.1-FIG.11
sequence: two functional block diagrams, three optical layouts, three distortion plots, and three
relative-illumination plots. The all-page contact sheets were visually audited. The remaining
pages reproduce the same nine text tables and narrative; no hidden F-number label or additional
optical embodiment is present.

| Publication | Retained official PDF SHA-256 | Retained recheck wrapper SHA-256 | Stable raster-set SHA-256 | Contact SHA-256 |
|---|---|---|---|---|
| B2 | `74b6834df87f70ebeebd9474f757c759f4e89bb50d592eb92d024baa1489bd0b` | `f3a52016ee541d4741af3027d8285b7831f10153b484d89a23e6a3166e93294d` | `b2793099a9bf7dc90968dd9c8e405459f26af160756facff8d6b70328ce6594b` | `7c4eef607c103488035de47c20dea2afcc3fe406906d933578e9a850efcbba5d` |
| A1 | `93ee8b4991518148a202505d58e58691e213a596f713ca2e9f8fe7cc0ad1098e` | `1e8d62469ec7a97e182ca07e4ae0f1698eb223ca55c6837b74422df481d8b597` | `96843395393b074b90c322b36f0819926aad41e05b35837740f8116f3530a56a` | `a2704cf7bc8ebe4a55ac45e62aff1549cbdd75a198761e14d4e8f2fc4adfe3fa` |

The two live PDF wrapper hashes differ for each publication, while all 15 decoded page-raster
hashes are equal within each publication. Therefore wrapper equality is not claimed. Both wrappers
and the stable decoded-raster sets are retained; structured paths and drawing roles are in
`family-78592599-raster-audit.json` and rehash in the test suite.

## Fail-closed outcome

Profile selection requires an exact publication ID and raw/normalized official HTML hashes.
Application/family/prior-publication identity, 11 ordered drawing declarations and roles, three
optical embodiment-to-table bindings, nine ordered table numbers and digests, direct system rows,
surface/asphere structures, and five independent zero-count F-number label patterns are checked.
Any drift returns all three optical items to parser review.

Each optical item terminates as `metadata_unpublished.system_f_number_absent`. No F-number is
derived, no conversion worker is launched, and no receipt, prescription fingerprint, formal
candidate, or ZMX is created.
