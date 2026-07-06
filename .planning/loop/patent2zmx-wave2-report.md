# DATA-06d patent-to-ZMX wave 2 report

## Run contract

- prior_wave: DATA-06b2 seed20260706
- prior_report: .planning\loop\patent2zmx-scale-report.md
- prior_baseline_patent_candidate_hit_rate: 16/60 (26.7%)
- pool_count_patents: 354
- prior_seed_sample_excluded: 60
- existing_zmx_patent_ids_excluded: 103
- available_after_exclusions: 246
- sample_size_patents: 80
- sample_method: load_patent_pool(data/patents) ordered by sorted uspto-smartphone-batch*.jsonl; exclude DATA-06b2 sampled patents plus patents already represented by data/zmx or data/zmx-staging ZMX stems; take first <=80 remaining candidates
- output_dir: data\zmx-staging\DATA-06d
- runner: scripts.patent_to_zmx load_patent_pool + _convert_candidate + write_patent_zmx + load_normalized_zmx
- parser: deterministic NFKC-normalized multi-embodiment table parse; no numeric LLM fill
- codev_dependency: none; this conversion path does not require CODE V and no CODE V skip was taken
- missing_success_artifacts_policy: successes=0, so data\zmx-staging\DATA-06d has no ZMX files and no placeholder is committed
- bom_check: report/cursor are written as UTF-8 without BOM
- real_imh_tail_check: no successful ZMX in this wave; ATELIER_REAL_IMH_MM tail requirement is not applicable
- strict_limit_check: exactly 80 patent candidates attempted; no expansion beyond selected candidates
- elapsed_seconds: 435.2

## Yield summary

- patent_candidates_attempted: 80
- embodiment_attempts: 228
- successes: 0
- failures: 228
- success_rate_by_embodiment_attempt: 0/228 (0.0%)
- patent_candidate_hit_rate: 0/80 (0.0%)
- baseline_patent_candidate_hit_rate: 16/60 (26.7%)
- delta_vs_26_7_baseline: -26.7 percentage points

## Failure reason buckets

| reason_bucket | failures | share_of_failures |
|---|---:|---:|
| meta line not found | 59 | 25.9% |
| unsupported nonzero high-order asphere terms | 55 | 24.1% |
| 'Aspheric Coefficients' section not found in embodiment | 46 | 20.2% |
| trace did not reach image | 28 | 12.3% |
| surface 4 radius is not numeric: Prism | 10 | 4.4% |
| surface 14 radius is not numeric: Plane | 5 | 2.2% |
| surface 13 radius is not numeric: Prism | 4 | 1.8% |
| surface 14 radius is not numeric: Prism | 4 | 1.8% |
| surface table index break | 4 | 1.8% |
| surface 5 radius is not numeric: Ape. | 4 | 1.8% |
| surface 16 radius is not numeric: Lend | 4 | 1.8% |
| surface 3 radius is not numeric: Ape. | 2 | 0.9% |
| USPTO HTML unavailable | 1 | 0.4% |
| surface 1 radius is not numeric: Fens | 1 | 0.4% |
| surface 1 radius is not numeric: Ape. | 1 | 0.4% |

## Selected patent candidates

| # | patent_id | pool_file | line | attempts | successes | failures |
|---:|---|---|---:|---:|---:|---:|
| 1 | US-20260160977-A1 | uspto-smartphone-batch1.jsonl | 1 | 1 | 0 | 1 |
| 2 | US-20260133409-A1 | uspto-smartphone-batch1.jsonl | 3 | 1 | 0 | 1 |
| 3 | US-12591115-B2 | uspto-smartphone-batch1.jsonl | 4 | 7 | 0 | 7 |
| 4 | US-20260036790-A1 | uspto-smartphone-batch1.jsonl | 5 | 1 | 0 | 1 |
| 5 | US-12638660-B2 | uspto-smartphone-batch1.jsonl | 13 | 1 | 0 | 1 |
| 6 | US-20260126622-A1 | uspto-smartphone-batch1.jsonl | 15 | 1 | 0 | 1 |
| 7 | US-12607827-B2 | uspto-smartphone-batch1.jsonl | 16 | 1 | 0 | 1 |
| 8 | US-20260063872-A1 | uspto-smartphone-batch1.jsonl | 18 | 1 | 0 | 1 |
| 9 | US-12535657-B2 | uspto-smartphone-batch1.jsonl | 20 | 1 | 0 | 1 |
| 10 | US-12523851-B2 | uspto-smartphone-batch1.jsonl | 21 | 1 | 0 | 1 |
| 11 | US-12474546-B2 | uspto-smartphone-batch1.jsonl | 24 | 1 | 0 | 1 |
| 12 | US-12461279-B2 | uspto-smartphone-batch1.jsonl | 26 | 1 | 0 | 1 |
| 13 | US-12461346-B2 | uspto-smartphone-batch1.jsonl | 27 | 1 | 0 | 1 |
| 14 | US-20250334721-A1 | uspto-smartphone-batch1.jsonl | 28 | 1 | 0 | 1 |
| 15 | US-20250314863-A1 | uspto-smartphone-batch1.jsonl | 29 | 1 | 0 | 1 |
| 16 | US-20250291157-A1 | uspto-smartphone-batch1.jsonl | 30 | 1 | 0 | 1 |
| 17 | US-20260009981-A1 | uspto-smartphone-batch2.jsonl | 1 | 8 | 0 | 8 |
| 18 | US-20260003159-A1 | uspto-smartphone-batch2.jsonl | 2 | 1 | 0 | 1 |
| 19 | US-12429670-B2 | uspto-smartphone-batch2.jsonl | 7 | 1 | 0 | 1 |
| 20 | US-12422650-B2 | uspto-smartphone-batch2.jsonl | 8 | 11 | 0 | 11 |
| 21 | US-20250231379-A1 | uspto-smartphone-batch2.jsonl | 9 | 1 | 0 | 1 |
| 22 | US-20250189763-A1 | uspto-smartphone-batch2.jsonl | 12 | 7 | 0 | 7 |
| 23 | US-12306465-B2 | uspto-smartphone-batch2.jsonl | 13 | 1 | 0 | 1 |
| 24 | US-20250147274-A1 | uspto-smartphone-batch2.jsonl | 14 | 7 | 0 | 7 |
| 25 | US-12032142-B2 | uspto-smartphone-batch2.jsonl | 22 | 1 | 0 | 1 |
| 26 | US-11994657-B2 | uspto-smartphone-batch2.jsonl | 25 | 1 | 0 | 1 |
| 27 | US-12461430-B2 | uspto-smartphone-batch3.jsonl | 2 | 1 | 0 | 1 |
| 28 | US-12372747-B2 | uspto-smartphone-batch3.jsonl | 6 | 1 | 0 | 1 |
| 29 | US-12352929-B2 | uspto-smartphone-batch3.jsonl | 7 | 1 | 0 | 1 |
| 30 | US-12353055-B2 | uspto-smartphone-batch3.jsonl | 8 | 1 | 0 | 1 |
| 31 | US-20260186247-A1 | uspto-smartphone-batch3.jsonl | 9 | 1 | 0 | 1 |
| 32 | US-20260186249-A1 | uspto-smartphone-batch3.jsonl | 10 | 1 | 0 | 1 |
| 33 | US-20260177783-A1 | uspto-smartphone-batch3.jsonl | 12 | 1 | 0 | 1 |
| 34 | US-20260169260-A1 | uspto-smartphone-batch3.jsonl | 14 | 1 | 0 | 1 |
| 35 | US-20260169264-A1 | uspto-smartphone-batch3.jsonl | 15 | 1 | 0 | 1 |
| 36 | US-20260186253-A1 | uspto-smartphone-batch3.jsonl | 18 | 1 | 0 | 1 |
| 37 | US-12669680-B2 | uspto-smartphone-batch3.jsonl | 19 | 1 | 0 | 1 |
| 38 | US-12607830-B2 | uspto-smartphone-batch3.jsonl | 22 | 1 | 0 | 1 |
| 39 | US-12585086-B2 | uspto-smartphone-batch3.jsonl | 23 | 1 | 0 | 1 |
| 40 | US-12585088-B2 | uspto-smartphone-batch3.jsonl | 24 | 1 | 0 | 1 |
| 41 | US-20220276465-A1 | uspto-smartphone-batch3.jsonl | 25 | 1 | 0 | 1 |
| 42 | US-20220163773-A1 | uspto-smartphone-batch3.jsonl | 26 | 1 | 0 | 1 |
| 43 | US-20220050269-A1 | uspto-smartphone-batch3.jsonl | 27 | 1 | 0 | 1 |
| 44 | US-20220011544-A1 | uspto-smartphone-batch3.jsonl | 28 | 1 | 0 | 1 |
| 45 | US-20210396957-A1 | uspto-smartphone-batch3.jsonl | 29 | 1 | 0 | 1 |
| 46 | US-12619054-B2 | uspto-smartphone-batch3.jsonl | 30 | 1 | 0 | 1 |
| 47 | US-12498545-B2 | uspto-smartphone-batch3.jsonl | 31 | 1 | 0 | 1 |
| 48 | US-12339423-B2 | uspto-smartphone-batch3.jsonl | 32 | 1 | 0 | 1 |
| 49 | US-12306384-B2 | uspto-smartphone-batch3.jsonl | 33 | 1 | 0 | 1 |
| 50 | US-12235412-B2 | uspto-smartphone-batch3.jsonl | 34 | 1 | 0 | 1 |
| 51 | US-20260147185-A1 | uspto-smartphone-batch4.jsonl | 2 | 9 | 0 | 9 |
| 52 | US-20260063876-A1 | uspto-smartphone-batch4.jsonl | 4 | 1 | 0 | 1 |
| 53 | US-20260036783-A1 | uspto-smartphone-batch4.jsonl | 5 | 7 | 0 | 7 |
| 54 | US-12468119-B2 | uspto-smartphone-batch4.jsonl | 7 | 7 | 0 | 7 |
| 55 | US-12181643-B2 | uspto-smartphone-batch4.jsonl | 18 | 10 | 0 | 10 |
| 56 | US-12158635-B2 | uspto-smartphone-batch4.jsonl | 19 | 6 | 0 | 6 |
| 57 | US-12061378-B2 | uspto-smartphone-batch4.jsonl | 22 | 9 | 0 | 9 |
| 58 | US-11867886-B2 | uspto-smartphone-batch4.jsonl | 40 | 10 | 0 | 10 |
| 59 | US-20260186254-A1 | uspto-smartphone-batch4.jsonl | 45 | 1 | 0 | 1 |
| 60 | US-20260186256-A1 | uspto-smartphone-batch4.jsonl | 46 | 1 | 0 | 1 |
| 61 | US-20260186258-A1 | uspto-smartphone-batch4.jsonl | 47 | 1 | 0 | 1 |
| 62 | US-20260186383-A1 | uspto-smartphone-batch4.jsonl | 48 | 1 | 0 | 1 |
| 63 | US-20260186259-A1 | uspto-smartphone-batch4.jsonl | 49 | 1 | 0 | 1 |
| 64 | US-20260186262-A1 | uspto-smartphone-batch4.jsonl | 50 | 1 | 0 | 1 |
| 65 | US-20260186273-A1 | uspto-smartphone-batch4.jsonl | 54 | 1 | 0 | 1 |
| 66 | US-20260186271-A1 | uspto-smartphone-batch4.jsonl | 56 | 1 | 0 | 1 |
| 67 | US-20260186381-A1 | uspto-smartphone-batch4.jsonl | 58 | 1 | 0 | 1 |
| 68 | US-20260186257-A1 | uspto-smartphone-batch4.jsonl | 59 | 1 | 0 | 1 |
| 69 | US-20260186384-A1 | uspto-smartphone-batch4.jsonl | 60 | 1 | 0 | 1 |
| 70 | US-12631854-B2 | uspto-smartphone-batch4.jsonl | 61 | 1 | 0 | 1 |
| 71 | US-20260126624-A1 | uspto-smartphone-batch4.jsonl | 62 | 1 | 0 | 1 |
| 72 | US-20260126625-A1 | uspto-smartphone-batch4.jsonl | 64 | 1 | 0 | 1 |
| 73 | US-20260140347-A1 | uspto-smartphone-batch5.jsonl | 1 | 3 | 0 | 3 |
| 74 | US-20260072251-A1 | uspto-smartphone-batch5.jsonl | 2 | 12 | 0 | 12 |
| 75 | US-12554099-B2 | uspto-smartphone-batch5.jsonl | 3 | 4 | 0 | 4 |
| 76 | US-20250044552-A1 | uspto-smartphone-batch5.jsonl | 9 | 10 | 0 | 10 |
| 77 | US-12181730-B2 | uspto-smartphone-batch5.jsonl | 12 | 10 | 0 | 10 |
| 78 | US-12174349-B2 | uspto-smartphone-batch5.jsonl | 13 | 9 | 0 | 9 |
| 79 | US-20240288668-A1 | uspto-smartphone-batch5.jsonl | 15 | 12 | 0 | 12 |
| 80 | US-20240231053-A1 | uspto-smartphone-batch5.jsonl | 16 | 10 | 0 | 10 |

## Per-embodiment attempts

| patent | embodiment | status | zmx | efl_mm | real_imh_mm | f_tan_sanity_mm | field coverage | reason |
|---|---|---|---|---:|---:|---:|---|---|
| US-20260160977-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260133409-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12591115-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S9:A22=-1.33, S10:A22=-1.37, S11:A22=0.549, S10:A24=0.221, S11:A24=-0.0773, S10:A26=-0.0208, S11:A26=0.00643, S10:A28=0.000869 |
| US-12591115-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=323, S8:A22=85.6, S9:A22=-1.55, S10:A22=0.278, S7:A24=-62, S8:A24=-28.5, S9:A24=0.148, S10:A24=-0.0367 |
| US-12591115-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S9:A22=-1.64, S10:A22=-1.47, S11:A22=0.49, S10:A24=0.24, S11:A24=-0.0681, S10:A26=-0.023, S11:A26=0.00559, S10:A28=0.00098 |
| US-12591115-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S9:A22=-1.67, S10:A22=-0.811, S11:A22=0.552, S10:A24=0.107, S11:A24=-0.0776, S10:A26=-0.00736, S11:A26=0.00644, S10:A28=0.000169 |
| US-12591115-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S9:A22=-1.04, S10:A22=-1.24, S11:A22=0.518, S10:A24=0.196, S11:A24=-0.0728, S10:A26=-0.0181, S11:A26=0.00604, S10:A28=0.000743 |
| US-12591115-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S9:A22=0.0415, S10:A22=-1.29, S11:A22=0.462, S10:A24=0.208, S11:A24=-0.064, S10:A26=-0.0195, S11:A26=0.00524, S10:A28=0.000818 |
| US-12591115-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-27.6, S9:A22=-1.49, S10:A22=-0.186, S8:A24=3.43, S9:A24=0.294, S10:A24=0.0395, S9:A26=-0.0383, S10:A26=-0.00523 |
| US-20260036790-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12638660-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260126622-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12607827-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260063872-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12535657-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12523851-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12474546-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12461279-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12461346-B2 |  | failed |  |  |  |  |  | PatentParseError: USPTO HTML unavailable (USPAT: ConnectError; US-PGPUB: HTTPStatusError; USOCR: HTTPStatusError) |
| US-20250334721-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250314863-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250291157-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260009981-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: surface 13 radius is not numeric: Prism |
| US-20260009981-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 13 radius is not numeric: Prism |
| US-20260009981-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 13 radius is not numeric: Prism |
| US-20260009981-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 13 radius is not numeric: Prism |
| US-20260009981-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: Prism |
| US-20260009981-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: Prism |
| US-20260009981-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: Prism |
| US-20260009981-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: Prism |
| US-20260003159-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12429670-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12422650-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Prism |
| US-12422650-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Prism |
| US-12422650-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Prism |
| US-12422650-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Prism |
| US-12422650-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Prism |
| US-12422650-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Prism |
| US-12422650-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Prism |
| US-12422650-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Prism |
| US-12422650-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Prism |
| US-12422650-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Prism |
| US-12422650-B2 | 11th Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 4, found 10 |
| US-20250231379-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250189763-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S9:A22=-1.33, S10:A22=-1.37, S11:A22=0.549, S10:A24=0.221, S11:A24=-0.0773, S10:A26=-0.0208, S11:A26=0.00643, S10:A28=0.000869 |
| US-20250189763-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=323, S8:A22=85.6, S9:A22=-1.55, S10:A22=0.278, S7:A24=-62, S8:A24=-28.5, S9:A24=0.148, S10:A24=-0.0367 |
| US-20250189763-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S9:A22=-1.64, S10:A22=-1.47, S11:A22=0.49, S10:A24=0.24, S11:A24=-0.0681, S10:A26=-0.023, S11:A26=0.00559, S10:A28=0.00098 |
| US-20250189763-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S9:A22=-1.67, S10:A22=-0.811, S11:A22=0.552, S10:A24=0.107, S11:A24=-0.0776, S10:A26=-0.00736, S11:A26=0.00644, S10:A28=0.000169 |
| US-20250189763-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S9:A22=-1.04, S10:A22=-1.24, S11:A22=0.518, S10:A24=0.196, S11:A24=-0.0728, S10:A26=-0.0181, S11:A26=0.00604, S10:A28=0.000743 |
| US-20250189763-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S9:A22=0.0415, S10:A22=-1.29, S11:A22=0.462, S10:A24=0.208, S11:A24=-0.064, S10:A26=-0.0195, S11:A26=0.00524, S10:A28=0.000818 |
| US-20250189763-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S8:A22=-27.6, S9:A22=-1.49, S10:A22=-0.186, S8:A24=3.43, S9:A24=0.294, S10:A24=0.0395, S9:A26=-0.0383, S10:A26=-0.00523 |
| US-12306465-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20250147274-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250147274-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250147274-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250147274-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250147274-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250147274-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250147274-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12032142-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-11994657-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12461430-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12372747-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12352929-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12353055-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186247-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186249-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260177783-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260169260-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260169264-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186253-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12669680-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12607830-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12585086-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12585088-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20220276465-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20220163773-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20220050269-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20220011544-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20210396957-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12619054-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12498545-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12339423-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12306384-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12235412-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260147185-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S12:A22=2.04e-08, S13:A22=1.06e-09, S14:A22=1.29e-10, S16:A22=1.67e-12, S17:A22=-4.4e-11, S16:A24=-1.59e-14, S17:A24=1.06e-12, S17:A26=-1.53e-14 |
| US-20260147185-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S12:A22=1.51e-06, S13:A22=-1.62e-07, S12:A24=-7.94e-08, S13:A24=8.78e-09, S12:A26=1.81e-09, S13:A26=-2.73e-10, S13:A28=3.76e-12, S14:A22=1.91e-10 |
| US-20260147185-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S12:A22=1.7e-07, S12:A24=-6.42e-09, S14:A22=1.46e-10, S15:A22=-7.05e-12, S16:A22=1.7e-12, S17:A22=-3.08e-12, S16:A24=-1.38e-14, S17:A24=4.45e-14 |
| US-20260147185-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S13:A22=-1.97e-09, S14:A22=8.15e-10, S15:A22=4.35e-12, S17:A22=1.7e-13, S18:A22=4.44e-12, S17:A24=-2.97e-15, S18:A24=-6.07e-14, S18:A26=3.66e-16 |
| US-20260147185-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S12:A22=2.01e-09, S13:A22=1.54e-09, S14:A22=1.19e-09, S16:A22=1.79e-11, S17:A22=1.61e-11, S16:A24=-1.58e-13, S17:A24=-2.43e-13, S17:A26=1.65e-15 |
| US-20260147185-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S12:A22=-1.38e-08, S13:A22=-1.21e-10, S14:A22=1.62e-10, S16:A22=-2.03e-12, S17:A22=-3.2e-12, S16:A24=1.27e-14, S17:A24=4.11e-14, S17:A26=-2.37e-16 |
| US-20260147185-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S13:A22=2.64e-09, S14:A22=1.11e-10, S16:A22=-4.22e-13, S17:A22=1.78e-12, S16:A24=1.89e-15, S17:A24=-2.96e-14, S17:A26=2.07e-16 |
| US-20260147185-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S12:A22=-1.48e-08, S13:A22=2.52e-09, S14:A22=1.81e-10, S16:A22=-1.5e-12, S17:A22=-4.12e-12, S16:A24=9.42e-15, S17:A24=6.42e-14, S17:A26=-4.41e-16 |
| US-20260147185-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S13:A22=1.9e-09, S14:A22=1.45e-10, S16:A22=-3.18e-13, S17:A22=1.71e-12, S16:A24=1.31e-15, S17:A24=-2.81e-14, S17:A26=1.94e-16 |
| US-20260063876-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260036783-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=1.35, S8:A22=-0.884, S10:A22=-3.97, S11:A22=1.19, S10:A24=1.03, S11:A24=-0.179, S10:A26=-0.16, S11:A26=0.0158 |
| US-20260036783-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=1.19, S8:A22=-0.83, S10:A22=-12, S11:A22=3.43, S10:A24=3.03, S11:A24=-0.728, S10:A26=-0.456, S11:A26=0.104 |
| US-20260036783-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=4.46, S8:A22=-0.185, S9:A22=-6.2, S10:A22=5.45, S9:A24=1.71, S10:A24=-1.15, S9:A26=-0.265, S10:A26=0.161 |
| US-20260036783-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=0.174, S8:A22=-0.55, S9:A22=4.28, S10:A22=0.801, S9:A24=-1.02, S10:A24=-0.116, S9:A26=0.14, S10:A26=0.00989 |
| US-20260036783-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=-1.91, S8:A22=-0.54, S9:A22=40.1, S10:A22=-1.93, S9:A24=-12.1, S10:A24=0.503, S9:A26=2.11, S10:A26=-0.0842 |
| US-20260036783-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=-2.29, S8:A22=-0.633, S9:A22=47.7, S10:A22=9.24, S9:A24=-12.9, S10:A24=-2.6, S9:A26=2.1, S10:A26=0.481 |
| US-20260036783-A1 | 7th embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=10.3, S8:A22=-1.52, S9:A22=10.4, S10:A22=4.86, S9:A24=-3.56, S10:A24=-1, S9:A26=0.687, S10:A26=0.135 |
| US-12468119-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=1.35, S8:A22=-0.884, S10:A22=-3.97, S11:A22=1.19, S10:A24=1.03, S11:A24=-0.179, S10:A26=-0.16, S11:A26=0.0158 |
| US-12468119-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=1.19, S8:A22=-0.83, S10:A22=-12, S11:A22=3.43, S10:A24=3.03, S11:A24=-0.728, S10:A26=-0.456, S11:A26=0.104 |
| US-12468119-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=4.46, S8:A22=-0.185, S9:A22=-6.2, S10:A22=5.45, S9:A24=1.71, S10:A24=-1.15, S9:A26=-0.265, S10:A26=0.161 |
| US-12468119-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=0.174, S8:A22=-0.55, S9:A22=4.28, S10:A22=0.801, S9:A24=-1.02, S10:A24=-0.116, S9:A26=0.14, S10:A26=0.00989 |
| US-12468119-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=-1.91, S8:A22=-0.54, S9:A22=40.1, S10:A22=-1.93, S9:A24=-12.1, S10:A24=0.503, S9:A26=2.11, S10:A26=-0.0842 |
| US-12468119-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=-2.29, S8:A22=-0.633, S9:A22=47.7, S10:A22=9.24, S9:A24=-12.9, S10:A24=-2.6, S9:A26=2.1, S10:A26=0.481 |
| US-12468119-B2 | 7th embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S7:A22=10.3, S8:A22=-1.52, S9:A22=10.4, S10:A22=4.86, S9:A24=-3.56, S10:A24=-1, S9:A26=0.687, S10:A26=0.135 |
| US-12181643-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12181643-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12181643-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12181643-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12181643-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12181643-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12181643-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12181643-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12181643-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12181643-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12158635-B2 | Embodiment 1 | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: Plane |
| US-12158635-B2 | Embodiment 2 | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: Plane |
| US-12158635-B2 | Embodiment 3 | failed |  |  |  |  |  | PatentParseError: surface 1 radius is not numeric: Fens |
| US-12158635-B2 | Embodiment 4 | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: Plane |
| US-12158635-B2 | Embodiment 5 | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: Plane |
| US-12158635-B2 | Embodiment 6 | failed |  |  |  |  |  | PatentParseError: surface 14 radius is not numeric: Plane |
| US-12061378-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12061378-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12061378-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12061378-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12061378-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12061378-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12061378-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12061378-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12061378-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-11867886-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11867886-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11867886-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11867886-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11867886-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11867886-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11867886-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11867886-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11867886-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-11867886-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20260186254-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186256-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186258-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186383-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186259-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186262-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186273-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186271-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186381-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186257-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260186384-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-12631854-B2 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260126624-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260126625-A1 |  | failed |  |  |  |  |  | PatentParseError: embodiment f/Fno/HFOV line not found |
| US-20260140347-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 3 radius is not numeric: Ape. |
| US-20260140347-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 5 radius is not numeric: Ape. |
| US-20260140347-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 5 radius is not numeric: Ape. |
| US-20260072251-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.0003, S14:A22=2.23e-09, S15:A22=3.69e-08, S16:A22=-1.57e-09, S14:A24=-1.92e-09, S15:A24=4.65e-11, S14:A26=6.51e-11, S15:A26=-9.13e-13 |
| US-20260072251-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.000828, S15:A22=2.15e-08, S16:A22=-1.7e-08, S17:A22=-2.57e-09, S15:A24=6.77e-10, S16:A24=7.47e-11, S15:A26=-1.78e-11, S16:A26=-1.44e-12 |
| US-20260072251-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.00117, S14:A22=-1.44e-09, S15:A22=1.93e-08, S16:A22=-2.91e-09, S14:A24=-8.92e-10, S15:A24=8.52e-11, S14:A26=2.72e-11, S15:A26=-1.65e-12 |
| US-20260072251-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-9.78e-05, S14:A22=-8.33e-11, S15:A22=-4.18e-08, S16:A22=-1.99e-09, S14:A24=1.89e-09, S15:A24=5.47e-11, S14:A26=-5.59e-11, S15:A26=-9.94e-13 |
| US-20260072251-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S1:A22=1.01e-17, S2:A22=-3.54e-10, S1:A24=5.67e-12, S10:A22=1.48e-05, S14:A22=4.17e-09, S15:A22=2.03e-08, S16:A22=4.59e-11, S14:A24=-7.3e-10 |
| US-20260072251-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=2.97e-05, S11:A22=-0.000328, S10:A24=5.99e-05, S10:A26=-7.39e-06, S10:A28=5.52e-07, S10:A30=-1.87e-08, S14:A22=1.06e-06, S15:A22=-1.6e-10 |
| US-20260072251-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.000142, S15:A22=-8.08e-10, S16:A22=-1.2e-08, S17:A22=-2.3e-09, S15:A24=6.4e-10, S16:A24=6.79e-11, S15:A26=-2.15e-11, S16:A26=-1.32e-12 |
| US-20260072251-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.000455, S14:A22=2.13e-09, S15:A22=1.31e-08, S16:A22=-1.08e-09, S14:A24=-6.27e-10, S15:A24=3e-11, S14:A26=1.95e-11, S15:A26=-5.53e-13 |
| US-20260072251-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.000296, S14:A22=-1e-09, S15:A22=-8.98e-08, S16:A22=-2.06e-09, S14:A24=4.09e-09, S15:A24=5.8e-11, S14:A26=-1.23e-10, S15:A26=-1.09e-12 |
| US-20260072251-A1 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 22, found 23 |
| US-20260072251-A1 | 11th Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 22, found 23 |
| US-20260072251-A1 | 12th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S10:A22=-0.00259, S15:A22=1.4e-07, S16:A22=-1.29e-07, S17:A22=-1.83e-08, S15:A24=5.42e-09, S16:A24=5.74e-10, S15:A26=-1.51e-10, S16:A26=-1.2e-11 |
| US-12554099-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: surface 1 radius is not numeric: Ape. |
| US-12554099-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 3 radius is not numeric: Ape. |
| US-12554099-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 5 radius is not numeric: Ape. |
| US-12554099-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 5 radius is not numeric: Ape. |
| US-20250044552-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250044552-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250044552-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250044552-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250044552-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250044552-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250044552-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250044552-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250044552-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20250044552-A1 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12181730-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12181730-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12181730-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12181730-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12181730-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12181730-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12181730-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12181730-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12181730-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12181730-B2 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-12174349-B2 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S14:A22=2e-07, S15:A22=1.87e-10, S14:A24=-5.54e-09, S15:A24=-1.37e-11, S16:A22=7.49e-09, S17:A22=2.36e-09, S18:A22=3.74e-10, S19:A22=5.74e-11 |
| US-12174349-B2 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S11:A22=1.2e-07, S12:A22=-1.29e-05, S13:A22=-1.21e-06, S14:A22=8.05e-10, S11:A24=-2.01e-08, S12:A24=7.64e-07, S13:A24=7.91e-08, S14:A24=-1.76e-10 |
| US-12174349-B2 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S14:A22=-2.83e-07, S15:A22=4.9e-09, S14:A24=7.51e-09, S15:A24=-6.95e-11, S16:A22=1.19e-08, S17:A22=3.74e-10, S18:A22=-1.58e-10, S19:A22=7.34e-12 |
| US-12174349-B2 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S11:A22=1.38e-06, S12:A22=-3.56e-06, S14:A22=-1.9e-07, S15:A22=-2.31e-09, S11:A24=-7.63e-08, S12:A24=1.94e-07, S14:A24=9.16e-09, S15:A24=9.36e-11 |
| US-12174349-B2 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S11:A22=-4.35e-07, S12:A22=-6.42e-08, S13:A22=-5.01e-09, S14:A22=-1.46e-09, S12:A24=1.3e-09, S13:A24=5.6e-11, S14:A24=5.73e-11, S13:A26=4.93e-13 |
| US-12174349-B2 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S11:A22=-7.57e-07, S12:A22=-2.2e-07, S14:A22=1.63e-08, S15:A22=1.77e-08, S12:A24=5.53e-09, S14:A24=-6.07e-10, S15:A24=-6.67e-10, S14:A26=9.69e-12 |
| US-12174349-B2 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 9, found 10 |
| US-12174349-B2 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S11:A22=-1.67e-06, S12:A22=-7.33e-06, S13:A22=2.1e-06, S14:A22=1.03e-07, S11:A24=5.09e-08, S12:A24=4.05e-07, S13:A24=-1.56e-07, S14:A24=-5.12e-09 |
| US-12174349-B2 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S11:A22=7.67e-06, S12:A22=-8.3e-06, S14:A22=-3.28e-07, S15:A22=-3.11e-08, S11:A24=-3.13e-07, S12:A24=5.16e-07, S14:A24=1.72e-08, S15:A24=1.19e-09 |
| US-20240288668-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240288668-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Lend |
| US-20240288668-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240288668-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240288668-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Lend |
| US-20240288668-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Lend |
| US-20240288668-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: surface 16 radius is not numeric: Lend |
| US-20240288668-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240288668-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240288668-A1 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240288668-A1 | 11th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240288668-A1 | 12th Embodiment | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-20240231053-A1 | 1st Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20240231053-A1 | 2nd Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20240231053-A1 | 3rd Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20240231053-A1 | 4th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20240231053-A1 | 5th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20240231053-A1 | 6th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20240231053-A1 | 7th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20240231053-A1 | 8th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20240231053-A1 | 9th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
| US-20240231053-A1 | 10th Embodiment | failed |  |  |  |  |  | PatentParseError: 'Aspheric Coefficients' section not found in embodiment |
