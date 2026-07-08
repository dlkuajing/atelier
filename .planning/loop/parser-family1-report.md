# DATA-09e parser family1 report

## Scope

- task: DATA-09e remaining assignee-family parser expansion, family 1
- selected_family: `LARGAN PRECISION CO., LTD.`
- primary_selection_basis: `.planning/loop/patent2zmx-rescan-report.md` absent; wave4 absent; wave5 contains five AAC/Raytech failures and one Fujifilm failure. AAC/Raytech is already covered by `.planning/loop/parser-sunny-report.md`, so the largest uncovered family in the available failure inventory is LARGAN from `patent2zmx-scale-report.md`.
- source_reports_used: `patent2zmx-wave5-report.md`, `patent2zmx-scale-report.md`
- source_failure_rows_rechecked: 169 failed embodiment rows across 27 failed LARGAN patent candidates in `patent2zmx-scale-report.md`
- parser_policy: deterministic USPTO PPUBS table parsing only; no LLM numeric fill
- backtest_policy: parser-only full failed-candidate backtest. Real ZMX conversion was not run for the full family because prior conversion probes hit the known Optiland real-ray trace wall.

## Failure Family Facts

- Top LARGAN source failure buckets before this patch:
  - `full-field real rays did not reach image surface`: 79
  - `unsupported nonzero high-order asphere terms`: 45
  - `surface 14 radius is not numeric`: 21
  - `surface table index break`: 6
  - `surface 13 radius is not numeric`: 4
  - `surface 16 radius is not numeric`: 4
- USPTO PPUBS full text inspected for table format facts: `US-20250383531-A1`, `US-10921568-B2`, `US-12443014-B2`, `US-11774728-B2`, `US-12117596-B2`.

## USPTO Format Facts

- LARGAN rows can express the aperture stop as `Ape. Stop Plano ...` or as standalone `Ape. Plano ... Stop`.
- IR-cut rows can appear as `IR-cut Piano ... Glass ... -- filter`; `Piano` is a PPUBS/OCR variant of `Plano`.
- Folded examples include standalone `Prism Plano ... Glass ...` rows.
- Some material rows use `Cement`, not only `CEMENTED`.
- PPUBS text can expose decimal comma material values such as `18,4`.
- LARGAN asphere tables contain real nonzero terms through A30. A32+ remains rejected by the parser.

## Parser Changes

- Added deterministic labels for standalone `Ape.`, standalone `IR-cut`, and `Prism` rows.
- Added `Piano` as a `Plano` radius synonym.
- Added `Cement` as a material token.
- Preserved decimal commas inside numeric tokens before table tokenization.
- Extended patent asphere parsing and XASPHERE XDAT write-out from A20 through A30.
- Kept A32+ as a fail-loud unsupported high-order term.

## Full Failed-Patent Parser Backtest

- failed_patents_rechecked: 27
- parser_embodiment_tables_discovered: 224
- successes: 213
- discovered_embodiment_parse_failures: 11
- no_metadata_patents: 2
- parser_candidate_hits: 25
- parser_success_rate_by_discovered_embodiment: 213/224 (95.1%)
- parser_candidate_hit_rate: 25/27 (92.6%)

| patent | source | parser attempts | parser successes | remaining parser failures |
|---|---|---:|---:|---|
| US-10921568-B2 | uspto-smartphone-batch5.jsonl:40 | 9 | 8 | surface table index break: 1 |
| US-11774728-B2 | uspto-smartphone-batch5.jsonl:25 | 8 | 8 | none |
| US-11927729-B2 | uspto-smartphone-batch2.jsonl:28 | 10 | 9 | surface table index break: 1 |
| US-11953657-B2 | uspto-smartphone-batch4.jsonl:31 | 8 | 8 | none |
| US-11966029-B2 | uspto-smartphone-batch4.jsonl:29 | 6 | 6 | none |
| US-12050306-B2 | uspto-smartphone-batch5.jsonl:29 | 10 | 9 | surface table index break: 1 |
| US-12117596-B2 | uspto-smartphone-batch2.jsonl:20 | 12 | 12 | none |
| US-12216255-B2 | uspto-smartphone-batch4.jsonl:16 | 8 | 8 | none |
| US-12216256-B2 | uspto-smartphone-batch4.jsonl:15 | 6 | 6 | none |
| US-12248126-B2 | uspto-smartphone-batch4.jsonl:14 | 8 | 8 | none |
| US-12416791-B2 | uspto-smartphone-batch1.jsonl:12 | 10 | 8 | surface table index break: 1; incomplete nd/vd: 1 |
| US-12443014-B2 | uspto-smartphone-batch2.jsonl:5 | 8 | 8 | none |
| US-12449639-B2 | uspto-smartphone-batch2.jsonl:4 | 0 | 0 | embodiment f/Fno/HFOV line not found |
| US-20200003996-A1 | uspto-smartphone-batch5.jsonl:44 | 8 | 7 | surface table index break: 1 |
| US-20220035131-A1 | uspto-smartphone-batch5.jsonl:38 | 11 | 11 | none |
| US-20220187578-A1 | uspto-smartphone-batch5.jsonl:35 | 9 | 9 | none |
| US-20230288669-A1 | uspto-smartphone-batch5.jsonl:26 | 7 | 7 | none |
| US-20240248285-A1 | uspto-smartphone-batch4.jsonl:24 | 8 | 8 | none |
| US-20240264412-A1 | uspto-smartphone-batch4.jsonl:23 | 8 | 8 | none |
| US-20250004254-A1 | uspto-smartphone-batch2.jsonl:19 | 12 | 12 | none |
| US-20250035890-A1 | uspto-smartphone-batch5.jsonl:10 | 7 | 7 | none |
| US-20250035892-A1 | uspto-smartphone-batch5.jsonl:27 | 7 | 7 | none |
| US-20250076615-A1 | uspto-smartphone-batch2.jsonl:18 | 10 | 10 | none |
| US-20250306338-A1 | uspto-smartphone-batch4.jsonl:9 | 12 | 12 | none |
| US-20250370227-A1 | uspto-smartphone-batch4.jsonl:6 | 12 | 8 | surface 16 radius is not numeric: Lend: 4 |
| US-20250383531-A1 | uspto-smartphone-batch2.jsonl:3 | 10 | 9 | surface table index break: 1 |
| US-20260140289-A1 | uspto-smartphone-batch1.jsonl:14 | 0 | 0 | embodiment f/Fno/HFOV line not found |

## Remaining Work

- `surface table index break` cases are PPUBS table-number or row-order anomalies and should be handled in a separate narrow slice.
- `surface 16 radius is not numeric: Lend` is a separate LARGAN/OCR row-label variant.
- Two LARGAN patents still expose no parseable f/Fno/HFOV metadata in PPUBS HTML.

## Self-Check

- `PYTHONUTF8=1 .\.venv\Scripts\python.exe -m pytest -q tests/test_patent_to_zmx.py`
- result: 22 passed
