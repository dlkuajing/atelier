# Family 59199108 source audit

## Identity and relationship

- `US-20240411113-A1` and `US-12298484-B2` are the publication and grant for application
  `18/743044`, Family ID `59199108`, title `Optical lens set`, and owner
  `Genius Electronic Optical (Xiamen) Co., Ltd.`. The B2 Prior Publication Data names A1.
- Retained official HTML SHA-256 values are
  `1197f4ec4bb5df4a37e2b93c1bf5292aab4b2f27fdfede1e09e0d0a896807da8` (A1) and
  `7a3936c854f9d03ed76cc79656f9fbcb69946c78a3020c9b43708d5a9b9b615b` (B2).
  Parser-normalized hashes are
  `8d9964870318343219462cd3ad79b2d7b9666b5c059c52c29a758d50c194ecc1` and
  `a1f8dbbf0ff28ef241acc6a1097965b42193956b46974fb998bacd0831ce9897`.
- Official related-document data gives a five-generation continuation chain through applications
  `18/119300`, `17/502019`, `17/351263`, `16/792894`, and `15/441253`, with priority
  `CN201611254134.1` dated 2016-12-30. Their five A1 publications and five grants are absent from
  the frozen 619-root cohort and are retained in `family-59199108-external-family-members.json`
  for post-frozen intake.

## Complete source denominator

Each official PDF has 36 pages. Pages 2-26 are all 25 drawing sheets, each page is image-only and
contains one decoded raster, and FIGS. 1-35 account for every numbered figure. Pages 11-24 bind
seven exact optical/asphere pairs: FIGS. 20/21, 22/23, 24/25, 26/27, 28/29, 30/31, and 32/33.
Pages 25-26 contain comparison FIGS. 34-35. Thus the key denominator is 16 pages: fourteen
example-table pages and two comparison pages.

The prose declares exactly seven examples. Each example publishes a seven-lens optical table and
an asphere table. Optical-table OCR finds seven lens rows per example, while the two-panel asphere
tables declare `K`, `A2`, `A4`, `A6`, `A8`, `A10`, `A12`, `A14`, and `A16`. The source also directly
publishes these system values:

| Example | TTL (mm) | Fno | Image height (mm) | HFOV (deg) | Optical-table EFL (mm) |
|---|---:|---:|---:|---:|---:|
| 1 | 5.5600 | 1.6239 | 3.241 | 38.0038 | 4.2413 |
| 2 | 5.3991 | 1.6025 | 3.238 | 38.0020 | 4.1379 |
| 3 | 5.3665 | 1.6197 | 2.420 | 30.1264 | 4.1320 |
| 4 | 5.3157 | 1.6115 | 3.225 | 37.9995 | 4.1078 |
| 5 | 5.3343 | 1.6059 | 3.237 | 37.9981 | 4.1035 |
| 6 | 5.0626 | 1.6014 | 3.176 | 37.9978 | 3.8729 |
| 7 | 5.5733 | 1.6110 | 3.238 | 37.9627 | 4.2062 |

These values are census evidence only. No optical or asphere numeric cell is promoted into a
prescription unless every required label, occurrence count, and OCR-confidence gate passes.

## Official-raster reconciliation

The two official PDFs have no text layer. Two independently downloaded PPUBS wrappers were
retained per publication. Wrapper bytes differ, while all 36 decoded page rasters are identical
between the two live wrappers for the same publication. The retained official PDF and Google OCR
overlay also have 36/36 pixel-identical decoded page rasters according to the replay manifests.
Every page was included in the contact-sheet audit; the 16 key pages retain their official page
image hashes and OCR provenance.

| Publication | Official PDF SHA-256 | Live wrapper SHA-256 values | Stable raster-set SHA-256 | Contact SHA-256 |
|---|---|---|---|---|
| A1 | `9f16309e6ce541068e0b53496f28706ac0a638c250b3a6a36c3601d2d02b7a88` | `879a5f20723b34160a3187e23c75d945b2424662fa5b193e920930df436e5be4`, `5f7ae605ea78190bcbb1269aa198124087cc16533b9d4913aeac42de6f642d4d` | `d5a61859795c5e931576977d4bef1de397665e9582cd5d6b4e2b45dfab7d8a6f` | `b2105824b8c4093822cfdc53b66f6b8c8d04d44e9461adf73b8ebde687ff0ea9` |
| B2 | `5c7eaf5c6585f30451a1c16931351ca3bd030c9ce780b5c6592733ad5b69a65b` | `c2f50c56fb27e803e99d7f8cbfbbf06946aa47cd0f5358354ade9ce1e9c70202`, `6e1bd37109900a7902c6b1d34547129d6e03c6c131d44f6e1e94f4a99cdd29b9` | `e411c4db38841d25930e3cbcc8b418cac6e01e0d70b5f1ceb14da54f4906acab` | `557055c9a721ae7dbf81b30e7e6731a2e20e096d77b381c29e5699ffcc98b72f` |

## Fail-closed outcome

The new `genius_seven_lens_seven_example_census_v1` profile source-locks both raw/normalized HTML
identities, application/family/owner facts, all fourteen example figure declarations, both
comparison declarations, all seven prose metadata tuples, the 36-page denominator, page/figure
bindings, per-role OCR scale, and required rotations. It emits exactly seven parser-review items per
root.

No prescription is accepted. The observed failures are source-faithful: low-confidence labels or
missing duplicate label occurrences in dense rotated asphere panels, plus isolated optical-table or
drawing-sheet labels below the confidence gate. Representative observed confidences include
`a12=0.897030`, `a10=0.923734`, `Curvature=0.937332`, `FIG.31=0.941667`, and a drawing-sheet header
at `0.945673`. There is no deterministic basis to repair, interpolate, or borrow those cells from
the family peer, so neither root receives a conversion worker, request, receipt, candidate, or ZMX.

Attempts 2 and 3 are append-only and byte-distinct only because of `result_attempt`. Their canonical
semantic SHA-256 values are
`8cd0db87eef5b3b69f7fe0f4098340d259414107d0220580eda3ada4bd0cdc60` (B2) and
`a1c060f58a1eabf4f8d3353f75efd58c9db91e2f4cf9536c3ff6d8b4998cc51b` (A1).
The resulting strict 619-root set is
`261a2747bba7ce93612121c408404742b1f75871289c6999c9f05df7837b30e6`, with no missing or
corrupt result. The generic census moves from 163 to 161 roots/items; two independent after-census
runs both produce `b45149cc9a064b42e6cff9c84c7ab8db816a98c05b926296cf64bce980dd8432`.
