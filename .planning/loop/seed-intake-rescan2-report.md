# DATA-06i seed intake rescan2 report

## Summary

- mode: local intake of DATA-06i rescan2 ZMX; no network in intake step
- source_dir: `data/zmx-staging/DATA-06i-rescan2`
- case_library_count_before: 343
- case_library_count_after: 353
- candidates: 14
- intaken: 10
- rejected: 4
- skipped_existing_index: 0
- manifest: `tests/data/data06i_rescan2_manifest.json` (10 records)
- gates: formal index stem de-dup; `ATELIER_REAL_IMH_MM` positive; `ATELIER_FTAN_IMH_SANITY_MM` positive; GLAS nd/vd in [1.3,2.2]/[10,100]; Optiland load with positive EFL; lightweight sample build; `mtf_max_field_frac <= 0.5`
- golden anchor: index `image_height_mm` is written from `ATELIER_REAL_IMH_MM`; `scripts/e2_golden.py` enforces <=2% deviation when regenerating `tests/data/eval_golden.json`

## Per-ZMX Intake Ledger

| zmx | status | reason | efl_mm | fov_deg | fnum | real_imh_mm | mtf_max_field_frac |
|---|---|---|---:|---:|---:|---:|---:|
| `US-10921568-B2-e1.zmx` | intaken | passes local intake gates | 2.8558963 | 76 | 2.3 | 1.2372216 | 0.5 |
| `US-10921568-B2-e2.zmx` | intaken | passes local intake gates | 2.90562016 | 76.4 | 2.4 | 0.299680801 | 0 |
| `US-10921568-B2-e7.zmx` | intaken | passes local intake gates | 2.92575673 | 75.4 | 2.3 | 3.07814634 | 0.5 |
| `US-10921568-B2-e9.zmx` | intaken | passes local intake gates | 4.25013245 | 76.2 | 2.18 | 3.08583772 | 0.5 |
| `US-12443014-B2-e1.zmx` | intaken | passes local intake gates | 17.3271113 | 15.8 | 2.8 | 2.43237252 | 0 |
| `US-12443014-B2-e2.zmx` | intaken | passes local intake gates | 22.9109897 | 19 | 2.8 | 3.8664357 | 0.5 |
| `US-12443014-B2-e3.zmx` | intaken | passes local intake gates | 21.3567092 | 20.4 | 2.65 | 5.07220228 | 0.5 |
| `US-12443014-B2-e4.zmx` | intaken | passes local intake gates | 18.74561 | 23 | 2.65 | 3.76175574 | 0.5 |
| `US-20250383531-A1-e4.zmx` | intaken | passes local intake gates | 0.725916375 | 122 | 1.7 | 0.451319587 | 0 |
| `US-20250383531-A1-e5.zmx` | intaken | passes local intake gates | 1.61460698 | 122.8 | 7 | 1.22261167 | 0.5 |
| `US-12443014-B2-e5.zmx` | rejected | lightweight sample build exceeded 70s local retry timeout; formal ZMX/case removed | 14.2728948 | 27.6 | 2.87 | 1.79307879 | n/a |
| `US-12443014-B2-e6.zmx` | rejected | lightweight sample build exceeded 120s timeout; left in staging only | 13.0470977 | 30 | 3.52 | 1.81445067 | n/a |
| `US-12443014-B2-e7.zmx` | rejected | lightweight sample build exceeded 120s timeout; left in staging only | 16.2964559 | 24.2 | 3.23 | 8.3111818 | n/a |
| `US-12443014-B2-e8.zmx` | rejected | lightweight sample build exceeded 120s timeout; left in staging only | 16.3219644 | 16 | 3.52 | 1.37306365 | n/a |
