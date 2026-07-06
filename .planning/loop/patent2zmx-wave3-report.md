# DATA-06f patent-to-ZMX wave 3 report

## Run contract

- prior_wave: DATA-06d wave2
- prior_cursor: data\patents\convert-cursor.json
- prior_cursor_after_patent_id: US-20240231053-A1
- prior_baseline_patent_candidate_hit_rate: 16/60 (26.7%)
- pool_count_patents: 354
- prior_seed_sample_excluded: 60
- existing_zmx_patent_ids_excluded: 86
- available_after_exclusions: 246
- sample_size_patents: 80
- sample_method: load_patent_pool(data/patents) ordered by sorted uspto-smartphone-batch*.jsonl; exclude DATA-06b2 sampled patents plus patents already represented by data/zmx or data/zmx-staging ZMX stems; resume after DATA-06d cursor; take first <=80 remaining candidates
- output_dir: data\zmx-staging\DATA-06f
- runner: scripts.patent_to_zmx load_patent_pool + _convert_candidate + write_patent_zmx + load_normalized_zmx
- parser: deterministic NFKC-normalized multi-embodiment table parse; no numeric LLM fill
- codev_dependency: none; this conversion path does not require CODE V and no CODE V skip was taken
- missing_success_artifacts_policy: not applicable; successful ZMX files are present in staging for intake
- bom_check: report/cursor are written as UTF-8 without BOM
- real_imh_tail_check: all successful ZMX artifacts carry ATELIER_REAL_IMH_MM tail comments
- strict_limit_check: exactly 80 patent candidates attempted; no expansion beyond selected candidates
- started_at: 2026-07-06T20:54:55+08:00
- elapsed_seconds: 1202.7

## Yield summary

- patent_candidates_attempted: 80
- embodiment_attempts: 248
- successes: 39
- failures: 209
- success_rate_by_embodiment_attempt: 39/248 (15.7%)
- patent_candidate_hit_rate: 9/80 (11.2%)
- baseline_patent_candidate_hit_rate: 16/60 (26.7%)
- delta_vs_26_7_baseline: -15.4 percentage points

## Failure reason buckets

| reason_bucket | failures | share_of_failures |
|---|---:|---:|
| meta line not found | 58 | 27.8% |
| trace did not reach image | 52 | 24.9% |
| unsupported nonzero high-order asphere terms | 35 | 16.7% |
| surface 14 radius is not numeric: IR-cut | 31 | 14.8% |
| 'Aspheric Coefficients' section not found in embodiment | 10 | 4.8% |
| surface table index break | 5 | 2.4% |
| surface 16 radius is not numeric: Lend | 4 | 1.9% |
| surface 3 radius is not numeric: Ape. | 4 | 1.9% |
| surface 1 radius is not numeric: Ape. | 3 | 1.4% |
| surface 14 radius is not numeric: IR-Cut | 2 | 1.0% |
| surface 5 radius is not numeric: Ape. | 2 | 1.0% |
| surface 12 radius is not numeric: Prism | 1 | 0.5% |
| surface 1 radius is not numeric: Prism | 1 | 0.5% |
| aspheric coefficient table had no Surface # block | 1 | 0.5% |

## Selected patent candidates

| # | patent_id | pool_file | line | attempts | successes | failures |
|---:|---|---|---:|---:|---:|---:|
| 1 | US-12007536-B2 | uspto-smartphone-batch5.jsonl | 19 | 12 | 0 | 12 |
| 2 | US-11971527-B2 | uspto-smartphone-batch5.jsonl | 20 | 10 | 0 | 10 |
| 3 | US-11940597-B2 | uspto-smartphone-batch5.jsonl | 21 | 8 | 3 | 5 |
| 4 | US-20240061217-A1 | uspto-smartphone-batch5.jsonl | 22 | 11 | 8 | 3 |
| 5 | US-11906710-B2 | uspto-smartphone-batch5.jsonl | 23 | 11 | 11 | 0 |
| 6 | US-11846759-B2 | uspto-smartphone-batch5.jsonl | 24 | 11 | 8 | 3 |
| 7 | US-12158566-B2 | uspto-smartphone-batch5.jsonl | 28 | 7 | 0 | 7 |
| 8 | US-20240061215-A1 | uspto-smartphone-batch5.jsonl | 30 | 7 | 0 | 7 |
| 9 | US-11828910-B2 | uspto-smartphone-batch5.jsonl | 31 | 12 | 0 | 12 |
| 10 | US-20230375803-A1 | uspto-smartphone-batch5.jsonl | 32 | 1 | 0 | 1 |
| 11 | US-11815662-B2 | uspto-smartphone-batch5.jsonl | 33 | 7 | 1 | 6 |
| 12 | US-11668898-B2 | uspto-smartphone-batch5.jsonl | 34 | 11 | 4 | 7 |
| 13 | US-20220099944-A1 | uspto-smartphone-batch5.jsonl | 36 | 12 | 0 | 12 |
| 14 | US-20220066146-A1 | uspto-smartphone-batch5.jsonl | 37 | 7 | 0 | 7 |
| 15 | US-20210132344-A1 | uspto-smartphone-batch5.jsonl | 39 | 10 | 0 | 10 |
| 16 | US-20200233184-A1 | uspto-smartphone-batch5.jsonl | 41 | 9 | 0 | 9 |
| 17 | US-10649183-B2 | uspto-smartphone-batch5.jsonl | 42 | 4 | 0 | 4 |
| 18 | US-10598906-B2 | uspto-smartphone-batch5.jsonl | 43 | 1 | 1 | 0 |
| 19 | US-10444475-B2 | uspto-smartphone-batch5.jsonl | 45 | 8 | 1 | 7 |
| 20 | US-20190271833-A1 | uspto-smartphone-batch5.jsonl | 46 | 4 | 0 | 4 |
| 21 | US-10338351-B2 | uspto-smartphone-batch5.jsonl | 47 | 10 | 0 | 10 |
| 22 | US-20260147257-A1 | uspto-smartphone-batch5.jsonl | 48 | 1 | 0 | 1 |
| 23 | US-12541079-B2 | uspto-smartphone-batch5.jsonl | 49 | 8 | 2 | 6 |
| 24 | US-12468121-B2 | uspto-smartphone-batch5.jsonl | 50 | 10 | 0 | 10 |
| 25 | US-20260169262-A1 | uspto-smartphone-batch5.jsonl | 51 | 1 | 0 | 1 |
| 26 | US-12578550-B2 | uspto-smartphone-batch5.jsonl | 53 | 1 | 0 | 1 |
| 27 | US-12571987-B2 | uspto-smartphone-batch5.jsonl | 54 | 1 | 0 | 1 |
| 28 | US-20260029620-A1 | uspto-smartphone-batch5.jsonl | 55 | 1 | 0 | 1 |
| 29 | US-20250327997-A1 | uspto-smartphone-batch5.jsonl | 56 | 1 | 0 | 1 |
| 30 | US-12386154-B2 | uspto-smartphone-batch5.jsonl | 57 | 1 | 0 | 1 |
| 31 | US-20250155675-A1 | uspto-smartphone-batch5.jsonl | 58 | 1 | 0 | 1 |
| 32 | US-20250155701-A1 | uspto-smartphone-batch5.jsonl | 59 | 1 | 0 | 1 |
| 33 | US-20240369807-A1 | uspto-smartphone-batch5.jsonl | 60 | 1 | 0 | 1 |
| 34 | US-20240184082-A1 | uspto-smartphone-batch5.jsonl | 61 | 1 | 0 | 1 |
| 35 | US-20240176104-A1 | uspto-smartphone-batch5.jsonl | 62 | 1 | 0 | 1 |
| 36 | US-20240118520-A1 | uspto-smartphone-batch5.jsonl | 64 | 1 | 0 | 1 |
| 37 | US-12669685-B2 | uspto-smartphone-batch6.jsonl | 1 | 1 | 0 | 1 |
| 38 | US-20260160982-A1 | uspto-smartphone-batch6.jsonl | 2 | 1 | 0 | 1 |
| 39 | US-20260153712-A1 | uspto-smartphone-batch6.jsonl | 3 | 1 | 0 | 1 |
| 40 | US-20260140349-A1 | uspto-smartphone-batch6.jsonl | 4 | 1 | 0 | 1 |
| 41 | US-20260110880-A1 | uspto-smartphone-batch6.jsonl | 5 | 1 | 0 | 1 |
| 42 | US-12591117-B2 | uspto-smartphone-batch6.jsonl | 6 | 1 | 0 | 1 |
| 43 | US-20260086334-A1 | uspto-smartphone-batch6.jsonl | 7 | 1 | 0 | 1 |
| 44 | US-20260086330-A1 | uspto-smartphone-batch6.jsonl | 8 | 1 | 0 | 1 |
| 45 | US-20260072253-A1 | uspto-smartphone-batch6.jsonl | 9 | 1 | 0 | 1 |
| 46 | US-20260063874-A1 | uspto-smartphone-batch6.jsonl | 10 | 1 | 0 | 1 |
| 47 | US-20260063870-A1 | uspto-smartphone-batch6.jsonl | 11 | 1 | 0 | 1 |
| 48 | US-12560782-B2 | uspto-smartphone-batch6.jsonl | 12 | 1 | 0 | 1 |
| 49 | US-12554102-B2 | uspto-smartphone-batch6.jsonl | 13 | 1 | 0 | 1 |
| 50 | US-20260043988-A1 | uspto-smartphone-batch6.jsonl | 14 | 1 | 0 | 1 |
| 51 | US-12345855-B2 | uspto-smartphone-batch6.jsonl | 15 | 1 | 0 | 1 |
| 52 | US-12306467-B2 | uspto-smartphone-batch6.jsonl | 16 | 1 | 0 | 1 |
| 53 | US-12292550-B2 | uspto-smartphone-batch6.jsonl | 17 | 1 | 0 | 1 |
| 54 | US-12287461-B2 | uspto-smartphone-batch6.jsonl | 18 | 1 | 0 | 1 |
| 55 | US-20250116846-A1 | uspto-smartphone-batch6.jsonl | 19 | 1 | 0 | 1 |
| 56 | US-12242033-B2 | uspto-smartphone-batch6.jsonl | 20 | 1 | 0 | 1 |
| 57 | US-12493169-B2 | uspto-smartphone-batch6.jsonl | 21 | 1 | 0 | 1 |
| 58 | US-12399348-B2 | uspto-smartphone-batch6.jsonl | 22 | 1 | 0 | 1 |
| 59 | US-12320958-B2 | uspto-smartphone-batch6.jsonl | 23 | 1 | 0 | 1 |
| 60 | US-12235419-B2 | uspto-smartphone-batch6.jsonl | 24 | 1 | 0 | 1 |
| 61 | US-12235415-B2 | uspto-smartphone-batch6.jsonl | 25 | 1 | 0 | 1 |
| 62 | US-12210213-B2 | uspto-smartphone-batch6.jsonl | 26 | 1 | 0 | 1 |
| 63 | US-12197039-B2 | uspto-smartphone-batch6.jsonl | 27 | 1 | 0 | 1 |
| 64 | US-12169324-B2 | uspto-smartphone-batch6.jsonl | 28 | 1 | 0 | 1 |
| 65 | US-12147088-B2 | uspto-smartphone-batch6.jsonl | 29 | 1 | 0 | 1 |
| 66 | US-12135409-B2 | uspto-smartphone-batch6.jsonl | 30 | 1 | 0 | 1 |
| 67 | US-12124009-B2 | uspto-smartphone-batch6.jsonl | 31 | 1 | 0 | 1 |
| 68 | US-12124006-B2 | uspto-smartphone-batch6.jsonl | 32 | 1 | 0 | 1 |
| 69 | US-12656577-B2 | uspto-smartphone-batch6.jsonl | 33 | 1 | 0 | 1 |
| 70 | US-12656578-B2 | uspto-smartphone-batch6.jsonl | 34 | 1 | 0 | 1 |
| 71 | US-20260147189-A1 | uspto-smartphone-batch6.jsonl | 35 | 1 | 0 | 1 |
| 72 | US-12625349-B2 | uspto-smartphone-batch6.jsonl | 36 | 1 | 0 | 1 |
| 73 | US-20260110881-A1 | uspto-smartphone-batch6.jsonl | 37 | 1 | 0 | 1 |
| 74 | US-20260093094-A1 | uspto-smartphone-batch6.jsonl | 38 | 1 | 0 | 1 |
| 75 | US-12607828-B2 | uspto-smartphone-batch6.jsonl | 39 | 1 | 0 | 1 |
| 76 | US-20260036791-A1 | uspto-smartphone-batch6.jsonl | 40 | 1 | 0 | 1 |
| 77 | US-20260009980-A1 | uspto-smartphone-batch6.jsonl | 41 | 1 | 0 | 1 |
| 78 | US-12461345-B2 | uspto-smartphone-batch6.jsonl | 42 | 1 | 0 | 1 |
| 79 | US-12429676-B2 | uspto-smartphone-batch6.jsonl | 43 | 1 | 0 | 1 |
| 80 | US-12298484-B2 | uspto-smartphone-batch6.jsonl | 44 | 1 | 0 | 1 |

## Per-embodiment attempts

| patent | embodiment | status | zmx | efl_mm | real_imh_mm | f_tan_sanity_mm | field coverage | reason |
|---|---|---|---|---:|---:|---:|---|---|
| US-12007536-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12007536-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Lend |
| US-12007536-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12007536-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12007536-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Lend |
| US-12007536-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Lend |
| US-12007536-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Lend |
| US-12007536-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12007536-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12007536-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12007536-B2 | 11th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12007536-B2 | 12th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11971527-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-11971527-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-11971527-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-11971527-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-11971527-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-11971527-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-11971527-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-11971527-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-11971527-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-11971527-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-11940597-B2 | 1st Embodiment | success | data\zmx-staging\DATA-06f\US-11940597-B2-e1.zmx | 12.0429 | 1.22244 | 2.03303 | surfaces=14; r=14/14; d=14/14; nd_vd=5/14; asphere_surfaces=8; f_mm=12.02; f_number=3.52; hfov_deg=9.6; real_image_height_mm=1.2224425005783308; sanity_image_height_mm=2.0330308238188284; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11940597-B2 | 2nd Embodiment | success | data\zmx-staging\DATA-06f\US-11940597-B2-e2.zmx | 12.5071 | 1.37296 | 2.03428 | surfaces=13; r=13/13; d=13/13; nd_vd=5/13; asphere_surfaces=4; f_mm=12.56; f_number=3.67; hfov_deg=9.2; real_image_height_mm=1.3729556321318404; sanity_image_height_mm=2.0342761060054544; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11940597-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 12 radius is not numeric: Prism |
| US-11940597-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 10, found 40 |
| US-11940597-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11940597-B2 | 6th Embodiment | success | data\zmx-staging\DATA-06f\US-11940597-B2-e6.zmx | 19.6731 | 3.4168 | 3.25304 | surfaces=12; r=12/12; d=12/12; nd_vd=5/12; asphere_surfaces=4; f_mm=19.65; f_number=3.57; hfov_deg=9.4; real_image_height_mm=3.4168006333805883; sanity_image_height_mm=3.253036405183324; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11940597-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 1 radius is not numeric: Prism |
| US-11940597-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: aspheric coefficient table had no Surface # block |
| US-20240061217-A1 | 1st Embodiment | success | data\zmx-staging\DATA-06f\US-20240061217-A1-e1.zmx | 6.18111 | 2.93613 | 2.87712 | surfaces=23; r=23/23; d=23/23; nd_vd=10/23; asphere_surfaces=18; f_mm=6.17; f_number=2.23; hfov_deg=25.0; real_image_height_mm=2.936125386891721; sanity_image_height_mm=2.8771182508163413; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20240061217-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240061217-A1 | 3rd Embodiment | success | data\zmx-staging\DATA-06f\US-20240061217-A1-e3.zmx | 4.37154 | 4.21922 | 5.26369 | surfaces=23; r=23/23; d=23/23; nd_vd=10/23; asphere_surfaces=18; f_mm=4.37; f_number=1.9; hfov_deg=50.3; real_image_height_mm=4.219222544299923; sanity_image_height_mm=5.263690441750895; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20240061217-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240061217-A1 | 5th Embodiment | success | data\zmx-staging\DATA-06f\US-20240061217-A1-e5.zmx | 6.47016 | 3.92839 | 6.14929 | surfaces=25; r=25/25; d=25/25; nd_vd=11/25; asphere_surfaces=20; f_mm=6.48; f_number=1.73; hfov_deg=43.5; real_image_height_mm=3.9283894316006727; sanity_image_height_mm=6.1492903923124205; finite_final_rays=2/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20240061217-A1 | 6th Embodiment | success | data\zmx-staging\DATA-06f\US-20240061217-A1-e6.zmx | 4.37258 | 4.41438 | 5.20796 | surfaces=24; r=24/24; d=24/24; nd_vd=10/24; asphere_surfaces=18; f_mm=4.37; f_number=1.9; hfov_deg=50.0; real_image_height_mm=4.41438315534764; sanity_image_height_mm=5.207963199636698; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20240061217-A1 | 7th Embodiment | success | data\zmx-staging\DATA-06f\US-20240061217-A1-e7.zmx | 1.93623 | 7.21709 | 3.49985 | surfaces=22; r=22/22; d=22/22; nd_vd=10/22; asphere_surfaces=18; f_mm=1.94; f_number=1.8; hfov_deg=61.0; real_image_height_mm=7.217093659407352; sanity_image_height_mm=3.4998526452265617; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20240061217-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240061217-A1 | 9th Embodiment | success | data\zmx-staging\DATA-06f\US-20240061217-A1-e9.zmx | 7.90652 | 2.9378 | 2.879 | surfaces=23; r=23/23; d=23/23; nd_vd=10/23; asphere_surfaces=18; f_mm=7.91; f_number=2.35; hfov_deg=20.0; real_image_height_mm=2.937803998723388; sanity_image_height_mm=2.8790045530456605; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20240061217-A1 | 10th Embodiment | success | data\zmx-staging\DATA-06f\US-20240061217-A1-e10.zmx | 6.75734 | 2.93836 | 2.87369 | surfaces=23; r=23/23; d=23/23; nd_vd=10/23; asphere_surfaces=18; f_mm=6.77; f_number=2.23; hfov_deg=23.0; real_image_height_mm=2.9383643103793697; sanity_image_height_mm=2.873694505739024; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20240061217-A1 | 11th Embodiment | success | data\zmx-staging\DATA-06f\US-20240061217-A1-e11.zmx | 7.30036 | 2.93696 | 2.87161 | surfaces=23; r=23/23; d=23/23; nd_vd=10/23; asphere_surfaces=18; f_mm=7.29; f_number=2.45; hfov_deg=21.5; real_image_height_mm=2.9369622388475047; sanity_image_height_mm=2.8716073672329303; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11906710-B2 | 1st Embodiment | success | data\zmx-staging\DATA-06f\US-11906710-B2-e1.zmx | 4.14439 | 3.00302 | 2.94214 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=4.14; f_number=2.2; hfov_deg=35.4; real_image_height_mm=3.003024088560101; sanity_image_height_mm=2.9421448588379664; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11906710-B2 | 2nd Embodiment | success | data\zmx-staging\DATA-06f\US-11906710-B2-e2.zmx | 3.64498 | 3.03105 | 2.94761 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=3.64; f_number=2.0; hfov_deg=39.0; real_image_height_mm=3.0310482929742557; sanity_image_height_mm=2.9476138808298256; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11906710-B2 | 3rd Embodiment | success | data\zmx-staging\DATA-06f\US-11906710-B2-e3.zmx | 4.20534 | 3.30078 | 3.23444 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=4.2; f_number=2.07; hfov_deg=37.6; real_image_height_mm=3.300784853638852; sanity_image_height_mm=3.2344354238093747; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11906710-B2 | 4th Embodiment | success | data\zmx-staging\DATA-06f\US-11906710-B2-e4.zmx | 3.51894 | 2.85758 | 2.85044 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=3.52; f_number=2.15; hfov_deg=39.0; real_image_height_mm=2.8575750750533127; sanity_image_height_mm=2.8504397968464246; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11906710-B2 | 5th Embodiment | success | data\zmx-staging\DATA-06f\US-11906710-B2-e5.zmx | 3.53005 | 2.85948 | 2.80789 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=3.53; f_number=2.28; hfov_deg=38.5; real_image_height_mm=2.859482947002693; sanity_image_height_mm=2.8078887858374344; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11906710-B2 | 6th Embodiment | success | data\zmx-staging\DATA-06f\US-11906710-B2-e6.zmx | 3.61656 | 2.86384 | 2.80796 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=3.62; f_number=2.35; hfov_deg=37.8; real_image_height_mm=2.863836805273073; sanity_image_height_mm=2.807959829999599; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11906710-B2 | 7th Embodiment | success | data\zmx-staging\DATA-06f\US-11906710-B2-e7.zmx | 3.75833 | 5.05617 | 2.88789 | surfaces=17; r=17/17; d=17/17; nd_vd=7/17; asphere_surfaces=12; f_mm=3.75; f_number=2.25; hfov_deg=37.6; real_image_height_mm=5.056168330266794; sanity_image_height_mm=2.88788877125837; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11906710-B2 | 8th Embodiment | success | data\zmx-staging\DATA-06f\US-11906710-B2-e8.zmx | 3.75899 | 2.96823 | 2.88789 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=3.75; f_number=2.22; hfov_deg=37.6; real_image_height_mm=2.9682333936624232; sanity_image_height_mm=2.88788877125837; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11906710-B2 | 9th Embodiment | success | data\zmx-staging\DATA-06f\US-11906710-B2-e9.zmx | 3.75554 | 5.78237 | 2.85673 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=3.75; f_number=2.25; hfov_deg=37.3; real_image_height_mm=5.782373786248194; sanity_image_height_mm=2.8567344552507334; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11906710-B2 | 10th Embodiment | success | data\zmx-staging\DATA-06f\US-11906710-B2-e10.zmx | 3.59734 | 6.4027 | 2.85561 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=3.59; f_number=2.25; hfov_deg=38.5; real_image_height_mm=6.402702079227596; sanity_image_height_mm=2.8556149408375044; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11906710-B2 | 11th Embodiment | success | data\zmx-staging\DATA-06f\US-11906710-B2-e11.zmx | 3.56955 | 7.88596 | 2.85788 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=3.58; f_number=2.6; hfov_deg=38.6; real_image_height_mm=7.885957016871733; sanity_image_height_mm=2.8578764537119774; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11846759-B2 | 1st Embodiment | success | data\zmx-staging\DATA-06f\US-11846759-B2-e1.zmx | 6.18111 | 2.93613 | 2.87712 | surfaces=23; r=23/23; d=23/23; nd_vd=10/23; asphere_surfaces=18; f_mm=6.17; f_number=2.23; hfov_deg=25.0; real_image_height_mm=2.936125386891721; sanity_image_height_mm=2.8771182508163413; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11846759-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11846759-B2 | 3rd Embodiment | success | data\zmx-staging\DATA-06f\US-11846759-B2-e3.zmx | 4.37154 | 3.87859 | 5.26369 | surfaces=23; r=23/23; d=23/23; nd_vd=10/23; asphere_surfaces=18; f_mm=4.37; f_number=1.9; hfov_deg=50.3; real_image_height_mm=3.8785931634775785; sanity_image_height_mm=5.263690441750895; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11846759-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11846759-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11846759-B2 | 6th Embodiment | success | data\zmx-staging\DATA-06f\US-11846759-B2-e6.zmx | 4.37258 | 4.41438 | 5.20796 | surfaces=24; r=24/24; d=24/24; nd_vd=10/24; asphere_surfaces=18; f_mm=4.37; f_number=1.9; hfov_deg=50.0; real_image_height_mm=4.41438315534764; sanity_image_height_mm=5.207963199636698; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11846759-B2 | 7th Embodiment | success | data\zmx-staging\DATA-06f\US-11846759-B2-e7.zmx | 1.93623 | 7.21709 | 3.49985 | surfaces=22; r=22/22; d=22/22; nd_vd=10/22; asphere_surfaces=18; f_mm=1.94; f_number=1.8; hfov_deg=61.0; real_image_height_mm=7.217093659407352; sanity_image_height_mm=3.4998526452265617; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11846759-B2 | 8th Embodiment | success | data\zmx-staging\DATA-06f\US-11846759-B2-e8.zmx | 1.83612 | 2.89812 | 4.13271 | surfaces=23; r=23/23; d=23/23; nd_vd=10/23; asphere_surfaces=18; f_mm=1.84; f_number=1.83; hfov_deg=66.0; real_image_height_mm=2.898115693077001; sanity_image_height_mm=4.1327076639837586; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11846759-B2 | 9th Embodiment | success | data\zmx-staging\DATA-06f\US-11846759-B2-e9.zmx | 7.90652 | 2.9378 | 2.879 | surfaces=23; r=23/23; d=23/23; nd_vd=10/23; asphere_surfaces=18; f_mm=7.91; f_number=2.35; hfov_deg=20.0; real_image_height_mm=2.937803998723388; sanity_image_height_mm=2.8790045530456605; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11846759-B2 | 10th Embodiment | success | data\zmx-staging\DATA-06f\US-11846759-B2-e10.zmx | 6.75734 | 2.93836 | 2.87369 | surfaces=23; r=23/23; d=23/23; nd_vd=10/23; asphere_surfaces=18; f_mm=6.77; f_number=2.23; hfov_deg=23.0; real_image_height_mm=2.9383643103793697; sanity_image_height_mm=2.873694505739024; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11846759-B2 | 11th Embodiment | success | data\zmx-staging\DATA-06f\US-11846759-B2-e11.zmx | 7.30036 | 2.93696 | 2.87161 | surfaces=23; r=23/23; d=23/23; nd_vd=10/23; asphere_surfaces=18; f_mm=7.29; f_number=2.45; hfov_deg=21.5; real_image_height_mm=2.9369622388475047; sanity_image_height_mm=2.8716073672329303; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12158566-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12158566-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12158566-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12158566-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12158566-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12158566-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12158566-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240061215-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240061215-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240061215-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240061215-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240061215-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240061215-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240061215-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11828910-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.023, S9:A22=-0.000371, S10:A22=-0.000265, S11:A22=0.000179, S8:A24=-0.00139, S9:A24=1.83e-05, S10:A24=-1.01e-05, S8:A26=-5.32e-07 |
| US-11828910-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.0169, S9:A22=-5.03e-05, S10:A22=-0.000197, S11:A22=0.000126, S8:A24=0.000985, S9:A24=1.64e-05, S10:A24=-6.87e-06, S8:A26=-5.76e-07 |
| US-11828910-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.00937, S9:A22=-0.0243, S10:A22=-0.0321, S11:A22=0.000684, S8:A24=0.000474, S9:A24=0.00197, S10:A24=0.00322, S11:A24=-3.23e-05 |
| US-11828910-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.0191, S9:A22=-0.0175, S10:A22=-0.0401, S11:A22=0.000843, S8:A24=-0.0012, S9:A24=0.00146, S10:A24=0.00406, S11:A24=-7.47e-05 |
| US-11828910-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.00113, S9:A22=-0.00527, S10:A22=5.16e-07, S8:A24=-5.03e-05, S9:A24=0.000387, S8:A26=-1.26e-05, S9:A26=146 |
| US-11828910-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 15, found 16 |
| US-11828910-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11828910-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.0314, S9:A22=-0.000113, S10:A22=-0.00092, S11:A22=-2.18e-05, S8:A24=0.00181, S9:A24=5.94e-05, S10:A24=1.34e-06, S8:A26=-1.69e-06 |
| US-11828910-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.00117, S9:A22=-0.000802, S10:A22=9.87e-05, S8:A24=7.32e-05, S9:A24=2.68e-06, S10:A24=-5.52e-06, S8:A26=1.37e-07, S9:A26=198 |
| US-11828910-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.00112, S9:A22=-0.00195, S10:A22=-0.00447, S11:A22=0.000106, S8:A24=9.57e-05, S9:A24=0.000289, S10:A24=-5.82e-06, S8:A26=-8.27e-06 |
| US-11828910-B2 | 11th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.125, S9:A22=0.0419, S10:A22=0.0294, S11:A22=0.00769, S8:A24=-0.00879, S9:A24=-0.00404, S10:A24=-0.00365, S11:A24=-0.000749 |
| US-11828910-B2 | 12th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.0579, S9:A22=-0.107, S10:A22=-0.00361, S11:A22=0.000228, S8:A24=-0.00368, S9:A24=0.0105, S10:A24=0.000289, S11:A24=-1.32e-05 |
| US-20230375803-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-11815662-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11815662-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11815662-B2 | 3rd Embodiment | success | data\zmx-staging\DATA-06f\US-11815662-B2-e3.zmx | 9.04219 | 0.144526 | 7.58546 | surfaces=23; r=23/23; d=23/23; nd_vd=10/23; asphere_surfaces=18; f_mm=9.04; f_number=1.71; hfov_deg=40.0; real_image_height_mm=0.14452581570841697; sanity_image_height_mm=7.58546066584261; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11815662-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11815662-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11815662-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11815662-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11668898-B2 | 1st Embodiment | success | data\zmx-staging\DATA-06f\US-11668898-B2-e1.zmx | 3.182 | 2.08134 | 2.75564 | surfaces=15; r=15/15; d=15/15; nd_vd=6/15; asphere_surfaces=10; f_mm=3.17; f_number=2.46; hfov_deg=41.0; real_image_height_mm=2.081335443367674; sanity_image_height_mm=2.755638958877438; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11668898-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11668898-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11668898-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11668898-B2 | 5th Embodiment | success | data\zmx-staging\DATA-06f\US-11668898-B2-e5.zmx | 3.16977 | 3.15508 | 3.17 | surfaces=15; r=15/15; d=15/15; nd_vd=6/15; asphere_surfaces=10; f_mm=3.17; f_number=2.23; hfov_deg=45.0; real_image_height_mm=3.1550806914800265; sanity_image_height_mm=3.1699999999999995; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11668898-B2 | 6th Embodiment | success | data\zmx-staging\DATA-06f\US-11668898-B2-e6.zmx | 2.83568 | 2.89918 | 2.8399 | surfaces=15; r=15/15; d=15/15; nd_vd=6/15; asphere_surfaces=10; f_mm=2.83; f_number=2.05; hfov_deg=45.1; real_image_height_mm=2.8991779901218817; sanity_image_height_mm=2.8398958451224114; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11668898-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11668898-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11668898-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11668898-B2 | 10th Embodiment | success | data\zmx-staging\DATA-06f\US-11668898-B2-e10.zmx | 2.95886 | 2.91859 | 2.95 | surfaces=16; r=16/16; d=16/16; nd_vd=6/16; asphere_surfaces=10; f_mm=2.95; f_number=2.05; hfov_deg=45.0; real_image_height_mm=2.918586630250893; sanity_image_height_mm=2.9499999999999997; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11668898-B2 | 11th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220099944-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.023, S9:A22=-0.000371, S10:A22=-0.000265, S11:A22=0.000179, S8:A24=-0.00139, S9:A24=1.83e-05, S10:A24=-1.01e-05, S8:A26=-5.32e-07 |
| US-20220099944-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.0169, S9:A22=-5.03e-05, S10:A22=-0.000197, S11:A22=0.000126, S8:A24=0.000985, S9:A24=1.64e-05, S10:A24=-6.87e-06, S8:A26=-5.76e-07 |
| US-20220099944-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.00937, S9:A22=-0.0243, S10:A22=-0.0321, S11:A22=0.000684, S8:A24=0.000474, S9:A24=0.00197, S10:A24=0.00322, S11:A24=-3.23e-05 |
| US-20220099944-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.0191, S9:A22=-0.0175, S10:A22=-0.0401, S11:A22=0.000843, S8:A24=-0.0012, S9:A24=0.00146, S10:A24=0.00406, S11:A24=-7.47e-05 |
| US-20220099944-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.00113, S9:A22=-0.00527, S10:A22=5.16e-07, S8:A24=-5.03e-05, S9:A24=0.000387, S8:A26=-1.26e-05 |
| US-20220099944-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 15, found 16 |
| US-20220099944-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220099944-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.0314, S9:A22=-0.000113, S10:A22=-0.00092, S11:A22=-2.18e-05, S8:A24=0.00181, S9:A24=5.94e-05, S10:A24=1.34e-06, S8:A26=-1.69e-06 |
| US-20220099944-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.00117, S9:A22=-0.000802, S10:A22=9.87e-05, S8:A24=7.32e-05, S9:A24=2.68e-06, S10:A24=-5.52e-06, S8:A26=1.37e-07 |
| US-20220099944-A1 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.00112, S9:A22=-0.00195, S10:A22=-0.00447, S11:A22=0.000106, S8:A24=9.57e-05, S9:A24=0.000289, S10:A24=-5.82e-06, S8:A26=-8.27e-06 |
| US-20220099944-A1 | 11th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.125, S9:A22=0.0419, S10:A22=0.0294, S11:A22=0.00769, S8:A24=-0.00879, S9:A24=-0.00404, S10:A24=-0.00365, S11:A24=-0.000749 |
| US-20220099944-A1 | 12th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.0579, S9:A22=-0.107, S10:A22=-0.00361, S11:A22=0.000228, S8:A24=-0.00368, S9:A24=0.0105, S10:A24=0.000289, S11:A24=-1.32e-05 |
| US-20220066146-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220066146-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220066146-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220066146-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220066146-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220066146-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220066146-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20210132344-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20210132344-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20210132344-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20210132344-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20210132344-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 6, found 8 |
| US-20210132344-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20210132344-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-Cut |
| US-20210132344-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20210132344-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20210132344-A1 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20200233184-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20200233184-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20200233184-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20200233184-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 6, found 8 |
| US-20200233184-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20200233184-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-Cut |
| US-20200233184-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20200233184-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20200233184-A1 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10649183-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10649183-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10649183-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10649183-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 5 radius is not numeric: Ape. |
| US-10598906-B2 | 1st Embodiment | success | data\zmx-staging\DATA-06f\US-10598906-B2-e1.zmx | 2.54663 | 1.11415 | 2.78284 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=2.55; f_number=2.01; hfov_deg=47.5; real_image_height_mm=1.1141464093561866; sanity_image_height_mm=2.7828366777266424; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-10444475-B2 | 1st Embodiment | success | data\zmx-staging\DATA-06f\US-10444475-B2-e1.zmx | 2.54663 | 1.11412 | 2.78284 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=2.55; f_number=2.01; hfov_deg=47.5; real_image_height_mm=1.114119351136773; sanity_image_height_mm=2.7828366777266424; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-10444475-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 3 radius is not numeric: Ape. |
| US-10444475-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 3 radius is not numeric: Ape. |
| US-10444475-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 3 radius is not numeric: Ape. |
| US-10444475-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 3 radius is not numeric: Ape. |
| US-10444475-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 1 radius is not numeric: Ape. |
| US-10444475-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 1 radius is not numeric: Ape. |
| US-10444475-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 1 radius is not numeric: Ape. |
| US-20190271833-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20190271833-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20190271833-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20190271833-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 5 radius is not numeric: Ape. |
| US-10338351-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10338351-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10338351-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10338351-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10338351-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10338351-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10338351-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10338351-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10338351-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10338351-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20260147257-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12541079-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=-2.11e+10, S8:A22=3.51e+08, S7:A24=3.97e+10, S8:A24=-5.46e+08, S7:A26=-4.94e+10, S8:A26=5.56e+08, S7:A28=3.65e+10, S8:A28=-3.34e+08 |
| US-12541079-B2 | 2nd Embodiment | success | data\zmx-staging\DATA-06f\US-12541079-B2-e2.zmx | 1.13726 | 0.661134 | 0.652406 | surfaces=10; r=10/10; d=10/10; nd_vd=4/10; asphere_surfaces=6; f_mm=1.13; f_number=1.4; hfov_deg=30.0; real_image_height_mm=0.6611335916511162; sanity_image_height_mm=0.652405804184277; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12541079-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=-2.22e+10, S8:A22=4e+06, S7:A24=4.43e+10, S8:A24=-2.81e+06, S7:A26=-5.86e+10, S8:A26=8.65e+05, S7:A28=4.61e+10, S7:A30=-1.63e+10 |
| US-12541079-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S2:A22=1.28e+12, S3:A22=2.84e+11, S5:A22=8.8e+10, S2:A24=-3.93e+12, S3:A24=-7.65e+11, S5:A24=-1.84e+11, S2:A26=8.02e+12, S3:A26=1.37e+12 |
| US-12541079-B2 | 5th Embodiment | success | data\zmx-staging\DATA-06f\US-12541079-B2-e5.zmx | 1.13653 | 0.64944 | 0.652406 | surfaces=10; r=10/10; d=10/10; nd_vd=4/10; asphere_surfaces=6; f_mm=1.13; f_number=1.4; hfov_deg=30.0; real_image_height_mm=0.6494396798495985; sanity_image_height_mm=0.652405804184277; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12541079-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=-2.34e+10, S8:A22=2.82e+08, S7:A24=4.46e+10, S8:A24=-4.45e+08, S7:A26=-5.62e+10, S8:A26=4.58e+08, S7:A28=4.19e+10, S8:A28=-2.77e+08 |
| US-12541079-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12541079-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S5:A22=-1.77e+08, S6:A22=1.21e+08, S7:A22=-2.44e+10, S8:A22=-5.5e+08, S7:A24=4.97e+10, S8:A24=8.13e+08, S7:A26=-6.72e+10, S8:A26=-7.95e+08 |
| US-12468121-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.278, S12:A22=-1.98e-06, S13:A22=-0.000511, S14:A22=0.00124, S15:A22=-0.00013, S13:A24=3.84e-05, S14:A24=-0.000182, S15:A24=1.11e-05 |
| US-12468121-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.19, S12:A22=2.06e-05, S13:A22=0.000808, S14:A22=0.00245, S15:A22=-0.000162, S13:A24=-4.76e-05, S14:A24=-0.000333, S15:A24=1.36e-05 |
| US-12468121-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.0164, S12:A22=3.72e-07, S13:A22=-0.000634, S14:A22=-0.00231, S15:A22=-0.000126, S13:A24=4.7e-05, S14:A24=0.000246, S15:A24=1.09e-05 |
| US-12468121-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.169, S12:A22=4.13e-05, S13:A22=-6.81e-05, S14:A22=-0.00493, S15:A22=-0.000104, S13:A24=1.55e-05, S14:A24=0.000557, S15:A24=9.51e-06 |
| US-12468121-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.237, S12:A22=7.68e-05, S13:A22=0.00243, S14:A22=-0.00116, S15:A22=-0.000233, S13:A24=-0.000166, S14:A24=6.53e-05, S15:A24=1.97e-05 |
| US-12468121-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-1.86, S12:A22=0.000223, S13:A22=0.00945, S14:A22=0.0102, S15:A22=-0.000522, S13:A24=-0.000699, S14:A24=-0.00156, S15:A24=4.4e-05 |
| US-12468121-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.0389, S14:A22=2.97e-06, S15:A22=-2.01e-06, S14:A24=-1.06e-07, S15:A24=4.32e-08 |
| US-12468121-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.189, S12:A22=6.78e-06, S13:A22=-4.02e-05, S14:A22=-0.00172, S15:A22=-4.09e-05, S13:A24=7.63e-06, S14:A24=0.000151, S15:A24=3.44e-06 |
| US-12468121-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.793, S15:A22=4.19e-07, S16:A22=6.86e-07, S15:A24=-2.13e-08, S16:A24=-1.43e-08 |
| US-12468121-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.949, S14:A22=-5.16e-07, S15:A22=1.56e-07 |
| US-20260169262-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12578550-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12571987-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260029620-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250327997-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12386154-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250155675-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250155701-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20240369807-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20240184082-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20240176104-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20240118520-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12669685-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260160982-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260153712-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260140349-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260110880-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12591117-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260086334-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260086330-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260072253-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260063874-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260063870-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12560782-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12554102-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260043988-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12345855-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12306467-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12292550-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12287461-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250116846-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12242033-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12493169-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12399348-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12320958-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12235419-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12235415-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12210213-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12197039-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12169324-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12147088-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12135409-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12124009-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12124006-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12656577-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12656578-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260147189-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12625349-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260110881-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260093094-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12607828-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260036791-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260009980-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12461345-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12429676-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12298484-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
