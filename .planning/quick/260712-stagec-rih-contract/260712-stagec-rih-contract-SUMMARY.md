# Stage C RIH machine contract — summary

## Delivered

- Bumped the synthetic machine readback/evidence boundary to v2 and requires exact
  `TYP FLD=RIH`; `IMG`, `ANG`, lowercase aliases, and legacy schemas fail closed.
- Separated the raw RIH field definition (`XRI`/`YRI`) from RSI chief-ray actual
  `X`/`Y`, direction cosines `L`/`M`/`N`, and raw `RAYRSI` return, `RER`, and `BLS`.
  Ray classification is now computed from those raw outcomes and cannot be supplied.
- Replaced the caller-filled builder with a closed parser over six raw byte artifacts:
  listing, metrics TSV, source ZMX, reconstructed ZMX, sequence, and manifest. Fields,
  measured EFL, counts, config, and vignetting are derived only from parsed bytes.
- Implemented a future-runner-compatible hash DAG: the sequence is generated from
  pre-known run/source/reconstruction/config identity; the manifest binds its SHA;
  listing and metrics repeat only pre-known identity; the final readback envelope binds
  all actual bytes. Raw CODE V outputs never need to predict their own or later hashes.
- Listing parsing requires exactly one complete Stage C run across the whole file,
  ordered per-field begin/ok/end records, exact metadata, and no unknown/error record.
  Rejections carry a stable `MachineListingFailure` category.
- Metrics use a closed, versioned TSV schema with strict UTF-8, unique metadata,
  contiguous unique fields, finite numerics, and exact RIH. Per-field raw
  `VUY`/`VLY`/`VUX`/`VLX` are retained independently; the current zero-only gate is
  derived from all four values at every field.
- Restore reparses retained artifacts and ignores serialized structured facts or gate
  booleans. A `model_copy` mutation cannot acquire authority because the gate reparses
  and compares the six retained artifacts.
- Candidate/export fixtures now use conforming synthetic raw contracts. Negative tests
  cover arbitrary bytes, all six artifact mutations, stale/foreign/truncated listings,
  legacy/duplicate TSV records, IMG/ANG impersonation, definition/actual separation,
  raw ray failures/blocks, non-zero vignetting, model-copy mutation, and strict restore.

## Independent-review correction

- The v2 contract is explicitly parser-only: without a real runner/host attestation it
  always reports `machine_execution_status=parsed-unverified`; IMH, EFL, ray, chief-ray,
  and `image_height_achieved` machine gates remain false. Only the independently
  validated offline reconstruction gate may be true. No self-reported receipt was added.
- Added an exact controlled sequence identity preamble for run ID, source/reconstructed
  SHA, and config fingerprint. The manifest binds the complete sequence SHA, while old
  listing/metrics bytes reject a paired sequence+manifest identity swap.
- Whole-listing marker discovery now catches leading-whitespace, foreign, and partial
  Stage C markers. Listing encoding, syntax, and field-index failures are normalized to
  stable `MachineListingFailure` categories.
- Restore now requires exact outer evidence v2, `evidence_kind=machine`, and readback v2;
  legacy records cannot be silently upgraded. Duplicate manifest JSON keys remain fatal.
- Workbook/bundle tests prove parsed synthetic facts never export a verified machine
  execution or achieved IMH. A real attested schema remains deferred to the verified
  probe/runner slice.
- Second-review cleanup removed the last local verified wording from v2 vignetting:
  classifications are now `zero-parsed-unverified` and
  `nonzero-parsed-unverified`. Model JSON, workbook status columns, and bundle README
  tests forbid verified machine/vignetting/chief-ray/RSI states; only the separately
  allowlisted offline reconstruction status may remain `constructed-verified`.

## Explicitly not implemented

- No CODE V process, probe, runner, matrix, production wiring, or claimed real syntax.
- No non-zero-vignetting interpretation; only the proven zero profile can pass.
- No optical qualification or `[EXPERT]` verdict.

## Verification

- `PYTHONUTF8=1 uv run pytest tests/test_stagec_field.py tests/test_orchestration_export.py -k "not real" -q`
- `uv run ruff check app/core/engines/stagec_field.py app/core/orchestration/candidate.py app/core/orchestration/export.py tests/test_stagec_field.py tests/test_orchestration_export.py`
- `git diff --check`
