# ENGINE-05a CODE V Optimize Report

Seed: `US20170003482A1.zmx`

Run: 2026-07-06 local CODE V 11.5 smoke via `tests/test_codev_optimize.py`

Adapter: `app/core/engines/codev_optimize.py`

Planned batch contract:

- Generate `atelier_codev_optimize.seq` from the seed ZMX.
- Import the seed through `CV_MACRO:ZEMAXOS_TO_CV`.
- Capture before/after metrics through explicit `BUF PUT` and `BUF EXP`.
- Run `AUT` with EFL held, no glass variables, and `MNT/MNE/MXT/MNA` thickness bounds.
- Optimize against lateral color and RMS spot objectives.
- Export optimized CODE V readout TSV, rebuild `optimized.zmx`, then pass it through `zmx_ingest`.
- The displayed sensitivity table is **CODE V perturbation replay** over eligible
  non-stop/non-image/non-dummy curved surfaces and thicknesses. It is not parsed
  from a TOR report and does not run TOR; rows come from explicit RDY/THI
  perturbations followed by CODE V MTF replay.

Metric columns:

| Stage | EFL Y mm | Lateral color um | RMS spot diameter um | Wavefront RMS waves | Distortion pct |
|---|---:|---:|---:|---:|---:|
| before | 3.62252 | 0.615114 | 9.57171 | 0.365371 | 2.00747 |
| after | 3.62249 | 0.0502348 | 3.76996 | 0.0493892 | 1.1004 |

EFL deviation: `0.000800163%`

Artifacts:

- Sequence: `atelier_codev_optimize.seq`
- Metrics TSV: `atelier_codev_optimize.tsv`
- Optimized readout TSV: `atelier_codev_optimized_readout.tsv`
- Rebuilt ZMX: `optimized.zmx`
- Demo cache artifact: `codev_artifact` carries before/after metrics, refined MTF,
  and run evidence fingerprints before the result page may label values as
  `data-provenance="codev-run"`.

Verification:

- Mock path exercises batch TSV parsing, optimized readout parsing, `zmx_writer`, and `zmx_ingest`.
- Real CODE V smoke passed on the local CODE V 11.5 install.
- Rebuilt `optimized.zmx` was produced and accepted by `zmx_ingest`.
- Batch 8 review fix tightened provenance: fixtures and fallback Optiland-only data
  render as `optiland-estimate`, while `codev-run` requires persisted run evidence.
