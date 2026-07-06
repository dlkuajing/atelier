# DATA-05d USPTO batch7 diversity report

Date: 2026-07-06

Output: `data/patents/uspto-smartphone-batch7.jsonl`

## Summary

- Script path used: `scripts/patent_crawler.py` USPTO PPUBS helpers (`_ppubs_search_docs`, `_ppubs_patent_html`, `_ppubs_record_from_doc`) plus `validate_patent_record`, followed by local batch1-6 ID dedupe and assignee/quality filtering.
- Source: USPTO Patent Public Search anonymous API.
- Query direction: non-Largan assignee targeting, extending batch6 with Sekonix, Ability, AAC, Newmax, OFILM/Jiangxi, Fujifilm, plus an IPC G02B13 wide-angle probe.
- Old pool checked for dedupe: batch1-6, 289 records.
- New records written: 65.
- Full pool after batch7: 354 records.
- Global ID duplicates after batch7: 0.
- Batch7 overlap with batch1-6: 0.
- Batch7 Largan records: 0.
- Batch7 G02B13 records: 59/65.
- Batch7 records mentioning large aperture or wide-angle in abstract/claims: 20/65.
- 去重数: 86 old batch1-6 ID appearances were skipped across the used USPTO result pages; final accepted batch7 IDs have 0 overlap with earlier batches.

## Largan Share Check

| Pool | Records | Largan records | Largan share |
|---|---:|---:|---:|
| Before batch7 (batch1-6) | 289 | 128 | 44.3% |
| Batch7 only | 65 | 0 | 0.0% |
| After batch7 (batch1-7) | 354 | 128 | 36.2% |

Largan full-pool share decreased from 44.3% to 36.2%; it did not rebound.

## Query Stats

Accepted uses first-query attribution, so IDs returned by multiple queries are counted once.

| 查询词 | Crawler limit | USPTO docs | Old-pool dedupe | Final records returned by query | Accepted | 命中率 |
|---|---:|---:|---:|---:|---:|---:|
| `((Sekonix).AANM. AND (small ADJ lens ADJ system).TI.)` | 40 | 19 | 4 | 12 | 12 | 80.0% |
| `((Sekonix).AANM. AND (lens ADJ system).TI.)` | 50 | 39 | 5 | 12 | 0 | 0.0% |
| `((Ability).AANM. AND (optical ADJ lens).TI.)` | 60 | 42 | 0 | 14 | 14 | 33.3% |
| `((Ability).AANM. AND (imaging ADJ lens).TI.)` | 50 | 29 | 1 | 0 | 0 | 0.0% |
| `((AAC).AANM. AND (optical ADJ lens).TI.)` | 70 | 70 | 36 | 18 | 18 | 52.9% |
| `((AAC).AANM. AND (camera ADJ optical ADJ lens).TI.)` | 100 | 100 | 36 | 11 | 0 | 0.0% |
| `((AAC).AANM. AND (lens ADJ assembly).TI.)` | 40 | 19 | 2 | 0 | 0 | 0.0% |
| `((Newmax).AANM. AND (optical ADJ lens).TI.)` | 70 | 70 | 0 | 11 | 11 | 15.7% |
| `((Newmax).AANM. AND (imaging ADJ lens).TI.)` | 20 | 6 | 2 | 0 | 0 | 0.0% |
| `((OFILM).AANM. AND (optical ADJ lens).TI.)` | 30 | 8 | 0 | 7 | 7 | 87.5% |
| `((Jiangxi).AANM. AND (optical ADJ lens).TI.)` | 60 | 31 | 0 | 8 | 1 | 3.2% |
| `((Fujifilm).AANM. AND (wide ADJ angle ADJ lens).TI.)` | 40 | 24 | 0 | 2 | 2 | 8.3% |
| `((G02B13/00.CPC.) AND (wide ADJ angle ADJ lens).TI.)` | 20 | 12 | 0 | 0 | 0 | 0.0% |

The generic G02B13 wide-angle probe was retained as a coverage check. No generic non-assignee record was accepted from it because the targeted assignee queries already supplied 59 G02B13 records with better smartphone/module fit.

## Replacement Pass

After the first 65-record pass, 5 records with off-target title signals (`capsule`, `endoscope`, or `head-mounted`) were removed and replaced with AAC `CAMERA OPTICAL LENS` records from the same USPTO query family:

| Removed ID | Reason |
|---|---|
| `US-20260093108-A1` | capsule endoscope title |
| `US-12607854-B2` | head-mounted title |
| `US-12607837-B2` | head-mounted title |
| `US-12504641-B2` | head-mounted title |
| `US-20260086325-A1` | endoscope title |

## Batch7 Target Family Distribution

| Family | Batch7 records |
|---|---:|
| AAC / Raytech | 18 |
| Ability | 14 |
| Sekonix | 12 |
| Newmax / Neoptic | 11 |
| OFILM / Jiangxi | 8 |
| Fujifilm | 2 |

## Batch7 Assignee Distribution

| Assignee | Batch7 records |
|---|---:|
| SEKONIX CO., LTD. | 12 |
| ABILITY ENTERPRISE CO., LTD. | 11 |
| Changzhou AAC Raytech Optronics Co., Ltd. | 11 |
| NEWMAX TECHNOLOGY CO., LTD. | 10 |
| ABILITY ENTERPRISE CO., LTD | 3 |
| AAC OPTICS (CHANGZHOU) CO., LTD. | 3 |
| AAC Optics (Suzhou) Co., Ltd. | 3 |
| Jiangxi OFILM Optical Co.,Ltd. | 3 |
| Jiangxi OFILM Optical Co., Ltd. | 2 |
| OFILM GROUP CO., LTD. (Shenzhen, CN); JIANGXI JINGCHAO OPTICAL CO., LTD. | 2 |
| FUJIFILM Corporation | 2 |
| DONGGUAN NEOPTIC CO., LTD. (Guangdong Province, CN); NEWMAX TECHNOLOGY CO., LTD. | 1 |
| Jiangxi OFLM Optical Co., Ltd. | 1 |
| AAC Optics (Changzhou) Co., Ltd. | 1 |

## Full Pool Assignee Distribution After Batch7

| Assignee | Full pool records |
|---|---:|
| LARGAN PRECISION CO., LTD. | 125 |
| Changzhou AAC Raytech Optronics Co., Ltd. | 38 |
| ZHEJIANG SUNNY OPTICS CO., LTD. | 23 |
| KANTATSU CO., LTD. | 18 |
| SEKONIX CO., LTD. | 17 |
| Samsung Electro-Mechanics Co., Ltd. | 13 |
| Zhejiang Sunny Optics Co., Ltd | 12 |
| Genius Electronic Optical (Xiamen) Co., Ltd. | 12 |
| NEWMAX TECHNOLOGY CO., LTD. | 12 |
| ABILITY ENTERPRISE CO., LTD. | 11 |
| GENIUS ELECTRONIC OPTICAL (XIAMEN) CO., LTD. | 10 |
| SAMSUNG ELECTRO-MECHANICS CO., LTD. | 9 |
| AAC OPTICS (CHANGZHOU) CO., LTD. | 8 |
| AAC Optics (Suzhou) Co., Ltd. | 7 |
| Zhejiang Sunny Optics Co., Ltd. | 6 |
| FUJIFILM Corporation | 3 |
| ABILITY ENTERPRISE CO., LTD | 3 |
| Jiangxi OFILM Optical Co.,Ltd. | 3 |
| ZHEJIANG SUNNY OPTICS CO., LTD | 2 |
| Maxell, Ltd. | 2 |
| Kantatsu Co., Ltd. | 2 |
| Jiangxi OFILM Optical Co., Ltd. | 2 |
| OFILM GROUP CO., LTD. (Shenzhen, CN); JIANGXI JINGCHAO OPTICAL CO., LTD. | 2 |
| Zhejiang Sunny Optical Co., Ltd | 1 |
| Sunny Optics(Zhongshan)Co., Ltd. | 1 |
| LARGAN INDUSTRIAL OPTICS CO., LTD. | 1 |
| LARGAN PRECISION CO.,LTD. | 1 |
| Largan Precision Co., Ltd. | 1 |
| GUANGDONG OPPO MOBILE TELECOMMUNICATIONS CORP., LTD. | 1 |
| ABILITY OPTO-ELECTRONICS TECHNOLOGY CO., LTD. | 1 |
| SAMSUNG ELECTRONICS CO., LTD. | 1 |
| SAMSUNG ELECTRO-MECHANICS CO., LTD | 1 |
| ZHEJIANG SUNNY OPTICAL, CO., LTD | 1 |
| ZHEJIANG SUNNY OPTICAL CO., LTD | 1 |
| DONGGUAN NEOPTIC CO., LTD. (Guangdong Province, CN); NEWMAX TECHNOLOGY CO., LTD. | 1 |
| Jiangxi OFLM Optical Co., Ltd. | 1 |
| AAC Optics (Changzhou) Co., Ltd. | 1 |

Notes:

- Accepted records were schema-validated through `validate_patent_record`.
- Records were retained only when parsed `Assignee` matched a non-Largan target family and title/body contained lens prescription signals such as refractive power, focal length, curvature radius, center thickness, TTL, f-number, image plane, aspheric surfaces, or serial lens-element language.
- Query hit rate is `Accepted / (USPTO docs - Old-pool dedupe)` after batch1-6 dedupe, with first-query attribution for overlapping result pages.
