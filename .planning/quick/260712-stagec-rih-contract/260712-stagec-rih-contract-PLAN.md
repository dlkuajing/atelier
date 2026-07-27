# Stage C RIH machine-contract hardening

## Objective

Harden the already-merged offline Stage C machine-evidence seam before any real
CODE V execution.  Official CODE V 11.5 macros prove that ZMX `FTYP 3` imports
as `RIH` (`XRI`/`YRI`), not `IMG` (`XIM`/`YIM`).  The contract must retain that
raw type and keep field definitions separate from the traced chief-ray facts.

## Scope

- Bump the unpopulated machine-readback schema and require raw `TYP FLD=RIH`.
- Replace ambiguous scalar/duplicated chief-ray fields with explicit RIH
  definition X/Y and RSI chief-ray X/Y plus direction cosines and raw
  `RAYRSI`/`RER`/`BLS` outcomes.
- Derive the ray classification from raw outcomes; callers cannot assert it.
- Bind the exact field type into the config and readback fingerprints.
- Replace the caller-filled readback builder with a closed, versioned parser:
  listing and metrics bytes are the sole source of machine facts, and their
  embedded run/source/sequence/config hashes must match supplied raw artifacts.
- Require a unique complete run segment in the listing and reject stale,
  duplicate, truncated, or error-bearing segments.
- Add fail-closed negative fixtures for IMG/ANG impersonation, X drift, blocked
  or failed rays, definition/trace transposition, arbitrary/swap artifacts,
  hash drift, duplicate fields, and incomplete listing segments.
- Update candidate/export fixtures and strict restore behavior for the schema.

## Out of scope

- No CODE V process, probe, runner, matrix, or production wiring.  This slice
  implements only the pure parser/validator boundary using synthetic fixtures;
  actual syntax and golden bytes remain gated on the later verified probe.
- No non-zero-vignetting interpretation and no claimed optical qualification.
- No `[EXPERT]` verdict.

## Verification

- `PYTHONUTF8=1 uv run pytest tests/test_stagec_field.py tests/test_orchestration_export.py -k "not real"`
- `uv run ruff check` on changed Python tests/modules.
- `git diff --check`.
- Independent adversarial review from an agent that did not author the patch.
