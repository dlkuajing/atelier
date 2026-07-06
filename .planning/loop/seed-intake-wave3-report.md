# DATA-06f seed intake wave 3 report

## Status

- verdict: promoted
- source conversion report: `.planning/loop/patent2zmx-wave3-report.md`
- source cursor: `data/patents/convert-cursor.json`
- source staging directory: `data/zmx-staging/DATA-06f`
- promoted ZMX directory: `data/zmx`

## Source Facts

| evidence | value |
|---|---:|
| DATA-06f patent candidates attempted | 80 |
| DATA-06f embodiment attempts | 248 |
| DATA-06f successful ZMX artifacts | 39 |
| DATA-06f failed embodiment attempts | 209 |
| DATA-06f patent candidate hits | 9 |
| files in `data/zmx-staging/DATA-06f` | 39 |

All 39 successful staging artifacts carry positive `ATELIER_REAL_IMH_MM` tail
comments. The promoted manifest records those real-traced image heights as
`image_height_source: ATELIER_REAL_IMH_MM`.

## Intake Actions

| step | outcome |
|---|---|
| Promote DATA-06f ZMX into `data/zmx/` | copied/verified 39 ZMX files |
| Add wave manifest | wrote `tests/data/data06f_manifest.json` with 39 entries |
| Persist real-traced IMH | extended `tests/data/seed_imh_overrides.json` to 78 anchored entries |
| Regenerate case index | `app/data/optical_cases/index.json` now has 145 cases |
| Generate case payloads | added 39 `app/data/optical_cases/US-*.json` payloads |
| Regenerate eval golden | `tests/data/eval_golden.json` now covers 145 case-library reanchors |
| Seed-intake audit semantics | DATA-06 lightweight gate now accepts 106/106 converted seeds |

## Library Delta

| asset | before | after | delta |
|---|---:|---:|---:|
| `tests.data.zmx_manifest.ZMX_AMMO` | 106 | 145 | +39 |
| `app/data/optical_cases/index.json` cases | 106 | 145 | +39 |
| DATA-06 converted manifest entries | 67 | 106 | +39 |
| DATA-06f promoted seeds | 0 | 39 | +39 |

## Seed-Intake Audit Snapshot

| metric | value |
|---|---:|
| total visible phone seeds | 145 |
| high-FOV seeds | 29 |
| full-field seeds | 19 |
| accepted high-FOV full-field seeds | 0 |
| lightweight DATA-06 accepted seeds | 106/106 |

The targeted high-FOV acquisition probe still reports `gap`: wave3 increases
the library scale, but does not add a seed that simultaneously satisfies the
EFL/F-number/image-height/element/full-field window.

## Verification

- `PYTHONUTF8=1 ./.venv/Scripts/python.exe -m pytest -q tests/test_zmx_ingest.py tests/test_case_library.py tests/test_eval_golden_seeds.py tests/test_seed_intake_audit.py`
- Result: 455 passed.

## Follow-up

DATA-06g should continue from the DATA-06f cursor after `US-12298484-B2` and
convert the next <=80 remaining candidates.

## Batch 11 review fix addendum

- material repair promoted: `US-12541079-B2-e2.zmx` and
  `US-12541079-B2-e5.zmx` were regenerated from USPTO PPUBS full text after the
  three-column material parser fix. Their case JSON, `index.json`, manifest
  entries, IMH overrides, and eval golden anchors were refreshed.
- corrected material aperture: e2 lens rows now use `nd=1.669/vd=19.5` and e5
  lens rows use `nd=1.660/vd=20.4`; both use filter `nd=1.517/vd=64.2`.
- missed cursor backfill: the prior staging-based skip漏掉
  `US-20240201471-A1` and `US-20240192468-A1`. After switching skip policy to
  formal case-index membership only, 12 successful ZMX artifacts were promoted:
  `US-20240201471-A1-e1`..`e11` plus `US-20240192468-A1-e1`.
- failed backfill embodiment: `US-20240192468-A1-e2` timed out during Optiland
  real-ray aperture tracing; only `.trace-tmp` existed, so it was not promoted.
- post-fix library size: `tests.data.zmx_manifest.ZMX_AMMO` and
  `app/data/optical_cases/index.json` now contain 157 cases; DATA-06 converted
  seeds now total 118.
- physical guard scan: 145 formal ZMX files scanned after material repair and
  157 formal ZMX files scanned after backfill; both scans found 0 nd/vd
  violations.
