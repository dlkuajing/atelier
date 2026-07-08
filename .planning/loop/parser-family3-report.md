# DATA-09g parser family3 report

## Scope

- task: DATA-09g remaining assignee-family parser expansion, family 3
- selected_family: `Changzhou AAC Raytech Optronics Co., Ltd.`
- primary_selection_basis: same DATA-09f source inventory method. `.planning/loop/patent2zmx-rescan-report.md` and wave4 report are absent, so selection used `patent2zmx-scale-report.md` plus `patent2zmx-wave5-report.md`. After DATA-09e LARGAN and DATA-09f Fujifilm, the largest current-code-uncovered assignee family with at least 5 failed patent candidates is Changzhou AAC Raytech.
- source_reports_used: `patent2zmx-scale-report.md`, `patent2zmx-wave5-report.md`
- source_failure_rows_rechecked: 12 failed patent rows across 12 Changzhou AAC Raytech patent candidates
- parser_policy: deterministic USPTO PPUBS table parsing only; no LLM numeric fill
- backtest_policy: parser-only full failed-candidate backtest; no real ZMX trace run for this slice

## Failure Family Facts

- Source failure reason before this patch: `embodiment f/Fno/HFOV line not found` for all 12 selected candidates.
- USPTO PPUBS full text inspected: `US-20260009973-A1`, `US-20260009978-A1`, `US-20260086326-A1`, `US-20260126617-A1`, `US-20260186239-A1`, `US-20260186243-A1`, `US-20260186255-A1`, `US-20260186268-A1`, `US-20260186270-A1`, `US-20260186272-A1`, `US-20260186274-A1`, `US-20260186382-A1`.

## USPTO Format Facts

- Fixed-focus AAC Raytech examples use compact surface tables headed `R d nd vd` or `R d nd νd`.
- The stop row is encoded as `S1 Infinity d0= ...` or `ST Infinity d0 ...`.
- Lens/filter rows are keyed by `R1`, `R2`, ... with adjacent `dN`, optional `ndN`, and `vN`/`vdN`/`νN` material values.
- Asphere data sits in the next table and is row-oriented by `R1`, `R2`, ... . Headers can repeat inside one table, for example `k A4 ... A12` followed by a second header `k A14 ... A22`.
- Metadata is detached. Some patents put `f`, `Fno`, `IH`, and `FOV` in the final parameters table; others put only `f/FNO/TTL` there and state per-example `IH/FOV` in the narrative immediately after each asphere table.
- `FOV` is full diagonal field and is converted to `hfov_deg = FOV / 2`.
- Zoom/periscope variants use `Rp*`, `dp*`, state tables, and dynamic spacing such as `d10`; those are recognized as the same family but left fail-loud in this fixed-focus parser slice.
- `A32+` remains fail-loud. One fixed-format patent exposes nonzero `A36`, which needs a separate XASPHERE writer-policy decision rather than silent truncation.

## Parser Changes

- Added an AAC Raytech fallback only when the existing embodiment metadata parser and Fujifilm fallback find no usable attempts.
- Added compact `R/d/nd/vd` surface parsing with stop row support and sequential ZMX surface indexing.
- Added row-oriented AAC Raytech asphere parsing for repeated `k/A4...` headers through the currently supported A30 writer limit.
- Added detached metadata synthesis from final summary rows plus per-example narrative `IH/FOV` facts.
- Kept zoom/Rp dynamic-spacing formats and A32+ coefficients fail-loud.
- Added a local fixture covering `νd`, repeated asphere headers, FOV-to-HFOV conversion, and A22 coefficient preservation.

## Full Failed-Patent Parser Backtest

- failed_patents_rechecked: 12
- parser_embodiment_tables_discovered: 65
- successes: 33
- discovered_embodiment_parse_failures: 32
- parser_candidate_hits: 7
- format_recognized_candidates: 12
- parser_success_rate_by_discovered_embodiment: 33/65 (50.8%)
- parser_candidate_hit_rate: 7/12 (58.3%)
- format_recognition_rate: 12/12 (100.0%)

| patent | source | parser attempts | parser successes | remaining parser failures |
|---|---|---:|---:|---|
| US-20260009973-A1 | uspto-smartphone-batch7.jsonl:63 | 5 | 5 | none |
| US-20260009978-A1 | uspto-smartphone-batch7.jsonl:64 | 5 | 5 | none |
| US-20260086326-A1 | uspto-smartphone-batch4.jsonl:65 | 5 | 5 | none |
| US-20260126617-A1 | uspto-smartphone-batch4.jsonl:63 | 5 | 5 | none |
| US-20260186239-A1 | uspto-smartphone-batch4.jsonl:42 | 5 | 5 | none |
| US-20260186243-A1 | uspto-smartphone-batch4.jsonl:43 | 5 | 0 | unsupported nonzero AAC Raytech A36 terms: 5 |
| US-20260186255-A1 | uspto-smartphone-batch4.jsonl:44 | 4 | 4 | none |
| US-20260186268-A1 | uspto-smartphone-batch4.jsonl:53 | 5 | 0 | zoom/Rp dynamic spacing or missing fixed-focus summary metadata: 5 |
| US-20260186270-A1 | uspto-smartphone-batch4.jsonl:52 | 4 | 4 | none |
| US-20260186272-A1 | uspto-smartphone-batch4.jsonl:57 | 6 | 0 | zoom/Rp dynamic spacing or missing fixed-focus summary metadata: 6 |
| US-20260186274-A1 | uspto-smartphone-batch4.jsonl:51 | 10 | 0 | zoom/Rp state-table format with `fA`, not fixed-focus `f`: 10 |
| US-20260186382-A1 | uspto-smartphone-batch4.jsonl:55 | 6 | 0 | zoom/Rp dynamic spacing or missing fixed-focus summary metadata: 6 |

## Remaining Work

- Add a separate zoom/periscope AAC Raytech parser for `Rp*`, `dp*`, state-specific `f/FOV/FNO`, and dynamic spacings.
- Decide whether the writer should support XASPHERE terms beyond A30 before accepting `A36` rows.

## Self-Check

- `PYTHONUTF8=1 uv run pytest -q tests/test_patent_to_zmx.py`
- result: 25 passed
- `bash scripts/run_slice_gate.sh`
- result: exit code 0
- parser-only real USPTO backtest:
  - failed patents: 12
  - parser attempts: 65
  - successes: 33
  - parser success rate: 33/65 (50.8%)
  - parser candidate hit rate: 7/12 (58.3%)
