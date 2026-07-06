# DATA-06b2 patent-to-ZMX scale report

## Run contract

- random_seed: 20260706
- sample_size_patents: 60
- pool_count_patents: 224
- sample_method: Python random.Random(seed).sample(load_patent_pool(data/patents), 60); load_patent_pool de-duplicates normalized patent ids from sorted uspto-smartphone-batch*.jsonl files
- output_dir: data/zmx-staging/DATA-06b2-seed20260706
- source: local data/patents/uspto-smartphone-batch*.jsonl + USPTO PPUBS HTML
- runner: scripts.patent_to_zmx load_patent_pool + _convert_candidate + write_patent_zmx + load_normalized_zmx
- parser: deterministic NFKC-normalized multi-embodiment table parse; no numeric LLM fill
- strict_limit_check: exactly 60 patent candidates attempted; no expansion beyond sampled candidates
- elapsed_seconds: 1151.6

## Yield summary

- patent_candidates_attempted: 60
- embodiment_attempts: 265
- successes: 64
- failures: 201
- success_rate_by_embodiment_attempt: 64/265 (24.2%)
- patent_candidate_hit_rate: 16/60 (26.7%)
- spike_baseline_success_rate: 3/41 (7.3%)
- delta_vs_spike_baseline: +16.8 percentage points

## Failure reason buckets

| reason_bucket | failures | share_of_failures |
|---|---:|---:|
| trace did not reach image | 79 | 39.3% |
| unsupported nonzero high-order asphere terms | 45 | 22.4% |
| meta line not found | 34 | 16.9% |
| surface 14 radius is not numeric: IR-cut | 15 | 7.5% |
| surface table index break | 6 | 3.0% |
| surface 13 radius is not numeric: Prism | 4 | 2.0% |
| surface 14 radius is not numeric: Prism | 4 | 2.0% |
| surface 16 radius is not numeric: Lend | 4 | 2.0% |
| surface 6 radius is not numeric: Ape. | 2 | 1.0% |
| surface 2 radius is not numeric: Ape. | 2 | 1.0% |
| surface 5 radius is not numeric: Ape. | 2 | 1.0% |
| surface 14 radius is not numeric: IR-Cut | 2 | 1.0% |
| surface 1 radius is not numeric: Prism | 1 | 0.5% |
| surface 12 radius is not numeric: Prism | 1 | 0.5% |

## Sampled patent candidates

| # | patent_id | pool_file | line | attempts | successes | failures |
|---:|---|---|---:|---:|---:|---:|
| 1 | US-12493167-B2 | uspto-smartphone-batch1.jsonl | 6 | 1 | 0 | 1 |
| 2 | US-12248126-B2 | uspto-smartphone-batch4.jsonl | 14 | 8 | 6 | 2 |
| 3 | US-20250383531-A1 | uspto-smartphone-batch2.jsonl | 3 | 10 | 2 | 8 |
| 4 | US-20240176106-A1 | uspto-smartphone-batch5.jsonl | 63 | 1 | 0 | 1 |
| 5 | US-20260140346-A1 | uspto-smartphone-batch5.jsonl | 52 | 1 | 0 | 1 |
| 6 | US-10921568-B2 | uspto-smartphone-batch5.jsonl | 40 | 9 | 0 | 9 |
| 7 | US-20240036290-A1 | uspto-smartphone-batch5.jsonl | 65 | 1 | 0 | 1 |
| 8 | US-12481124-B2 | uspto-smartphone-batch1.jsonl | 23 | 1 | 0 | 1 |
| 9 | US-12523849-B2 | uspto-smartphone-batch3.jsonl | 1 | 1 | 0 | 1 |
| 10 | US-12443014-B2 | uspto-smartphone-batch2.jsonl | 5 | 8 | 0 | 8 |
| 11 | US-20260140289-A1 | uspto-smartphone-batch1.jsonl | 14 | 1 | 0 | 1 |
| 12 | US-20250035892-A1 | uspto-smartphone-batch5.jsonl | 27 | 7 | 0 | 7 |
| 13 | US-20260186251-A1 | uspto-smartphone-batch3.jsonl | 17 | 1 | 0 | 1 |
| 14 | US-20220035131-A1 | uspto-smartphone-batch5.jsonl | 38 | 11 | 4 | 7 |
| 15 | US-20260186268-A1 | uspto-smartphone-batch4.jsonl | 53 | 1 | 0 | 1 |
| 16 | US-20250341704-A1 | uspto-smartphone-batch1.jsonl | 10 | 1 | 0 | 1 |
| 17 | US-20220187578-A1 | uspto-smartphone-batch5.jsonl | 35 | 9 | 7 | 2 |
| 18 | US-11966029-B2 | uspto-smartphone-batch4.jsonl | 29 | 6 | 3 | 3 |
| 19 | US-12449639-B2 | uspto-smartphone-batch2.jsonl | 4 | 1 | 0 | 1 |
| 20 | US-20250334774-A1 | uspto-smartphone-batch1.jsonl | 11 | 1 | 0 | 1 |
| 21 | US-11927729-B2 | uspto-smartphone-batch2.jsonl | 28 | 10 | 1 | 9 |
| 22 | US-20250076615-A1 | uspto-smartphone-batch2.jsonl | 18 | 10 | 0 | 10 |
| 23 | US-12578554-B2 | uspto-smartphone-batch1.jsonl | 17 | 1 | 0 | 1 |
| 24 | US-20250377520-A1 | uspto-smartphone-batch1.jsonl | 22 | 1 | 0 | 1 |
| 25 | US-20260186239-A1 | uspto-smartphone-batch4.jsonl | 42 | 1 | 0 | 1 |
| 26 | US-20260186382-A1 | uspto-smartphone-batch4.jsonl | 55 | 1 | 0 | 1 |
| 27 | US-12379574-B2 | uspto-smartphone-batch3.jsonl | 4 | 1 | 0 | 1 |
| 28 | US-12216256-B2 | uspto-smartphone-batch4.jsonl | 15 | 6 | 2 | 4 |
| 29 | US-20250251569-A1 | uspto-smartphone-batch3.jsonl | 3 | 1 | 0 | 1 |
| 30 | US-12416791-B2 | uspto-smartphone-batch1.jsonl | 12 | 10 | 4 | 6 |
| 31 | US-11953657-B2 | uspto-smartphone-batch4.jsonl | 31 | 8 | 0 | 8 |
| 32 | US-20260186272-A1 | uspto-smartphone-batch4.jsonl | 57 | 1 | 0 | 1 |
| 33 | US-20250306338-A1 | uspto-smartphone-batch4.jsonl | 9 | 12 | 5 | 7 |
| 34 | US-20260169267-A1 | uspto-smartphone-batch3.jsonl | 13 | 1 | 0 | 1 |
| 35 | US-20250035890-A1 | uspto-smartphone-batch5.jsonl | 10 | 7 | 3 | 4 |
| 36 | US-20240264412-A1 | uspto-smartphone-batch4.jsonl | 23 | 8 | 6 | 2 |
| 37 | US-20250004254-A1 | uspto-smartphone-batch2.jsonl | 19 | 12 | 1 | 11 |
| 38 | US-11774728-B2 | uspto-smartphone-batch5.jsonl | 25 | 8 | 0 | 8 |
| 39 | US-12117596-B2 | uspto-smartphone-batch2.jsonl | 20 | 12 | 0 | 12 |
| 40 | US-12663616-B2 | uspto-smartphone-batch3.jsonl | 20 | 1 | 0 | 1 |
| 41 | US-12169265-B2 | uspto-smartphone-batch5.jsonl | 14 | 7 | 7 | 0 |
| 42 | US-20260126617-A1 | uspto-smartphone-batch4.jsonl | 63 | 1 | 0 | 1 |
| 43 | US-20260186250-A1 | uspto-smartphone-batch3.jsonl | 11 | 1 | 0 | 1 |
| 44 | US-12638661-B2 | uspto-smartphone-batch3.jsonl | 21 | 1 | 0 | 1 |
| 45 | US-20260186270-A1 | uspto-smartphone-batch4.jsonl | 52 | 1 | 0 | 1 |
| 46 | US-20230288669-A1 | uspto-smartphone-batch5.jsonl | 26 | 7 | 6 | 1 |
| 47 | US-20260186274-A1 | uspto-smartphone-batch4.jsonl | 51 | 1 | 0 | 1 |
| 48 | US-20250370222-A1 | uspto-smartphone-batch1.jsonl | 8 | 1 | 0 | 1 |
| 49 | US-20260086326-A1 | uspto-smartphone-batch4.jsonl | 65 | 1 | 0 | 1 |
| 50 | US-20260169265-A1 | uspto-smartphone-batch3.jsonl | 16 | 1 | 0 | 1 |
| 51 | US-12372750-B2 | uspto-smartphone-batch3.jsonl | 5 | 1 | 0 | 1 |
| 52 | US-12216255-B2 | uspto-smartphone-batch4.jsonl | 16 | 8 | 0 | 8 |
| 53 | US-20240248285-A1 | uspto-smartphone-batch4.jsonl | 24 | 8 | 0 | 8 |
| 54 | US-12461337-B2 | uspto-smartphone-batch1.jsonl | 25 | 1 | 0 | 1 |
| 55 | US-20250370227-A1 | uspto-smartphone-batch4.jsonl | 6 | 12 | 3 | 9 |
| 56 | US-20200003996-A1 | uspto-smartphone-batch5.jsonl | 44 | 8 | 4 | 4 |
| 57 | US-20260186243-A1 | uspto-smartphone-batch4.jsonl | 43 | 1 | 0 | 1 |
| 58 | US-12050306-B2 | uspto-smartphone-batch5.jsonl | 29 | 10 | 0 | 10 |
| 59 | US-20260186255-A1 | uspto-smartphone-batch4.jsonl | 44 | 1 | 0 | 1 |
| 60 | US-12546974-B2 | uspto-smartphone-batch1.jsonl | 19 | 1 | 0 | 1 |

## Per-embodiment attempts

| patent | embodiment | status | zmx | efl_mm | real_imh_mm | f_tan_sanity_mm | field coverage | reason |
|---|---|---|---|---:|---:|---:|---|---|
| US-12493167-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12248126-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12248126-B2 | 2nd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12248126-B2-e2.zmx | 2.64459 | 3.05659 | 3.88464 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=2.64; f_number=1.95; hfov_deg=55.8; real_image_height_mm=3.0565909511860285; sanity_image_height_mm=3.8846420337647176; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12248126-B2 | 3rd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12248126-B2-e3.zmx | 2.43882 | 2.81723 | 4.3303 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=2.44; f_number=1.95; hfov_deg=60.6; real_image_height_mm=2.817228698791419; sanity_image_height_mm=4.330302393246352; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12248126-B2 | 4th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12248126-B2-e4.zmx | 2.49481 | 2.79165 | 4.43679 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=2.5; f_number=1.92; hfov_deg=60.6; real_image_height_mm=2.7916501037867643; sanity_image_height_mm=4.436785238981918; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12248126-B2 | 5th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12248126-B2-e5.zmx | 3.06219 | 2.81568 | 3.98787 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=3.06; f_number=1.93; hfov_deg=52.5; real_image_height_mm=2.815679034208536; sanity_image_height_mm=3.9878696408940897; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12248126-B2 | 6th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12248126-B2-e6.zmx | 2.58772 | 2.49489 | 3.37535 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=2.59; f_number=1.62; hfov_deg=52.5; real_image_height_mm=2.494886532956688; sanity_image_height_mm=3.3753537156587226; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12248126-B2 | 7th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12248126-B2-e7.zmx | 2.58694 | 2.70186 | 3.36232 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=2.58; f_number=1.75; hfov_deg=52.5; real_image_height_mm=2.7018599549520306; sanity_image_height_mm=3.362321461930311; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12248126-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250383531-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250383531-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250383531-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250383531-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 6 radius is not numeric: Ape. |
| US-20250383531-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 2 radius is not numeric: Ape. |
| US-20250383531-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 5 radius is not numeric: Ape. |
| US-20250383531-A1 | 7th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250383531-A1-e7.zmx | 0.950051 | 0.722054 | 3.54545 | surfaces=20; r=20/20; d=20/20; nd_vd=9/20; asphere_surfaces=14; f_mm=0.95; f_number=1.3; hfov_deg=75.0; real_image_height_mm=0.7220542716791011; sanity_image_height_mm=3.5454482671904337; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250383531-A1 | 8th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250383531-A1-e8.zmx | 3.57561 | 1.42988 | 2.6101 | surfaces=20; r=20/20; d=20/20; nd_vd=9/20; asphere_surfaces=14; f_mm=0.95; f_number=1.45; hfov_deg=70.0; real_image_height_mm=1.4298808478931346; sanity_image_height_mm=2.6101035484818906; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250383531-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 15, found 16 |
| US-20250383531-A1 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240176106-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260140346-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-10921568-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10921568-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10921568-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10921568-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 6, found 8 |
| US-10921568-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10921568-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-Cut |
| US-10921568-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10921568-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-10921568-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20240036290-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12481124-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12523849-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12443014-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: surface 13 radius is not numeric: Prism |
| US-12443014-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 13 radius is not numeric: Prism |
| US-12443014-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 13 radius is not numeric: Prism |
| US-12443014-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 13 radius is not numeric: Prism |
| US-12443014-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: Prism |
| US-12443014-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: Prism |
| US-12443014-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: Prism |
| US-12443014-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: Prism |
| US-20260140289-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250035892-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250035892-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250035892-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250035892-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250035892-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250035892-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250035892-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20260186251-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20220035131-A1 | 1st Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20220035131-A1-e1.zmx | 3.182 | 2.08134 | 2.75564 | surfaces=15; r=15/15; d=15/15; nd_vd=6/15; asphere_surfaces=10; f_mm=3.17; f_number=2.46; hfov_deg=41.0; real_image_height_mm=2.081335443367674; sanity_image_height_mm=2.755638958877438; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20220035131-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220035131-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220035131-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220035131-A1 | 5th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20220035131-A1-e5.zmx | 3.16977 | 3.15508 | 3.17 | surfaces=15; r=15/15; d=15/15; nd_vd=6/15; asphere_surfaces=10; f_mm=3.17; f_number=2.23; hfov_deg=45.0; real_image_height_mm=3.1550806914800265; sanity_image_height_mm=3.1699999999999995; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20220035131-A1 | 6th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20220035131-A1-e6.zmx | 2.83568 | 2.89918 | 2.8399 | surfaces=15; r=15/15; d=15/15; nd_vd=6/15; asphere_surfaces=10; f_mm=2.83; f_number=2.05; hfov_deg=45.1; real_image_height_mm=2.8991779901218817; sanity_image_height_mm=2.8398958451224114; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20220035131-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220035131-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220035131-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20220035131-A1 | 10th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20220035131-A1-e10.zmx | 2.95886 | 2.91859 | 2.95 | surfaces=16; r=16/16; d=16/16; nd_vd=6/16; asphere_surfaces=10; f_mm=2.95; f_number=2.05; hfov_deg=45.0; real_image_height_mm=2.918586630250893; sanity_image_height_mm=2.9499999999999997; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20220035131-A1 | 11th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20260186268-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250341704-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20220187578-A1 | 1st Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20220187578-A1-e1.zmx | 22.7177 | 3.51336 | 3.47512 | surfaces=14; r=14/14; d=14/14; nd_vd=6/14; asphere_surfaces=10; f_mm=22.71; f_number=3.06; hfov_deg=8.7; real_image_height_mm=3.5133560440744214; sanity_image_height_mm=3.475118332703655; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20220187578-A1 | 2nd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20220187578-A1-e2.zmx | 22.6418 | 3.5428 | 3.50641 | surfaces=14; r=14/14; d=14/14; nd_vd=6/14; asphere_surfaces=10; f_mm=22.65; f_number=2.9; hfov_deg=8.8; real_image_height_mm=3.542803096542542; sanity_image_height_mm=3.5064052570128195; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20220187578-A1 | 3rd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20220187578-A1-e3.zmx | 21.2562 | 3.53661 | 3.51957 | surfaces=14; r=14/14; d=14/14; nd_vd=6/14; asphere_surfaces=10; f_mm=21.26; f_number=3.05; hfov_deg=9.4; real_image_height_mm=3.5366087141815687; sanity_image_height_mm=3.519570176803943; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20220187578-A1 | 4th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20220187578-A1-e4.zmx | 19.2452 | 3.51829 | 3.46182 | surfaces=14; r=14/14; d=14/14; nd_vd=6/14; asphere_surfaces=10; f_mm=19.24; f_number=2.95; hfov_deg=10.2; real_image_height_mm=3.518290366632695; sanity_image_height_mm=3.461822402132952; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20220187578-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 1 radius is not numeric: Prism |
| US-20220187578-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 12 radius is not numeric: Prism |
| US-20220187578-A1 | 7th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20220187578-A1-e7.zmx | 22.7496 | 3.53972 | 3.52189 | surfaces=15; r=15/15; d=15/15; nd_vd=6/15; asphere_surfaces=10; f_mm=22.75; f_number=3.06; hfov_deg=8.8; real_image_height_mm=3.5397224405308925; sanity_image_height_mm=3.521886074924576; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20220187578-A1 | 8th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20220187578-A1-e8.zmx | 22.7667 | 3.56707 | 3.52343 | surfaces=15; r=15/15; d=15/15; nd_vd=6/15; asphere_surfaces=10; f_mm=22.76; f_number=3.06; hfov_deg=8.8; real_image_height_mm=3.5670658219780513; sanity_image_height_mm=3.523434156715752; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20220187578-A1 | 9th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20220187578-A1-e9.zmx | 19.1053 | 4.15356 | 3.46924 | surfaces=14; r=14/14; d=14/14; nd_vd=6/14; asphere_surfaces=10; f_mm=19.09; f_number=2.95; hfov_deg=10.3; real_image_height_mm=4.153562537274523; sanity_image_height_mm=3.4692409732545135; finite_final_rays=2/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11966029-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11966029-B2 | 2nd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-11966029-B2-e2.zmx | 4.02832 | 5.15486 | 3.01483 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=4.03; f_number=2.0; hfov_deg=36.8; real_image_height_mm=5.15485655910468; sanity_image_height_mm=3.014825183079246; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11966029-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11966029-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11966029-B2 | 5th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-11966029-B2-e5.zmx | 3.66051 | 5.76983 | 3.0795 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=3.67; f_number=2.3; hfov_deg=40.0; real_image_height_mm=5.7698308670930265; sanity_image_height_mm=3.079495646420617; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11966029-B2 | 6th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-11966029-B2-e6.zmx | 4.0615 | 7.88727 | 3.03727 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=4.06; f_number=2.4; hfov_deg=36.8; real_image_height_mm=7.887270388689468; sanity_image_height_mm=3.0372680504470813; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12449639-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250334774-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-11927729-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11927729-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11927729-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11927729-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 6 radius is not numeric: Ape. |
| US-11927729-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 2 radius is not numeric: Ape. |
| US-11927729-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 5 radius is not numeric: Ape. |
| US-11927729-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11927729-B2 | 8th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-11927729-B2-e8.zmx | 3.57561 | 1.42988 | 2.6101 | surfaces=20; r=20/20; d=20/20; nd_vd=9/20; asphere_surfaces=14; f_mm=0.95; f_number=1.45; hfov_deg=70.0; real_image_height_mm=1.4298808478931346; sanity_image_height_mm=2.6101035484818906; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11927729-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 15, found 16 |
| US-11927729-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250076615-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S2:A22=-4.09e+08, S3:A22=1.95e+07, S4:A22=2.71e+03, S2:A24=4.97e+08, S3:A24=-1.08e+07, S2:A26=-2.66e+08, S8:A22=-4.16e+03, S9:A22=-32.8 |
| US-20250076615-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S2:A22=1.06e+08, S3:A22=5.34e+04, S2:A24=-1.43e+08, S3:A24=-1.81e+04, S2:A26=8.46e+07, S8:A22=1.31e+04, S9:A22=6.71e+03, S10:A22=184 |
| US-20250076615-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S2:A22=-5.28e+09, S3:A22=-5.49e+09, S5:A22=-6.06e+09, S6:A22=9.72e+08, S8:A22=6.91e+06, S2:A24=1.11e+10, S3:A24=1.82e+10, S5:A24=1.37e+10 |
| US-20250076615-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S2:A22=1.75e+08, S3:A22=1.05e+10, S4:A22=6e+09, S5:A22=-9.58e+08, S7:A22=2.05e+06, S2:A24=-1.46e+08, S3:A24=-2.45e+10, S4:A24=-1.25e+10 |
| US-20250076615-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S2:A22=-3.7e+09, S3:A22=1.2e+10, S5:A22=1.06e+10, S6:A22=2.64e+09, S8:A22=4.12e+06, S2:A24=7.27e+09, S3:A24=-2.59e+10, S5:A24=-2.73e+10 |
| US-20250076615-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S2:A22=-8.12e+09, S3:A22=1.41e+10, S5:A22=3.42e+09, S6:A22=-2.57e+09, S8:A22=-1.59e+07, S2:A24=1.74e+10, S3:A24=-3.69e+10, S5:A24=-4.89e+09 |
| US-20250076615-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S2:A22=3.37e+08, S3:A22=6.93e+09, S4:A22=1.01e+10, S5:A22=-2.81e+09, S7:A22=3.81e+06, S2:A24=-4.29e+08, S3:A24=-1.44e+10, S4:A24=-2.11e+10 |
| US-20250076615-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S2:A22=6.19e+09, S3:A22=-6.6e+09, S5:A22=-9.15e+09, S6:A22=2.28e+09, S8:A22=1.79e+06, S2:A24=-1.3e+10, S3:A24=1.72e+10, S5:A24=2.16e+10 |
| US-20250076615-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S2:A22=3.32e+09, S3:A22=5.98e+10, S4:A22=3.4e+10, S5:A22=-3.51e+10, S7:A22=-1.33e+08, S2:A24=-4.65e+09, S3:A24=-1.21e+11, S4:A24=-6.75e+10 |
| US-20250076615-A1 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S2:A22=1.41e+09, S3:A22=1.11e+10, S5:A22=1.15e+10, S6:A22=5.08e+09, S8:A22=9.02e+07, S2:A24=-2.73e+09, S3:A24=-2.78e+10, S5:A24=-2.54e+10 |
| US-12578554-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250377520-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186239-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186382-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12379574-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12216256-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12216256-B2 | 2nd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12216256-B2-e2.zmx | 4.02832 | 5.15486 | 3.01483 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=4.03; f_number=2.0; hfov_deg=36.8; real_image_height_mm=5.15485655910468; sanity_image_height_mm=3.014825183079246; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12216256-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12216256-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12216256-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12216256-B2 | 6th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12216256-B2-e6.zmx | 4.0615 | 5.14529 | 3.03727 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=4.06; f_number=2.4; hfov_deg=36.8; real_image_height_mm=5.145292518228324; sanity_image_height_mm=3.0372680504470813; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250251569-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12416791-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 9, found 6 |
| US-12416791-B2 | 2nd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12416791-B2-e2.zmx | 1.09086 | 1.50088 | 4.06794 | surfaces=16; r=16/16; d=16/16; nd_vd=6/16; asphere_surfaces=12; f_mm=1.09; f_number=1.98; hfov_deg=75.0; real_image_height_mm=1.500878802167457; sanity_image_height_mm=4.067935380250077; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12416791-B2 | 3rd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12416791-B2-e3.zmx | 1.12205 | 1.10727 | -16.0167 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=1.12; f_number=2.05; hfov_deg=94.0; real_image_height_mm=1.1072654433752256; sanity_image_height_mm=-16.016746207517354; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12416791-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12416791-B2 | 5th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12416791-B2-e5.zmx | 1.03982 | 1.64219 | 1.69845e+16 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=10; f_mm=1.04; f_number=2.04; hfov_deg=90.0; real_image_height_mm=1.6421862704959866; sanity_image_height_mm=1.6984488927323186e+16; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12416791-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12416791-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12416791-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12416791-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12416791-B2 | 10th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12416791-B2-e10.zmx | 1.13741 | 1.63862 | 1.84543e+16 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=10; f_mm=1.13; f_number=2.04; hfov_deg=90.0; real_image_height_mm=1.6386206833261958; sanity_image_height_mm=1.845430046911077e+16; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-11953657-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11953657-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11953657-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11953657-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11953657-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11953657-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11953657-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11953657-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20260186272-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250306338-A1 | 1st Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250306338-A1-e1.zmx | 1.9115 | 2.40869 | 6.05775 | surfaces=18; r=18/18; d=18/18; nd_vd=7/18; asphere_surfaces=12; f_mm=1.91; f_number=2.4; hfov_deg=72.5; real_image_height_mm=2.4086891724846966; sanity_image_height_mm=6.057746072513737; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250306338-A1 | 2nd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250306338-A1-e2.zmx | 1.7999 | 2.01194 | 7.44031 | surfaces=18; r=18/18; d=18/18; nd_vd=7/18; asphere_surfaces=12; f_mm=1.8; f_number=2.27; hfov_deg=76.4; real_image_height_mm=2.011943273903791; sanity_image_height_mm=7.440308237249201; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250306338-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250306338-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250306338-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250306338-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250306338-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250306338-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250306338-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250306338-A1 | 10th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250306338-A1-e10.zmx | 1.8482 | 2.36416 | 6.8564 | surfaces=17; r=17/17; d=17/17; nd_vd=7/17; asphere_surfaces=12; f_mm=1.85; f_number=2.32; hfov_deg=74.9; real_image_height_mm=2.3641556463035576; sanity_image_height_mm=6.856404814001568; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250306338-A1 | 11th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250306338-A1-e11.zmx | 1.89082 | 2.43045 | 6.14354 | surfaces=17; r=17/17; d=17/17; nd_vd=7/17; asphere_surfaces=12; f_mm=1.89; f_number=2.35; hfov_deg=72.9; real_image_height_mm=2.4304453830778554; sanity_image_height_mm=6.143541014456692; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250306338-A1 | 12th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250306338-A1-e12.zmx | 2.04045 | 2.42953 | 3.90216 | surfaces=17; r=17/17; d=17/17; nd_vd=7/17; asphere_surfaces=12; f_mm=2.04; f_number=2.0; hfov_deg=62.4; real_image_height_mm=2.429528643401465; sanity_image_height_mm=3.90216009762302; finite_final_rays=2/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20260169267-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250035890-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S1:A22=-0.000225, S2:A22=-1.79e+05, S3:A22=-2.38e+04, S1:A24=6.46e-06, S2:A24=1.75e+05, S1:A26=-2.59e-08, S2:A26=-9.13e+04, S1:A28=8.49e-09 |
| US-20250035890-A1 | 2nd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250035890-A1-e2.zmx | 0.543531 | 1.98032 | 3.06249 | surfaces=17; r=17/17; d=17/17; nd_vd=7/17; asphere_surfaces=12; f_mm=0.54; f_number=1.8; hfov_deg=80.0; real_image_height_mm=1.9803235686302958; sanity_image_height_mm=3.062492182593562; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250035890-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S1:A22=-0.00108, S2:A22=-5.64e+03, S4:A22=-3.21e+04, S5:A22=1.4e+13, S7:A22=-9.97e+08, S1:A24=7.62e-05, S2:A24=1.23e+03, S4:A24=-5.66e+13 |
| US-20250035890-A1 | 4th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250035890-A1-e4.zmx | 0.545183 | 0.997862 | 3.06249 | surfaces=17; r=17/17; d=17/17; nd_vd=7/17; asphere_surfaces=12; f_mm=0.54; f_number=1.8; hfov_deg=80.0; real_image_height_mm=0.99786208905781; sanity_image_height_mm=3.062492182593562; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250035890-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S1:A22=-0.000246, S2:A22=-4.05e+04, S4:A22=1.82e+04, S5:A22=-1.78e+14, S7:A22=-1.15e+10, S1:A24=1.24e-05, S2:A24=9.09e+03, S4:A24=9.83e+14 |
| US-20250035890-A1 | 6th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250035890-A1-e6.zmx | 0.43809 | 0.820002 | 1.70135 | surfaces=17; r=17/17; d=17/17; nd_vd=7/17; asphere_surfaces=12; f_mm=0.44; f_number=1.8; hfov_deg=75.5; real_image_height_mm=0.820001840666875; sanity_image_height_mm=1.7013537617554444; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250035890-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S1:A22=-0.00419, S2:A22=2.66e+05, S4:A22=-1.19e+06, S5:A22=-1.21e+14, S7:A22=6.2e+09, S1:A24=0.000325, S2:A24=-8.27e+04, S4:A24=6.64e+14 |
| US-20240264412-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240264412-A1 | 2nd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20240264412-A1-e2.zmx | 2.64459 | 3.05659 | 3.88464 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=2.64; f_number=1.95; hfov_deg=55.8; real_image_height_mm=3.0565909511860285; sanity_image_height_mm=3.8846420337647176; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20240264412-A1 | 3rd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20240264412-A1-e3.zmx | 2.43882 | 2.81723 | 4.3303 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=2.44; f_number=1.95; hfov_deg=60.6; real_image_height_mm=2.817228698791419; sanity_image_height_mm=4.330302393246352; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20240264412-A1 | 4th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20240264412-A1-e4.zmx | 2.49481 | 2.79165 | 4.43679 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=2.5; f_number=1.92; hfov_deg=60.6; real_image_height_mm=2.7916501037867643; sanity_image_height_mm=4.436785238981918; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20240264412-A1 | 5th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20240264412-A1-e5.zmx | 3.06219 | 2.81568 | 3.98787 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=3.06; f_number=1.93; hfov_deg=52.5; real_image_height_mm=2.815679034208536; sanity_image_height_mm=3.9878696408940897; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20240264412-A1 | 6th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20240264412-A1-e6.zmx | 2.58772 | 2.49489 | 3.37535 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=2.59; f_number=1.62; hfov_deg=52.5; real_image_height_mm=2.494886532956688; sanity_image_height_mm=3.3753537156587226; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20240264412-A1 | 7th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20240264412-A1-e7.zmx | 2.58694 | 2.70186 | 3.36232 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=2.58; f_number=1.75; hfov_deg=52.5; real_image_height_mm=2.7018599549520306; sanity_image_height_mm=3.362321461930311; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20240264412-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250004254-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.023, S9:A22=-0.000371, S10:A22=-0.000265, S11:A22=0.000179, S8:A24=-0.00139, S9:A24=1.83e-05, S10:A24=-1.01e-05, S8:A26=-5.32e-07 |
| US-20250004254-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.0169, S9:A22=-5.03e-05, S10:A22=-0.000197, S11:A22=0.000126, S8:A24=0.000985, S9:A24=1.64e-05, S10:A24=-6.87e-06, S8:A26=-5.76e-07 |
| US-20250004254-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.00937, S9:A22=-0.0243, S10:A22=-0.0321, S11:A22=0.000684, S8:A24=0.000474, S9:A24=0.00197, S10:A24=0.00322, S11:A24=-3.23e-05 |
| US-20250004254-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.0191, S9:A22=-0.0175, S10:A22=-0.0401, S11:A22=0.000843, S8:A24=-0.0012, S9:A24=0.00146, S10:A24=0.00406, S11:A24=-7.47e-05 |
| US-20250004254-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.00113, S9:A22=-0.00527, S10:A22=5.16e-07, S8:A24=-5.03e-05, S9:A24=0.000387, S8:A26=-1.26e-05 |
| US-20250004254-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.000589, S9:A22=-6.72e-05, S10:A22=-0.00027, S11:A22=8.05e-06, S8:A24=1.67e-05, S9:A24=-3.32e-07, S8:A26=-4.66e-07, S9:A26=5.97e-09 |
| US-20250004254-A1 | 7th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250004254-A1-e7.zmx | 3.63409 | 0.827558 | 3.19782 | surfaces=15; r=15/15; d=15/15; nd_vd=6/15; asphere_surfaces=10; f_mm=3.64; f_number=2.47; hfov_deg=41.3; real_image_height_mm=0.8275575037586416; sanity_image_height_mm=3.197818136444526; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250004254-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.0314, S9:A22=-0.000113, S10:A22=-0.00092, S11:A22=-2.18e-05, S8:A24=0.00181, S9:A24=5.94e-05, S10:A24=1.34e-06, S8:A26=-1.69e-06 |
| US-20250004254-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.00117, S9:A22=-0.000802, S10:A22=9.87e-05, S8:A24=7.32e-05, S9:A24=2.58e-05, S10:A24=-5.52e-06, S8:A26=1.37e-07 |
| US-20250004254-A1 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.00112, S9:A22=-0.00195, S10:A22=-0.00447, S11:A22=0.000106, S8:A24=9.57e-05, S9:A24=0.000289, S10:A24=-5.82e-06, S8:A26=-8.27e-06 |
| US-20250004254-A1 | 11th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.125, S9:A22=0.0419, S10:A22=0.0294, S11:A22=0.00769, S8:A24=-0.00879, S9:A24=-0.00404, S10:A24=-0.00365, S11:A24=-0.000749 |
| US-20250004254-A1 | 12th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.0579, S9:A22=-0.107, S10:A22=-0.00361, S11:A22=0.000228, S8:A24=-0.00368, S9:A24=0.0105, S10:A24=0.000289, S11:A24=-1.32e-05 |
| US-11774728-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S14:A22=5.06e-05, S15:A22=-1.51e-05, S16:A22=1.84e-06, S14:A24=-2.2e-06, S15:A24=1.01e-06, S16:A24=-9.8e-08, S15:A26=-4.5e-08, S16:A26=3.46e-09 |
| US-11774728-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S14:A22=1.26e-05, S15:A22=-1.41e-05, S16:A22=1.06e-06, S14:A24=-4.2e-07, S15:A24=1.06e-06, S16:A24=-5.63e-08, S15:A26=-5.4e-08, S16:A26=1.99e-09 |
| US-11774728-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S12:A22=0.000166, S14:A22=-6.96e-05, S16:A22=-9.17e-07, S17:A22=3.67e-09, S14:A24=2.4e-06, S16:A24=3.08e-08, S17:A24=-8.43e-11, S16:A26=-4.62e-10 |
| US-11774728-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S15:A22=-0.000178, S16:A22=-1.98e-05, S17:A22=2.37e-07, S15:A24=8.09e-06, S16:A24=1.41e-06, S17:A24=-1.22e-08, S16:A26=-6.75e-08, S17:A26=4.21e-10 |
| US-11774728-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S14:A22=-2.19e-06, S15:A22=-1.8e-05, S16:A22=4.19e-07, S14:A24=5.41e-08, S15:A24=1.24e-06, S16:A24=-2e-08, S15:A26=-5.7e-08, S16:A26=6.36e-10 |
| US-11774728-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S15:A22=0.000249, S16:A22=-3.5e-05, S17:A22=2.66e-07, S15:A24=-1.02e-05, S16:A24=2.48e-06, S17:A24=-8.63e-09, S16:A26=-1.17e-07, S17:A26=1.12e-10 |
| US-11774728-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S14:A22=1.67e-05, S15:A22=-1.96e-05, S16:A22=1.01e-06, S14:A24=-5.82e-07, S15:A24=1.48e-06, S16:A24=-5.25e-08, S15:A26=-7.54e-08, S16:A26=1.82e-09 |
| US-11774728-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S14:A22=-6.56e-05, S15:A22=-1.45e-05, S16:A22=-9.67e-07, S14:A24=1.97e-06, S15:A24=8.94e-07, S16:A24=6.26e-08, S15:A26=-3.72e-08, S16:A26=-2.6e-09 |
| US-12117596-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.023, S9:A22=-0.000371, S10:A22=-0.000265, S11:A22=0.000179, S8:A24=-0.00139, S9:A24=1.83e-05, S10:A24=-1.01e-05, S8:A26=-5.32e-07 |
| US-12117596-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.0169, S9:A22=-5.03e-05, S10:A22=-0.000197, S11:A22=0.000126, S8:A24=0.000985, S9:A24=1.64e-05, S10:A24=-6.87e-06, S8:A26=-5.76e-07 |
| US-12117596-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.00937, S9:A22=-0.0243, S10:A22=-0.0321, S11:A22=0.000684, S8:A24=0.000474, S9:A24=0.00197, S10:A24=0.00322, S11:A24=-3.23e-05 |
| US-12117596-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.0191, S9:A22=-0.0175, S10:A22=-0.0401, S11:A22=0.000843, S8:A24=-0.0012, S9:A24=0.00146, S10:A24=0.00406, S11:A24=-7.47e-05 |
| US-12117596-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.00113, S9:A22=-0.00527, S10:A22=5.16e-07, S8:A24=-5.03e-05, S9:A24=0.000387, S8:A26=-1.26e-05, S9:A26=147 |
| US-12117596-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.000589, S9:A22=-6.72e-05, S10:A22=-0.00027, S11:A22=8.05e-06, S8:A24=1.67e-05, S9:A24=-3.32e-07, S8:A26=-4.66e-07, S9:A26=5.97e-09 |
| US-12117596-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12117596-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.0314, S9:A22=-0.000113, S10:A22=-0.00092, S11:A22=-2.18e-05, S8:A24=0.00181, S9:A24=5.94e-05, S10:A24=1.34e-06, S8:A26=-1.69e-06 |
| US-12117596-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.00117, S9:A22=-0.000802, S10:A22=9.87e-05, S8:A24=7.32e-05, S9:A24=2.58e-05, S10:A24=-5.52e-06, S8:A26=1.37e-07, S9:A26=199 |
| US-12117596-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-0.00112, S9:A22=-0.00195, S10:A22=-0.00447, S11:A22=0.000106, S8:A24=9.57e-05, S9:A24=0.000289, S10:A24=-5.82e-06, S8:A26=-8.27e-06 |
| US-12117596-B2 | 11th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.125, S9:A22=0.0419, S10:A22=0.0294, S11:A22=0.00769, S8:A24=-0.00879, S9:A24=-0.00404, S10:A24=-0.00365, S11:A24=-0.000749 |
| US-12117596-B2 | 12th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=0.0579, S9:A22=-0.107, S10:A22=-0.00361, S11:A22=0.000228, S8:A24=-0.00368, S9:A24=0.0105, S10:A24=0.000289, S11:A24=-1.32e-05 |
| US-12663616-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12169265-B2 | 1st Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12169265-B2-e1.zmx | 4.29356 | 3.91867 | 3.94022 | surfaces=19; r=19/19; d=19/19; nd_vd=8/19; asphere_surfaces=14; f_mm=4.3; f_number=1.5; hfov_deg=42.5; real_image_height_mm=3.9186714829366656; sanity_image_height_mm=3.9402240482749202; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12169265-B2 | 2nd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12169265-B2-e2.zmx | 4.43106 | 3.98534 | 3.91933 | surfaces=19; r=19/19; d=19/19; nd_vd=8/19; asphere_surfaces=14; f_mm=4.43; f_number=1.7; hfov_deg=41.5; real_image_height_mm=3.9853399510869676; sanity_image_height_mm=3.919332921982831; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12169265-B2 | 3rd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12169265-B2-e3.zmx | 4.16662 | 3.534 | 3.51147 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=4.17; f_number=1.75; hfov_deg=40.1; real_image_height_mm=3.5340025816295237; sanity_image_height_mm=3.5114660576628385; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12169265-B2 | 4th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12169265-B2-e4.zmx | 4.31012 | 3.71368 | 3.65515 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=4.31; f_number=1.8; hfov_deg=40.3; real_image_height_mm=3.713683678577087; sanity_image_height_mm=3.655145809977954; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12169265-B2 | 5th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12169265-B2-e5.zmx | 4.20249 | 3.90556 | 3.80833 | surfaces=19; r=19/19; d=19/19; nd_vd=8/19; asphere_surfaces=14; f_mm=4.2; f_number=1.65; hfov_deg=42.2; real_image_height_mm=3.9055572877739846; sanity_image_height_mm=3.8083274446430684; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12169265-B2 | 6th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12169265-B2-e6.zmx | 4.58434 | 3.83104 | 3.97598 | surfaces=19; r=19/19; d=19/19; nd_vd=8/19; asphere_surfaces=14; f_mm=4.59; f_number=1.65; hfov_deg=40.9; real_image_height_mm=3.8310353463693754; sanity_image_height_mm=3.975982723572123; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-12169265-B2 | 7th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-12169265-B2-e7.zmx | 4.60242 | 3.84411 | 3.99872 | surfaces=19; r=19/19; d=19/19; nd_vd=8/19; asphere_surfaces=14; f_mm=4.6; f_number=1.69; hfov_deg=41.0; real_image_height_mm=3.8441069753608135; sanity_image_height_mm=3.998718993954642; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20260126617-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186250-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12638661-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186270-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20230288669-A1 | 1st Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20230288669-A1-e1.zmx | 2.40317 | 3.22193 | 33.4817 | surfaces=19; r=19/19; d=19/19; nd_vd=9/19; asphere_surfaces=6; f_mm=2.4; f_number=2.05; hfov_deg=85.9; real_image_height_mm=3.221932451084139; sanity_image_height_mm=33.4817265341034; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20230288669-A1 | 2nd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20230288669-A1-e2.zmx | 2.35429 | 3.57855 | 27.4116 | surfaces=19; r=19/19; d=19/19; nd_vd=8/19; asphere_surfaces=8; f_mm=2.35; f_number=2.09; hfov_deg=85.1; real_image_height_mm=3.578550168137935; sanity_image_height_mm=27.411563892124413; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20230288669-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S1:A22=-9.08e-17, S1:A24=4.55e-19 |
| US-20230288669-A1 | 4th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20230288669-A1-e4.zmx | 2.4006 | 3.12834 | 72.3471 | surfaces=19; r=19/19; d=19/19; nd_vd=9/19; asphere_surfaces=6; f_mm=2.4; f_number=2.05; hfov_deg=88.1; real_image_height_mm=3.1283400905070478; sanity_image_height_mm=72.34708527734212; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20230288669-A1 | 5th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20230288669-A1-e5.zmx | 2.26354 | 3.42917 | 18.6756 | surfaces=19; r=19/19; d=19/19; nd_vd=8/19; asphere_surfaces=12; f_mm=2.26; f_number=2.08; hfov_deg=83.1; real_image_height_mm=3.4291662022978664; sanity_image_height_mm=18.67563367343646; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20230288669-A1 | 6th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20230288669-A1-e6.zmx | 2.29636 | 3.2367 | 26.8283 | surfaces=19; r=19/19; d=19/19; nd_vd=9/19; asphere_surfaces=6; f_mm=2.3; f_number=2.09; hfov_deg=85.1; real_image_height_mm=3.236704553881599; sanity_image_height_mm=26.828339128462186; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20230288669-A1 | 7th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20230288669-A1-e7.zmx | 2.32992 | 3.14868 | 27.1783 | surfaces=19; r=19/19; d=19/19; nd_vd=9/19; asphere_surfaces=6; f_mm=2.33; f_number=1.93; hfov_deg=85.1; real_image_height_mm=3.1486842317909014; sanity_image_height_mm=27.178273986659523; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20260186274-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250370222-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260086326-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260169265-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12372750-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12216255-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12216255-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12216255-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12216255-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12216255-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12216255-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12216255-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12216255-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240248285-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240248285-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240248285-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240248285-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240248285-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240248285-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240248285-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240248285-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12461337-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250370227-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250370227-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Lend |
| US-20250370227-A1 | 3rd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250370227-A1-e3.zmx | 3.97007 | 2.91625 | 2.80053 | surfaces=20; r=20/20; d=20/20; nd_vd=9/20; asphere_surfaces=16; f_mm=3.97; f_number=1.75; hfov_deg=35.2; real_image_height_mm=2.916245786063329; sanity_image_height_mm=2.8005269320736104; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250370227-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250370227-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Lend |
| US-20250370227-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Lend |
| US-20250370227-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Lend |
| US-20250370227-A1 | 8th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250370227-A1-e8.zmx | 6.04791 | 5.14785 | 4.86432 | surfaces=20; r=20/20; d=20/20; nd_vd=9/20; asphere_surfaces=16; f_mm=6.05; f_number=2.5; hfov_deg=38.8; real_image_height_mm=5.147847380040968; sanity_image_height_mm=4.864324887711993; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250370227-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250370227-A1 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250370227-A1 | 11th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20250370227-A1 | 12th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20250370227-A1-e12.zmx | 8.57364 | 5.92138 | 5.59323 | surfaces=20; r=20/20; d=20/20; nd_vd=9/20; asphere_surfaces=16; f_mm=8.58; f_number=2.5; hfov_deg=33.1; real_image_height_mm=5.921383974088757; sanity_image_height_mm=5.593231633174522; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20200003996-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 5, found 6 |
| US-20200003996-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20200003996-A1 | 3rd Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20200003996-A1-e3.zmx | 2.41636 | 1.34507 | 2.88404 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=2.42; f_number=2.08; hfov_deg=50.0; real_image_height_mm=1.3450678992232006; sanity_image_height_mm=2.884043694077988; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20200003996-A1 | 4th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20200003996-A1-e4.zmx | 2.54102 | 1.81078 | 2.77192 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=2.54; f_number=1.89; hfov_deg=47.5; real_image_height_mm=1.8107766744945042; sanity_image_height_mm=2.77192359271595; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20200003996-A1 | 5th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20200003996-A1-e5.zmx | 2.53324 | 2.01133 | 2.77192 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=2.54; f_number=1.89; hfov_deg=47.5; real_image_height_mm=2.011326584923905; sanity_image_height_mm=2.77192359271595; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20200003996-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20200003996-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20200003996-A1 | 8th Embodiment | success | data\zmx-staging\DATA-06b2-seed20260706\US-20200003996-A1-e8.zmx | 3.29154 | 4.5917 | 2.91075 | surfaces=16; r=16/16; d=16/16; nd_vd=7/16; asphere_surfaces=12; f_mm=3.29; f_number=2.22; hfov_deg=41.5; real_image_height_mm=4.591701203737379; sanity_image_height_mm=2.9107461203890552; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20260186243-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12050306-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-12050306-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-12050306-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-12050306-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-12050306-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 6, found 8 |
| US-12050306-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-12050306-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-Cut |
| US-12050306-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-12050306-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-12050306-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: IR-cut |
| US-20260186255-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12546974-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
