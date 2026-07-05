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

Verification:

- Mock path exercises batch TSV parsing, optimized readout parsing, `zmx_writer`, and `zmx_ingest`.
- Real CODE V smoke passed on the local CODE V 11.5 install.
- Rebuilt `optimized.zmx` was produced and accepted by `zmx_ingest`.
