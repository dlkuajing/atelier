# Family 55525612 source audit

## Identity and denominator

- `US-20160085051-A1` and `US-9541733-B2` both publish Family ID `55525612`,
  application `14/858521`, title `IMAGING LENS ASSEMBLY`, and Taiwan priority
  `2014-09-24`. The B2 Prior Publication Data names `US 20160085051 A1`.
- Retained official HTML SHA-256 values are respectively
  `a389c98016a9f5af18165a30a2041fe29a761d3d37958ffce100e8bfb81ea50d` and
  `e9fee581375c0ca2c0946fe8b27032c078f14aa82e90aa6365889cd4667319f0`.
  The recovery-normalized text hashes are
  `a7a4d8d7489ef8db8b76b64868fdcf31cfc32b37934a5c17f39484893f212b1f` and
  `5089537a9bb04df736b4cef2a4146e377b92aced134d7432870fddde145b205c`.
- Each source contains exactly one detailed specification for each of the first through fifth
  embodiments. Therefore the denominator is five prescriptions per publication, not one family
  summary and not ten independent inventions.

## Published optical evidence

Each source binds the same eleven image-only table declarations exactly once: surface tables in
FIGS. 3/7/11/15/19, asphere tables in FIGS. 4/8/12/16/20, and the five-embodiment comparison in
FIG. 21. There are zero PPUBS `TABLE-US` tables because the tables are drawing rasters.

The five detailed HTML paragraphs directly publish the following system values. These are source
values only; no ratio is treated as a substitute for a missing field.

| Embodiment | EPD (mm) | f (mm) | full FOV (deg) |
|---|---:|---:|---:|
| first | 0.666 | 1.619 | 84.0 |
| second | 1.075 | 2.408 | 84.0 |
| third | 1.178 | 2.393 | 84.0 |
| fourth | 1.097 | 2.227 | 87.0 |
| fifth | 1.124 | 2.716 | 77.4 |

The same paragraphs also publish OL, f3, Vd1/Vd2/Vd3, SD32, R1-R5, summed center
thickness, f1, D12, D23, TL, YC32, SAG31, SAG22, and CT3. The surface-table rasters expose
radius of curvature, thickness, refractive index, Abbe number, and effective focal distance; the
asphere-table rasters expose `k` and coefficient columns. Thus these are real prescriptions, not
architecture-only figures.

Neither official HTML contains `FNO`, `F-number`, or `F/#` (all three exact label counts are zero).
The retained OCR views contain no such label either. Although `f` and EPD are published, deriving
`f/EPD` would invent a required system field and is forbidden. The source-proven outcome is five
`metadata_unpublished.system_f_number_absent` items per publication.

## Official PDF and exact-raster recovery

| Publication | Pages | Official PDF SHA-256 | Google PDF SHA-256 | Raster-set SHA-256 |
|---|---:|---|---|---|
| A1 | 27 | `0e8c2ae7bfa2d96abc06215920a02bab8cd86f90eaac32de5b0567ef076f0115` | `cac485a4bda0a1d3ff483795d4f0c1295b5b52eecee53c7b6ee8d42bf92ea056` | `68cc39a52dcd2eedc7cba7e66814182d8301c92e5ca5af8b1b41ec7571c059fb` |
| B2 | 26 | `6204860e8417a6d60b59f8b620f25a1b0f564e26f2017b0438567f37f9c1d206` | `abe79dcdb9e0fa2d7223ae9df880938db35c50dc77571d37d44fce4dcc037a62` | `7a5db3a1658b677a2da1960032a7dd13e3993ba6561cd32701a935a882b35fc1` |

- Every official and Google PDF page contains exactly one image. All 27 A1 decoded raster pairs
  and all 26 B2 pairs are pixel-identical. The raster-set hash is SHA-256 over compact JSON of the
  ordered canonical raster hashes.
- Google overlay blank-page sets are `{}` for A1 and `{3,4,12,17,21}` for B2. These exact sets are
  source-locked; key pages always use RapidOCR on the official raster.
- Fixed key pages are 4/5, 8/9, 12/13, 16/17, 20/21, and 22. Across A1, surface/asphere pages
  retain 62-98 OCR tokens and at least 28/60 numeric tokens at confidence 0.90; FIG. 21 retains 90
  tokens and 62 such numbers. Across B2 the corresponding ranges are 61-98, at least 26/60, and
  92 tokens/63 numbers. Figure, table-column, embodiment, and FOV labels are independently checked.
- Canonical parser inputs are
  `ec2895a458fb4ecb70d6c6f84942149f52d15859480843dd4fe453dedb9eb54f` (A1) and
  `5fa63ba7c9b0160f45f90dbca391a200cf0df052b714b6de0fc4ea32cb1c1200` (B2).
  Recovery manifests are
  `421646ce71e474a95642961b4407a44f772e2d3c404124a55989f9211115b633` and
  `a2779d8ef689bddc5213b1bc91127a6416d910c26a653d5ab134f912d1d78c3d`.
- All-page contact sheets were inspected. Their hashes are
  `37a7fb22c32c9da5301b15ca8e90a121b70751a2ab5deb56feea15b429c849ed` and
  `6976ed16af9a5481e4c4a88bd9b64a9b58d77160aca92da3850f6d1e73ac1467`.

## Fail-closed decision

Profile selection requires one of the two exact official HTML hashes plus every figure marker.
Page counts, overlay blank sets, drawing-sheet headers when present, decoded raster equality,
eleven fixed roles, numeric table coverage, all five direct system-value bundles, and zero
F-number labels must all remain true. Any drift returns to parser review. No trace worker,
conversion receipt, fingerprint, formal candidate, or ZMX is created.
