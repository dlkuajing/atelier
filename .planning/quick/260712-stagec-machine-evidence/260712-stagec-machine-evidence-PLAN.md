# Stage C machine evidence — offline/fail-closed foundation

## GSD quick entry

- Scope: pure models, controlled factory, serialization/export/scorecard boundaries, and mocks.
- Hard boundary: do not run, attach, probe, resume, or parse CODE V; do not touch
  `D:\atelier-wt-ctl`; do not invent RSI/chief-ray/WRX/WRY/vignetting syntax.
- Evidence contract: offline and machine evidence are discriminated variants. Machine
  evidence is created only from a complete structured readback and existing reconstructed
  artifact provenance; callers cannot supply an `achieved` assertion.
- Gate: reconstruction applied, IMH field valid, EFL relative error strictly below 2%, and
  ray metrics valid are derived independently. Missing/non-finite/zero sentinel/unknown
  classification/profile mismatch fail closed.
- Persist: canonical EFL/IMH, field profile and readbacks, per-field valid counts,
  classifications, vignetting provenance, artifact SHA-256 values, config fingerprint.
- Product truth: FOV remains derived-only; IMH is constructed then machine-verified;
  neither IMH nor FOV is added to `CONVERGED_FIELDS`; `[EXPERT]` remains blank.

## Verification

- `PYTHONUTF8=1 uv run pytest ... -k "not real"`
- `uv run ruff check ...`
- local commit only; no push or PR.
