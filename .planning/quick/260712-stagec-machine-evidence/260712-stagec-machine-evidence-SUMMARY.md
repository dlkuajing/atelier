# Stage C machine evidence — summary

## Delivered

- Added an explicit `evidence_kind` discriminator: existing offline evidence remains
  machine-blocked; machine evidence is a separate factory-only variant.
- Added structured, immutable readback models for canonical field coordinates, per-field
  RSI/chief-ray/spot/WFE values and valid/attempted counts, ray classifications,
  vignetting classification/profile/provenance, artifact SHA-256 values, and config
  fingerprint.
- Machine evidence stores only reconstruction provenance plus raw readback. Four gate
  booleans and `image_height_achieved` are computed fields, not constructor inputs.
- Persisted computed booleans are non-authoritative: candidate restore ignores them and
  rebuilds evidence through the controlled factory from reconstruction/readback facts.
- Gates fail closed on missing/non-finite values, non-axial zero sentinels, zero spot/WFE,
  incomplete valid counts, unknown/non-valid ray classifications, field/profile count or
  fraction mismatch, inconsistent/unknown vignetting provenance, artifact drift, and EFL
  relative error greater than or equal to the existing 2% boundary.
- Candidate and export boundaries bind machine evidence to the same reconstructed artifact,
  canonical target EFL/IMH, field profile, payload, and SHA. Bundle README persists complete
  structured evidence; workbook presents derived status without a verdict.
- FOV remains derived-only, IMH is labelled constructed-machine-verified only after all raw
  field checks, IMH/FOV remain absent from `CONVERGED_FIELDS`, and `[EXPERT]` stays blank.

## Explicitly not implemented

- No CODE V execution, attachment, runner integration, parser, or sequence generation.
- No RSI/chief-ray/WRX/WRY or non-zero-vignetting syntax was guessed.
- No Stage C production runner wiring and no machine-side reader was added.

## Verification

- `PYTHONUTF8=1 uv run pytest tests/test_stagec_field.py tests/test_orchestration_candidate.py tests/test_orchestration_scorecard.py tests/test_orchestration_export.py -k "not real" -q`
  — **127 passed, 5 deselected**.
- `uv run ruff check app/core/engines/stagec_field.py app/core/orchestration/candidate.py app/core/orchestration/export.py tests/test_stagec_field.py tests/test_orchestration_export.py`
  — **all checks passed**.
- Extra full-repository `PYTHONUTF8=1 uv run pytest -k "not real" -q` was attempted twice,
  but produced no terminal result before the command limits (124 s and 604 s). It is not
  counted as passing evidence.
- `D:\atelier-wt-ctl` was not touched; CODE V/codevm was not run, attached, or operated.
