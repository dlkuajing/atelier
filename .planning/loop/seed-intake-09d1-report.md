# DATA-09d1 staging seed intake report

## Summary

- mode: pure local, no network
- source_dirs: `data/zmx-staging/DATA-09a-kantatsu`, `DATA-09b-samsungem`, `DATA-09c-sunny`, `DATA-09d-rescan`
- case_library_count_before: 157
- case_library_count_after: 343
- candidates: 195
- intaken: 186
- rejected: 9
- skipped_existing_index: 0
- manifest: `tests/data/data09d1_manifest.json` (186 records)
- gates: formal index stem de-dup; `ATELIER_REAL_IMH_MM` positive; `ATELIER_FTAN_IMH_SANITY_MM` positive; GLAS nd/vd in [1.3,2.2]/[10,100]; Optiland load with positive EFL; lightweight sample build; `mtf_max_field_frac <= 0.5`
- golden anchor: index `image_height_mm` is written from `ATELIER_REAL_IMH_MM`; `scripts/e2_golden.py` enforces <=2% deviation when regenerating `tests/data/eval_golden.json`

## By Source Family

| source_family | candidates | intaken | rejected | skipped_existing_index |
|---|---:|---:|---:|---:|
| DATA-09a-kantatsu | 29 | 29 | 0 | 0 |
| DATA-09b-samsungem | 26 | 26 | 0 | 0 |
| DATA-09c-sunny | 12 | 10 | 2 | 0 |
| DATA-09d-rescan | 128 | 121 | 7 | 0 |

## Per-ZMX Intake Ledger

| source_family | zmx | status | reason | efl_mm | fov_deg | fnum | real_imh_mm | mtf_max_field_frac |
|---|---|---|---|---:|---:|---:|---:|---:|
| DATA-09a-kantatsu | `US-20210364737-A1-e1.zmx` | intaken | passes local intake gates | 10.3487257 | 14.205449 | 2.8 | 2.61117061 | 0.5 |
| DATA-09a-kantatsu | `US-20210364737-A1-e2.zmx` | intaken | passes local intake gates | 10.3626853 | 14.1922915 | 2.8 | 2.61403862 | 0.5 |
| DATA-09a-kantatsu | `US-20210364737-A1-e3.zmx` | intaken | passes local intake gates | 10.4132005 | 14.205449 | 2.8 | 2.93007838 | 0.5 |
| DATA-09a-kantatsu | `US-20210364737-A1-e4.zmx` | intaken | passes local intake gates | 9.91435352 | 14.8232985 | 2.6 | 2.38804911 | 0.5 |
| DATA-09a-kantatsu | `US-20210364737-A1-e5.zmx` | intaken | passes local intake gates | 12.0130139 | 12.3163023 | 2.8 | 2.41635235 | 0 |
| DATA-09a-kantatsu | `US-20210364737-A1-e6.zmx` | intaken | passes local intake gates | 12.0123887 | 12.3163023 | 2.8 | 2.59322912 | 0 |
| DATA-09a-kantatsu | `US-20210364737-A1-e7.zmx` | intaken | passes local intake gates | 12.0139041 | 12.3163023 | 2.8 | 2.58944336 | 0.5 |
| DATA-09a-kantatsu | `US-20210364737-A1-e8.zmx` | intaken | passes local intake gates | 12.0116484 | 12.3163023 | 2.6 | 2.57078283 | 0.5 |
| DATA-09a-kantatsu | `US-20210364737-A1-e9.zmx` | intaken | passes local intake gates | 12.0137163 | 12.3163023 | 2.6 | 2.5845327 | 0.5 |
| DATA-09a-kantatsu | `US-20210364762-A1-e3.zmx` | intaken | passes local intake gates | 4.24487857 | 37.6596926 | 1.48 | 3.29654731 | 0.5 |
| DATA-09a-kantatsu | `US-20210364762-A1-e4.zmx` | intaken | passes local intake gates | 4.24874599 | 39.7126232 | 1.47 | 3.48396693 | 0.5 |
| DATA-09a-kantatsu | `US-20210364763-A1-e5.zmx` | intaken | passes local intake gates | 4.09291258 | 38.6598083 | 1.71 | 0.916367938 | 0.5 |
| DATA-09a-kantatsu | `US-20210364765-A1-e3.zmx` | intaken | passes local intake gates | 5.8525248 | 26.4865101 | 2.41 | 3.19348473 | 0.5 |
| DATA-09a-kantatsu | `US-20210364765-A1-e4.zmx` | intaken | passes local intake gates | 5.85344936 | 26.4865101 | 2.41 | 2.84581655 | 0.5 |
| DATA-09a-kantatsu | `US-20210373297-A1-e1.zmx` | intaken | passes local intake gates | 4.66860383 | 39.9013633 | 1.7 | 1.71908965 | 0 |
| DATA-09a-kantatsu | `US-20210373297-A1-e11.zmx` | intaken | passes local intake gates | 5.46048508 | 40.1425304 | 1.55 | 3.34576142 | 0 |
| DATA-09a-kantatsu | `US-20210389571-A1-e1.zmx` | intaken | passes local intake gates | 1.51415666 | 50.1633068 | 2.44 | 1.24012864 | 0.5 |
| DATA-09a-kantatsu | `US-20210389571-A1-e2.zmx` | intaken | passes local intake gates | 1.56080126 | 49.2426573 | 2.44 | 1.33931383 | 0.5 |
| DATA-09a-kantatsu | `US-20210389571-A1-e3.zmx` | intaken | passes local intake gates | 1.49714061 | 50.3504628 | 2.44 | 1.38881538 | 0.5 |
| DATA-09a-kantatsu | `US-20210389571-A1-e4.zmx` | intaken | passes local intake gates | 1.65261792 | 47.6476297 | 2.44 | 1.40506755 | 0.5 |
| DATA-09a-kantatsu | `US-20210389571-A1-e5.zmx` | intaken | passes local intake gates | 1.45979491 | 51.1093168 | 2.44 | 1.35899257 | 0.5 |
| DATA-09a-kantatsu | `US-20210389571-A1-e6.zmx` | intaken | passes local intake gates | 1.28963486 | 54.522255 | 2.44 | 1.34085658 | 0.5 |
| DATA-09a-kantatsu | `US-20210389571-A1-e7.zmx` | intaken | passes local intake gates | 1.03548798 | 60.1189436 | 2.44 | 1.35641165 | 0.5 |
| DATA-09a-kantatsu | `US-20210389572-A1-e1.zmx` | intaken | passes local intake gates | 5.87203154 | 23.3518189 | 2.4 | 2.48515626 | 0.5 |
| DATA-09a-kantatsu | `US-20210389572-A1-e2.zmx` | intaken | passes local intake gates | 5.87398522 | 23.3518189 | 2.4 | 2.41217864 | 0.5 |
| DATA-09a-kantatsu | `US-20210389572-A1-e5.zmx` | intaken | passes local intake gates | 6.39508173 | 19.8243129 | 2.4 | 2.27480276 | 0.5 |
| DATA-09a-kantatsu | `US-20210389572-A1-e6.zmx` | intaken | passes local intake gates | 6.18307912 | 20.4440202 | 2.4 | 2.32808114 | 0.5 |
| DATA-09a-kantatsu | `US-20210389572-A1-e7.zmx` | intaken | passes local intake gates | 6.18063369 | 20.4440202 | 2.4 | 2.30584711 | 0.5 |
| DATA-09a-kantatsu | `US-20210389572-A1-e8.zmx` | intaken | passes local intake gates | 6.17767432 | 20.4744564 | 2.4 | 1.59168745 | 0.5 |
| DATA-09b-samsungem | `US-12571987-B2-e1.zmx` | intaken | passes local intake gates | 18.035803 | 8.7989942 | 4.5 | 2.96092189 | 0.5 |
| DATA-09b-samsungem | `US-12571987-B2-e2.zmx` | intaken | passes local intake gates | 17.9762448 | 6.6533261 | 3.6 | 2.10695923 | 0.5 |
| DATA-09b-samsungem | `US-12571987-B2-e3.zmx` | intaken | passes local intake gates | 18.0141987 | 6.65405869 | 3.7 | 2.10590174 | 0.5 |
| DATA-09b-samsungem | `US-12571987-B2-e4.zmx` | intaken | passes local intake gates | 18.0006 | 6.65405869 | 3.8 | 2.11220443 | 0.5 |
| DATA-09b-samsungem | `US-12571987-B2-e5.zmx` | intaken | passes local intake gates | 17.7273363 | 8.94599304 | 4.4 | 2.82887994 | 0.5 |
| DATA-09b-samsungem | `US-12571987-B2-e6.zmx` | intaken | passes local intake gates | 27.0801148 | 8.78163129 | 4.4 | 4.22221296 | 0.5 |
| DATA-09b-samsungem | `US-12571987-B2-e7.zmx` | intaken | passes local intake gates | 27.1488016 | 8.75816449 | 4.4 | 4.22223708 | 0.5 |
| DATA-09b-samsungem | `US-12571987-B2-e8.zmx` | intaken | passes local intake gates | 28.3030038 | 8.44429008 | 4.4 | 4.22094721 | 0.5 |
| DATA-09b-samsungem | `US-20240176104-A1-e1.zmx` | intaken | passes local intake gates | 18.035803 | 8.7989942 | 4.5 | 2.96092189 | 0.5 |
| DATA-09b-samsungem | `US-20240176104-A1-e2.zmx` | intaken | passes local intake gates | 17.9762448 | 6.6533261 | 3.6 | 2.10695923 | 0.5 |
| DATA-09b-samsungem | `US-20240176104-A1-e3.zmx` | intaken | passes local intake gates | 18.0141987 | 6.65405869 | 3.7 | 2.10590174 | 0.5 |
| DATA-09b-samsungem | `US-20240176104-A1-e4.zmx` | intaken | passes local intake gates | 18.0006 | 6.65405869 | 3.8 | 2.11220443 | 0.5 |
| DATA-09b-samsungem | `US-20240176104-A1-e5.zmx` | intaken | passes local intake gates | 17.7273363 | 8.94599304 | 4.4 | 2.82887994 | 0.5 |
| DATA-09b-samsungem | `US-20240176104-A1-e6.zmx` | intaken | passes local intake gates | 27.0801148 | 8.78163129 | 4.4 | 4.22221296 | 0.5 |
| DATA-09b-samsungem | `US-20240176104-A1-e7.zmx` | intaken | passes local intake gates | 27.1488016 | 8.75816449 | 4.4 | 4.22223708 | 0.5 |
| DATA-09b-samsungem | `US-20240176104-A1-e8.zmx` | intaken | passes local intake gates | 28.3030038 | 8.44429008 | 4.4 | 4.22094721 | 0.5 |
| DATA-09b-samsungem | `US-20240369807-A1-e1.zmx` | intaken | passes local intake gates | 18.035803 | 8.7989942 | 4.5 | 2.96092189 | 0.5 |
| DATA-09b-samsungem | `US-20240369807-A1-e2.zmx` | intaken | passes local intake gates | 17.9762448 | 6.6533261 | 3.6 | 2.10695923 | 0.5 |
| DATA-09b-samsungem | `US-20240369807-A1-e3.zmx` | intaken | passes local intake gates | 18.0141987 | 6.65405869 | 3.7 | 2.10590174 | 0.5 |
| DATA-09b-samsungem | `US-20240369807-A1-e4.zmx` | intaken | passes local intake gates | 18.0006 | 6.65405869 | 3.8 | 2.11220443 | 0.5 |
| DATA-09b-samsungem | `US-20240369807-A1-e5.zmx` | intaken | passes local intake gates | 17.7273363 | 8.94599304 | 4.4 | 2.82887994 | 0.5 |
| DATA-09b-samsungem | `US-20240369807-A1-e6.zmx` | intaken | passes local intake gates | 27.0801148 | 8.78163129 | 4.4 | 4.22221296 | 0.5 |
| DATA-09b-samsungem | `US-20240369807-A1-e7.zmx` | intaken | passes local intake gates | 27.1488016 | 8.75816449 | 4.4 | 4.22223708 | 0.5 |
| DATA-09b-samsungem | `US-20240369807-A1-e8.zmx` | intaken | passes local intake gates | 28.3030038 | 8.44429008 | 4.4 | 4.22094721 | 0.5 |
| DATA-09b-samsungem | `US-20260140349-A1-e3.zmx` | intaken | passes local intake gates | 5.65723918 | 41.2645 | 1.629 | 1.80166609 | 0.5 |
| DATA-09b-samsungem | `US-20260140349-A1-e4.zmx` | intaken | passes local intake gates | 5.555911 | 40.1455 | 1.763 | 2.84048347 | 0.5 |
| DATA-09c-sunny | `US-12306467-B2-e1.zmx` | rejected | timeout: lightweight Optiland build exceeded 45s |  |  | 1.8 | 0.282808176 |  |
| DATA-09c-sunny | `US-12345855-B2-e1.zmx` | rejected | ValueError: non-positive computed EFL -0.3944289594652125 |  |  | 3 | 4.32786891 |  |
| DATA-09c-sunny | `US-12345855-B2-e2.zmx` | intaken | passes local intake gates | 4.81969676 | 79 | 3 | 25.3736388 | 0.5 |
| DATA-09c-sunny | `US-12345855-B2-e3.zmx` | intaken | passes local intake gates | 6.26229312 | 79 | 3 | 40.2917735 | 0.5 |
| DATA-09c-sunny | `US-12345855-B2-e4.zmx` | intaken | passes local intake gates | 4.51107837 | 79 | 3 | 44.6627789 | 0.5 |
| DATA-09c-sunny | `US-12353055-B2-e1.zmx` | intaken | passes local intake gates | 2.62944324 | 42.2 | 3.2 | 1.99028233 | 0.5 |
| DATA-09c-sunny | `US-12607827-B2-e3.zmx` | intaken | passes local intake gates | 6.64325318 | 23.5 | 2.45 | 44.1458732 | 0 |
| DATA-09c-sunny | `US-20260133409-A1-e1.zmx` | intaken | passes local intake gates | 5.96495208 | 39.5 | 1.59 | 3.69477409 | 0.5 |
| DATA-09c-sunny | `US-20260186251-A1-e1.zmx` | intaken | passes local intake gates | 1.9916195 | 60.52 | 2.4 | 3.45402882 | 0.5 |
| DATA-09c-sunny | `US-20260186251-A1-e2.zmx` | intaken | passes local intake gates | 2.44261464 | 54.705 | 2.4 | 3.39189222 | 0.5 |
| DATA-09c-sunny | `US-20260186251-A1-e3.zmx` | intaken | passes local intake gates | 1.76955713 | 62.725 | 2.4 | 3.44581368 | 0.5 |
| DATA-09c-sunny | `US-20260186251-A1-e4.zmx` | intaken | passes local intake gates | 2.19939198 | 57.5 | 2.4 | 3.42617099 | 0.5 |
| DATA-09d-rescan | `US-11899172-B2-e1.zmx` | intaken | passes local intake gates | 3.82647405 | 36 | 1.3 | 1.72324421 | 0.5 |
| DATA-09d-rescan | `US-11899172-B2-e4.zmx` | intaken | passes local intake gates | 3.45415702 | 39 | 1.12 | 2.67510818 | 0 |
| DATA-09d-rescan | `US-11899172-B2-e5.zmx` | intaken | passes local intake gates | 3.44671847 | 39 | 1.12 | 0.421368419 | 0 |
| DATA-09d-rescan | `US-11933948-B2-e10.zmx` | intaken | passes local intake gates | 4.30727252 | 38.7 | 2.35 | 3.61206366 | 0.5 |
| DATA-09d-rescan | `US-11933948-B2-e11.zmx` | intaken | passes local intake gates | 3.96148158 | 41.3 | 2.3 | 3.61120509 | 0.5 |
| DATA-09d-rescan | `US-11933948-B2-e12.zmx` | intaken | passes local intake gates | 4.11078514 | 40.9 | 2.3 | 6.68533049 | 0.5 |
| DATA-09d-rescan | `US-11933948-B2-e6.zmx` | intaken | passes local intake gates | 5.04266095 | 37.4 | 1.85 | 6.68961847 | 0.5 |
| DATA-09d-rescan | `US-11933948-B2-e7.zmx` | intaken | passes local intake gates | 3.8583167 | 36 | 1.65 | 2.9079348 | 0.5 |
| DATA-09d-rescan | `US-11933948-B2-e8.zmx` | intaken | passes local intake gates | 3.92714087 | 35.1 | 2.3 | 2.85601562 | 0.5 |
| DATA-09d-rescan | `US-11933948-B2-e9.zmx` | intaken | passes local intake gates | 3.93586008 | 35.6 | 2.25 | 2.87150637 | 0.5 |
| DATA-09d-rescan | `US-12000991-B2-e1.zmx` | intaken | passes local intake gates | 1.38276774 | 65 | 2.35 | 1.13356622 | 0.5 |
| DATA-09d-rescan | `US-12000991-B2-e2.zmx` | intaken | passes local intake gates | 2.03046153 | 55.1 | 2.18 | 1.03468326 | 0.5 |
| DATA-09d-rescan | `US-12000991-B2-e7.zmx` | intaken | passes local intake gates | 1.80813151 | 58.8 | 2.42 | 1.12178096 | 0.5 |
| DATA-09d-rescan | `US-12000991-B2-e8.zmx` | intaken | passes local intake gates | 1.66906272 | 60.6 | 2.45 | 1.08253069 | 0.5 |
| DATA-09d-rescan | `US-12072472-B2-e8.zmx` | intaken | passes local intake gates | 3.97858393 | 37.1 | 1.97 | 3.73878887 | 0 |
| DATA-09d-rescan | `US-12210142-B2-e1.zmx` | intaken | passes local intake gates | 5.31241613 | 37.5 | 2.1 | 3.99810679 | 0.5 |
| DATA-09d-rescan | `US-12210142-B2-e2.zmx` | intaken | passes local intake gates | 4.8810326 | 38.7 | 1.85 | 4.00223505 | 0.5 |
| DATA-09d-rescan | `US-12210142-B2-e3.zmx` | intaken | passes local intake gates | 5.37963035 | 36.8 | 1.73 | 8.66226791 | 0.5 |
| DATA-09d-rescan | `US-12210142-B2-e4.zmx` | intaken | passes local intake gates | 4.95056079 | 39.5 | 2.2 | 4.00134727 | 0.5 |
| DATA-09d-rescan | `US-12210142-B2-e5.zmx` | intaken | passes local intake gates | 5.10060078 | 38 | 2.32 | 3.95398035 | 0.5 |
| DATA-09d-rescan | `US-12210142-B2-e6.zmx` | intaken | passes local intake gates | 5.56791298 | 35.5 | 2.02 | 51.8753678 | 0.5 |
| DATA-09d-rescan | `US-12210142-B2-e7.zmx` | intaken | passes local intake gates | 4.7320967 | 39.5 | 2.28 | 3.99617089 | 0.5 |
| DATA-09d-rescan | `US-12210142-B2-e8.zmx` | intaken | passes local intake gates | 5.42113357 | 36 | 2.4 | 3.99929672 | 0.5 |
| DATA-09d-rescan | `US-12210142-B2-e9.zmx` | intaken | passes local intake gates | 4.66824019 | 36.8 | 1.95 | 3.42787644 | 0.5 |
| DATA-09d-rescan | `US-12259531-B2-e10.zmx` | intaken | passes local intake gates | 4.30727252 | 38.7 | 2.35 | 3.61206366 | 0.5 |
| DATA-09d-rescan | `US-12259531-B2-e11.zmx` | intaken | passes local intake gates | 3.96148158 | 41.3 | 2.3 | 3.61120509 | 0.5 |
| DATA-09d-rescan | `US-12259531-B2-e12.zmx` | intaken | passes local intake gates | 4.11078514 | 40.9 | 2.3 | 6.68533049 | 0.5 |
| DATA-09d-rescan | `US-12259531-B2-e6.zmx` | intaken | passes local intake gates | 5.04266095 | 37.4 | 1.85 | 6.68961847 | 0.5 |
| DATA-09d-rescan | `US-12259531-B2-e7.zmx` | intaken | passes local intake gates | 3.8583167 | 36 | 1.65 | 2.9079348 | 0.5 |
| DATA-09d-rescan | `US-12259531-B2-e8.zmx` | intaken | passes local intake gates | 3.92714087 | 35.1 | 2.3 | 2.85601562 | 0.5 |
| DATA-09d-rescan | `US-12259531-B2-e9.zmx` | intaken | passes local intake gates | 3.93586008 | 35.6 | 2.25 | 2.87150637 | 0.5 |
| DATA-09d-rescan | `US-12282142-B2-e1.zmx` | intaken | passes local intake gates | 4.01530276 | 44.3 | 2 | 3.82812672 | 0.5 |
| DATA-09d-rescan | `US-12282142-B2-e10.zmx` | intaken | passes local intake gates | 4.87987193 | 39.6 | 2.15 | 3.89264933 | 0.5 |
| DATA-09d-rescan | `US-12282142-B2-e2.zmx` | intaken | passes local intake gates | 4.69599412 | 39.9 | 2 | 3.80670364 | 0.5 |
| DATA-09d-rescan | `US-12282142-B2-e3.zmx` | intaken | passes local intake gates | 5.19620182 | 40.3 | 2.2 | 4.23294638 | 0.5 |
| DATA-09d-rescan | `US-12282142-B2-e4.zmx` | intaken | passes local intake gates | 4.61345147 | 37.5 | 2.3 | 3.57423458 | 0.5 |
| DATA-09d-rescan | `US-12282142-B2-e6.zmx` | intaken | passes local intake gates | 5.37906239 | 39.1 | 2.2 | 4.22408683 | 0.5 |
| DATA-09d-rescan | `US-12282142-B2-e7.zmx` | intaken | passes local intake gates | 4.70393612 | 39.9 | 2.05 | 3.9741384 | 0.5 |
| DATA-09d-rescan | `US-12282142-B2-e9.zmx` | intaken | passes local intake gates | 5.18943362 | 36.9 | 2.2 | 19.5155669 | 0.5 |
| DATA-09d-rescan | `US-12360347-B2-e1.zmx` | intaken | passes local intake gates | 6.17028187 | 20.8 | 2.4 | 0.615333979 | 0 |
| DATA-09d-rescan | `US-12372756-B2-e1.zmx` | intaken | passes local intake gates | 10.2126764 | 15 | 3 | 2.81385291 | 0.5 |
| DATA-09d-rescan | `US-12372756-B2-e10.zmx` | intaken | passes local intake gates | 10.6932863 | 15.1 | 2.85 | 2.92609166 | 0 |
| DATA-09d-rescan | `US-12372756-B2-e11.zmx` | intaken | passes local intake gates | 10.648056 | 15.1 | 2.82 | 2.93662612 | 0 |
| DATA-09d-rescan | `US-12372756-B2-e2.zmx` | intaken | passes local intake gates | 10.147984 | 14.5 | 3.2 | 2.68249876 | 0 |
| DATA-09d-rescan | `US-12372756-B2-e3.zmx` | intaken | passes local intake gates | 9.67176829 | 15.3 | 2.85 | 3.90014059 | 0 |
| DATA-09d-rescan | `US-12372756-B2-e4.zmx` | intaken | passes local intake gates | 10.0084397 | 15 | 2.81 | 2.74228661 | 0 |
| DATA-09d-rescan | `US-12372756-B2-e5.zmx` | intaken | passes local intake gates | 10.860497 | 14.8 | 2.83 | 2.93727699 | 0 |
| DATA-09d-rescan | `US-12372756-B2-e6.zmx` | intaken | passes local intake gates | 10.8783434 | 14.5 | 2.65 | 3.19076293 | 0 |
| DATA-09d-rescan | `US-12372756-B2-e7.zmx` | intaken | passes local intake gates | 10.4239089 | 15.3 | 2.65 | 2.92940606 | 0 |
| DATA-09d-rescan | `US-12372756-B2-e8.zmx` | intaken | passes local intake gates | 9.9704888 | 15.9 | 2.45 | 2.93650491 | 0 |
| DATA-09d-rescan | `US-12372756-B2-e9.zmx` | intaken | passes local intake gates | 10.6588585 | 15.3 | 2.85 | 2.93851196 | 0 |
| DATA-09d-rescan | `US-12416792-B2-e12.zmx` | intaken | passes local intake gates | 8.57363624 | 33.1 | 2.5 | 5.92138397 | 0.5 |
| DATA-09d-rescan | `US-12416792-B2-e3.zmx` | intaken | passes local intake gates | 3.97007243 | 35.2 | 1.75 | 2.91624579 | 0.5 |
| DATA-09d-rescan | `US-12416792-B2-e8.zmx` | intaken | passes local intake gates | 6.04791101 | 38.8 | 2.5 | 5.14784738 | 0.5 |
| DATA-09d-rescan | `US-12429675-B2-e7.zmx` | intaken | passes local intake gates | 0.950051107 | 75 | 1.3 | 0.722054272 | 0.5 |
| DATA-09d-rescan | `US-12429675-B2-e8.zmx` | intaken | passes local intake gates | 3.57561144 | 70 | 1.45 | 1.42988085 | 0 |
| DATA-09d-rescan | `US-12436366-B2-e10.zmx` | intaken | passes local intake gates | 14.5172356 | 13.7 | 2.81 | 3.63891384 | 0.5 |
| DATA-09d-rescan | `US-12436366-B2-e11.zmx` | intaken | passes local intake gates | 14.8761998 | 13.4 | 3.15 | 3.65564802 | 0.5 |
| DATA-09d-rescan | `US-12436366-B2-e3.zmx` | intaken | passes local intake gates | 14.9093853 | 13.4 | 3.05 | 17.4021171 | 0 |
| DATA-09d-rescan | `US-12436366-B2-e5.zmx` | intaken | passes local intake gates | 15.8035049 | 14.3 | 3.52 | 4.31742802 | 0.5 |
| DATA-09d-rescan | `US-12436366-B2-e6.zmx` | intaken | passes local intake gates | 15.476434 | 14.6 | 3.52 | 14.7020666 | 0.5 |
| DATA-09d-rescan | `US-12436366-B2-e7.zmx` | intaken | passes local intake gates | 15.8042445 | 14.3 | 3.52 | 5.89899902 | 0.5 |
| DATA-09d-rescan | `US-12436366-B2-e8.zmx` | intaken | passes local intake gates | 14.5323386 | 13.7 | 3.16 | 3.57346766 | 0.5 |
| DATA-09d-rescan | `US-12436366-B2-e9.zmx` | intaken | passes local intake gates | 13.8379218 | 14.3 | 3.16 | 3.58317454 | 0.5 |
| DATA-09d-rescan | `US-12468127-B2-e1.zmx` | intaken | passes local intake gates | 1.28996281 | 83.4 | 1.82 | 2.17911234 | 0.5 |
| DATA-09d-rescan | `US-12468127-B2-e10.zmx` | rejected | ValueError: non-positive ATELIER_FTAN_IMH_SANITY_MM -5.808651394 |  |  |  |  |  |
| DATA-09d-rescan | `US-12468127-B2-e11.zmx` | intaken | passes local intake gates | 1.10886604 | 80 | 1.78 | 2.2384519 | 0.5 |
| DATA-09d-rescan | `US-12468127-B2-e2.zmx` | intaken | passes local intake gates | 1.22779916 | 83.5 | 1.8 | 2.31256295 | 0.5 |
| DATA-09d-rescan | `US-12468127-B2-e3.zmx` | rejected | ValueError: non-positive ATELIER_FTAN_IMH_SANITY_MM -8.513580736 |  |  |  |  |  |
| DATA-09d-rescan | `US-12468127-B2-e4.zmx` | rejected | timeout: lightweight Optiland build exceeded 45s |  |  | 1.68 | 0.0387145846 |  |
| DATA-09d-rescan | `US-12468127-B2-e5.zmx` | intaken | passes local intake gates | 1.19222166 | 74 | 1.8 | 2.24041432 | 0.5 |
| DATA-09d-rescan | `US-12468127-B2-e6.zmx` | rejected | ValueError: non-positive ATELIER_FTAN_IMH_SANITY_MM -8.112832774 |  |  |  |  |  |
| DATA-09d-rescan | `US-12468127-B2-e7.zmx` | intaken | passes local intake gates | 1.28538115 | 78 | 1.89 | 2.17598094 | 0.5 |
| DATA-09d-rescan | `US-12468127-B2-e8.zmx` | intaken | passes local intake gates | 1.06169908 | 73.9 | 2 | 2.20810604 | 0.5 |
| DATA-09d-rescan | `US-12468127-B2-e9.zmx` | rejected | ValueError: non-positive ATELIER_FTAN_IMH_SANITY_MM -11.43558426 |  |  |  |  |  |
| DATA-09d-rescan | `US-12571994-B2-e1.zmx` | intaken | passes local intake gates | 6.62460659 | 16.3 | 2.85 | 1.77880632 | 0.5 |
| DATA-09d-rescan | `US-12571994-B2-e4.zmx` | intaken | passes local intake gates | 6.39024913 | 16.8 | 2.85 | 2.81398231 | 0.5 |
| DATA-09d-rescan | `US-12650578-B2-e1.zmx` | intaken | passes local intake gates | 1.91230848 | 59 | 2.15 | 2.28800042 | 0.5 |
| DATA-09d-rescan | `US-12650578-B2-e3.zmx` | intaken | passes local intake gates | 1.65222173 | 57.5 | 1.87 | 1.92155313 | 0.5 |
| DATA-09d-rescan | `US-12650578-B2-e5.zmx` | intaken | passes local intake gates | 3.1286498 | 55.6 | 2.01 | 3.37224244 | 0.5 |
| DATA-09d-rescan | `US-12650578-B2-e6.zmx` | intaken | passes local intake gates | 1.39273409 | 60.5 | 1.98 | 2.28571086 | 0.5 |
| DATA-09d-rescan | `US-12650578-B2-e7.zmx` | intaken | passes local intake gates | 1.6313988 | 57.5 | 2.1 | 2.28721939 | 0.5 |
| DATA-09d-rescan | `US-20220011544-A1-e2.zmx` | intaken | passes local intake gates | 2.88735843 | 48.6168016 | 2 | 3.21069164 | 0.5 |
| DATA-09d-rescan | `US-20220011544-A1-e3.zmx` | intaken | passes local intake gates | 3.01635681 | 47.3632466 | 2 | 3.21520044 | 0.5 |
| DATA-09d-rescan | `US-20220011544-A1-e5.zmx` | intaken | passes local intake gates | 2.89857491 | 48.5186115 | 2 | 3.54979922 | 0.5 |
| DATA-09d-rescan | `US-20220050269-A1-e3.zmx` | intaken | passes local intake gates | 2.48878224 | 40.1433961 | 2 | 2.06771073 | 0.5 |
| DATA-09d-rescan | `US-20220050269-A1-e4.zmx` | intaken | passes local intake gates | 2.48710605 | 40.1433961 | 2.2 | 2.01773512 | 0.5 |
| DATA-09d-rescan | `US-20240168263-A1-e10.zmx` | intaken | passes local intake gates | 4.30727252 | 38.7 | 2.35 | 3.61206366 | 0.5 |
| DATA-09d-rescan | `US-20240168263-A1-e11.zmx` | intaken | passes local intake gates | 3.96148158 | 41.3 | 2.3 | 3.61120509 | 0.5 |
| DATA-09d-rescan | `US-20240168263-A1-e12.zmx` | intaken | passes local intake gates | 4.11078514 | 40.9 | 2.3 | 6.68533049 | 0.5 |
| DATA-09d-rescan | `US-20240168263-A1-e6.zmx` | intaken | passes local intake gates | 5.04266095 | 37.4 | 1.85 | 6.68961847 | 0.5 |
| DATA-09d-rescan | `US-20240168263-A1-e7.zmx` | intaken | passes local intake gates | 3.8583167 | 36 | 1.65 | 2.9079348 | 0.5 |
| DATA-09d-rescan | `US-20240168263-A1-e8.zmx` | intaken | passes local intake gates | 3.92714087 | 35.1 | 2.3 | 2.85601562 | 0.5 |
| DATA-09d-rescan | `US-20240168263-A1-e9.zmx` | intaken | passes local intake gates | 3.93586008 | 35.6 | 2.25 | 2.87150637 | 0.5 |
| DATA-09d-rescan | `US-20240176110-A1-e7.zmx` | intaken | passes local intake gates | 0.950051107 | 75 | 1.3 | 0.722054272 | 0.5 |
| DATA-09d-rescan | `US-20240176110-A1-e8.zmx` | intaken | passes local intake gates | 3.57561144 | 70 | 1.45 | 1.42988085 | 0 |
| DATA-09d-rescan | `US-20250123465-A1-e3.zmx` | rejected | ValueError: non-positive ATELIER_FTAN_IMH_SANITY_MM -10.09488164 |  |  |  |  |  |
| DATA-09d-rescan | `US-20250189767-A1-e10.zmx` | intaken | passes local intake gates | 4.30727252 | 38.7 | 2.35 | 3.61206366 | 0.5 |
| DATA-09d-rescan | `US-20250189767-A1-e11.zmx` | intaken | passes local intake gates | 3.96148158 | 41.3 | 2.3 | 3.61120509 | 0.5 |
| DATA-09d-rescan | `US-20250189767-A1-e12.zmx` | intaken | passes local intake gates | 4.11078514 | 40.9 | 2.3 | 6.68533049 | 0.5 |
| DATA-09d-rescan | `US-20250189767-A1-e6.zmx` | intaken | passes local intake gates | 5.04266095 | 37.4 | 1.85 | 6.68961847 | 0.5 |
| DATA-09d-rescan | `US-20250189767-A1-e7.zmx` | intaken | passes local intake gates | 3.8583167 | 36 | 1.65 | 2.9079348 | 0.5 |
| DATA-09d-rescan | `US-20250189767-A1-e8.zmx` | intaken | passes local intake gates | 3.92714087 | 35.1 | 2.3 | 2.85601562 | 0.5 |
| DATA-09d-rescan | `US-20250189767-A1-e9.zmx` | intaken | passes local intake gates | 3.93586008 | 35.6 | 2.25 | 2.87150637 | 0.5 |
| DATA-09d-rescan | `US-20250216655-A1-e1.zmx` | intaken | passes local intake gates | 4.01530276 | 44.3 | 2 | 3.82812672 | 0.5 |
| DATA-09d-rescan | `US-20250216655-A1-e10.zmx` | intaken | passes local intake gates | 4.87987193 | 39.6 | 2.15 | 3.89264933 | 0.5 |
| DATA-09d-rescan | `US-20250216655-A1-e2.zmx` | intaken | passes local intake gates | 4.69599412 | 39.9 | 2 | 3.80670364 | 0.5 |
| DATA-09d-rescan | `US-20250216655-A1-e3.zmx` | intaken | passes local intake gates | 5.19620182 | 40.3 | 2.2 | 4.23294638 | 0.5 |
| DATA-09d-rescan | `US-20250216655-A1-e4.zmx` | intaken | passes local intake gates | 4.61345147 | 37.5 | 2.3 | 3.57423458 | 0.5 |
| DATA-09d-rescan | `US-20250216655-A1-e6.zmx` | intaken | passes local intake gates | 5.37906239 | 39.1 | 2.2 | 4.22408683 | 0.5 |
| DATA-09d-rescan | `US-20250216655-A1-e7.zmx` | intaken | passes local intake gates | 4.70393612 | 39.9 | 2.05 | 3.9741384 | 0.5 |
| DATA-09d-rescan | `US-20250216655-A1-e9.zmx` | intaken | passes local intake gates | 5.18943362 | 36.9 | 2.2 | 19.5155669 | 0.5 |
| DATA-09d-rescan | `US-20250298222-A1-e1.zmx` | intaken | passes local intake gates | 6.17028187 | 20.8 | 2.4 | 0.615333979 | 0 |
| DATA-09d-rescan | `US-20250298222-A1-e4.zmx` | intaken | passes local intake gates | 6.1449978 | 17.5 | 2.4 | 1.89046331 | 0 |
| DATA-09d-rescan | `US-20250298222-A1-e5.zmx` | intaken | passes local intake gates | 6.14345041 | 21 | 2.38 | 2.20590888 | 0 |
| DATA-09d-rescan | `US-20250298222-A1-e6.zmx` | intaken | passes local intake gates | 6.16355087 | 21 | 2.45 | 2.21957886 | 0 |
| DATA-09d-rescan | `US-20250370230-A1-e10.zmx` | intaken | passes local intake gates | 1.13740787 | 90 | 2.04 | 1.63862068 | 0.5 |
| DATA-09d-rescan | `US-20250370230-A1-e3.zmx` | rejected | ValueError: non-positive ATELIER_FTAN_IMH_SANITY_MM -16.01674621 |  |  |  |  |  |
| DATA-09d-rescan | `US-20250370230-A1-e5.zmx` | intaken | passes local intake gates | 1.03982196 | 90 | 2.04 | 1.64218627 | 0.5 |
| DATA-09d-rescan | `US-20260160979-A1-e1.zmx` | intaken | passes local intake gates | 12.9841734 | 20 | 1.71 | 4.63058195 | 0.5 |
| DATA-09d-rescan | `US-20260160979-A1-e2.zmx` | intaken | passes local intake gates | 15.2867685 | 17.2 | 1.65 | 4.64762212 | 0.5 |
| DATA-09d-rescan | `US-20260160979-A1-e3.zmx` | intaken | passes local intake gates | 13.420291 | 19 | 1.68 | 4.54780756 | 0.5 |
| DATA-09d-rescan | `US-20260160979-A1-e4.zmx` | intaken | passes local intake gates | 11.3819973 | 23.6 | 1.84 | 4.93722317 | 0.5 |
| DATA-09d-rescan | `US-20260160979-A1-e5.zmx` | intaken | passes local intake gates | 15.2677539 | 17.2 | 1.65 | 4.64916201 | 0.5 |
| DATA-09d-rescan | `US-20260160979-A1-e6.zmx` | intaken | passes local intake gates | 14.7466811 | 15.8 | 1.55 | 4.13077144 | 0.5 |
| DATA-09d-rescan | `US-20260160979-A1-e7.zmx` | intaken | passes local intake gates | 14.878304 | 17.4 | 1.6 | 4.66083873 | 0.5 |
| DATA-09d-rescan | `US-20260160979-A1-e8.zmx` | intaken | passes local intake gates | 19.8402978 | 13.2 | 1.45 | 4.71164162 | 0.5 |
| DATA-09d-rescan | `US-20260160979-A1-e9.zmx` | intaken | passes local intake gates | 14.5714668 | 17.8 | 1.63 | 4.65072437 | 0.5 |
