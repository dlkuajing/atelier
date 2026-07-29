# Patent saturation baseline

## Result

- saturation_complete: `false`
- snapshot_sha256: `5dcebb2008cc8f1430c66bf85b5c068800b35212195de128315b3f3ea4feed1d`
- pool_concat_sha256: `bba21147e576ee4674105884a95eb31b466b0f1aa6e8166e627dd9ba8867309e`
- case_index_sha256: `1f7f8f73b92a99a0de53e5462203dc9ff8fe2d518016981b7fa6515cc164b735`

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
- staging-only patent candidates: 613

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
- `staging_patent_candidates:613`
- `unresolved_embodiment_outcomes:425`
- `unresolved_family_roots:735`
- `unresolved_root_outcomes:735`

This report is a baseline control-plane artifact, not saturation completion, an expert verdict,
or evidence of production usability.
