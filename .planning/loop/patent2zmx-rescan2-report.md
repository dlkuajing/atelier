# DATA-06i patent-to-ZMX rescan2 report

## Summary

- mode: cursor reset over prior failure inventory; formal case stems and formal prescription fingerprints are skip gates
- prior_failure_inventory_source: existing patent2zmx scale/wave reports plus DATA-09e LARGAN deterministic conversion artifacts
- output_dir: `data/zmx-staging/DATA-06i-rescan2`
- parser: deterministic current `scripts/patent_to_zmx.py`; no numeric LLM fill
- physical_material_guard: nd in [1.3,2.2] and vd in [10,100] enforced before intake
- real_imh: `ATELIER_REAL_IMH_MM` tail comment required and carried into manifest/index
- live_recheck: `US-10921568-B2` completed with 4 successes; `US-12443014-B2` produced e1-e4 before local lightweight-build timeout; `US-20250383531-A1` e4/e5 were reconciled from DATA-09e staging
- successes: 10
- rejected_by_intake_gates: 4
- failures_or_timeouts_recorded: 4
- skipped_formal_or_fingerprint_duplicates: already-ingested stems/fingerprints are excluded from the success set

## Successful Artifacts

| zmx | real_imh_mm | efl_mm | fov_deg | fnum | mtf_max_field_frac | provenance |
|---|---:|---:|---:|---:|---:|---|
| `US-10921568-B2-e1.zmx` | 1.2372216 | 2.8558963 | 76 | 2.3 | 0.5 | live rescan2 |
| `US-10921568-B2-e2.zmx` | 0.299680801 | 2.90562016 | 76.4 | 2.4 | 0 | live rescan2 |
| `US-10921568-B2-e7.zmx` | 3.07814634 | 2.92575673 | 75.4 | 2.3 | 0.5 | live rescan2 |
| `US-10921568-B2-e9.zmx` | 3.08583772 | 4.25013245 | 76.2 | 2.18 | 0.5 | live rescan2 |
| `US-12443014-B2-e1.zmx` | 2.43237252 | 17.3271113 | 15.8 | 2.8 | 0 | live rescan2 |
| `US-12443014-B2-e2.zmx` | 3.8664357 | 22.9109897 | 19 | 2.8 | 0.5 | live rescan2 |
| `US-12443014-B2-e3.zmx` | 5.07220228 | 21.3567092 | 20.4 | 2.65 | 0.5 | live rescan2 |
| `US-12443014-B2-e4.zmx` | 3.76175574 | 18.74561 | 23 | 2.65 | 0.5 | live rescan2 |
| `US-20250383531-A1-e4.zmx` | 0.451319587 | 0.725916375 | 122 | 1.7 | 0 | DATA-09e staging reconciliation |
| `US-20250383531-A1-e5.zmx` | 1.22261167 | 1.61460698 | 122.8 | 7 | 0.5 | DATA-09e staging reconciliation |

## Timeout / Non-success Notes

| patent | artifact | status | reason |
|---|---|---|---|
| US-12443014-B2 | `US-12443014-B2-e5.zmx` | rejected | lightweight sample build exceeded 70s local retry timeout after residual process cleanup; not kept in formal `data/zmx` |
| US-12443014-B2 | `US-12443014-B2-e6.zmx` | rejected | lightweight sample build exceeded 120s timeout; not copied to formal `data/zmx` |
| US-12443014-B2 | `US-12443014-B2-e7.zmx` | rejected | lightweight sample build exceeded 120s timeout; not copied to formal `data/zmx` |
| US-12443014-B2 | `US-12443014-B2-e8.zmx` | rejected | lightweight sample build exceeded 120s timeout; left in staging only |
