# P15 FNO 阶梯全矩阵 — 汇总（数据与分类，不下良品判定=[EXPERT] 红线）

| seed | dir | target F# | native 实测 | target_achieved | 爬到 | blocked | retry 触发/采纳 | 耗时(s) |
|---|---|---|---|---|---|---|---|---|
| US20210165194A1 | loosen | 2.4 | 2.0 | True | rung3 | False | 1/1 | 76 |
| US20170003482A1 | loosen | 2.4 | 2.319990518229984 | True | rung3 | False | 0/0 | 43 |
| US8908290B1 | loosen | 2.4 | 1.9999949371190182 | True | rung3 | False | 3/3 | 81 |
| US-11940597-B2-e6 | loosen | 4.0 | 3.5699949915436937 | False | rung3 | False | 3/0 | 74 |
| US-12443014-B2-e1 | loosen | 4.0 | 2.8000038789947586 | False | rung3 | False | 4/0 | 197 |
| US-12372756-B2-e8 | loosen | 4.0 | 2.4500027018927986 | False | rung3 | False | 4/0 | 47 |
| US10281683B2 | loosen | 3.0 | 1.6799984272120905 | False | rung3 | False | 4/1 | 313 |
| US20140111876A1 | loosen | 3.0 | 2.07000163220085 | False | rung3 | False | 4/0 | 180 |
| US10330891B2 | loosen | 2.4 | 2.080002754560088 | False | rung3 | False | 4/0 | 182 |
| US20170003482A1 | tighten | 2.0 | 2.319990518229984 | True | rung3 | False | 1/1 | 68 |
| US8908290B1 | tighten | 1.8 | 1.9999949371190182 | True | rung3 | False | 4/4 | 95 |
| US20210165194A1 | tighten | 1.8 | 2.0 | False | rung2 | False | 3/3 | 248 |
| US-11940597-B2-e6 | tighten | 2.0 | 3.5699949915436937 | False | rung3 | False | 4/0 | 72 |
| US20180143405A1 | loosen | 2.4 | None | False | rungNone | True | 0/0 | 180 |

- target_achieved: 5/14（分母含 error ladder）
- ladder 完整产出: 14/14
- per-seed 明细：各子目录 ladder-result.json（per-rung 双维记录 + ray_retry 轨迹） + per-rung seq/tsv/lis 全文。
- 口径：measured_fnum=EFL_real/EPD_real 活算；RMS/WFE 若在裁瞳（effective_edge_used>0）上测=偏乐观，须连列读；ray-retry 采纳格详见各 rung ray_retry.quality_note。
