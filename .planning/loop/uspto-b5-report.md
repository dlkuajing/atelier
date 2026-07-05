# DATA-05b USPTO batch5 report

Date: 2026-07-05

Output: `data/patents/uspto-smartphone-batch5.jsonl`

## Summary

- Script path used: `scripts/patent_crawler.py` USPTO PPUBS helpers (`_ppubs_search_docs`, `_ppubs_patent_html`, `_ppubs_record_from_doc`) with local batch1-4 dedupe before body fetch
- Source: USPTO Patent Public Search anonymous API
- Old pool checked for dedupe: batch1-4, 159 records
- New records written: 65
- Full pool after batch5: 224 records
- Global ID duplicates after batch5: 0
- 3P-7P keyword hits in batch5: 64/65 = 98.5%
- 去重数: 33 old batch1-4 IDs appeared in the used USPTO result pages and were skipped; 0 accepted batch5 IDs overlap with earlier batches

## Query Stats

| 查询词 | USPTO docs returned | Processed old-pool dedupe | New result-page candidates | Accepted into batch5 | 命中率 |
|---|---:|---:|---:|---:|---:|
| `(optical ADJ lens ADJ system).TI.` | 50 | 1 | 49 | 26 | 53.1% |
| `(image ADJ lens ADJ assembly).TI.` | 50 | 5 | 45 | 21 | 46.7% |
| `(imaging ADJ lens ADJ assembly).TI.` | 50 | 24 | 26 | 3 | 11.5% |
| `((G02B13/00.CPC.) AND (imaging ADJ lens).TI.)` (stopped at target) | 50 | 3 | 47 | 15 | 31.9% |

Notes:

- Batch5 deliberately avoids the two batch4 title queries: `(photographing ADJ optical ADJ lens ADJ assembly).TI.` and `(camera ADJ optical ADJ lens).TI.`.
- Queries expand coverage through title variants plus the CPC dimension while staying on USPTO Patent Public Search.
- The table attributes final accepted IDs to the first USPTO result-page query that returned them. Hit rate is `accepted / new result-page candidates` after batch1-4 dedupe.
- Accepted records were schema-validated and filtered for camera/electronic-device lens wording plus optical prescription signals such as focal length, curvature radius, central thickness, refractive index, Abbe number, aspheric surfaces, refractive power, aperture stop, or conditional expressions.
