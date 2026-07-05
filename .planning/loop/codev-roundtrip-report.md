# ENGINE-04c CODE V ZMX Roundtrip Closure Report

Date: 2026-07-05

## Scope

- Selected patent seed: `data/zmx/US20170003482A1.zmx`
- CODE V executable: `D:\CODEV115\codev.exe` (11.5, see `codev-probe-report.md`)
- Import macro: `IN CV_MACRO:ZEMAXOS_TO_CV "<seed.zmx>"`
- Readout path: `app/core/engines/codev_readout.py` schema `atelier-codev-readout-v1`
- Rebuild path: `app/core/engines/zmx_writer.py` writes ASCII/CRLF Zemax text
- Comparison path: `app.core.engines.codev_roundtrip.compare_roundtrip_zmx`

## Result

PASS. ENGINE-04c closes the Phase 5 roundtrip gap through CODE V database readout
and self-authored ZMX rebuild:

`US20170003482A1.zmx -> CODE V import -> 04a readout TSV -> 04b exported.zmx -> zmx_ingest compare`

Observed run facts:

- CODE V batch wrote a complete `atelier-codev-readout-v1` TSV with `status=ok`.
- CODE V process return code was `1` after a complete ok result file; the readout path treats this CODE V 11.5 behavior as acceptable only when the explicit result file passes schema, status, and required-key validation.
- Readout: `num_surfaces=18`, `num_fields=3`, `field_type=ANG`, `stop_surface=3`, `image_height_y_mm=3.62257`.
- Rebuilt artifact: `exported.zmx` parsed through existing `app/core/zmx_ingest.load_normalized_zmx`.
- `comparison.passed=True`.

## Four Fidelity Gates

| Gate | Source vs rebuilt `exported.zmx` evidence | Status |
| --- | --- | --- |
| EFL deviation <2% | source EFL `3.6212546768437277`; rebuilt EFL `3.6212546768437393`; deviation `3.19e-13%`. | PASS |
| Per-surface glass nd/vd | S1 `1.544/55.9`, S4 `1.544/55.9`, S6 `1.639/23.5`, S8 `1.544/55.9`, S10 `1.639/23.5`, S12 `1.544/55.9`, S14 `1.535/55.7`, S16 `1.517/64.2`; no nd/vd mismatch. | PASS |
| 非球面系数项数 | Source and rebuilt ZMX both have 15 EVENASPH surfaces, S1-S15 each with 8 terms. Writer maps CODE V A..G to Zemax `PARM 2..8` and preserves reserved `PARM 1`. | PASS |
| VDX/VDY | Source `VDX=(0,0,0)`, `VDY=(0,0,0)`; rebuilt `VDX=(0,0,0)`, `VDY=(0,0,0)`. | PASS |

## Test Coverage

- `tests/test_codev_roundtrip_close.py` runs the real CODE V loop with no CODE V skip and asserts `comparison.passed`.
- Targeted verification: `PYTHONUTF8=1 .\.venv\Scripts\python.exe -m pytest -q tests/test_codev_roundtrip_close.py` -> `1 passed`.
