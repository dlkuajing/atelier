# Stage C machine evidence — independent review hardening

## GSD quick entry

- Bind listing/metrics SHA-256 to retained bytes; bind config fingerprint to canonical JSON;
  bind the complete structured readback to both artifacts and config.
- Require configured sample counts (minimum two), machine X readback, and proven X=0.
- Bind vignetting provenance to reconstructed bytes or machine listing/metrics and reject
  any nonzero-vignetting claim against the current zero-vignetting reconstruction seam.
- Make the existing EFL `<2%` gate conservative at the exact numeric boundary.
- Revalidate export inputs through strict JSON roundtrip so `model_copy` cannot bypass
  candidate invariants or emit machine-verified/ZMX output.
- Pure offline work only: no CODE V, parser, sequence, runner, or control-worktree action.

## Verification

- `PYTHONUTF8=1`, explicit `-k "not real"`.
- Targeted Stage C/candidate/scorecard/export/web regressions.
- Ruff and local commit only; no push/PR.
