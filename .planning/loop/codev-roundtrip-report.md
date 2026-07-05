# ENGINE-03c CODE V ZMX Roundtrip Report

Date: 2026-07-05

## Scope

- Selected patent seed: `data/zmx/US20170003482A1.zmx`
- CODE V executable: `D:\CODEV115\codev.exe` (11.5, see `codev-probe-report.md`)
- Import macro used: `IN CV_MACRO:ZEMAXOS_TO_CV "<seed.zmx>"`
- Structured output contract: `BUF PUT` + `BUF EXP`, schema `atelier-codev-roundtrip-v1`
- Command-file export: `WRL "atelier_codev_roundtrip_export.seq"`

## Result

Partial pass, with one explicit blocker.

CODE V successfully imported the patent ZMX and computed first-order facts:

- `efl_y_mm`: `3.62252`
- `max_image_height_y_mm`: `3.62257`
- `num_surfaces`: `18`
- `num_fields`: `3`
- `WRL` command export was produced.

Native CODE V export back to Zemax `.zmx` is not confirmed in CODE V 11.5 on this machine. The installed Lens System Setup manual documents `.ZMX` import and exports to command file / IGES / STEP / SAT / LightTools; `WRL` writes CODE V `.seq`, not Zemax `.zmx`. Therefore the final "exported ZMX vs zmx_ingest" comparison gate is implemented and tested, but cannot be honestly marked closed until a real exported `.zmx` artifact exists.

## Four Fidelity Records

| Gate | Source / CODE V evidence | Status |
| --- | --- | --- |
| EFL deviation <2% | `zmx_ingest` source EFL `3.6212546768437277`; CODE V imported EFL `3.62252`; import-vs-ingest deviation `0.035%`. | PASS for CODE V import; exported-ZMX comparison pending |
| Per-surface glass nd/vd | `zmx_ingest` source rows: S1 `1.544/55.9`, S4 `1.544/55.9`, S6 `1.639/23.5`, S8 `1.544/55.9`, S10 `1.639/23.5`, S12 `1.544/55.9`, S14 `1.535/55.7`, S16 `1.517/64.2`. | Baseline recorded; exported-ZMX comparison pending |
| 非球面系数项数 | `zmx_ingest` source has 15 asphere surfaces, S1-S15 each with 8 terms. CODE V `WRL` command export converted Zemax `EVENASPH` to CODE V `ASP` with A-H coefficient slots. | Baseline recorded; exported-ZMX comparison pending |
| VDX/VDY | Source ZMX carries `VDXN=(0,0,0)` and `VDYN=(0,0,0)`, normalized as `VDX=(0,0,0)` and `VDY=(0,0,0)`. CODE V `WRL` command export emitted zero Y vignetting rows (`VUY/VLY`). | Baseline recorded; exported-ZMX comparison pending |

## Test Coverage

- `tests/test_codev_roundtrip.py` covers sequence generation, mock CODE V TSV parsing, the four-gate ZMX comparison helper, report presence, and a real CODE V import smoke.
- The real CODE V smoke skips when `D:\CODEV115\codev.exe` is absent or license checkout is unavailable.
