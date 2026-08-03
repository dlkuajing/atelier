# P2 的瓶颈是 seed 供给，而供给早就躺在仓库里（2026-08-03）

## 一句话

`data/zmx-staging/patent-local-replay` 里 613 颗 git 跟踪的 ZMX，
过 6 道 soundness 闸后的 **157 颗**接进 P2 的 **seed 池**（**只当 seed，绝不当对照**），
**分母一位不动**，而被优化器拿来当起点的那颗镜头从 **101.27 µm 变成 5.02 µm**。

## 缺陷

2026-08-02 那轮 49 条 trial 里，**48/59** 条从同一颗 seed 出发，
它自己的 CODE V 全场读数是 **101.27 µm**，而要打平的对照在 **2–11 µm**。
不是比不过，是**起点就不成像**。

原因在 `p2_pair_census.census` 的这一行：

```python
pool = preferred or reachable or cross_source     # 三级 fail-open
```

`preferred`（既够得着又过质量闸）在 **53/59** 条上是**空的**，于是每次都掉到
未筛池，选中同一颗 101 µm 的种子。**这不是打分错了，是池子里没东西可选。**

而 `data/zmx-staging/patent-local-replay` 有 613 颗本仓自己的 patent→ZMX 转换产物，
**与 `data/zmx` 文件名零重叠**，没有任何消费者——因为 seed 选择读的是 case index。

## 做法：只当 seed，绝不当对照

两条路都建过、都实测过（同一天）：

| 策略 | trials | seed 池 basis | 被选 seed 的 CODE V 全场直径 p50 |
|---|---|---|---|
| 排除（= main 今天） | 59 | quality **6**，兜底 53 | **101.27 µm** |
| **只当 seed（本 PR）** | **59** | quality **56**，兜底 3 | **5.02 µm** |
| 也当对照（进语料） | 137 | quality 124，兜底 13 | 5.02 µm |

进语料那条能把 trial 数推到 137，但**其中 78 条的对照是我们自己这周造出来的**，
还会连带改掉 **97/445** 条产品路由决策。**打平率是一个以对照为分母的分数**——
往分母里塞自造件，改的是被测量的那个东西本身。

**只当 seed 这条路，对照集与改动前逐条相同**（集合相等验证，两向差集皆 0），
所以改动前后的打平率**可比**。这就是全部的设计理由。

## 实测（`--census perfield-census.jsonl`）

```
                        main 今天      本 PR
case index                 442          442     ← 不动
usable（对照）              74           74     ← 不动
cross-brand trials          59           59     ← 不动
对照集                                identical（集合相等，两向差集 0）

seed 池 basis    {quality 6, 兜底 53}  {quality 56, 兜底 3}
distinct seeds               6           12
top-5 占比               58/59        43/59
被选 seed CODE V p50    101.27 µm     5.02 µm
                 p90    101.27 µm     8.75 µm
```

157 颗全部建通（`staging_seeds_unbuildable` 为空），54/59 条 trial 的 seed 来自 staging。

闸的落选分布：`1_no_full_field_codev_reading` 375、`2_fidelity_quarantined` 33、
`5_image_height_*` 18、`6_prescription_already_in_corpus` **30**。
留下 **157 颗**，8 个受让人品牌，**非 LARGAN 95 颗 / 31 件专利**。

### 第 6 道闸是被一条测试逼出来的，不是设计出来的

原本只有 5 道。接上之后 `test_the_backfill_does_not_pair_a_control_with_a_seed_of_the_same_design`
挂了——它按 case index 查 seed 的 ZMX，而 staging seed 不在 index 里。
把它**扩到覆盖两个池**（而不是放宽它）之后，顺手量了一下真正的问题：

**187 颗里有 30 颗的处方与 `data/zmx` 里某颗逐字节相同。**
文件名零重叠 ≠ 设计零重叠——专利续案把同一个 embodiment 换个公开号再发一次
（`prescription_identity` 这个模块存在的理由就是：442 个语料文件只有 354 个不同处方）。

它们**不带来任何供给**（那个设计本来就能当语料 seed 选到），
却带来一个风险：一条「异源」trial 的 seed 可能就是它自己的对照——
**这是对拍器能给出的最谄媚的读数**，而挡在中间的只有受让人品牌规则。⇒ 直接筛掉。

**代价为零**：30 颗全是 LARGAN（92→62），非 LARGAN **95 颗一颗没少**；
头条数字（59 trials / basis {56,3} / distinct 12 / top-5 43）**逐项不变**
⇒ 这 30 颗本来就没被选中过，筛掉它们只是关掉一条没走过的后门。

### 第二个缺陷是「跑一遍」抓到的，不是「读一遍」

manifest 接好、census 读数漂亮之后，我去**实际排一轮**（`--plan`），
结果只排出 **5 条** trial，而同一份产物里 `trials_available` 写着 **59**。

根因：`p2_crosssource_trial.plan_trials` 把 control 和 seed **都**拿去 case index 查，
查不到就 `continue`——而 staging seed **按设计就不在 index 里** ⇒ **59 条里 54 条被静默丢弃**。
没有任何东西报错，计划只是「短了」，读起来像语料变小而不像 bug。
**真机跑下去会测 5 条，而每一份产物都写着 59。**

三处修法：① `TrialPlan` 带上 `seed_pool`（`corpus` / `staging`），
`seed_zmx_path()` 按它解析目录——**显式按池解析，不是「先试这个目录再试那个」**，
这样文件缺失会在它缺失的地方报错，而不会被另一个池里的同名文件顶替；
② 那个 `continue` 改成**硬拒绝**：任何一条解析不出来就中止整个计划，绝不缩短；
③ 两条测试钉死：计划长度必须等于 census 的 trial 数、每条计划的 seed 文件必须存在。

修完：**59 条排出，12 颗 distinct seed，54 条来自 staging。**

## 三条诚实边界

1. **尾巴反而变差了。** 被选 seed 的 **max 从 101.27 涨到 526.09 µm**。
   兜底那条路径还在（3 条 trial），只是从 53 条降到 3 条。
   **报 p50/p90 必须连 max 一起报**，否则这条会被藏掉。
2. **两侧的入池闸不对称，这是我引入的。** 语料 seed 必须过 `usable_set`
   （含 screen 3「对照的 spec 在产品参数域内」），staging seed 过的是 manifest 那 6 道。
   我的看法是 screen 3 本来就是**对照侧**判据（`load_usable_case_ids` 的 docstring
   自己这么写的），拿它筛 seed 一直是过严；但**这个论点没有被实测检验**，
   而不对称是真的存在。
3. **157 颗只是 31 件非 LARGAN 专利 + 62 颗 LARGAN。** seed 多样性从 6 到 12 是真的，
   但 top-5 仍占 43/59（73%）——**trial 依然不是独立样本**，产物里的 WARNING 照旧。

## 复算

```bash
uv run python scripts/p2_pair_census.py --census <perfield-census.jsonl>
```

加 `--no-staging-seeds` 复现改动前读数（有测试钉死它必须给出 59 trials /
`{reachable_only: 53, reachable_and_quality: 6}` / 6 颗 distinct seed）。

manifest 重建：`uv run python scripts/p2_staging_seed_manifest.py --emit`。

```bash
uv run pytest tests/test_p2_staging_seed_supply.py
```

9 条测试，承重的那条是 `test_admitting_staging_seeds_does_not_change_the_denominator`
与 `test_no_staging_design_is_ever_a_control`——**只要这两条绿，跨改动的打平率就可比。**
