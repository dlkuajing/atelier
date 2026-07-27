# Quick: Patent generic Family 77725725

**Status:** complete-shovel-saturation-incomplete
**Parent:** patent saturation engineering (active / incomplete)
**Started:** 2026-07-15
**Entry evidence:** strict 619/619 replay result set
`502722f70ef4f4478a991d642709120537d91c385a27e59c8a9b37e69f1bb104`, with
`generic_summary_metadata_missing` at 195 items/195 roots and no corrupt result.

## Objective

Resolve the tied-largest three-root official Family ID 77725725 using only retained source facts.
Determine the disclosure class before implementation; classify as no-prescription only if the
complete official text, drawings, and any tables prove absence of a surface prescription. Preserve
all prior results append-only and keep any ambiguity in parser review.

## Plan

1. Freeze the 195-item generic census and the exact three-root cohort.
2. Audit each official document independently for title, application/family bindings, table and
   drawing references, architecture counts, and all surface-prescription markers.
3. Add an exact-source classifier or parser only for facts published by all bound records; any
   source, layout, marker, or count drift must fail closed.
4. Replay all three roots append-only twice, compare canonical semantics excluding only retry
   identity, and audit all 619 roots.
5. Rebuild the generic after census twice; run explicit parser/replay/census/process/saturation
   tests, Ruff, and `git diff --check` with `PYTHONUTF8=1` and CODE V inventory zero.
6. Update STATE, decisions, and this plan with exact hashes and the next measured bucket. Parent
   saturation remains incomplete.

## Result

- The before census is byte-identical to the preceding shovel's after census: 195 items/195 roots,
  result set `502722f70ef4f4478a991d642709120537d91c385a27e59c8a9b37e69f1bb104`,
  SHA-256 `4aa52fede7442af380df0b15c0c7b2e0e307587da953ac3b5b7dd067569c6dce`.
- Exact official Family ID 77725725 records `US-11722760-B2`, `US-12088905-B2`, and
  `US-20230353852-A1` are independently bound to raw hashes
  `414e34d63d4331fa4caee23b523035adc9aa4805c7db23c10deb0ef0f6b96bcc`,
  `7242c9295f2f5c6ba76ac26061e7c59dec855b3c92466b0c1406222256bd3055`, and
  `3eca590960e69369b5474ffac654dc0b8597ff9563387efcd027feef3f0a3a24`; normalized hashes
  are `2e4280dbd1fbc1ece18329fa544e46f4feb53c639e141f1c4dd7a7a62d952712`,
  `ab9fcb48acc448ca03dccc35ebc0e10e302f9c87bba4766c208546a616d2131a`, and
  `ba8b3dc979f32ce054fc9fdd130eed90fc4a19a2049024287b8e98a10ac47b33`.
- Every source has exactly two formal sections. Example 1 publishes folded lens barrels, rolling
  bearings, magnets/coils, sensing elements, and only `d1/d2=1.4 mm` sensing-element axial
  distances. Example 2 publishes smartphone/image-sensor/multiple-camera architecture. The sole
  nonnumeric `focal length` occurrence describes combining different camera modules; no curvature,
  glass, asphere, EFL, F-number, Surface table, optical data, lens data, or prescription is present.
- Each root expands to two `confirmed_no_prescription` terminals and creates no worker, receipt, or
  ZMX. Attempts 2/3 are canonical-equal after excluding only `result_attempt`, with SHA-256 values
  `3c611fe3e0445937fe66318fee8cebb3a068e89cd9b526d59d5c1625d64bff5b`,
  `30dfa3cead7cb15f362cef91ed5ca9efe2c028dc65640cd07e8bedc0cceb607f`, and
  `9f31d773ec38d548733f483797d5330ac1e4fc0c1264b2fca868db4199cbfa3a`.
- The after census is 192 items/192 roots at result set
  `3d12a5b3ea27617286578ab122d3ee1f9a19f2720b3c8e097f538d90ca83beb6`; two builds are
  byte-identical at SHA-256
  `d9b439acdefac29a347d225baf2127cee2149bdc22fbdd97ea3915bb622f4bf7`.
  Full-pool audit is 619/619 with `corrupt=0`; summary/report SHA-256 values are
  `d22182571e3915cc58c66fefe5eadd7ffde7319028ad7e9995c6f05b7706e138` and
  `b4b7fd773c0a69967e034c5f91a40cc3b1afd2802c37faab73c4af6d80ee5071`.
- 247 focused tests, Ruff, and `git diff --check` pass with CODE V inventory zero. Generic summary
  remains the largest measured parser bucket at 192, ahead of Sunny at 187.
- Parent saturation remains incomplete: official-source exhaustion/family closure, remaining
  parser/trace/intake work, frozen-pool zero-yield replay, independent review, PR/CI, and
  incremental operation are still open.
