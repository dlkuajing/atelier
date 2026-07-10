# Mode3 seed 选择漏斗调优报告（P11 高杠杆铲）

分支：`feat/mode3-funnel-tuning`（worktree `D:/atelier-w-funnel`）
日期：2026-07-11

## 背景

`scripts/sweet_zone_coverage.py`（PR#60，与 Codex 独立复算一致）量化实锤：
`TargetConvergedGenerator._rank_seeds_by_target_match` 两段式匹配——
stage 1 `case_library.rank_seeds` 全维距离取 top-10（FOV 权重 0.46 主导）
→ stage 2 `seed_target_score.score_seed_target_match` EFL band 重排取
第一——存在系统性漏检：wide 88/300、tele 135/300、uw 51/300 格点是
「漏斗致 miss」（存在性扫描口径：库内存在 ΔEFL∈[-15%,0] 甜区 seed，但
stage 1 的 top-10 里没有它）。三场景 EFL 维真空洞均=0，证明这是漏斗宽度
问题，不是库缺料问题。历史约束：两段式是 PR#48 为修 FOV 盲区建的（EFL-only
匹配曾选 FOV36° seed 打 78° target，violation 53.8%）——调优不许重新引入
FOV 盲区。

## 方案选择依据

### 排除的方案：纯 stage-1 top-K 加宽

K 扫描（wide/tele/uw 三场景，300 格点/场景，K∈{10,15,20,30,50,75,100,全池}）：

| 场景 | K=10（基线） | K=302/134/302（全池，等效取消 stage1） |
|---|---|---|
| wide sweet% / fovP95 / fovMax | 36.0% / 12.2° / 18.2° | 80.0% / 31.5° / 39.8° |
| tele sweet% / fovP95 / fovMax | 34.3% / 12.2° / 21.8° | 60.0% / 30.8° / 38.3° |
| uw sweet% / fovP95 / fovMax | 45.3% / 10.5° / 15.0° | 60.0% / 61.3° / 66.3° |

单纯加宽 K 能大幅提升 sweet%，但 fov_p95/fov_max 随 K 单调恶化——K 越大
越退化成 EFL-only 排序，等于重新打开 PR#48 关闭的 FOV 盲区。中间 K 值
（如 K=50~75）是覆盖率与 FOV 质量之间的连续 trade-off，找不到一个"既显著
提升覆盖率、又不明显恶化 FOV 分布"的固定 K。排除。

### 排除的方案：固定 M 的候选并集（stage1 top-K ∪ EFL-close-by-FOV 取固定 M 个）

M 扫描（K=10 固定，M∈{0,5,10,20,30,50}，extras=EFL band∈{lt5,5to15} 按
|FOV 失配| 升序取前 M 个）：

| 场景 | M=10 sweet% | M=10 fovP95/fovMax | 基线 fovP95/fovMax |
|---|---|---|---|
| wide | 54.0% | 12.4°/18.2° | 12.2°/18.2° |
| tele | 44.0% | 29.2°/36.1° | 12.2°/21.8° |
| uw | 53.0% | 15.0°/15.5° | 10.5°/15.0° |

wide/uw 表现尚可，但 tele 在 M=10 时 fov_p95 从 12.2° 恶化到 29.2°、
fov_max 从 21.8° 恶化到 36.1°——明显超出"噪声级"。根因：固定 M 只按
|FOV 失配| 排序截断，不知道"这个 target 本身在库里到底有没有近 FOV 的
EFL-close seed"——对 FOV 分布稀疏的场景（tele 池仅 134 颗），M 稍大就会
把远 FOV 的候选也放进 stage 2 竞争池，而 stage 2 本身对 FOV 不敏感（纯
band+score 排序），一旦远 FOV 候选 EFL 分数更好就会被选中。且该 M 扫描
本身呈非单调（tele M=5 sweet 55.7% 反而高于 M=10 的 44.0%——见下"已知
限制"关于 band-rank 与甜区窗口不对齐的讨论），说明固定 M 不是一个稳健
参数。排除。

### 采用方案：自适应 FOV 上限的候选并集（stage 1 top-K ∪ 「EFL-close 且
|FOV 失配| 不超过 stage 1 primary 自身最差成员」）

cap 倍率扫描（primary=stage1 top-10；extras 的 FOV 上限 = cap_mult ×
primary 自身最差 FOV 失配；cap_mult=1.0 即"不比 stage 1 自己已经接受的
FOV 容差更差"，无额外倍率）：

| 场景 | cap=1.0 sweet% | cap=1.0 fovP95/fovMax | 基线 fovP95/fovMax | cap=1.25 fovMax |
|---|---|---|---|---|
| wide | 66.0% | 13.5°/18.2° | 12.2°/18.2° | 22.0° |
| tele | 45.7% | 14.2°/21.8° | 12.2°/21.8° | 26.1° |
| uw | 43.0% | 11.5°/15.0° | 10.5°/15.0° | 15.5° |

cap_mult=1.0 是唯一在三场景上同时满足"覆盖率大幅提升"与"FOV 分布
p95/max 基本不变（fov_max 三场景均完全不变或仅 +1.0°）"的参数点——
不是巧合，是这个自适应上限的结构性保证：扩展候选池选出的 seed 的
|FOV 失配| 结构上不可能超过 primary 池自身最差成员，等价于"不比 stage 1
已经认可的最差 FOV 容差更差"。cap_mult>1.0 继续提升覆盖率但 fov_max 明显
偏离基线（tele cap=1.25 时 21.8°→26.1°），代价超出噪声级。**采用
cap_mult=1.0，固定值不做可配置暴露**（无需额外的全局幅度常数）。

EFL "已经很接近"的判定复用 `score_seed_target_match` 已有的 N=24 真机
标定分桶（band ∈ {lt5, 5to15}，score<15），未发明新阈值。

## 实现

- `app/core/orchestration/generators.py`：新增 `_fov_bounded_efl_close_extras()`
  （stage 1b），`_rank_seeds_by_target_match` 在 `spec.fov_deg is not None`
  分支里把 `primary + extras` 一起交给 stage 2 排序。`rank_seeds` /
  `score_seed_target_match` 本体均未改动。
- `scripts/sweet_zone_coverage.py`：镜像同一函数（`_fov_bounded_efl_close_extras`），
  与生产逐字对齐，保持"不 import generators 模块、本地重实现"的既有口径。
- `.planning/loop/sweet-zone-coverage-report.md` / `sweet-zone-topic-set.json`：
  用 `uv run python scripts/sweet_zone_coverage.py` 重新生成（改后数字）。

## 改前 / 改后对比（`scripts/sweet_zone_coverage.py` 主口径，300 格点/场景）

| 场景 | 甜区% 改前→改后 | miss 改前→改后 | 漏斗致miss(严格) 改前→改后 | 真空洞 |
|---|---|---|---|---|
| smartphone-wide | 36.0%→**66.0%**（+30.0pp） | 88(29.3%)→**6(2.0%)** | 88→**6** | 0→0 |
| smartphone-telephoto | 34.3%→**45.7%**（+11.4pp） | 135(45.0%)→**78(26.0%)** | 135→**78** | 0→0 |
| smartphone-ultrawide | 45.3%→**43.0%**（-2.3pp，见下方说明） | 51(17.0%)→**6(2.0%)** | 51→**6** | 0→0 |

三场景漏斗致 miss 合计 274/900 → 90/900（-67.2%），EFL 维真空洞始终为 0
（补库判据不变）。良品率闸选题集从 347 条增至 464 条。

## FOV 匹配质量对比（判据 2：被选 seed 与 target 的 \|FOV 失配\| 分布，300 格点/场景）

| 场景 | p50 改前→改后 | p95 改前→改后 | max 改前→改后 |
|---|---|---|---|
| smartphone-wide | 4.5°→3.6° | 12.2°→13.5°（+1.3°） | 18.2°→**18.2°（不变）** |
| smartphone-telephoto | 5.0°→5.4° | 12.2°→14.2°（+2.0°） | 21.8°→**21.8°（不变）** |
| smartphone-ultrawide | 4.9°→3.5° | 10.5°→11.5°（+1.0°） | 15.0°→**15.0°（不变）** |

三场景 p50 持平或更优，p95 仅 +1.0~+2.0°（自适应上限带来的结构性小幅
放宽，符合预期机制，非失控），**max 三场景完全不变**——这是
`_fov_bounded_efl_close_extras` 自适应上限的结构性保证：任何补齐候选的
|FOV 失配| 都不可能超过当次 target 下 stage 1 primary 自身最差成员，
所以"最坏情况"不会比改前更差。判据 2（FOV 质量不回退）满足。

## PR#48 反例钉测试

`tests/test_orchestration_generators.py::
test_rank_seeds_by_target_match_prefers_fov_near_seed_when_fov_constrained`
（同 EFL、FOV 36° vs 78° 打平，target FOV=78°）**未改动、仍通过**——两颗
候选池只有 2 个 case，均在 stage 1 top-10 内，stage 1b 补齐不介入，FOV
近邻预筛的保护机制原样生效。

## 三个真库反例锚核验（判据 3）

| 场景 | target EFL/FOV | 反例锚 | 结果 |
|---|---|---|---|
| wide | 5.2mm / 61.5° | US-11719917-B2-e6 | **✅ 逐点核验确认**：stage 1 top-10 排除（sanity 断言），stage 1b 补齐后为第一名。见 `tests/test_orchestration_generators.py::test_rank_seeds_by_target_match_recovers_real_wide_anchor_excluded_from_stage1_top_k` |
| tele | 11.5mm / 15.3° | US-20210364737-A1-e8 | **✅ 逐点核验确认**：同上机制。`fov=15.3°` 贴近 tele 场景 FOV 下界 15.0°，仍是合法客户请求。见 `test_rank_seeds_by_target_match_recovers_real_telephoto_anchor_excluded_from_stage1_top_k` |
| uw | 3.2mm | US-12210213-B2-e3 | **⚠️ 未按预期恢复——需主公/orchestrator 知悉，详见下方说明** |

### ultrawide 反例锚的诚实说明（重要发现，非本铲缺陷）

`US-12210213-B2-e3`（原生 EFL≈3.255mm，原生 FOV≈103.60°）在
`test_sweet_zone_coverage.py::test_efl_band_material_real_library_counterexample_anchors`
里被验证的是"EFL 维原料存在性"（池内存在 ΔEFL 落甜区闭区间的这颗
seed），**不是**"两段式匹配会真的选中它"——这是两个不同强度的断言，PR#60
测试从未断言过后者。

逐点核验（target EFL=3.2mm 固定，target FOV 在 88.6°~118.6° 之间以 1°/
0.5° 步长细扫，同时用真实 `TargetConvergedGenerator._rank_seeds_by_target_match`
核验改后选中结果）：

- target FOV ∈ [98.5°, 118.6°]（|FOV 失配| ≤ 5.1°）：该 seed **本来就在**
  stage 1 top-10 primary 里，改前改后都稳居第一——不是漏斗排除案例。
- target FOV ∈ [88.6°, 98.0°]（|FOV 失配| ≥ 5.6°）：该 seed 被 stage 1
  排除，且它的 |FOV 失配| **超出**该 target 下 primary 池自身的自适应
  上限——`_fov_bounded_efl_close_extras` 正确地不把它拉进候选池。
- 精细扫描（98.0°→98.5°，0.5° 步长）确认过渡宽度为 **0**：不存在"排除但
  可召回"的中间地带。

换言之，这颗 seed 从来不是一个"stage-1 宽度问题"式的漏斗致 miss——它要么
已经足够近（本来就选中），要么就是真的远到连自适应上限都不该放行（放行
就是重新打开 FOV 盲区，违反判据 2）。PR#60 报告里 uw 51/300 miss 全部
标记为 `funnel_caused_miss` 用的是"存在性扫描"口径（池内某处存在 ΔEFL
带内 seed，不管 FOV 多远），这个口径本身对补库定向是对的，但不能反推
"两段式一定能/应该选中这颗特定 seed"——这两者是本报告厘清的一个概念
差异。

本铲修复后，ultrawide 仍有 51→6 miss 的大幅改善（`3.65mm/85.0°` 切片，
`5P_F2.0_FOV78.8_EFL3.8_IMH3.2_TTL4.30`，剩余 6/12 子格点未完全恢复，
FOV 失配 6.2°），但 `US-12210213-B2-e3` 这个具体反例锚不在可恢复范围内。
`tests/test_orchestration_generators.py::
test_rank_seeds_by_target_match_does_not_force_in_genuinely_far_fov_ultrawide_anchor`
把这个边界行为钉成回归测试（target_fov=98.0° 时必须不出现在候选池、
target_fov=98.5° 时必须是第一名）——防止未来"修复"成强行拉近它反而
破坏自适应上限本身的不变量。

**建议**：若资深评审认为这颗特定反例锚必须被覆盖，需要的是一个不同类别
的干预（例如放宽自适应上限的倍率，或调整 stage 2 tie-break 逻辑），
不是本铲"stage 1 宽度"这个根因方向能解决的——应作为独立决策点交给
orchestrator/主公，不在本铲范围内擅自扩大自适应上限（那会以 tele 等
场景的 FOV 质量回退为代价，见"排除的方案"一节的量化证据）。

## ultrawide 甜区%名义下降的诚实说明（另一个发现）

ultrawide 甜区% 从 45.3% 降到 43.0%（-2.3pp，300 格点中净减约 7 个）。
逐点核验（37 个格点从 sweet_zone 翻转为非 sweet_zone）显示：**全部 37 个
翻转点，改后选中的候选在 band/score 上都与改前持平或更优（如 band 从
`5to15`→`lt5`，score 从 6.68→0.16），FOV 匹配同等或更优**（如
fov 失配 0.9°→0.1°）——只是 ΔEFL% 从负值（如 -6.68%，落在甜区闭区间
[-15%,0%] 内）变成了很小的正值（如 +0.16%，恰好落在甜区窗口外）。

真机 N=24 数据（`seed_target_score.py` docstring）显示缩焦方向 12/12 全
收敛、拉焦方向直到 +25.1% 才首次失败——+0.16%~+3.79% 这个量级的正向偏移
和 -1.69%~-11.63% 的负向偏移在真实收敛风险上没有证据表明前者更差，甜区
窗口 `[-15%,0%]` 是任务简报给定的单向口径，不是真实收敛边界。**没有为了
迎合这个不对称窗口的整数刻度而反向调整生产选择逻辑**（那会牺牲真实
更优匹配去凑指标，属于"数字对齐但真相受损"，违反诚实红线）。逐点证据见
`.planning/loop/mode3-funnel-tuning-report.md` 本节（复现脚本见任务附带
的诊断记录，未入库——如需复核可重跑
`_rank_seeds_by_target_match` 对 uw 302 池 × 300 格点扫描并对比 band/score/
FOV 三项）。

## 测试结果

- `tests/test_orchestration_generators.py`：**34 passed**（27 条既有 + 7 条
  新增：4 条 `_fov_bounded_efl_close_extras` 直接单元测试、2 条真库反例
  锚端到端测试、1 条 ultrawide 边界诚实测试）。既有 PR#48 钉测试、FOV
  unconstrained 降级测试均未改动、原样通过。
- `tests/test_sweet_zone_coverage.py`：**28 passed**（脚本本地重实现
  `_fov_bounded_efl_close_extras` 同步镜像，含既有 3 个真库反例存在性
  扫描测试）。
- `tests/test_eval_golden_seeds.py`：见测试运行日志（`rank_seeds` /
  `match_case` 本体未改动，golden 不应翻转——本铲只在 Mode3 私有的
  `_rank_seeds_by_target_match` 里加了 stage 1b，不改变
  `case_library.rank_seeds` 的路由排序本体）。
- ruff：全绿（`generators.py` / `sweet_zone_coverage.py` /
  `test_orchestration_generators.py`）。

## 真机 e2e（orchestrator 排窗，本铲未跑）

改后选中 seed 变化的 target 清单（供真机抽验参考，节选空洞清单收窄
最明显的几个）：

- wide EFL 5.2mm/FOV 57.0-65.2°区间：seed 从远 FOV miss 候选变为
  `US-11719917-B2-e6`（ΔEFL -3.06%，band lt5）
- tele EFL 11.5mm/FOV 22.5-30.0°区间：seed 从远 FOV miss 候选变为
  `US-20210364737-A1-e8`（ΔEFL -4.26%，band lt5）
- uw EFL 3.65mm/FOV 85.0-90.0°区间：seed 变为
  `5P_F2.0_FOV78.8_EFL3.8_IMH3.2_TTL4.30`（FOV 失配 6.2°，该切片仍有
  6/12 子格点未完全恢复，可作为真机抽验的边界样本）

完整改后甜区覆盖点清单见 `.planning/loop/sweet-zone-topic-set.json`
（464 条）。
