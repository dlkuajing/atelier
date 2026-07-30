# 把 `fov_deg` 重锚到 ZMX 实际追迹的视场（2026-07-29）

**一句话**：`fov_unit_census` 证明 `index.json` 与 442 个 per-case JSON 的 `fov_deg`
混着半视场与全视场两种口径；本铲把 **254 颗**的 `fov_deg` 重写为 `2θ`（θ = 该 case 自己
ZMX 的外场角），并把 **104 颗**由它派生的 `scenario` 一并重算。
**配对质量实测改善：seed/对照视场角落在 0.8–1.25× 的比例 60.0% → 89.8%，最坏 2.046× → 1.369×。**

## 为什么方向是「乘 2」而不是「除 2」

三条独立证据同向：

1. **schema 自述**：`optical_sample.py` 写 "Nominal full FOV from the manifest"，
   `lens_system.py` 写 "nominal full field angle"。
2. **物理自查**：两组的 `声明像高 / (EFL·tanθ)` 中位数都是 1.00（0.9957 / 1.0004）——
   θ 在两组里都是真半角，所以要动的是 manifest 那一列，不是 ZMX。
3. **阈值只有按全视场读才讲得通**：`_TELEPHOTO_FOV_MAX = 45.0`、`_ULTRAWIDE_FOV_MIN = 85.0`。
   45° **全**视场（半角 22.5°）是长焦；45° **半**角（全 90°）是广角。
   85° 全视场是超广的合理起点；85° 半角 = 170° 是鱼眼。

## 改动面

| | |
|---|---|
| 可重锚 | 425（余 17 颗原生 `FTYP 3`，无角度，**跳过不猜**） |
| `fov_deg` 实际改变 | **254** |
| `scenario` 实际改变 | **104** |
| 文件 diff | 255 + 105 文件 —— **每文件每字段恰好一行** |
| 幂等 | 重跑 `--check` 报 `would change 0` |

**两个文件都要动**：`load_case_library()` 读的是 per-case 文件、**不读 index.json**。
**两个字段也都要动**：只挪 `fov_deg` 会让语料自相矛盾——`load_case_library` 在 load 时
用 `fov_deg` 重算 scenario、与持久化的字符串不一致，而 `p2_pair_census` 的域内筛读的是
**持久化**的那个标签、会拿新 FOV 去过旧桶的边界。实测：只挪 FOV 会让 **104/442** 个标签
与分类器对不上（原本只有 2 个）。

## 后果一：场景分桶

104 / 425（24.5%）换桶：**wide→ultrawide 73、telephoto→wide 29、wide→telephoto 2**。

`tests/test_case_library.py::test_telephoto_tier_is_populated_after_reclassification`
的基线 139 → **110**。那 29 颗存的是半角：72° 的镜头被读成 36°，从 45° 长焦上限底下溜了进去。
**上限没动，动的是喂给它的数的单位。**

## 后果二：配对质量（真正想要的那个）

同一份 census、同一套代码，只有语料的 `fov_deg` 变了：

| | main 基线 | 只改 `fov_deg` | **本铲（fov + scenario）** |
|---|---|---|---|
| 可用 case | 71 | 71 | **74** |
| 可用 trial | 30 | 46 | **49** |
| min / max 视场角比 | 0.473 / **2.046** | 0.747 / 1.369 | 0.747 / **1.369** |
| 落在 0.8–1.25× | 18/30 = **60.0%** | 41/46 = 89.1% | **44/49 = 89.8%** |

**要撑到两倍视场的配对全部消失**——而消融实测里主导的失败模式正是视场受限。


## 独立见证：一阶几何自洽的 case 数几乎翻倍

`tests/test_eval_golden_seeds.py` 里有一个**先于本次改动就存在**的量：
「一阶离群」= 声明像高与该 case 自己的 `efl · tan(fov_deg / 2)` 相差超过 25% 的 case 数。
公式和 25% 这个门槛都不是我写的，量的是我**没有动过**的 `image_height_mm`。

**314 → 164。**

而且归因是**完全的**，不是部分的：离开离群集的 **153 颗，153 颗全都是本次被翻倍的**；
新进入离群集的 11 颗，也**全部**是被翻倍的。**没有别的东西动过。**

这是这次迁移最强的一条证据——把 `fov_deg` 从半角改成它本来声明的全视场之后，
`fov_deg / 2` 才是真半角，几何才闭合。

## 路由结果：尾巴塌了，中位略松（诚实两面）

`tests/data/eval_golden.json` 445 条基线里 **123 条（27.6%）选中的 seed 变了**。
按「所选 case 与请求源 case 的**视场角**相对偏差」评这 108 条可比的（ZMX 真值，不经 manifest）：

| | 旧 | 新 |
|---|---|---|
| p50 | **0.0103** | 0.0222 |
| p75 | 0.0966 | **0.0397** |
| p90 | 0.7717 | **0.0714** |
| max | 1.0916 | **0.2767** |
| 偏差 >20% 的条数 | **21** | **1** |
| 偏差 >50% 的条数 | **19** | **0** |

**逐条计数是 43 更好 / 55 更差 / 10 持平**，中位数确实**变差**了（1.0% → 2.2%）。
但**尾巴塌了**：19 条偏差超过 50% 的选择归零，最坏从偏 109% 降到偏 28%。
平均偏差 0.1602 → 0.0293（5.5×）。

**两面都要说**：典型匹配略松，灾难性错配消失。
注意本次迁移的**理由不是**这个结果——理由是单位对不上、schema 写死了口径、
两个阈值只有按全视场读才讲得通；路由变化是**后果**，不是论据。

## ⚠️ 同时变坏的一项：seed 集中度

| | main 基线 | 只改 `fov_deg` | **本铲** |
|---|---|---|---|
| 独立 seed 数 | 5 | 4 | **5** |
| 头号 seed 占比 | 17/30 = 57% | 40/46 = 87% | **41/49 = 84%** |

（只挪 FOV 会把独立 seed 压到 4；补上 scenario 后回到 5，并让 KANTATSU 首次进入
可用池——但集中度仍明显差于 main 基线。）

trial 数涨了，**独立设计数没涨反降**。按既有纪律，P2 报数必须
「trial 数 + 独立 seed 数」两个数同报；本铲让第一个数更好看、第二个数更差，
**不得只引用前者**。这条独立于本铲存在（底库异源可配对面本来就窄），
但本铲把它放大了，必须记在同一页上。

## 复算

```
uv run python scripts/reanchor_fov_deg.py --check   # 退出码 0 = 语料已锚定
uv run python scripts/fov_unit_census.py
uv run pytest tests/test_fov_manifest_convention.py # 上游 manifest 未回退
```

---

# 补完：上游 manifest（2026-07-30）

**上面那一铲改的是产物，没改产生产物的那份原料。** `index.json` 的 `fov_deg`
不是算出来的，是从 intake manifest **抄**过来的：`generate_cases.py` 把
`a["nominal_fov_deg"]` 传进 `build_sample_from_optic`，`case_library.py` 直接
`fov_deg=nominal_fov_deg`。所以上一铲之后，**跑一次 `generate_cases.py` 就会把
253 颗改回半角**。

同一个值还喂给 `regularize_fields_to_angle(optic, nominal_fov_deg)`——那个形参
在别处就叫 `full_fov_deg`。也就是说这 253 颗**一直是在真视场的一半上被追迹的**：
`half = fov/2`，喂进去半角就等于按 θ/2 建场，而 θ 才是 ZMX 自己的外场角。
metadata 声明 2θ、artifact 却按 θ/2 追——**语料内部本来就自相矛盾**，
上一铲只把矛盾的一半改对了。

## 改了什么

| | |
|---|---|
| 翻倍的 manifest 行 | **253**（`data06c_manifest.json` 67 + `data09d1_manifest.json` 186，两批**整批**都是半角） |
| 按 ZMX 读数改写 | **1**（`US10330891B2` 100.0 → **101.6**，语料里唯一的第三种口径：专利正文的圆整值） |
| 重生成的 case | **254**（全部走 lightweight artifact 路径 + 那一颗 full 路径），`generate_cases.py --only` |
| 未动 | 其余 **188** 行 manifest、188 颗 case 的 JSON **逐字节未变** |

`--only` 是这次给 `generate_cases.py` 加的：全库重跑要把 442 颗都过一遍 Optiland，
还要面对 `BUILD_TIMEOUT_S` 那条注释记的挂死风险；已知子集的改动没有理由去搅动整个语料。
**先跑了一次空 `--only` 作阳性对照**：442 颗全部走 reuse 分支，`index.json`
**零 diff**——所以真跑之后的 diff 全部可归因于重建本身。

## 验证：重生成的 `fov_deg` 确实等于重锚值（实测，不是假定）

| | |
|---|---|
| 与重锚值**逐位相同** | 384 / 442 |
| 有差的 | 58 行，**最大相对偏差 4.4e-9** |
| 按重锚脚本自己的渲染口径（`.9g`）相同 | **442 / 442** |
| `index.fov_deg == manifest.nominal_fov_deg` 精确相等 | **442 / 442** |

那 58 行的差**方向是精度回来了不是丢了**：上一铲的文本改写器按 `.9g` 落盘
（它当时在给一个已存值翻倍，怕二进制噪声），而 manifest 本来就带 11 位有效数字；
重生成写的是 manifest 的原值，所以 9 位之后的数字回来了。
`reanchor_fov_deg.py --check` 仍报 `would change 0`。

## 后果：三条不动的、两条动的

**不动的**（都是阳性对照，任何一条动了都说明我改错了）：

- `efl_mm` **442/442 未变**——视场规整不影响近轴量，本来就该一位不动。
- `scenario` **442/442 未变**——上一铲重算的 104 个标签，与
  `_classify_scenario(2θ, efl)` 现在从 manifest 算出来的结果**完全一致**。
  这是「翻倍是对的」的独立见证：两条互不相干的路径落到同一批标签上。
- 轴上视场 RMS 比值 **208/208 恰好 1.000**——轴上不依赖视场角。

**动的**：

- **离轴像质**（这才是这一铲真正买到/付出的东西）。采样视场角翻倍
  （lightweight 的第二个视场从 `0.5×θ/2` 变成 `0.5×θ`），
  离轴 RMS 新/旧 **中位 1.095，四分位 0.783 / 1.514**，36.5% 反而变好。
  旧值不是可比基线——它是在设计视场一半上量出来的。
- **14 颗丢掉离轴 MTF**：`mtf_max_field_frac` 0.5 → **0.0**，
  语料整体 58 → **72**。
  ⚠️ 这里的 `0.0` 是 `_lightweight_mtf` 的 **fail-closed 返回**
  （`compute_mtf` 抛异常或出 NaN → `_conservative_zero_mtf`），
  **不是「轴上完美」**——按本仓「退化值等于理想读数」的既有教训，这一条要写明：
  它是悲观值，会让这些 case 在需要全场证据的路径上被挡下，不会被误读成好数。
  14 颗全在 DATA-06c / DATA-09d1，全是被翻倍的：
  它们在**自己的设计视场**上追不出 MTF，此前之所以有数，是因为只被追了一半视场。

## 连带重算

- `tests/data/eval_golden.json`：`scripts/e2_golden.py` 重跑。
  445 条里 **47 条（10.6%）选中的 seed 变了**，196 条质量证据（`quality_floor_gap` /
  `quality_min250`）变了，58 条 `first_order_image_height_mm` 跟着精度动。
- `data/patent-ledger/`：**触发了，但只到第二级**。⚠️ 我先前写「未触发」是**错的**——
  当时只跑了 `patent_saturation.py audit`（它读的是已提交的 snapshot，当然不动），
  没有跑 replay 侧。`tests/test_patent_replay.py` 6 条挂在
  `PatentReplayError: frozen case index hash drift`：snapshot 冻结了
  `app/data/optical_cases/index.json` 的 sha256，而 index 变了。
  正确处置是 **只跑 `patent_saturation.py build`**——重算后 6 条全过，
  移动面精确到两处：`inputs/case_index/sha256` 与 `formal_artifacts`（254 个 per-case JSON 的哈希），
  计数、embodiments、`pool_concat_sha256` 一位没动。

  ⛔ **不要跑 `patent_pool_replay.py freeze`**（我跑了一次，已回滚）。
  它会重算 `cohort_sha256`，而 619 条已完成的 replay 结果是按旧 cohort 校验的：
  `roots_with_results 619 → 0`、`corrupt_results 0 → 619`、
  `cohort_replay_complete true → false`。**一条命令把 619 条真机结果全判成损坏。**
  refreeze 只在 cohort 成员本身要变时才做；index 内容变了但 619 个 root 一个没变，
  不需要 refreeze。

## 测试归因（54 条挂了，其中我造成的是 6 条）

全量 `pytest -n 8 -m "not real_machine"`：**54 failed / 4528 passed**（1:42:37）。
把这 54 条**逐条**在本铲的父提交上重跑（同一 worktree、detach 到父提交、`-n 4`）：
**45 failed / 9 passed**——即 45 条与本铲无关。剩下 9 条里：

- **3 条是 xdist worker 崩溃**，不是断言失败（`worker 'gw10' crashed while running ...`）。
  串行重跑全过。这是 `-n 8` 在这台机器上的产物（Optiland 峰值 ~1.2GB × 8）。
- **6 条是真的、是我造成的**：上面那条 `frozen case index hash drift`，已按
  `patent_saturation.py build` 修好，25 条全过。

⚠️ **更正我自己的一条中途判断**：我一度认为
`test_p2_pair_census::test_gating_at_the_corpus_median_costs_no_trials`
（`assert 4 == 49`）是本铲造成的——理由听起来很顺：种子质量闸按语料中位数设，
而我改了语料的离轴 RMS。**父提交上同样挂**，所以它是本branch既有的，不是本铲的。
`load_distribution()` 读的是已提交的 `app/data/corpus_quality_distribution.json`，
源头是 worktree 外的 CODE V 真机 census（`D:/atelier-stagec-runs/…`），
**本来就不从 `index.json` 派生**——机制上也不可能被我改到。
教训还是那条：**先比基线，再归因**。

📌 那 45 条里约 35 条是同一个环境原因，与代码无关：
`ValueError: CODE V-unsafe source_zmx '…\.claude\worktrees\…': dot-prefixed path
component '.claude'`。仓库有一条守卫拒绝含点前缀目录的路径（`ZEMAXOS_TO_CV` 会静默
导入 dummy system），而 worktree 自己就住在 `D:\atelier\.claude\worktrees\` 底下。
**在 `.claude/worktrees/` 里跑不了 CODE V 路径相关的测试**——这条对以后每一个
worktree 都成立，不是本铲的问题，但值得记下来。

## 没做，及为什么

- **`SCENARIO_BOUNDS` 没有重新标定。** `US10330891B2` 从 100.0 挪到 101.6 之后，
  按 `compute_bounds_stats.py` 的口径重推，超广 FOV 上限会从 105.0 变成 106.7。
  **没改**：放宽 bounds = 改产品接单范围，是主公的待裁定项，不能作为一次语料修复的副作用。
  105.0 仍然覆盖 101.6，测试里把这层依赖写明了。
- **`PATENT_PROVENANCE["US10330891B2"]` 仍是 100.0**。那是 E2-01 对专利正文声明值的
  交叉验证记录（`fov_declared_deg = 2 × declared HFOV`），与 ZMX 追迹角是两个量，不该同步。
- 上一铲「未做」里那三条（17 颗 `FTYP 3`、抽样回查专利原文、`rank_seeds` 权重）
  **一条都没动**。

## 未做

- 17 颗原生 `FTYP 3` 未处理（没有角度可锚）。
- 未回查专利原文抽样复核那 254 颗的原始标签。三条证据已同向，但抽样仍值得做。
- `rank_seeds` 的权重与 `fov_miss > 5°` 惩罚**一个字没改**——本铲只修被比较的数，
  不动比较规则。
- seed 集中度没有改善手段落地；扩底库仍是 P2 样本量的唯一上游。

## 连锁反应链，与一处结构性冲突（必须记下来）

重锚 `index.json` 触发了一条四级链：

```
index.json 改
  → patent-ledger/snapshot.json 冻结的 index sha 失配（replay gate 挂）
  → 按脚本重建 snapshot（AGENTS.md：必须由脚本重算）
  → audit.json 从 45122 → 83583 字节
  → .planning/quick/260719-.../family-94801574-source-evidence.json
     这条**冻结历史证据**记录的 audit.json 字节数/哈希失配
```

⚠️ **第四级暴露了一处结构性冲突，不是我这次改动引入的**：
那条 2026-07-19 的冻结证据记录**按哈希引用了一个由脚本重算的活artifact**
（`data/patent-ledger/audit.json`）。活artifact 按设计就会漂移，
所以这条引用**注定会在下一次重算时失配**——它检测到的不是数据损坏，是重算本身。

本次按最小改动更新了那条记录的 `bytes`/`sha256`（83583 / `dbf16c95…`），
但**这只是把冲突推后一次**。真正要裁的是：**冻结的历史证据记录能不能按哈希引用可重算的活artifact**？
两条既有仓规在这里对顶——AGENTS.md 要求 ledger 由脚本重算，而冻结记录要求字节不变。
出路二选一：① 冻结记录改为引用**当时的快照副本**而非活路径
② 该 rehash 测试对已知可重算的 artifact 走白名单并另行披露。

📌 顺带：`audit.json` 之所以长了 38KB，是新出现的 `staging_patent_candidates:613`，
**与本次重锚无关**——旧快照是在 staging 普查存在之前冻的。
