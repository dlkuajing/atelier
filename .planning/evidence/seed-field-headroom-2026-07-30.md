# Seed 视场余量：不是「问 seed 要它做不到的视场」（2026-07-30）

## 要否掉的假设

phase-1 批跑前 10 条里 8 条 `unmeasurable`，形状全是**候选在离轴不成像**
（`rms_fields_ok=1/2`、`mtf_fields_ok=0/2`，而对照 `2/2`）。
最省事的解释是「视场重标把 seed 推到了它做不到的角度」。

**这个解释是错的。** 零计算就能证伪 —— 只读 ZMX 的 `YFLN`，不追迹。

## 实测（49 条计划全覆盖）

「plan 向 seed 要的角度」÷「seed 自身原生最大角度」：

| | |
|---|---|
| min | **0.730** |
| p25 | 0.865 |
| **median** | **0.925** |
| p75 | 0.959 |
| max | 1.339 |

| 门槛 | 条数 |
|---|---|
| > 1.0× 原生 | **7/49** |
| > 1.1× | **1/49** |
| > 1.2× | 1/49 |
| > 1.5× | 0/49 |

⇒ **绝大多数 trial 问 seed 要的是比它原生更小的视场。** 中位是 0.925，即少要 7.5%。

## 逐 seed（顺带把样本集中度钉住）

| seed | 原生最大角 | trial 数 | 要求比 min / med / max |
|---|---|---|---|
| `US-12044826-B2-e4` | 41.60° | **41** | 0.84 / 0.93 / 1.08 |
| `US-20260063869-A1-e3` | 18.35° | 4 | 0.73 / 0.76 / 0.78 |
| `US-11668898-B2-e6` | 45.10° | 2 | 1.08 / 1.08 / 1.08 |
| `US-12282142-B2-e7` | 39.90° | 1 | 1.04 |
| `US-12436366-B2-e10` | 13.70° | 1 | **1.34** |

**一颗 seed 设计承担 41/49 = 84% 的 trial。** 这比 memory 里按公开号算的
「top-5 占 59.3%」更集中 —— 因为那是**公开号**计数，本表是**设计**计数
（见 `project-corpus-design-identity-354`）。

## 结论

1. **「seed 撑不到那个视场」被否掉，第二次。** 第一次是单变量真机实测
   （未经优化的重标 seed 在 36.8° 仍 `2/2`，而 trial 用的是 38.7°）；
   这一次是全 49 条计划的口径统计。**两条独立证据同向。**
2. ⇒ **离轴不成像是优化过程的产物**，与 AUT merit 一阶根因一致
   （`@rmssum` 跳过追迹失败的视场，丢场让被最小化的量变小）。
3. ⇒ **路由侧的修法帮不上忙**。「挑视场余量更大的 seed」不会改善产出率，
   因为余量本来就够 —— 中位还多出 7.5%。别去做这一铲。
4. 唯一真正被推到原生之外的是 `US-12436366-B2-e10`（1.34×，n=1）。
   单条，不能支撑任何结论；记下来供日后逐颗诊断时排除。

## 复算

```
uv run python -c "
from pathlib import Path
from app.core.engines.seed_field_rebuild import max_field_angle_deg
from app.core.engines.zmx_import_prep import decode_zmx_text
from scripts.p2_crosssource_trial import plan_trials, ZMX_DIR
plans,_ = plan_trials(Path('<perfield-census.jsonl>'))
for p in plans:
    a = lambda n: max_field_angle_deg(decode_zmx_text((ZMX_DIR/n).read_bytes())[0])
    print(p.control_case_id, p.seed_case_id, a(p.seed_zmx), a(p.control_zmx))
"
```

相关：[[project-aut-merit-rewards-losing-a-field]]（机制）、
`project-corpus-design-identity-354`（为什么按设计计数而不按公开号）、
`.planning/evidence/aut-merit-rewards-losing-a-field-2026-07-29.md`（第一次否掉同一假设）
