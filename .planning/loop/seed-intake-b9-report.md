# DATA-06c Seed Intake B9 Report

## Summary

- Intake set: 67 tracked successful ZMX files from `data/zmx-staging`.
  - DATA-06a spike successes: 3
  - DATA-06b2 scale successes: 64
- Formal ZMX location: `data/zmx/`
- Case library count: 39 -> 106
- Case generation: `scripts/generate_cases.py`, 106 generated, 0 failed
- New DATA-06c index image-height source: `ATELIER_REAL_IMH_MM` from the converted ZMX tail comments, written through `tests/data/data06c_manifest.json`
- Review fix: `scripts/audit_seed_intake.py` now reports strict full-field accepted seeds separately from DATA-06c lightweight-path seed acceptance.

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

Original batch-9 JSON remains at `.planning/loop/seed-intake-b9-audit.json`.
Review-fix spot-check output from the command above:

- status: `gap`
- total_seed_count: 106
- full_field_seed_count: 19
- high_fov_seed_count: 16
- accepted_seed_count: 0
- full_field_accepted_seed_count: 0
- accepted_seed_count semantics: strict high-FOV full-field acquisition-window gate only; DATA-06c lightweight-path seeds with bounded payload MTF are not counted here
- lightweight_seed_count: 67
- lightweight_accepted_seed_count: 67
- lightweight_rejected_seed_count: 0
- lightweight gate: loaded + finite positive paraxial + IMH > 0 + JSON surface count equals ZMX `SURF` count
- nearest high-FOV seed: `US-20230288669-A1-e4`, MTF field 0.5
- best stable high-FOV seed: `US20170003482A1`, stable 1.0 field

## Eval Golden

- `tests/data/eval_golden.json`: 109 briefs
  - 3 base briefs
  - 106 case-anchored briefs, one for every `app/data/optical_cases/index.json` case
  - DATA-06c contributes all 67 converted seeds
  - 64 DATA-06c seeds whose index IMH differs from first-order `f*tan(FOV/2)` by >25% are included; f*tan is now recorded as sanity metadata, not used as a gate
  - For the 67 ZMX files with `ATELIER_REAL_IMH_MM`, index `image_height_mm` is checked against the tail-comment real-ray IMH at <=2% before golden generation

## Verification

Review-fix command:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_eval_golden_seeds.py tests/test_seed_intake_audit.py -q
```

Result: 325 passed, 1575 warnings.

Audit semantics spot-check:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe scripts/audit_seed_intake.py --target-fov 88 --target-efl 2.8 --target-fnum 1.9 --min-fov 85 --required-field 1.0 --target-image-height 2.9 --image-height-lo 2.55 --image-height-hi 3.25 --target-elements 5 --element-count-lo 4 --element-count-hi 6 --json
```

Spot-check result: `accepted_seed_count=0`, `full_field_accepted_seed_count=0`, `lightweight_accepted_seed_count=67/67`.

Original batch-9 verification before review fix:

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
