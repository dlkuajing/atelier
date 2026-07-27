# Patent saturation baseline

## Result

- saturation_complete: `false`
- snapshot_sha256: `c86527b71e0500074bf14e1668bc3ab6701e5d54d3d22ef5826686101d6b5ec1`
- pool_concat_sha256: `bba21147e576ee4674105884a95eb31b466b0f1aa6e8166e627dd9ba8867309e`
- case_index_sha256: `3845d04dff1a86048a3dc8552a3e815db0ac24d37ce8f38573660676cf50a441`

The snapshot is intentionally fail-closed. Existing formal patent ZMX/case files are recorded
as artifacts, but are not promoted to `intaken` until retained source/full-text and exact
embodiment provenance satisfy the stricter saturation contract.

## Recomputed inventory

- pool records / unique publications / unique roots: 714 /
  714 / 714
- formal designs / patent artifacts / patent roots: 442 /
  425 / 116
- raw/formal overlap roots: 95
- raw roots without formal artifact: 619
- formal roots outside raw pool: 21
- discovered union roots: 735
- known formal embodiments / legacy-unspecified: 425 /
  25
- retained raw documents: 0
- staging-only patent candidates: 0

## Terminal status counts

- `intaken`: 0
- `duplicate`: 0
- `quality_rejected`: 0
- `confirmed_no_prescription`: 0
- `fulltext_unavailable`: 0
- `parser_family_missing`: 0
- `metadata_unpublished`: 0
- `trace_failed`: 0
- `trace_timeout`: 0
- `externally_blocked`: 0

## Failing completeness checks

- `legacy_unspecified_embodiments:25`
- `roots_without_retained_fulltext:735`
- `unresolved_embodiment_outcomes:425`
- `unresolved_family_roots:735`
- `unresolved_root_outcomes:735`

This report is a baseline control-plane artifact, not saturation completion, an expert verdict,
or evidence of production usability.
