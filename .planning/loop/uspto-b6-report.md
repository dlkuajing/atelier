# DATA-05c USPTO batch6 diversity report

Date: 2026-07-06

Output: `data/patents/uspto-smartphone-batch6.jsonl`

## Summary

- Script path used: `scripts/patent_crawler.py` CLI and USPTO PPUBS helpers (`_ppubs_search_docs`, `_ppubs_patent_html`, `_ppubs_record_from_doc`), followed by local batch1-5 ID dedupe and assignee/quality filtering.
- Source: USPTO Patent Public Search anonymous API.
- Query direction: non-Largan assignee targeting via PPUBS assignee/applicant keyword field `AANM` plus lens-title constraints. Short `.AS.` probes returned broad single-token hits but were unstable for full assignee phrases, so the accepted batch uses parsed body `Assignee` as the final truth.
- Old pool checked for dedupe: batch1-5, 224 records.
- New records written: 65.
- Full pool after batch6: 289 records.
- Global ID duplicates after batch6: 0.
- Batch6 overlap with batch1-5: 0.
- 3P-8P lens-count / prescription hits in batch6: 65/65 = 100.0%.
- 去重数: 63 old batch1-5 IDs appeared in the used crawler outputs and were skipped; 0 in-run duplicate IDs were skipped.

## Largan Share Check

| Pool | Records | Largan records | Largan share |
|---|---:|---:|---:|
| Before batch6 (batch1-5) | 224 | 128 | 57.1% |
| Batch6 only | 65 | 0 | 0.0% |
| After batch6 (batch1-6) | 289 | 128 | 44.3% |

Largan full-pool share decreased from 57.1% to 44.3%.

## Query Stats

| 查询词 | Crawler limit | Records fetched | Old-pool dedupe | New candidates | Accepted | Assignee rejects | Quality rejects | Cap skips | 命中率 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `((Samsung).AANM. AND (imaging ADJ lens).TI.)` | 18 | 18 | 3 | 15 | 14 | 0 | 0 | 1 | 93.3% |
| `((Zhejiang).AANM. AND (optical ADJ imaging ADJ lens ADJ assembly).TI.)` | 30 | 30 | 24 | 6 | 6 | 0 | 0 | 0 | 100.0% |
| `((Sunny).AANM. AND (lens ADJ group).TI.)` | 24 | 24 | 2 | 22 | 12 | 1 | 0 | 9 | 54.5% |
| `((Genius).AANM. AND (optical ADJ imaging ADJ lens).TI.)` | 18 | 18 | 6 | 12 | 6 | 0 | 6 | 0 | 50.0% |
| `((Genius).AANM. AND (optical ADJ lens).TI.)` | 24 | 24 | 2 | 22 | 8 | 1 | 3 | 10 | 36.4% |
| `((AAC).AANM. AND (camera ADJ optical ADJ lens).TI.)` | 22 | 22 | 21 | 1 | 0 | 0 | 1 | 0 | 0.0% |
| `((AAC).AANM. AND (lens ADJ assembly).TI.)` | 19 | 19 | 0 | 19 | 2 | 0 | 2 | 15 | 10.5% |
| `((Kantatsu).AANM. AND (imaging ADJ lens).TI.)` | 24 | 24 | 5 | 19 | 15 | 1 | 0 | 3 | 78.9% |
| `((Newmax).AANM. AND (optical ADJ imaging ADJ lens).TI.)` | 4 | 4 | 0 | 4 | 2 | 0 | 0 | 2 | 50.0% |
| `((Sekonix).AANM. AND (optical ADJ system).TI.)` | 4 | 4 | 0 | 4 | 0 | 0 | 0 | 4 | 0.0% |

## Batch6 Target Family Distribution

| Family | Batch6 records |
|---|---:|
| sunny | 18 |
| kantatsu | 15 |
| samsung | 14 |
| genius | 14 |
| aac | 2 |
| newmax | 2 |

## Batch6 Assignee Distribution

| Assignee | Batch6 records |
|---|---:|
| KANTATSU CO., LTD. | 13 |
| Samsung Electro-Mechanics Co., Ltd. | 10 |
| ZHEJIANG SUNNY OPTICS CO., LTD. | 7 |
| Genius Electronic Optical (Xiamen) Co., Ltd. | 7 |
| GENIUS ELECTRONIC OPTICAL (XIAMEN) CO., LTD. | 7 |
| Zhejiang Sunny Optics Co., Ltd | 6 |
| SAMSUNG ELECTRO-MECHANICS CO., LTD. | 3 |
| Zhejiang Sunny Optics Co., Ltd. | 2 |
| Changzhou AAC Raytech Optronics Co., Ltd. | 2 |
| Kantatsu Co., Ltd. | 2 |
| NEWMAX TECHNOLOGY CO., LTD. | 2 |
| SAMSUNG ELECTRO-MECHANICS CO., LTD | 1 |
| ZHEJIANG SUNNY OPTICS CO., LTD | 1 |
| ZHEJIANG SUNNY OPTICAL, CO., LTD | 1 |
| ZHEJIANG SUNNY OPTICAL CO., LTD | 1 |

## Full Pool Top Assignees After Batch6

| Assignee | Full pool records after batch6 |
|---|---:|
| LARGAN PRECISION CO., LTD. | 125 |
| Changzhou AAC Raytech Optronics Co., Ltd. | 27 |
| ZHEJIANG SUNNY OPTICS CO., LTD. | 23 |
| KANTATSU CO., LTD. | 18 |
| Samsung Electro-Mechanics Co., Ltd. | 13 |
| Zhejiang Sunny Optics Co., Ltd | 12 |
| Genius Electronic Optical (Xiamen) Co., Ltd. | 12 |
| GENIUS ELECTRONIC OPTICAL (XIAMEN) CO., LTD. | 10 |
| SAMSUNG ELECTRO-MECHANICS CO., LTD. | 9 |
| Zhejiang Sunny Optics Co., Ltd. | 6 |
| AAC OPTICS (CHANGZHOU) CO., LTD. | 5 |
| SEKONIX CO., LTD. | 5 |
| AAC Optics (Suzhou) Co., Ltd. | 4 |
| ZHEJIANG SUNNY OPTICS CO., LTD | 2 |
| Maxell, Ltd. | 2 |
| Kantatsu Co., Ltd. | 2 |
| NEWMAX TECHNOLOGY CO., LTD. | 2 |
| Zhejiang Sunny Optical Co., Ltd | 1 |

Notes:

- Accepted records were schema-validated through `validate_patent_record` and retained only when parsed `Assignee` matched a non-Largan target family and the title/body contained lens prescription signals such as focal length, curvature radius, refractive power, Abbe number, aspheric surfaces, lens elements, optical axis, image plane, field-of-view, or aperture constraints.
- Query hit rate is `accepted / new candidates` after batch1-5 and in-run dedupe. `Cap skips` are otherwise acceptable records left out to keep batch6 distributed across assignees.
- Sekonix was probed as requested, but the available PPUBS hits were head-mounted-display optical-system records, so no Sekonix record was accepted into this smartphone-lens batch.
