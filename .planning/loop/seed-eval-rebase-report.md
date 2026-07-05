# SEED-03a eval golden rebase report

Date: 2026-07-06

## Scope

`scripts/e2_golden.py` now expands patent golden briefs directly from
`app/data/optical_cases/index.json`, so all 22 reanchored `US*` seeds are covered
instead of the previous hand-picked five. The generated golden file has 25 briefs:
3 existing baseline briefs plus 22 patent reanchor briefs.

The five original patent golden names are preserved for compatibility with
`scripts/evaluate_design_agent.py`; the other patent seeds use
`patent_<case_id>_reanchor` names.

## Patent coverage

- Patent source seeds covered: 22/22.
- Self-selected exact briefs: 18/22.
- Non-self selected exact briefs recorded as source -> selected:
  - `US8908290B1` -> `US20170003482A1`
  - `US10310222B2` -> `US10031318B2`
  - `US20140111876A1` -> `US9195030B2`
  - `US9316811B2` -> `US9063319B1`
- Physical anchor gate: every patent index IMH is checked against
  `EFL*tan(FOV/2)` with a <=25% deviation limit; latest probe max was 2.94%
  (`US10330891B2`).

## Verification

- Regenerated `tests/data/eval_golden.json` with
  `PYTHONUTF8=1 .\.venv\Scripts\python.exe scripts\e2_golden.py`.
- Slice pytest passed:
  `PYTHONUTF8=1 .\.venv\Scripts\python.exe -m pytest tests/test_seed_imh_rebase.py tests/test_seed_routing.py tests/test_eval_golden_seeds.py tests/test_codev_readout.py -q`
- Result: 57 passed, 120 Optiland deprecation warnings.

No full pytest run was performed for this slice.
