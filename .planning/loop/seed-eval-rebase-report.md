# SEED-03a eval golden rebase report

Date: 2026-07-05

## Scope

Extended the fixed design-agent regression set so `scripts/evaluate_design_agent.py`
covers reanchored patent seeds after the real-IMH and routing rebases.

## Golden patent seeds

Five patent seed briefs were added to `scripts/e2_golden.py`,
`tests/data/eval_golden.json`, and `scripts/evaluate_design_agent.py`:

| Eval case | Patent seed | Reason |
|---|---:|---|
| `patent_wide_8p_low_f_number_reanchor` | `US20170045714A1` | Wide 8P, low F/# 1.75, FOV 70.4, IMH 2.91317; covers high element count / fast wide seed. |
| `patent_ultrawide_7p_full_field_reanchor` | `US20170003482A1` | Ultrawide 7P, FOV 91.0, IMH 3.62257, full-field MTF coverage; anchors the high-FOV full-field evidence path. |
| `patent_ultrawide_6p_fast_reanchor` | `US20180143405A1` | Ultrawide 6P, F/# 1.86, FOV 95.0, IMH 3.26503; covers fast ultrawide partial-field evidence. |
| `patent_ultrawide_6p_extreme_fov_reanchor` | `US10330891B2` | Ultrawide 6P, FOV 100.0, short EFL 2.41636, IMH 2.97599; covers extreme-FOV routing after IMH reanchor. |
| `patent_wide_6p_full_field_reanchor` | `US9651759B2` | Wide 6P, FOV 82.0, IMH 2.94563, full-field MTF coverage; covers the wide/full-field patent seed class. |

`US8908290B1` was probed but not used: its exact brief routed to
`US20170003482A1`, so it is not a stable self-reanchor golden. The accepted
patent golden entries require `source_case_id == selected_case_id`.

## Verification

- Regenerated `tests/data/eval_golden.json` with
  `PYTHONUTF8=1 ./.venv/Scripts/python.exe scripts/e2_golden.py`.
- `PYTHONUTF8=1 ./.venv/Scripts/python.exe scripts/evaluate_design_agent.py --fail-on-regression --json`
  passed: 13/13 eval cases, 0 failures.
- Slice pytest passed and was written to `.planning/loop/gate-last.log`:
  `PYTHONUTF8=1 ./.venv/Scripts/python.exe -m pytest -q tests/test_eval_golden_seeds.py`.

No full pytest run was performed for this slice.
