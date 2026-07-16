# Family 44121309 source audit

## Scope and family relationships

- All three frozen generic-summary roots identify Family ID `44121309` and the title
  `LOW THERMAL STRESS BIREFRINGENCE IMAGING LENS`.
- `US-8649094-B2` is application `12/784520` and identifies prior publication
  `US-20110292505-A1`.
- `US-20140036377-A1` is application `14/042755`, a continuation of application
  `12/784520`.
- `US-9069105-B2` is application `14/042755`, identifies `US-20140036377-A1` as its prior
  publication, and identifies `US-8649094-B2` as the continuation parent.
- `US-20110292505-A1` is not a member of the frozen 619-root cohort and is not claimed as
  audited or closed here. This shovel closes only the three measured roots; it is not a global
  family-closure claim.

## Exact official HTML sources

| Publication | Application | Raw SHA-256 | Normalized-text SHA-256 |
|---|---:|---|---|
| `US-20140036377-A1` | `14/042755` | `2efe34e5641c40bcb2c93d330d9288271b19f2d851f1bba26e03aef85d269819` | `8affd3aaf0079a69bd7d4a8e68fb31a653b857f6bcbd352b9666d696cd2be572` |
| `US-8649094-B2` | `12/784520` | `ddb70ad8434854ab534ae7fb26e1c015147b0ea1518c9ef792f5d112ede1c3e5` | `1c2a2c4c9be26ae4aa04bcbb80595ea827d5252f89a37c7210e2dc68595c0c98` |
| `US-9069105-B2` | `14/042755` | `2e5c75ff60cb61628fb6c256aa18b23a43adbfc04a60fac0974f8a60027173e8` | `e0196b6186bec0b637bfee3cfc5bdcad39fb273a9275e7894199cb5eff9f857e` |

Each exact source has the same measured disclosure:

- one binding each for FIG. 14A as the third projection-lens parameter table and FIG. 14B as
  the third relay-lens parameter table;
- two word-bounded `prescription` occurrences, and one statement that the FIG. 14A/14B designs
  were fabricated, assembled, and tested;
- one statement that all surfaces in the projection prescription are spherical rather than
  aspheric, toric, or cylindrical;
- zero numeric assignments to `F`, `FNO`, `FOV`, `HFOV`, or `EFL`, and zero occurrences of
  `effective focal length`;
- three generic `focal length` occurrences and one generic `field of view` occurrence, none
  bound to either prescription;
- exactly one occurrence each of the three retained F-number contexts: relay collection of F/6
  light, a preference for a projection lens about F/3 and faster than the relay, and a possible
  improvement operating at F/2.5 or faster. These contexts are counted but never substituted for
  prescription-specific system metadata.

## Official PDF and independent overlay evidence

| Publication | Official PDF SHA-256 | Overlay PDF SHA-256 | Pages | Key PDF pages | Exact blank overlay pages |
|---|---|---|---:|---|---|
| `US-20140036377-A1` | `f7625270e786d797d2c0d2b85391453634aa75531bb07dbd815be6032c7189af` | `b831b1c41eb695e18d08f477a1ce71abb734a4e5756c6a777abb8388c4598de2` | 61 | 36, 37 | 7, 23, 30, 34, 37, 39 |
| `US-8649094-B2` | `04a60eb3f67a4a54f43f1f892fb877a08aabd4415d48e0b0334c6f3e176b91cf` | `aa8ceb56db138a4338ad4a68b6ae420e9e4703e3d905848ff4ae002f5da2f39f` | 60 | 37, 38 | 12, 14, 19, 21, 22, 26, 30, 39 |
| `US-9069105-B2` | `7c19df97137773281b8b6036b373a3e3b2a2e7cb482a56946ad32895d954e7b8` | `0ad165c81b5794346f677a46dc3c60e44fc10d8c9d3bca507ce886a95ba5989c` | 61 | 37, 38 | 12, 14, 19, 22, 23, 24, 28, 29, 30, 31, 34, 35, 38, 39 |

Every official page raster is pixel-identical to the corresponding Google overlay raster in all
three documents (zero mismatches). The retained source-pin hashes are respectively
`5f88af9ec2beec356da94f20145ef80e3013e21e590b02985382f07114beec99`,
`3ecf7c4b22d2a8d1a7e455a2bc6637378e358300c9d5f8fd8a6502b2bef0746f`, and
`205a052b9d52da252b1c394c489720db0013e06e36fa5098894f3c19d16d1c2d`.

The 39-sheet `US-9069105-B2` contact sheet and the full-resolution FIG. 14A/14B join were visually
inspected. FIG. 14A contains columns Surface/Radius/Thickness/Aperture/Glass, object `SCREEN`, a
stop, and image `INT IMG`; FIG. 14B contains the same columns, object `DLP`, an aperture stop, and
`INT IMAGE`. Neither sheet publishes EFL, FNO, FOV, or HFOV. No image-only prescription was
misclassified as absent.

## Deterministic OCR and terminal boundary

RapidOCR uses the source-bound `counterclockwise_90` rotation and the unchanged 0.95 label gate.
The canonical parser inputs are:

| Publication | OCR tokens on FIG. 14A/14B | Parser-input SHA-256 | Recovery-manifest SHA-256 |
|---|---:|---|---|
| `US-20140036377-A1` | 82 / 90 | `967e85f0393ec6342aa71d5d7b624ef282e52f73e4955cfac6bb8f905b7e5144` | `618944d3b2ef4bfc29b43099d5a480d39b537b8585a1ff72a9930a43d20b7e54` |
| `US-8649094-B2` | 84 / 94 | `6be7486154e7220c479c7b93f85c3e7843ccd186e66d800a40c4e82220a928f4` | `68714793597ddffc108f7ba5eadc3229863c8e6258eac29b02419e021ef04710` |
| `US-9069105-B2` | 85 / 95 | `86c4effe5dada8f5d3156d523ae3b7ec77aedf91a099605d4de3c11e4cab7f7b` | `51ff83fb29c014990dcfa97be0a5a2c29c60ea5321f610f8924edb562f2f894e` |

The parser accepts no table number. It uses OCR only to prove the unique figure/table structure
and absence of high-confidence system labels. Each root therefore expands to two source-proven
`metadata_unpublished.prescription_specific_efl_and_field_absent` terminals, one for FIG. 14A and
one for FIG. 14B. No EFL or field is inferred, no worker is started, and no ZMX is generated.
