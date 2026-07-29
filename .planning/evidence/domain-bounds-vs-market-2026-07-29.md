> ⚠️ 本页只测量，**不改任何 bound**。改 `SCENARIO_BOUNDS` = 改产品接单范围，
> 且 `AGENTS.md` 记着官网滑块 BOUNDS 必须 ⊆ 它——那是产品决策，应当**看着这张表做**，
> 而不是"想要更大样本"的副作用。

# P2 样本量的真瓶颈不是底库大小，是产品自己的参数闸（2026-07-29）

**一句话**：底库六家受让人本来够分散，**三道可用性筛里前两道都保住了分散度，
第三道（产品自己的 `SCENARIO_BOUNDS`）把它压成了一家**；
而这些 bound 里 **14 条有 13 条被 ≥2 家独立受让人跨过、4 条被 4 家跨过**——
它们描述的是我们的窗口，不是市场。

## 逐家过筛

| 受让人 | 全部 | 可追迹 | +保真 | **+域内** | 末端占比 |
|---|---|---|---|---|---|
| LARGAN | 245 | 114 | 108 | **44** | 18.0% |
| NINGBO SUNNY | 68 | 24 | 17 | **1** | 1.5% |
| (无受让人) | 38 | 28 | 25 | 25 | 65.8% |
| KANTATSU | 34 | 15 | 15 | **0** | 0.0% |
| SAMSUNG ELECTRO-MECH | 26 | 24 | 18 | **0** | 0.0% |
| AAC | 18 | 7 | 3 | **1** | 5.6% |
| ABILITY | 13 | 6 | 6 | **0** | 0.0% |
| **合计** | **442** | **218** | **192** | **74** | 16.7% |

前两道筛之后仍是 Largan 108 / 无名 25 / Samsung 18 / Sunny 17 / Kantatsu 15 / Ability 6 / AAC 3。
**第三道之后：Largan 44，其余全部 0 或 1。**

直接后果（重锚后实测，非估计）：**45/49 的对照，其异源种子池只有 4 颗**
（池大小分布 `{4: 45, 47: 2, 48: 2}`——只有那 4 个非 Largan 对照拿得到大池）。
所以 49 条 trial 里 **41 条共用同一颗 seed**。
**卡住主指标的是样本独立性，不是底库规模。**

> 口径提醒：`fov_deg`+`scenario` 重锚前该数字是 **2 颗**（当时可用带受让人的只有
> 44 Largan + 1 AAC + 1 Sunny）；重锚让 KANTATSU 进来 2 颗，池才到 4。
> 引用这个数必须说清是哪一版语料。

## 哪条 bound 拦下了谁

在 192 颗（可追迹 ∧ 保真干净）里跑产品自己的 `validate_scenario_params`：

```
considered 192 | accepted 74 | rejected 113 | 荒谬像高 5（语料缺陷，不算市场证据）
```

被 **≥2 家独立受让人**跨过的 bound：

| 参数 | 场景 | 案例数 | 家数 | 受让人 |
|---|---|---|---|---|
| FOV | ultrawide | 32 | **4** | ABILITY, KANTATSU, LARGAN, NINGBO |
| EFL | ultrawide | 28 | **4** | ABILITY, KANTATSU, LARGAN, NINGBO |
| image_height | ultrawide | 27 | **4** | ABILITY, KANTATSU, LARGAN, NINGBO |
| EFL | wide | 12 | **4** | AAC, KANTATSU, LARGAN, NINGBO |
| f/# | ultrawide | 11 | **4** | ABILITY, KANTATSU, LARGAN, NINGBO |
| image_height | wide | 28 | 3 | AAC, KANTATSU, LARGAN |
| EFL | telephoto | 25 | 3 | LARGAN, NINGBO, SAMSUNG |
| FOV | wide | 3 | 3 | AAC, KANTATSU, LARGAN |
| n_elements | telephoto | 23 | 2 | KANTATSU, SAMSUNG |
| f/# | telephoto | 23 | 2 | LARGAN, SAMSUNG |
| n_elements | ultrawide | 8 | 2 | ABILITY, LARGAN |
| FOV | telephoto | 8 | 2 | NINGBO, SAMSUNG |
| image_height | telephoto | 4 | 2 | KANTATSU, SAMSUNG |

**只被 1 家跨过的 bound：1 条。**

## 判据为什么是"几家"而不是"多少颗"

一条 bound 被**单独一家**跨过，可能真的是那家的边缘设计。
被**多家独立受让人**跨过，说明市场在那一侧有量产设计，而我们的窗口画窄了。
**语料本身就是市场证据**，不需要引入任何外部数字——这也符合红线③：不先验拍板。

## 几个具体的例子（拒因是可读的）

- `n_elements 4 out of [5, 9] for smartphone-telephoto` —— Samsung 15 颗、Kantatsu 5 颗。
  **四片长焦是真实在售的品类**，我们的下限写了 5。
- `f/# 4.4 out of [1.8, 4.0] for smartphone-telephoto` —— Samsung 12 颗。潜望长焦本来就慢。
- `EFL 26–28mm for smartphone-telephoto`（上限 18）—— Sunny 与 Samsung 的折叠潜望。
- `FOV 128–134° for smartphone-ultrawide`（上限 105）—— 四家都有。
- 反例（**不是**市场证据）：`image_height 5.9e+17mm`、`EFL 0.44mm` —— 语料自己的退化读数，
  本脚本按 `> 100mm` 单列 5 颗，不混进上表。


## 顺手证伪一条 backlog：给 `rank_seeds` 加视场距离**不值得做**

实测（重锚后的语料）：

- **45/49 的对照，其异源种子池只有 4 颗**（分布 `{4: 45, 47: 2, 48: 2}`——
  只有那 4 个非 Largan 对照拿得到 47–48 颗的池）。
- 而 `rank_seeds` **已经在 45/49 上选中了视场最接近的那一颗**。
  4 次"选偏"的偏差差值是 `0.078 vs 0.076` 这种噪声级，最大的一次是 `0.253 vs 0.221`。

**打分不是瓶颈，可选项的数量才是。** 92% 的 trial 是在 4 个里挑 1 个，
再往打分函数里加一维视场距离改变不了任何配对。
这条 backlog 关闭；真正的上游是上面那张 bound 表。

## 复算

```
uv run python scripts/domain_rejection_census.py --census <perfield.jsonl> --json out.json
```

## 未做 / 待裁定

- **一个 bound 都没改。** 建议按上表逐条评估，但那是产品决策。
- 25 颗"无受让人"里 15 颗是老的合成 seed（本就没有专利），
  10 颗是老式专利号（`US9239447B1` 等），**在 `data/patents` 的 714 条发现池里一条都查不到**——
  要补得重新采集，属外部依赖。
- 本页只看被拒的**参数**，没看被拒设计的**像质**——被拒的未必是好对照。
