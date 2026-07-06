# DATA-06c Seed Intake B9 Report

## Summary

- Intake set: 67 tracked successful ZMX files from `data/zmx-staging`.
  - DATA-06a spike successes: 3
  - DATA-06b2 scale successes: 64
- Formal ZMX location: `data/zmx/`
- Case library count: 39 -> 106
- Case generation: `scripts/generate_cases.py`, 106 generated, 0 failed
- New DATA-06c index image-height source: `ATELIER_REAL_IMH_MM` from the converted ZMX tail comments, written through `tests/data/data06c_manifest.json`

## Artifact Policy

DATA-06c converted patent seeds can make Optiland's full demo SVG/MTF path hang
on some prescriptions. Formal intake therefore keeps the physical facts from the
normal path:

- ZMX source file is the stored truth.
- Optiland load/paraxial/surface extraction/trace still run for every seed.
- `image_height_mm` is the converter's real-ray `ATELIER_REAL_IMH_MM`.
- DATA-06c display artifacts use a bounded lightweight path:
  - fast surface-stack SVG
  - low-sample MTF at 0/0.5 field when available
  - `mtf_max_field_frac` stays <= 0.5, so these seeds cannot satisfy full-field audit gates by accident

Existing 39 seed image heights are preserved via `tests/data/seed_imh_overrides.json`
so prior true-IMH rebasing is not overwritten by regeneration.

## Audit

Command:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe scripts/audit_seed_intake.py --target-fov 88 --target-efl 2.8 --target-fnum 1.9 --min-fov 85 --required-field 1.0 --target-image-height 2.9 --image-height-lo 2.55 --image-height-hi 3.25 --target-elements 5 --element-count-lo 4 --element-count-hi 6 --json
```

Result written to `.planning/loop/seed-intake-b9-audit.json`:

- status: `gap`
- total_seed_count: 106
- full_field_seed_count: 19
- high_fov_seed_count: 16
- accepted_seed_count: 0
- nearest high-FOV seed: `US-20230288669-A1-e4`, MTF field 0.5
- best stable high-FOV seed: `US20170003482A1`, stable 1.0 field

## Eval Golden

- `tests/data/eval_golden.json`: 28 briefs
  - 3 base briefs
  - 25 physically anchored patent briefs
  - DATA-06c adds 3 patent golden briefs under the <=25% first-order anchor convention

## Verification

Slice test command:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest -q tests/test_zmx_ingest.py tests/test_case_library.py tests/test_seed_intake_audit.py tests/test_eval_golden_seeds.py tests/test_parameter_guards.py tests/test_design_agent_eval_cli.py
```

Result: 84 passed.

Full gate command:

```bash
PATH="$HOME/.local/bin:$PATH" PYTHONUTF8=1 ./.venv/Scripts/python.exe -m pytest -q > .planning/loop/gate-last.log 2>&1
```

Result: 422 passed, 2 skipped.
