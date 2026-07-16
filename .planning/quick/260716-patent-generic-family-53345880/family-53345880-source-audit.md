# Family 53345880 source audit

## Identity and denominator

- `US-20160161712-A1` and `US-9810879-B2` both publish Family ID `53345880`,
  application `14/832442`, assignee AAC Technologies Pte. Ltd., and the same title. The B2
  Prior Publication Data explicitly names `US 20160161712 A1`.
- Retained official HTML SHA-256 values are respectively
  `d442fce31a21057546974505b5aa3e5361304ad8525afe7455a4cb438bfb5600` and
  `cd5bc9f6cab04ac685e4dca612a9b974767d03f6021fd7527230bdbafc7d3047`.
  Recovery-normalized text hashes are
  `99c5ebf699ef689f6769d12e6a755c33eda8e3fac4021eccdf3f36abf693213d` and
  `f4b1e6f46bcf5d0bb7ab11e94de42ab706d8a488f58df6cd6a572e54e0bf086f`.
- Each publication declares exactly two embodiments. Each embodiment has one surface-data table
  and one asphere-coefficient table; TABLE 5 contains only the two systems' conditions. The
  denominator is therefore two prescriptions per publication, not one family summary and not
  four distinct inventions.

## Published optical evidence

The five ordered PPUBS table blocks are hash-bound independently for each publication. TABLES 1/2
belong to the first embodiment, TABLES 3/4 to the second, and TABLE 5 supplies the following direct
system values:

| Embodiment | focal length (mm) | F-number | published DOF (deg) |
|---|---:|---:|---:|
| first | 3.5246 | 2.8 | 33.41 |
| second | 2.3412 | 2.6 | 37.72 |

The source expands the first `DOF` occurrence as `depth of feild` (source typo) and then uses `DOF`
for both numeric rows. There are exactly two `DOF` labels and one expansion. Neither source defines
DOF as field of view.

Both exact HTML records contain zero `FOV`, `HFOV`, `field of view`, and `angle of view` labels.
The drawing rasters and retained OCR views contain zero such labels as well. A depth-of-field value
is not substituted for a required optical field angle. Consequently both real prescriptions in
each publication have an unpublished required system field and must fail closed as
`metadata_unpublished.system_field_of_view_absent`.

## Figures, official PDF, and exact-raster recovery

Each source declares exactly FIGS. 1-4. FIGS. 1/2 are the first/second embodiment layouts and
FIGS. 3/4 are aberration plots. The two drawing sheets are PDF pages 2/3 and are explicitly headed
Sheet 1 of 2 / Sheet 2 of 2.

| Publication | Pages | Official PDF SHA-256 | Google PDF SHA-256 | Raster-set SHA-256 |
|---|---:|---|---|---|
| A1 | 7 | `f310f3984e28678cde3ad38ab239ebe4a3ac51ebcf5cbdfc83ace6d9c813339e` | `b6eac91b9a645ca0a5f25700349dcbbeb435115fdb74ec9c066102fd922d9e6d` | `8b3a12f46f899021c4e1f02c4e8a0890d7428835db3cc61f05b2ada6177cd085` |
| B2 | 7 | `fa7b3a3d795ec9778e44bd3bb6e2b5573c272bbd34abd33b3334deace825a33c` | `d8d4b80e34212c50d3c1e65b1de3eb15f36b055d170f9ccec712916afc9ac8ca` | `c8718a19ba6b60b5330d5f378d863590bf75d3eaf80fdc383e476bf2348dbcbb` |

- Every official and Google PDF page contains exactly one image. All seven raster pairs for each
  publication are pixel-identical, and both Google overlay blank-page sets are empty. Raster-set
  hashes are SHA-256 over compact JSON of the ordered official-page image hashes.
- A1 page 2 OCR retains 28 tokens (15 at confidence >=0.90), including FIG. 1 at 0.979564 and
  FIG. 2 at 0.999848. Page 3 retains 17/5, with FIG. 3 at 0.998410 and FIG. 4 at 0.996423.
  B2 pages 2/3 retain 30/14 and 29/6; corresponding figure confidences are 0.983096,
  0.999733, 0.999744, and 0.999819.
- Canonical parser inputs are
  `9ca71958edbc57661c8e0b1c9fc02b7cd582a6d114b4de6ae67810a4c87faa49` (A1) and
  `87dbda75e49e9e077e252d3a6f82059797c0c88fa9c5aab7e558a260ce193f75` (B2).
  Recovery manifests are
  `ad508a2fc2b12eac7d2a49a60d9d16e3edf69736b61d35439b8c8959a560d0a7` and
  `c1fb6604471c999ca3df398c6e92ab66136127c456e680ce0fbbc655e102efdc`;
  source pins are
  `418063f9f5fbe8ed81e194112391ebabea2f718204bafbe4ecc13da2e09547bc` and
  `f1b7ff42f36865e9cf0bcea99ece975a452d095cf796c76242a6207a95675c6f`.
- All-page contact sheets were inspected. Their SHA-256 values are
  `e3e2f21ea391f209887f79f737e1f902975d3f6409fa566c56da9c7d64916cb1` and
  `22e1002f3a740308f86cbb48c1350d01005799d7623946ac8366121ae7cec3ac`.
  Pages 2/3 contain only layouts and aberration plots; pages 5/6 expose the five textual tables.

## Fail-closed decision

Profile selection requires one of the two exact official HTML hashes plus all four figure
declarations. Application/family identity, five ordered table digests, table roles, both direct
system-value triples, exact DOF label/expansion counts, seven-page raster equality, drawing-sheet
headers, figure OCR, and zero field labels must all remain true. Any drift returns to parser
review. No trace worker, conversion receipt, request fingerprint, formal candidate, or ZMX is
created.
