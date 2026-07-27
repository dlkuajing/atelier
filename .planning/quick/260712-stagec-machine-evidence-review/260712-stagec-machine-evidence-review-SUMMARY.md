# Stage C machine evidence — review hardening summary

## Closed findings

1. Listing and metrics digests now retain base64 artifact bytes and re-hash them. Config is
   canonical-JSON fingerprinted; the complete readback has a second canonical fingerprint
   coupling all per-field values/counts/classifications to those artifacts and config.
2. Counts must equal the bound configured count and the configured count is at least two;
   self-consistent `1/1` cannot pass. Every field carries machine X readback and X must be
   finite exact zero, including the axial field.
3. Artifact vignetting provenance must reference the actual reconstructed artifact SHA;
   machine-readback provenance must reference retained listing/metrics bytes. Current Stage C
   reconstruction is verified-zero only, so unknown, mismatched, or nonzero claims fail.
4. EFL relative error uses decimal canonical values and strict `< Decimal("0.02")`;
   target `5`, measured `5.1` fails deterministically.
5. Workbook and bundle public entries strict-JSON revalidate candidate invariants. Invalid
   workbook input raises; invalid bundle input emits only a neutral rejection README with no
   candidate status, verified evidence, ZMX, or sequence.

FOV remains derived-only, IMH/FOV remain outside `CONVERGED_FIELDS`, and `[EXPERT]` remains
blank. No CODE V process, parser, machine syntax, production runner, or control worktree was
touched.

## Verification

- `PYTHONUTF8=1 uv run pytest tests/test_stagec_field.py tests/test_orchestration_candidate.py tests/test_orchestration_scorecard.py tests/test_orchestration_export.py tests/test_web_candidates.py tests/test_p16_stagec_offline_manifest.py -k "not real" -q`
  — **162 passed, 5 deselected**.
- Ruff on all changed Python files — **all checks passed**.
