# Phase 12 shovel 4A — SEKONIX + NEWMAX conversion ledger

## Honest yield summary

- targeted patents: 29/29 accounted (SEKONIX 17; NEWMAX 12)
- pipeline embodiment results: 107 (success 18; failed 88; duplicate prescription 1)
- converted: 18 embodiments from 4 patents; all staging artifacts remain outside the formal case index
- census table-count estimate for this target list: 141 embodiments (SEKONIX 73; NEWMAX 68, including the 7 estimated for census-partial US-12474548-B2)
- census estimate vs observed results: 141 -> 107 accounted (-34, -24.1%); 141 -> 18 converted (-123, -87.2%)
- scope note: the task specified 12 NEWMAX patents, while the census detail has 11 exact `parseable-with-new-family` rows. The twelfth target, US-12474548-B2, is marked `partially` in the census and is included here to honor the specified 12-patent wave.

### Family yield

| family | patents accounted | embodiment results | converted | failed | duplicate | patents with conversion |
|---|---:|---:|---:|---:|---:|---:|
| SEKONIX | 17 | 61 | 0 | 61 | 0 | 0 |
| NEWMAX | 12 | 46 | 18 | 27 | 1 | 4 |
| **total** | **29** | **107** | **18** | **88** | **1** | **4** |

### Fail-closed reason categories

These counts classify every non-success row below exactly once. `other` contains 73 remaining fail-closed parser-shape errors plus one exact duplicate prescription; no parser behavior was relaxed.

| category | SEKONIX | NEWMAX | total |
|---|---:|---:|---:|
| metadata missing exact instance values | 2 | 4 | 6 |
| glass code unresolved or nd/vd unavailable | 9 | 0 | 9 |
| Qcon fail-closed | 0 | 0 | 0 |
| ray-trace failure | 0 | 0 | 0 |
| other | 50 | 24 | 74 |
| **total non-success** | **61** | **28** | **89** |

### Converted design readout

FOV below is full field (`2 × hfov_deg`) computed from the pipeline-published half-field value; EFL, F-number, and surface count are the pipeline values in each success row below.

| patent | embodiment | EFL mm | F/# | full FOV deg | surfaces |
|---|---|---:|---:|---:|---:|
| US-10101561-B2 | Embodiment 3 | 3.35432 | 2.20 | 84.00 | 15 |
| US-12596237-B2 | Embodiment 1 | 2.34505 | 1.21 | 149.87 | 14 |
| US-12596237-B2 | Embodiment 2 | 2.32549 | 1.20 | 151.93 | 14 |
| US-12596237-B2 | Embodiment 3 | 2.31693 | 1.20 | 152.14 | 14 |
| US-12596237-B2 | Embodiment 4 | 2.31929 | 1.20 | 153.35 | 14 |
| US-12596237-B2 | Embodiment 5 | 2.30761 | 1.19 | 155.14 | 14 |
| US-12596237-B2 | Embodiment 6 | 2.20417 | 1.29 | 151.83 | 14 |
| US-12596237-B2 | Embodiment 7 | 2.79908 | 1.29 | 142.51 | 14 |
| US-12578548-B2 | Embodiment 1 | 1.26532 | 2.00 | 190.00 | 18 |
| US-12578548-B2 | Embodiment 2 | 1.30859 | 2.00 | 190.00 | 18 |
| US-12578548-B2 | Embodiment 3 | 1.39385 | 2.00 | 190.00 | 18 |
| US-12578548-B2 | Embodiment 4 | 1.27211 | 2.00 | 192.00 | 18 |
| US-12578548-B2 | Embodiment 5 | 1.07671 | 2.05 | 190.00 | 18 |
| US-20260063869-A1 | Embodiment 2 | 14.6927 | 2.58 | 36.20 | 12 |
| US-20260063869-A1 | Embodiment 3 | 13.2521 | 2.15 | 36.70 | 12 |
| US-20260063869-A1 | Embodiment 4 | 12.8763 | 2.38 | 37.80 | 12 |
| US-20260063869-A1 | Embodiment 5 | 13.4642 | 2.38 | 36.30 | 12 |
| US-20260063869-A1 | Embodiment 6 | 13.0458 | 2.48 | 40.50 | 12 |

## Pipeline run summary

- target_successes: 201
- attempts: 107
- successes: 18
- success_rate: 18/107 (16.8%)
- rechecked_failures: 89
- failure_reason_counts:
  - PatentParseError: 88
  - duplicate_prescription: 1
- source: local data/patents/uspto-smartphone-batch*.jsonl + USPTO PPUBS HTML
- parser: deterministic NFKC-normalized embodiment table parse; no numeric LLM fill
- clear_aperture: ZMX -> zmx_ingest/Optiland real-ray sampled per-surface envelope; f*tan(HFOV) is sanity-only
- imh: Optiland edge-field finite-ray image height persisted in report and ZMX tail comments

## Per-patent attempts

| patent | embodiment | status | zmx | efl_mm | real_imh_mm | f_tan_sanity_mm | field coverage | reason |
|---|---|---|---|---:|---:|---:|---|---|
| US-12474548-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12619054-B2 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX Glass Code cannot be split deterministically: 'D263T' |
| US-12498545-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12339423-B2 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX 3 radius is not numeric: , |
| US-12339423-B2 | SEKONIX embodiment 2 | failed |  |  |  |  |  | PatentParseError: SEKONIX 5 radius is not numeric: , |
| US-12339423-B2 | SEKONIX embodiment 3 | failed |  |  |  |  |  | PatentParseError: SEKONIX 7 radius is not numeric: , |
| US-12339423-B2 | SEKONIX embodiment 4 | failed |  |  |  |  |  | PatentParseError: SEKONIX 9 radius is not numeric: , |
| US-12339423-B2 | SEKONIX embodiment 5 | failed |  |  |  |  |  | PatentParseError: SEKONIX 11 radius is not numeric: , |
| US-12306384-B2 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX Glass Code cannot be split deterministically: BK7_SCHOTT |
| US-12306384-B2 | SEKONIX embodiment 2 | failed |  |  |  |  |  | PatentParseError: SEKONIX surface 1 row is incomplete |
| US-12306384-B2 | SEKONIX embodiment 3 | failed |  |  |  |  |  | PatentParseError: SEKONIX Glass Code cannot be split deterministically: BK7_SCHOTT |
| US-12306384-B2 | SEKONIX embodiment 4 | failed |  |  |  |  |  | PatentParseError: SEKONIX Glass Code cannot be split deterministically: BK7_SCHOTT |
| US-12306384-B2 | SEKONIX embodiment 5 | failed |  |  |  |  |  | PatentParseError: SEKONIX Glass Code cannot be split deterministically: BK7_SCHOTT |
| US-12235412-B2 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX 2 radius is not numeric: , |
| US-12235412-B2 | SEKONIX embodiment 2 | failed |  |  |  |  |  | PatentParseError: SEKONIX 4 radius is not numeric: , |
| US-12235412-B2 | SEKONIX embodiment 3 | failed |  |  |  |  |  | PatentParseError: SEKONIX 6 radius is not numeric: , |
| US-12235412-B2 | SEKONIX embodiment 4 | failed |  |  |  |  |  | PatentParseError: SEKONIX 8 radius is not numeric: , |
| US-12235412-B2 | SEKONIX embodiment 5 | failed |  |  |  |  |  | PatentParseError: SEKONIX 10 radius is not numeric: , |
| US-10101561-B2 | Embodiment 1 | failed |  |  |  |  |  | PatentParseError: NEWMAX A row has nonnumeric data token: positive |
| US-10101561-B2 | Embodiment 2 | failed |  |  |  |  |  | PatentParseError: NEWMAX A row has nonnumeric data token: positive |
| US-10101561-B2 | Embodiment 3 | success | data\zmx_staging_p12\US-10101561-B2-e3.zmx | 3.35432 | 3.12693 | 3.01635 | surfaces=15; r=15/15; d=15/15; nd_vd=6/15; asphere_surfaces=10; f_mm=3.35; f_number=2.2; hfov_deg=42.0; real_image_height_mm=3.1269300571956795; sanity_image_height_mm=3.0163535483977637; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20180113281-A1 | Embodiment 1 | failed |  |  |  |  |  | PatentParseError: NEWMAX A row has nonnumeric data token: positive |
| US-20180113281-A1 | Embodiment 2 | failed |  |  |  |  |  | PatentParseError: NEWMAX A row has nonnumeric data token: positive |
| US-20180113281-A1 | Embodiment 3 | duplicate_prescription |  |  |  |  | surfaces=15; r=15/15; d=15/15; nd_vd=6/15; asphere_surfaces=10; f_mm=3.35; f_number=2.2; hfov_deg=42.0; sanity_image_height_mm=3.0163535483977637 | duplicate_prescription: prescription fingerprint\|duplicate_prescription a7d7cc7c954a3997 |
| US-12174344-B2 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX 2 radius is not numeric: , |
| US-12174344-B2 | SEKONIX embodiment 2 | failed |  |  |  |  |  | PatentParseError: SEKONIX 4 radius is not numeric: , |
| US-12174344-B2 | SEKONIX embodiment 3 | failed |  |  |  |  |  | PatentParseError: SEKONIX 6 radius is not numeric: , |
| US-12174344-B2 | SEKONIX embodiment 4 | failed |  |  |  |  |  | PatentParseError: SEKONIX 8 radius is not numeric: , |
| US-12174344-B2 | SEKONIX embodiment 5 | failed |  |  |  |  |  | PatentParseError: SEKONIX 10 radius is not numeric: , |
| US-20240184081-A1 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX Glass Code cannot be split deterministically: BSC7_HOYA |
| US-20240184081-A1 | SEKONIX embodiment 2 | failed |  |  |  |  |  | PatentParseError: SEKONIX Glass Code cannot be split deterministically: BSC7_HOYA |
| US-20240184081-A1 | SEKONIX embodiment 3 | failed |  |  |  |  |  | PatentParseError: SEKONIX Glass Code cannot be split deterministically: BSC7_HOYA |
| US-20240053586-A1 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX Glass Code cannot be split deterministically: 'D263T' |
| US-20230048740-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20220326489-A1 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX 3 radius is not numeric: , |
| US-20220326489-A1 | SEKONIX embodiment 2 | failed |  |  |  |  |  | PatentParseError: SEKONIX 5 radius is not numeric: , |
| US-20220326489-A1 | SEKONIX embodiment 3 | failed |  |  |  |  |  | PatentParseError: SEKONIX 7 radius is not numeric: , |
| US-20220326489-A1 | SEKONIX embodiment 4 | failed |  |  |  |  |  | PatentParseError: SEKONIX 9 radius is not numeric: , |
| US-20220326489-A1 | SEKONIX embodiment 5 | failed |  |  |  |  |  | PatentParseError: SEKONIX 11 radius is not numeric: , |
| US-11454785-B2 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX Stop radius is not numeric: (S2) |
| US-11454785-B2 | SEKONIX embodiment 2 | failed |  |  |  |  |  | PatentParseError: SEKONIX Stop radius is not numeric: (S2) |
| US-11454786-B2 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX surface 3600 row is incomplete |
| US-11454786-B2 | SEKONIX embodiment 2 | failed |  |  |  |  |  | PatentParseError: SEKONIX surface 3600 row is incomplete |
| US-11454786-B2 | SEKONIX embodiment 3 | failed |  |  |  |  |  | PatentParseError: SEKONIX surface 3600 row is incomplete |
| US-11454786-B2 | SEKONIX embodiment 4 | failed |  |  |  |  |  | PatentParseError: SEKONIX surface 3600 row is incomplete |
| US-11454786-B2 | SEKONIX embodiment 5 | failed |  |  |  |  |  | PatentParseError: SEKONIX surface 3600 row is incomplete |
| US-11409081-B2 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX Stop radius is not numeric: (S2) |
| US-11409081-B2 | SEKONIX embodiment 2 | failed |  |  |  |  |  | PatentParseError: SEKONIX 4 radius is not numeric: , |
| US-11409081-B2 | SEKONIX embodiment 3 | failed |  |  |  |  |  | PatentParseError: SEKONIX 6 radius is not numeric: , |
| US-11409081-B2 | SEKONIX embodiment 4 | failed |  |  |  |  |  | PatentParseError: SEKONIX 8 radius is not numeric: , |
| US-11409081-B2 | SEKONIX embodiment 5 | failed |  |  |  |  |  | PatentParseError: SEKONIX 10 radius is not numeric: , |
| US-20220128796-A1 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX 2 radius is not numeric: , |
| US-20220128796-A1 | SEKONIX embodiment 2 | failed |  |  |  |  |  | PatentParseError: SEKONIX 4 radius is not numeric: , |
| US-20220128796-A1 | SEKONIX embodiment 3 | failed |  |  |  |  |  | PatentParseError: SEKONIX 6 radius is not numeric: , |
| US-20220128796-A1 | SEKONIX embodiment 4 | failed |  |  |  |  |  | PatentParseError: SEKONIX 8 radius is not numeric: , |
| US-20220128796-A1 | SEKONIX embodiment 5 | failed |  |  |  |  |  | PatentParseError: SEKONIX 10 radius is not numeric: , |
| US-20220128795-A1 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX 2 radius is not numeric: , |
| US-20220128795-A1 | SEKONIX embodiment 2 | failed |  |  |  |  |  | PatentParseError: SEKONIX 4 radius is not numeric: , |
| US-20220128795-A1 | SEKONIX embodiment 3 | failed |  |  |  |  |  | PatentParseError: SEKONIX 6 radius is not numeric: , |
| US-20220128795-A1 | SEKONIX embodiment 4 | failed |  |  |  |  |  | PatentParseError: SEKONIX 8 radius is not numeric: , |
| US-20220128795-A1 | SEKONIX embodiment 5 | failed |  |  |  |  |  | PatentParseError: SEKONIX 10 radius is not numeric: , |
| US-11099361-B2 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX 2 radius is not numeric: , |
| US-11099361-B2 | SEKONIX embodiment 2 | failed |  |  |  |  |  | PatentParseError: SEKONIX 4 radius is not numeric: , |
| US-11099361-B2 | SEKONIX embodiment 3 | failed |  |  |  |  |  | PatentParseError: SEKONIX 6 radius is not numeric: , |
| US-11099361-B2 | SEKONIX embodiment 4 | failed |  |  |  |  |  | PatentParseError: SEKONIX 8 radius is not numeric: , |
| US-11099361-B2 | SEKONIX embodiment 5 | failed |  |  |  |  |  | PatentParseError: SEKONIX 10 radius is not numeric: , |
| US-20210124150-A1 | SEKONIX embodiment 1 | failed |  |  |  |  |  | PatentParseError: SEKONIX Stop radius is not numeric: (S2) |
| US-20210124150-A1 | SEKONIX embodiment 2 | failed |  |  |  |  |  | PatentParseError: SEKONIX Stop radius is not numeric: (S2) |
| US-12596237-B2 | Embodiment 1 | success | data\zmx_staging_p12\US-12596237-B2-e1.zmx | 2.34505 | 2.68852 | 9.17651 | surfaces=14; r=14/14; d=14/14; nd_vd=6/14; asphere_surfaces=10; f_mm=2.47; f_number=1.21; hfov_deg=74.935; real_image_height_mm=2.688524571618705; sanity_image_height_mm=9.17651112819587; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12596237-B2 | Embodiment 2 | success | data\zmx_staging_p12\US-12596237-B2-e2.zmx | 2.32549 | 2.54567 | 9.8009 | surfaces=14; r=14/14; d=14/14; nd_vd=6/14; asphere_surfaces=10; f_mm=2.45; f_number=1.2; hfov_deg=75.965; real_image_height_mm=2.545665491487191; sanity_image_height_mm=9.800903992160109; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12596237-B2 | Embodiment 3 | success | data\zmx_staging_p12\US-12596237-B2-e3.zmx | 2.31693 | 2.91199 | 9.83749 | surfaces=14; r=14/14; d=14/14; nd_vd=6/14; asphere_surfaces=10; f_mm=2.44; f_number=1.2; hfov_deg=76.07; real_image_height_mm=2.9119899958970836; sanity_image_height_mm=9.837491150136849; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12596237-B2 | Embodiment 4 | success | data\zmx_staging_p12\US-12596237-B2-e4.zmx | 2.31929 | 2.89864 | 10.3018 | surfaces=14; r=14/14; d=14/14; nd_vd=6/14; asphere_surfaces=10; f_mm=2.44; f_number=1.2; hfov_deg=76.675; real_image_height_mm=2.8986411388206927; sanity_image_height_mm=10.30184641313146; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12596237-B2 | Embodiment 5 | success | data\zmx_staging_p12\US-12596237-B2-e5.zmx | 2.30761 | 3.07453 | 11.0247 | surfaces=14; r=14/14; d=14/14; nd_vd=6/14; asphere_surfaces=10; f_mm=2.43; f_number=1.19; hfov_deg=77.57; real_image_height_mm=3.074532410569147; sanity_image_height_mm=11.024746445648015; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12596237-B2 | Embodiment 6 | success | data\zmx_staging_p12\US-12596237-B2-e6.zmx | 2.20417 | 3.13325 | 9.24655 | surfaces=14; r=14/14; d=14/14; nd_vd=6/14; asphere_surfaces=10; f_mm=2.32; f_number=1.29; hfov_deg=75.915; real_image_height_mm=3.133249718925321; sanity_image_height_mm=9.246551902237004; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12596237-B2 | Embodiment 7 | success | data\zmx_staging_p12\US-12596237-B2-e7.zmx | 2.79908 | 2.74368 | 8.60451 | surfaces=14; r=14/14; d=14/14; nd_vd=6/14; asphere_surfaces=6; f_mm=2.92; f_number=1.29; hfov_deg=71.255; real_image_height_mm=2.743680932775469; sanity_image_height_mm=8.604509467535392; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12578548-B2 | Embodiment 1 | success | data\zmx_staging_p12\US-12578548-B2-e1.zmx | 1.26532 | 1.88425 | -14.2876 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=12; f_mm=1.25; f_number=2.0; hfov_deg=95.0; real_image_height_mm=1.8842505668204892; sanity_image_height_mm=-14.28756537845167; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12578548-B2 | Embodiment 2 | success | data\zmx_staging_p12\US-12578548-B2-e2.zmx | 1.30859 | 1.70751 | -14.6305 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=12; f_mm=1.28; f_number=2.0; hfov_deg=95.0; real_image_height_mm=1.7075069339469524; sanity_image_height_mm=-14.63046694753451; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12578548-B2 | Embodiment 3 | success | data\zmx_staging_p12\US-12578548-B2-e3.zmx | 1.39385 | 1.87658 | -15.6592 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=12; f_mm=1.37; f_number=2.0; hfov_deg=95.0; real_image_height_mm=1.8765845230083615; sanity_image_height_mm=-15.659171654783032; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12578548-B2 | Embodiment 4 | success | data\zmx_staging_p12\US-12578548-B2-e4.zmx | 1.27211 | 1.93804 | -11.893 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=12; f_mm=1.25; f_number=2.0; hfov_deg=96.0; real_image_height_mm=1.9380433789911582; sanity_image_height_mm=-11.89295556777822; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12578548-B2 | Embodiment 5 | success | data\zmx_staging_p12\US-12578548-B2-e5.zmx | 1.07671 | 1.90203 | -12.1159 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=12; f_mm=1.06; f_number=2.05; hfov_deg=95.0; real_image_height_mm=1.9020267052007584; sanity_image_height_mm=-12.115855440927017; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20260063869-A1 | Embodiment 1 | failed |  |  |  |  |  | PatentParseError: NEWMAX A row has nonnumeric data token: gap |
| US-20260063869-A1 | Embodiment 2 | success | data\zmx_staging_p12\US-20260063869-A1-e2.zmx | 14.6927 | 14.0379 | 4.73933 | surfaces=12; r=12/12; d=12/12; nd_vd=5/12; asphere_surfaces=8; f_mm=14.5; f_number=2.58; hfov_deg=18.1; real_image_height_mm=14.037910992314224; sanity_image_height_mm=4.739330533678812; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20260063869-A1 | Embodiment 3 | success | data\zmx_staging_p12\US-20260063869-A1-e3.zmx | 13.2521 | 4.39335 | 4.33846 | surfaces=12; r=12/12; d=12/12; nd_vd=5/12; asphere_surfaces=8; f_mm=13.08; f_number=2.15; hfov_deg=18.35; real_image_height_mm=4.393351279783055; sanity_image_height_mm=4.338462975350497; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20260063869-A1 | Embodiment 4 | success | data\zmx_staging_p12\US-20260063869-A1-e4.zmx | 12.8763 | 4.34592 | 4.34818 | surfaces=12; r=12/12; d=12/12; nd_vd=5/12; asphere_surfaces=8; f_mm=12.7; f_number=2.38; hfov_deg=18.9; real_image_height_mm=4.345920913946563; sanity_image_height_mm=4.348181876754274; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20260063869-A1 | Embodiment 5 | success | data\zmx_staging_p12\US-20260063869-A1-e5.zmx | 13.4642 | 4.39204 | 4.36324 | surfaces=12; r=12/12; d=12/12; nd_vd=5/12; asphere_surfaces=8; f_mm=13.31; f_number=2.38; hfov_deg=18.15; real_image_height_mm=4.392044609538248; sanity_image_height_mm=4.363238278768635; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20260063869-A1 | Embodiment 6 | success | data\zmx_staging_p12\US-20260063869-A1-e6.zmx | 13.0458 | 4.88959 | 4.75906 | surfaces=12; r=12/12; d=12/12; nd_vd=5/12; asphere_surfaces=8; f_mm=12.9; f_number=2.48; hfov_deg=20.25; real_image_height_mm=4.889589834526289; sanity_image_height_mm=4.759061254716769; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12554104-B2 | Embodiment 1 | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Eighth |
| US-12554104-B2 | Embodiment 2 | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Eighth |
| US-12554104-B2 | Embodiment 3 | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Eighth |
| US-12554104-B2 | Embodiment 4 | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Eighth |
| US-12554104-B2 | Embodiment 5 | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Eighth |
| US-12554104-B2 | Embodiment 6 | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Eighth |
| US-12554104-B2 | Embodiment 7 | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Eighth |
| US-12535652-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12510732-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12510730-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12498546-B2 | Embodiment 1 | failed |  |  |  |  |  | PatentParseError: surface 10 radius is not numeric: Light |
| US-12498546-B2 | Embodiment 2 | failed |  |  |  |  |  | PatentParseError: surface 10 radius is not numeric: Light |
| US-12498546-B2 | Embodiment 3 | failed |  |  |  |  |  | PatentParseError: surface 10 radius is not numeric: Light |
| US-12498546-B2 | Embodiment 4 | failed |  |  |  |  |  | PatentParseError: surface 10 radius is not numeric: Light |
| US-12498546-B2 | Embodiment 5 | failed |  |  |  |  |  | PatentParseError: surface 10 radius is not numeric: Light |
| US-12487435-B2 | Embodiment 1 | failed |  |  |  |  |  | PatentParseError: surface 2 radius is not numeric: First |
| US-12487435-B2 | Embodiment 2 | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Second |
| US-12487435-B2 | Embodiment 3 | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Second |
| US-12487435-B2 | Embodiment 4 | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Second |
| US-12487435-B2 | Embodiment 5 | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Second |
| US-12487435-B2 | Embodiment 6 | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Second |
