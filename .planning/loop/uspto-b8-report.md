# DATA-08b USPTO batch8 report

Date: 2026-07-07

Output: `data/patents/uspto-smartphone-batch8.jsonl`

## Summary

- Script path used: `scripts/patent_crawler.py`
- Source: USPTO Patent Public Search anonymous API
- Mode: calibrated IPC sweep (`--ipc-sweep`)
- Limit: 60
- Old pool checked for dedupe/quota: batch1-7, 354 records
- New records written: 60
- Full pool after batch8: 414 records
- Global ID duplicates after batch8: 0

## Crawler Stats

Structured log source: `.planning/loop/uspto-b8-crawl.out`

| Metric | Count | Notes |
|---|---:|---|
| Parsed candidates seen by pool filter | 135 | Candidates that passed USPTO fetch/parse and entered pool filtering |
| Accepted records written | 60 | Exactly the requested limit; no expanded sampling |
| Accepted rate | 44.4% | 60 / 135 |
| 10/100 baseline | 10.0% | Baseline accepted rate |
| Lift vs baseline | 4.4x | 44.4% / 10.0% |
| Exact patent ID duplicates skipped | 9 | Already present in batch1-7 or current run |
| Family hints tagged | 37 | Near-family records kept and marked, not skipped |
| Family duplicate skipped | 0 | Calibrated behavior: tag instead of skip |
| Assignee quota skipped | 61 | Rejected to keep single-assignee share under quota |

## Failure Reasons

| Category | Count | Stage | Evidence |
|---|---:|---|---|
| Assignee quota | 61 | pool filter | `assignee_quota_skipped=61` |
| Exact patent ID duplicate | 9 | pool filter | `id_duplicate_skipped=9` |
| Missing assignee schema | 9 | parse | `PatentRecordSchemaError: assignee must be non-empty` |
| USPTO request error | 2 | fetch | `ConnectError('')`, classified as `request_error` |

Notes:

- Batch8 contains 60 JSONL rows, so DATA-08b stayed within the strict `<=60` cap.
- Pool size moved from 354 to 414, matching the updated `tests/test_patent_pool.py` threshold.
- The crawler reached the target despite eleven record-level fetch/parse failures; those failed records were not written.
