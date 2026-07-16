# Family 48495278 source audit

## Identity and relationship

- `US-20150138653-A1` is application `14/608769`; its official related-document section declares
  a continuation of application `13/757675`. `US-8976467-B2` is application `13/757675`; its
  official Prior Publication Data names `US-20140071340-A1`, published 2014-03-13.
- Both retained documents publish Family ID `48495278`, title `Mobile device and optical imaging
  lens thereof`, Genius Electronic Optical ownership, and the same two Chinese priorities.
  `US-20140071340-A1` is not in the frozen 619-root cohort and is retained in
  `family-48495278-external-family-members.json` for post-frozen intake.
- Retained official HTML SHA-256 values are
  `cc17913116d0dc5ee3b49fcaf720e69824f8fd1cf2ea4c79aa94e8ae1c1da145` (A1) and
  `dc2eefd750653fe96b856789b279f2fe8b461cdf13fad7e39e9a89a03d38a2ed` (B2).
  Parser-normalized hashes are
  `62d6440ae13e941f8dff3394a3b998eefb8f42f9815352a9bf509809f4fdd0b2` and
  `1501a3dce84f0b68734dbc8691f7e3bb6ddfb7127a9064be12a7a572ccaf8f9b`.

## Complete source denominator

The HTML text layer contains zero tables and zero occurrences of `FNO`, `F-number`, `F/#`,
`HFOV`, or `field of view`; therefore it is not the prescription denominator. The prose declares
exactly six four-lens embodiments, twelve optical/asphere table figures (FIGS. 4/5, 8/9, 12/13,
16/17, 20/21, and 24/25), comparison FIG. 26, and mobile-device FIGS. 27-28. Every declared
FIG. 1-28 was located. Each PDF page contains exactly one decoded image.

| Publication | PDF pages | Drawing sheets | Declared/located figures | Declared/recovered table figures | Prose embodiments / ledger items |
|---|---:|---:|---:|---:|---:|
| `US-20150138653-A1` | 36 | 27 | 28 / 28 | 13 / 13 | 6 / 6 |
| `US-8976467-B2` | 31 | 21 | 28 / 28 | 13 / 13 | 6 / 6 |

The A1 key pages are 5/6, 9/10, 13/14, 17/18, 21/22, 25/26, and comparison page 27. The B2 key
pages are 5/6, 8/9, 11/12, 14/15, 17/18, 20/21, and comparison page 22. The other drawing pages,
cover/front matter, text pages, FIG. 26, and FIGS. 27-28 were retained in the all-page raster and
contact-sheet audit; there is no hidden extra prescription or table outside the denominator.

## Official-raster reconciliation

Three PPUBS container variants were retained for each publication, including the exact wrapper
selected by append-only replay. Their PDF wrapper bytes differ, but every decoded page raster is
equal. The Google OCR overlay is also pixel-identical to
the selected official wrapper on all 36 A1 pages and all 31 B2 pages. A1 has mirror text on every
page; B2 mirror page 12 is blank, and the exact blank-page set is source-locked.

| Publication | PPUBS wrapper SHA-256 values | Google PDF SHA-256 | Decoded equality | Contact SHA-256 |
|---|---|---|---|---|
| A1 | `a985d294a8f440b358dc29600dde0ff927e93751840614cbb9b14bffa8b8f7e4`, `2e66c4a87272ab311fb3a0cd6eb548294bf0bec9ad26512cfc3b7d395e27e4cf`, replay `fce561d8e3f2a85f60b6ba63cd459b5caaba506a0b122b45635331210b5379e3` | `6f54b0e5f7d1fa69de8fbc886e01b31d3e41482bec7c02871b93f935fbc90382` | 36/36 | `0a2f4b19033b228897918726213a7d4cfa5f1c13907d9a84578f1f9bdea7d7f0` |
| B2 | `7ed192b29ae52a2851a7992286f1dd9d28b80c4577b276b41eb0c6a1e942a494`, `6a5a81448b9482697895a356870303387b0573890d898b94435fb964c8c35026`, replay `39763dbca905ee204b2a4e8b3ad5fae634be44f5ddec10b2282bc37307192572` | `09ca8c75f3d7d4222291ae307a8e3ec0c145fc201d97c75d64b1df4a4603c8b9` | 31/31 | `99b321156e15f3749f8074a6d47015ec6e6c18414fe328a701874b5d378f14b9` |

The full raster audit SHA-256 is
`4548cf92729b7b0f4b92c0de0a5a86595533f023f8259dd36db03b4e7b1aae83`; the independent
26-key-page RapidOCR audit is
`27d5f1b8e1e63f9b9036376a06ceea9f6576bc5a748958964e42b973d36cb107`. A production recovery
rerun reproduced every RapidOCR token exactly; mirror text differs only in whitespace and is equal
after whitespace normalization. Its evidence artifact is
`db0e7d42b37ee16413c4df0dc37f4202f76e9e645b9fa9ce643a63c29f7dfb07`.
The exact replay source-pin JSON files are retained beside the selected PDF wrappers, with SHA-256
`3ad0c7c24e06c3b92c30140fa93c2eed5834c394ccf90fd55b97d60a0f472c65` (A1) and
`5537f23db483d134ced7989f302849e43262522617e237f06d465a9481055f16` (B2).

## Published system values and correction

The initial generic parser error incorrectly suggested that embodiment `f/Fno/HFOV` data was not
found. The official raster does publish these fields: each optical table has an `f(Focus)` and
half-angular-field line, while FIG. 26 directly publishes Fno values `2.536`, `2.591`, `2.811`,
`2.790`, `3.029`, and `2.537` for embodiments 1-6. These are source census facts, not accepted
prescription cells.

The data still cannot be converted deterministically. The A1 FIG. 26 `Fno` label has confidence
`0.800164`, and values `2.591` and `3.029` have confidence `0.934143` and `0.925040`; the B2 Fno
numbers pass the numeric gate but its label confidence is `0.919803`. Optical rows retain isolated
low-confidence or missing labels, and the dense asphere panels retain real missing/misread duplicate
labels and coefficient tokens. Examples include a drawing-sheet header at `0.949288`, `Surface` at
`0.947064`, `Refractive` at `0.848627`, missing duplicate `a4/a6/a8/a10/a12` labels, and OCR strings
such as `1.8897B+01` and `-2.1706E ±00`. No cell is repaired, interpolated, derived, or borrowed
from the family peer.

## Fail-closed outcome

The exact `genius_four_lens_six_embodiment_census_v1` profile source-locks both raw and normalized
HTML identities, application/family/owner/priority/relationship facts, the 6-embodiment and
28-figure denominator, all 67 page rasters, each key page/sheet/figure role, the mirror blank-page
set, and OCR label/numeric confidence gates. It emits exactly six `deterministic_parser_rejected`
items per root. Neither root receives a prescription, conversion request, worker receipt,
fingerprint, candidate, or ZMX.

Attempts 2 and 3 are append-only. After excluding only `result_attempt`, their canonical semantic
SHA-256 values are
`909deaf10b565b79011a88f4656148c02c1722500f9294db0da3e858bcf9c207` (A1) and
`b9a50e93e90cecd9f7249cefeb076fcd113eb3d103f78b7f443efd255e4e6562` (B2). The strict
619-root result set is `eb1d03194b2e6f7daa50d14f4fe4409518e0a63df7a7e2be1b4ad3a55bd6076e`, with no
missing or corrupt result. Generic census moves from 157 to 155 roots/items; two independent runs
both produce `1a112e9d347999b23462cf363a961ca3d30b169529ba50b0858b4c8a05172b22`. All 400
offline patent tests pass.
