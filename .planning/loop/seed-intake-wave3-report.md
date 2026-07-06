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
