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
- CODE V process return code was `1` after a complete ok result file; the readout path now accepts only `{0, 1}` after schema/status/required-key validation. Any other non-zero return code is a `CodeVBatchError(kind="failure")` even when TSV data exists.
- Readout: `num_surfaces=18`, `num_fields=3`, `field_type=ANG`, `stop_surface=3`, `image_height_y_mm=3.62257`, `aperture_type=FNO`, `f_number=2.32`, `entrance_pupil_diameter_mm=1.56143`.
- Wavelength readout from CODE V: `[(1, 0.656273, 1.0), (2, 0.587562, 1.0), (3, 0.486133, 1.0)]` in ZMX `WAVM` units/weights. Source ZMX carries 24 `WAVM` rows; CODE V imports the active three-line table, and the rebuilt ZMX writes those three true readout rows without adding defaults.
- Rebuilt artifact: `exported.zmx` parsed through existing `app/core/zmx_ingest.load_normalized_zmx`.
- `comparison.passed=True`.

## Fidelity Gates And Records

| Gate | Source vs rebuilt `exported.zmx` evidence | Status |
| --- | --- | --- |
| EFL deviation <2% | source EFL `3.6212546768437277`; rebuilt EFL `3.6212546768437393`; deviation `3.19e-13%`. | PASS |
| Per-surface glass nd/vd | S1 `1.544/55.9`, S4 `1.544/55.9`, S6 `1.639/23.5`, S8 `1.544/55.9`, S10 `1.639/23.5`, S12 `1.544/55.9`, S14 `1.535/55.7`, S16 `1.517/64.2`; no nd/vd mismatch. | PASS |
| 非球面系数项数 | Source and rebuilt ZMX both have 15 EVENASPH surfaces, S1-S15 each with 8 terms. Writer maps CODE V A..G to Zemax `PARM 2..8`, preserves reserved `PARM 1`, and rejects non-zero H/J rather than truncating r^18/r^20 terms. | PASS |
| VDX/VDY | Source `VDX=(0,0,0)`, `VDY=(0,0,0)`; rebuilt `VDX=(0,0,0)`, `VDY=(0,0,0)`. | PASS |
| VCX/VCY | Source `VCX=(0,0,0)`, `VCY=(0,0,0)`; rebuilt `VCX=(0,0,0)`, `VCY=(0,0,0)`. | PASS |
| Aperture/wavelength record | Source FNUM `2.32`; rebuilt FNUM `2.32`. Source wavelength rows `24`; rebuilt wavelength rows `3`, matching CODE V readout `num_wavelengths=3`. | RECORDED |

## Test Coverage

- `tests/test_codev_roundtrip_close.py` runs the real CODE V loop with no CODE V skip and asserts `comparison.passed`.
- Targeted verification: `PYTHONUTF8=1 uv run pytest tests/test_zmx_writer.py tests/test_codev_readout.py tests/test_codev_roundtrip_close.py tests/test_codev_batch.py -q` -> `26 passed`.
