# 路由和 P2 判决对「什么算好镜头」用的不是同一把尺子（2026-08-03）

## 缺陷

`app/core/case_library.py::_seed_has_floor_violation` 把
**Optiland 的 RMS 光斑半径**（在该 case 的 MTF 恰好构建于哪几个视场上算的）
和 100.0 µm 比；而 `scripts/p2_pair_census.py::seed_quality_ok` 筛同一批 seed，
用的是 **CODE V 全视场 max RMS 光斑直径**。
**同一个系统的两个部分，两套「可用 seed」的定义，而路由用的是松的那套。**

差距不是小数点级的。实测本仓 442 行语料中两把尺子都有读数的 **218 行**：

```
CODE V 直径 ÷ Optiland 半径     min 0.26   中位 4.02   max 379.6
（纯半径→直径换算应当恰为 2.00）
```

**76 / 218（34.9%）是「今天这道闸放行、而语料中位不会放行」的 seed。**

具体的受害者就是主指标路径上那颗：`US-12044826-B2-e4` 在这里存的是
**25.55 µm**（半径）＝ 51.11 µm（直径），舒舒服服过 100 µm 闸；
CODE V 全场量它是 **101.27 µm**。它随后**承担了 59 条 P2 trial 里的 48 条**。

## 本 PR 做了什么

**换仪器，不动闸值。**

- 新增 `app/data/codev_seed_quality.json`：442 行语料里 **218 行**的 CODE V 全场
  读数，逐条带 census 来源与 sha256。committed 而非现算——per-field census 是
  住在仓库外的运行时产物（`D:/atelier-stagec-runs/…`），没有 CODE V 的机器也必须能路由。
  这条先例是 `corpus_quality_distribution.json` 立的，本文件照抄它的形态。
- `_seed_max_rms_spot_diameter_um`：**有 CODE V 读数就用 CODE V**；没有的 224 行
  回退到 `2 × Optiland 半径`——因为那是半径而闸是直径，直接比会把老错误留给
  我们了解最少的那批 seed。两者都没有 ⇒ 返回 None ⇒ 判违规
  （**量不出来的 seed 不是可以拿出去展示的 seed**）。

**刻意不做的**：不动 `_SEED_ROUTING_MAX_RMS_UM = 100.0`。
换仪器是修缺陷，动闸值是「seed 要多好我们才肯拿出去」的产品决策，
两件事做完之后必须还能分开看。

## 代价（实测，442 行语料）

| | healthy→violation | violation→healthy |
|---|---|---|
| **只换仪器（闸仍 100.0）＝本 PR** | **16** | **9** |
| 再把闸降到 10.2312（P2 已在用的语料中位） | 111 | 0 |

**没有任何一个 scenario 桶被清空**：最稀的 telephoto 是 87 → **85** → 57 颗健康。

golden 树（`tests/data/eval_golden.json`，445 条 brief 全部重算）：

```
brief 改变选择        47 / 445
去重到不同的 seed 互换  26
  按互换记分：better 6 | worse 1 | 无法判定 19
被选中 seed 的 CODE V 全场直径   p50 13.16 → 13.16   p90 58.57 → 55.48
```

⚠️ **19/26 判不了**，因为旧选择那侧本身就没有全场读数——
这本身就是缺陷的一部分（路由此前在选它量不了的东西），但它意味着
**「6 好 1 坏」是在 26 里的 7 个上说的，不是在 26 个上说的**。

## 三条诚实边界

1. **brief 数不是观测数。** 445 条 brief 只对应少得多的 seed 互换；
   第一次读这份对比时我按 brief 记成「8 好 13 坏」，去重后是 **7:7**，
   净差完全是同一个互换被多条 brief 重复计数造出来的。本页所有结论按互换记。
2. **回退支路没有被这次验证覆盖。** 224/442 行走 `2 × Optiland 半径`，
   而这条路径的偏差正是本页在说的那个偏差——只是没有更好的东西可用。
   缩小它的唯一办法是给那批补 CODE V 全场读数。
3. **闸值 100.0 仍然是个没有出处的数。** 本 PR 没有为它辩护，只是没在同一次
   改动里动它。它与 P2 判据的 10.2312 相差约 10×，这个矛盾**依然存在**，
   只是现在两边至少在量同一种东西。

## 待主公裁定（已入队列，不阻塞）

**闸值是否从 100.0 改到语料中位 10.2312**（即让路由和 P2 判据同值）。
实测代价：111/442 行由 healthy 变 violation，telephoto 桶剩 57 颗健康。
好处：路由不再选出 P2 判决会直接判死的 seed。
这是产品口径决策（我们愿意拿多差的镜头出去演示），不该由 AI 单方面定。

## 复算

```bash
uv run pytest tests/test_seed_quality_ruler.py tests/test_case_library.py
```

产物重建：

```bash
uv run python scripts/build_seed_quality_artifact.py --census D:/atelier-stagec-runs/trace-census-20260728/perfield-census.jsonl
```

`test_the_committed_artifact_is_what_the_builder_produces` 会在有 census 的机器上
逐条比对重建结果与已提交文件；没有 census 的机器上跳过（该 census 是运行时产物）。
