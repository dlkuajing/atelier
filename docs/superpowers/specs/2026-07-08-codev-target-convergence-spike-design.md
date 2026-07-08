# ③优化落地最小可行性 Spike — 接缝设计 Spec

- **日期**：2026-07-08（v7 修订 2026-07-09）
- **状态**：设计草案 **v7**（Codex + 5 棱镜对抗轮1-6；轮6 **2 棱镜判 design-converged**，余 6 条 A 精确尾全采纳）；待轮7 验设计层收敛 + 主公 ratify
- **里程碑语境**：Phase 10 探路阶 · 北极星（量产设计产出引擎）go/no-go 命门
- **基线**：origin/main `7177325`；worktree `D:\atelier-opt3` @ `spike/codev-target-convergence`；GSD session `.planning/debug/codev-target-convergence.md`
- **范围**：C1 §10 六接缝中的 **接缝1（EFL 解锁朝 target）+ 接缝3（客户 F#/IMH 目标）**。不碰接缝4-6。

---

## 0. 核心方法论转变（v4 · 轮3 识别）

轮3-4 双方发现：大量残余漏洞卡在 **CODE V 实际运行行为未知**（FNO 模式是否锁 F#、ANG 场 IMH 是否漂、畸变原语有无失败码、(FNO) 读活算还是设定值、seed 有无 rel-1.0 场、AUT 有无收敛标志、AUT 是否可复现、场重建后渐晕是否需重解——共 8 条 E1-E8）。**这些无法靠文档断言解决——越断言越假绿。** v4 把它们从"断言"改为 **§3 闸2 Step-0 经验探针（scratch 动态、跑 AUT 观测但不 mutate 交付）+ 决策分支**：spike 先探针确定 CODE V 真行为，设计按结果分支。这是把"错误假设→假绿"改成"显式经验决策点"的唯一诚实办法。**轮4 确认此 parking 攻不动（诚实、无逻辑漏洞）。**

## 1. 目的与 go/no-go 分层

验命门：改接缝1+3 后，CODE V AUT 能否在真实 seed 上让 **EFL 真优化朝 target 收敛**，并**实测** F#/IMH/像质对 target 的达成/代价？产出=数据 + 资深 go/no-go。

### 1.1 判定分层（[EXPERT] 红线 · 轮2 M5 + 轮3 强化）

**关键区分（轮4 收敛）**：**几何 target 达成度**（EFL/F#/IMH 是否落各自预设容差）是**客观量**——脚本可 emit `*_converged` bool，与"值不值得看一眼"无关。**像质好坏**（RMS/畸变多大算灾难）是[EXPERT]维——脚本**只出裸倍率数字、不设任何阈 bool**，资深判。两者本质不同：前者是"打没打中几何靶"，后者是"打中了但成品好不好"。

| 层 | 谁 emit | 内容 |
|---|---|---|
| **纯客观机器量** | 脚本 | **三维几何达成 bool**（预设容差、非像质判定）：`efl_converged`（§6.2）· `f_number_converged`（实测 vs target 落 F# 容差）· `imh_converged`（实测真实 IMH 落 IMH 容差）· `validity_pass`（fail-closed §4.4）· `aut_converged`（§4.4.5）· **裸算术倍率数字** `rms_ratio_vs_seed_baseline` 等（**无阈无 bool**）· 三维实测偏差数字 |
| **资深填（脚本留空）** | 仅资深 | **像质**"值得看一眼/接近可用"、三色 verdict、良品率、灾难与否 |

> **轮3-4 采纳**：**删除 `catastrophic_degradation_flag`**（其 N× 是**像质**容忍度阈=[EXPERT]维，越线）。**但 `*_converged` 三 bool 是几何 target 达成度、非像质判定，脚本可 emit**（容差是预设几何验收常量，见 §6.3，非像质好坏阈）。灾难与否仍由资深看裸倍率判。

### 1.2 go/no-go 证据链闭合（轮3 采纳）

- **窄域 GREEN 解锁的具体下一步**（§5.1 外推边界内）：→ **小规模扩样闸（≥1 长焦 + ≥1 异 F# 族）**，**非**直接解锁完整 harness。窄域证据只支撑"最易族机制非零"，扩样闸才桥到全族决策。
- **资深 go/no-go 决策框架**（供资深、非机器 verdict，§8）：三态北极星裁决对齐 §5.3——
  - **go 充分条件**：≥1 seed Stage C 真成功（validity 全过 + IMH 实追迹落容差 + EFL 收敛）+ 甜区双 seed EFL 收敛 + 可收敛半径覆盖客户常见偏移。
  - **no-go 触发（统一句式"真跑负结果=no-go、无数据=blocked"）**：Stage C **真跑(b 桶)但全 RED**（IMH 不达/像质崩）/ 甜区 EFL 都不收敛 / **天花板臂真跑出数据但无 RED→发散拐点**（轮6 限定：**排除**天花板臂 INVALID/回退 INVALID/tooling-blocked=证据缺失、走 blocked 支非 no-go）。
  - **blocked（≠no-go，轮5-6 对齐）**：Stage C 全 `imh_field_valid=0`（工具链阻塞）/ 天花板臂 tooling-blocked（可收敛半径上界证据缺失）→ 派生对应 debug 为已识别下一 blocker，非 no-go（EFL+F# partial 仍成立）。
  - **mixed 跨 seed（轮6）**：两 seed Stage C 结局混合（如 seed-1 defer + seed-2 (b)RED）→ 按 seed 分别裁决；整体 go 仍需 ≥1 seed 真成功；**无真成功且含 ≥1 真 RED → no-go，含 defer 支同时派生 field-conversion debug**。

## 2. 核心物理判断（主公 ratify 独立集不变 · v4 修正 provenance）

{EFL,F#,IMH} 独立 + FOV 派生（`F#=EFL/EPD`；`IMH≈EFL·tan(半FOV)·畸变`）。

### 2.1 落地手柄 + provenance（轮2-3 修正：F# 与 IMH 同为经验测定）

| 目标 | 手柄 | provenance | 达成校验 |
|---|---|---|---|
| **EFL** | AUT 一阶约束 `EFL={target}` | **优化收敛**（唯一确定的真优化维） | post_aut 实测 vs target < 2% + 移动达阈 + 方向对 |
| **F#** | 见 §3-E1 分支（EPD 模式测漂 / FNO 模式锁 F#） | **经验测定**（≠假设≈0）：AUT 拉 EFL 时 F# 是否漂**取决于 aperture 模式（E1 探针定）** | **post_aut 实测**（用 EFL_real/EPD_real 活算，交叉核对 (FNO)，E4）vs target；出容差→封顶 YELLOW |
| **IMH** | 见 §3-E2/E5 分支（原生场测漂 / 场重建锚 target） | pre-Stage-C：`source=measured`（ANG 场 IMH∝EFL，AUT 拉 EFL 后随之漂，`codev_optimize.py:766-769` 宏内 readout 块 `^yh=^efy·TANF(angle)`）。**Stage C：`source=constructed`**（设 yim=target、readout 直读 YIM=设定值=构造钉死，非优化收敛——轮5 修正"实测真实 IMH"的自相矛盾） | **实追迹主光线像高**（RSI 真实落点，含畸变）vs target；constructed 维仅验"守住"不计 GREEN attainment（§6.3） |
| **FOV** | —— | **派生测量量**（非目标/约束/收敛维） | 只测量报告 |

> **关键（轮3 两 blocker）**：只有 **EFL 是确定真优化收敛维**。**F# 与 IMH 同为"经验测定、须实测漂移/达成"**——都不得假设"构造即达≈0"。F# 是否漂由 aperture 模式定（E1）；IMH pre-Stage-C 必漂（ANG 场），Stage C 场重建后才锚（E2/E5）。三维实测出各自容差 → 见 §6 封顶规则。

### 2.2 provenance 冲突 = 给 C1 owner 的建议（轮3：改为纯记录，非本 spike gate/交付物）

本 spike **无授权改已定稿 C1 spec**（PR#44 六轮收敛）。以下为**发现记录，留待 Mode3 接入时由 C1 owner 决策**（非本 spike 的 gate/patch）：
- 本 spike 物理判定：EFL=优化收敛、F#/IMH=经验/构造达成、FOV=派生——与 C1 §5.2 `CONVERGED_FIELDS[TARGET_CONVERGED]={efl,fnum,imh,fov}` 冲突。
- **C1 的 `converged_toward_target` 是唯一表达"该维达 target"的 per-field 布尔**；把构造/经验达标的 fnum/imh 标 False=谎报未达标、标 True=谎报优化收敛。→ 建议 C1 引入**第三态 `achieved_by: optimized|constructed|measured`**，而非塞进 not-converged 布尔。fov 应剔除收敛维。§10 seam-3"merit 加 F#/IMH/FOV 操作数"措辞与本 spike 物理判定冲突，一并建议 C1 owner 复核。

## 3. 闸2 Step-0：CODE V 行为经验探针（v4 中心 · scratch 动态探针、先跑）

改宏前先跑一个 **scratch 动态探针**（导入 seed → 读系统状态/**跑 AUT 观测行为** → 结构化输出），确定下列真行为，设计按结果分支。**探针可跑 AUT（E1/E6/E7 本就需要），但不 mutate 交付宏、不持久化设计、产物只入 probe-report——纯发现，非交付路径**（轮4 修："只读无优化"与 E1/E6/E7 需跑 AUT 自相矛盾）。

| # | 经验未知 | 探针方法 | 决策分支 |
|---|---|---|---|
| **E1** | FNO 模式在 AUT 中是否每轮重解 EPD 保 F# | 小 seed 上：EPD 模式跑 AUT 拉 EFL 测 F# 漂；再 FNO 模式同跑测 F# 是否锁 | 锁→F# 手柄=FNO 模式（F# 达 target，测 EPD/像质代价）；不锁→EPD 模式测自然漂移 |
| **E2** | ANG 场 IMH 在 AUT 拉 EFL 后是否随之漂 | 读 seed 场类型；EFL 约束前后测 IMH | 漂（预期）→ pre-Stage-C IMH 标经验漂移；Stage C 场重建后再锚 |
| **E3** | 畸变 `(DIX/DIY)` 追迹失败有无 err 出口 | 构造必失败边缘场，看 DIX/DIY 返回 | 有 err→直接守卫；无→改用 RSI 主光线追迹取 `^err` 前置守卫（守卫定义写死 §4.4） |
| **E4** | `(FNO)` 各 aperture 模式读活算 vs 设定值 | 两模式下比对 `(FNO)` 与 `EFL/EPD` 活算 | 读设定值→F# 一律用 EFL_real/EPD_real 活算，不信 (FNO) |
| **E5** | seed 原生场集是否含近轴最大像高（rel 1.0 等价）边缘场、场类型 | 读 `(NUM F)`/`(TYP FLD)`/逐场 YIM | 无 rel-1.0→必需集用"归一化像高最大场"机器定义（§4.4）；决定是否导入后注入场 |
| **E6** | AUT 输出有无收敛/发散或撞 MXC 标志 | 跑一次读 AUT 状态输出 | **有**→写 `aut_converged` required_key；天花板臂发散=RED。**无（承重最坏支·轮4）**→ `aut_converged` 退化为机器代理：`aut_diverged := (撞 MXC 循环耗尽) OR (逐 cycle merit/EFL 未单调收窄) OR (\|post−target\|/target ≥ 2%)`；天花板臂 RED/INVALID 三态改用多点 `\|post−target\|` 曲线拐点定，**不依赖不存在的 flag**（否则天花板 RED 判据落空=假绿） |
| **E7** | AUT 同 seed 同 target 是否逐位可复现 | 同参跑两次比对 post_aut.efl | 确定性→复现规则可轻；非确定性→§5 复现定向到 2% 阈附近 |
| **E8** | Stage C 场 ANG→IMG 重建后，seed 原生渐晕系数(VUY/VLY/VUX/VLX)/主光线是否随场重定位失配、是否需重解 | 小 seed 读原生 VUY/VLY→构造 ANG→IMG 重建→比对重建前后渐晕系数/主光线足迹 | 失配→Stage C 场重建须**同步重解渐晕(VDX/VDY)**并写死重解步骤（呼应 codebase 已知雷区 E1-02）；一致→记录可沿用 |

探针产出 `.planning/loop/codev-behavior-probe-report.md`。**E1-E8 结果是设计定稿的输入**（部分分支现"待探针定"，探针后收敛）。
- **探针自身失败兜底（轮5）**：任一 Ex 探测 run 本身 INVALID/崩溃/超时（如 E3 构造失败场把 CODE V 打崩、scratch 导入失败）→ 该 Ex 记 `probe-blocked、未知留未知`，对应设计分支**保守取 fail-closed 支**（distortion 不计 validity / IMH 标经验漂移不锚），派生"probe-tooling debug"为已识别下一 blocker，不阻塞其余 Ex。
- **探针↔正式 run 环境一致性（轮5）**：探针的 seed 导入(`IN ZEMAXOS_TO_CV`)、CODE V 可执行版本、aperture 模式与场定义须与正式 Stage run **同源**（同 codev_optimize 宏骨架的 scratch 变体）；probe-report 记配置指纹供正式 run 比对。

## 4. 加法式宏改造设计（零回归 · 全路径）

新增可选 `target_efl_mm/target_f_number/target_imh_mm`。**参数校验契约（轮4 completeness）**：三者提供时必须 `>0 且有限`，沿用现有 `_validate_positive`（`codev_optimize.py:200-212`）在 `build_codev_optimize_sequence` 入口 raise ValueError——非法值（负/0/NaN）不得写进 .seq（否则污染 go/no-go 数据/除零）。

### 4.1 零回归契约（轮2 B3 + 轮3：parse **和** run 双路径）

- **baseline 模式（三全 None）= 现状零改动**：`^before_*`/`^after_*` 变量 + `before.*`/`after.*` 键 + `EFL=^baseline_efl_y_mm`；现有 7 测一字不动。**不重命名任何现有变量/键。**
- **target 模式（任一非 None）= 全新增路径**：新增 `mode=target` 键 + 三快照新键，与旧键并存不覆盖。
- **run 路径同步 + per-stage 对齐（轮3-4）**：`run_codev_optimize` 必须**按 stage(baseline/A/B/C) 组装 `required_keys`** 传给 `run_codev_batch`(:356)——**非**二元(baseline vs target)选择（轮4：二元与 §4.3 的三元 per-stage 矛盾，会让 Stage A run 被 B/C 键判假 INVALID）。即 run_codev_optimize 接受 stage/target 三参，按 stage 选 per-stage 必填键集（单一真相 §4.3），parse 路径同法。否则 target run 在 :356 被错键校验吞成假 INVALID。

### 4.2 三快照（防配置损伤藏进 before）

`import → 【快照1 seed_baseline】(seed 原生场，仅对照) → 应用 target 配置(§3 分支) → 【快照2 config_pre_aut】 → AUT(EFL 约束) → GO → 【快照3 post_aut】`。**度量捕获在配置前**。

### 4.3 per-stage 结果契约（轮3 Codex R3-C1）

target 模式 required_keys **按 stage 分**（防 A/B 被强制全三 target 键判 INVALID）：Stage A 要 `target.efl_mm`；B 加 `target.f_number`；C 加 `target.imh_mm`。**未施加维标 `source=seed_hold`，不计入 target achieved**。parser/report 缺该 stage 必填键 → INVALID。

### 4.4 fail-closed 有效性（全度量 + 机器可判必需集 + AUT/快照兜底）

1. **必需集机器可判（轮3-6：绝对 mm、非无量纲抽象）**：`REQUIRED_METRICS = {spot, wfe}`（**distortion 与 MTF 同为"条件必需"：E3 守卫写死后并入**）。必需场 = **该快照活动场集里"绝对像高 `|yh_mm|` 最大的场"必须有效 + 全 N 场有效 + N ≥ seed_baseline N**。**中间场覆盖（防成分软化）**：post_aut 场集须**逐档覆盖** seed_baseline 各场绝对像高分档——每个 seed 场的 `|yh_mm|` 在**对比基准**（见 §4.4.2 分母）有 `±field_tol` 内对应场（**`field_tol` 预定死默认 10%、run 前可改、留空 fail-closed**，与 §6.3 容差同款兜底；轮6 修"±tol 未定义"）。`N ≥ N` 只防场数缩水、不防成分软化。
2. **分母 per-stage（轮6：只 Stage C 施加 IMH 下界）+ 畸变绝不进 validity（轮6 对偶洞）**：
   - seed_baseline/config_pre_aut/**Stage A/B 的 post_aut** 用 **seed-native 活动场集**为分母（IMH=seed_hold，**不施加 target_imh 下界**——轮6：否则 A/B 无 target_imh 却被判假 INVALID、最小闸首信号被误路由 tooling-blocked）。
   - **仅 Stage C（IMH status=applied）**：post_aut 用 target 场集为分母，且必需集**必须含至少一场"到 target 像圈"**——**此覆盖检查用近轴/折算像高 + 宽松结构容差（默认 `target_imh_mm×(1−edge_tol)`，`edge_tol` 默认 15%，纯反-gaming 确认有场跨到像圈，非精度）**，**distortion-insensitive**。
   - **畸变绝不进 fail-closed validity（轮6 blocker）**：手机 wide/主摄 barrel 畸变常 2~4%，若把含畸变 RSI 实追迹像高塞进 2% 硬 validity 闸会把**真实设计误弹 INVALID**、良品率证据系统性偏低畸变 seed。故：validity 的"到像圈"用近轴+宽松容差；**边缘实追迹像高 vs target 之差=畸变项，另出裸数字键**喂 §6.3 imh 判定 + 资深报告，**永不进 validity_pass**。
3. **每度量 per-field 成功计数**：`@rmssum`/`@mtfmin`/`@dstpct` FOR 内对追迹成功场计数输出 `<snap>.<metric>_valid_fields`。**`@dstpct` 守卫（E3 定）**：有 err 出口则直接；无则改 RSI 主光线追迹取 `^err` 前置，成功才读 DIX/DIY——**守卫判据探针后写死本节，未定义前 distortion 不计入 validity**。
4. **`@wfewav` 整批门**（非 per-field）：`^ok=RMSWE(...)`；`^ok<0 → wfe 整维 INVALID`（非 max=0 假完美）。
5. **AUT/快照整体兜底（轮3 consistency major）**：写 `aut_converged`（E6：撞 MXC/发散标志）；每快照捕获包 error 守卫，任一快照整体失败/超时 → run INVALID；**天花板臂不收敛 = RED 证据（非 INVALID/GREEN）**。
6. **判据 fail-closed**：必需场×必需度量任一无效 → run `INVALID` 出局禁 GREEN。

### 4.5 target 模式结果键（轮4：加 stage 判别键 + per-dim 对象）

- **`stage` 判别键**（`baseline|A|B|C`）：机器可判，据此选 per-stage required_keys（补齐 §4.3 的 parse 路径校验闸）。**实现 locus（轮5 精确化）**：required_keys 强制校验在入口 `parse_codev_optimize_file`→`parse_codev_result_file`（`codev_batch.py:227`）；per-stage 做法=`parse_codev_optimize_file` 先传 `required_keys=()` 读出 stage，再由 optimize 层按 stage post-validate。`parse_codev_optimize_data`（`:409`）只消费已选定 data、不接触 required_keys（勿在此加校验致与入口重复）。
- **三维 per-dim 对象**（EFL/F#/IMH 各一）：`{actual, target, deviation, source: optimized|constructed|measured|seed_hold, status: applied|seed_hold, converged: true|false|not_applicable}`。**`deviation`/`converged` 仅当该 stage 施加了该维 target 才有意义**；未施加维输出 `actual + source=seed_hold + status=seed_hold + converged=not_applicable`，**不计入 achieved/GREEN**（消除"Stage A/B 被逼输出空/伪造偏差"）。`source=constructed` 维的 `converged` 仅表"构造 pin 经 RSI 实追迹验证守住"、**不计 GREEN attainment**（§6.3）。
- 其余：`mode` · 三快照全度量 + 各 `_valid_fields` + `required_field_count` · 三维 `*_converged` bool（§1.1）· `aut_converged` · 裸倍率数字 · 固定 `max_cycles/mxc/mnc/imp`（复现）。

## 5. 受控实验矩阵

### 5.1 Seed + 外推边界

- Seed-1=`US20170003482A1.zmx`（批次5 证可导入）；Seed-2=不同片数真实设计（闸2 baseline 自检后纳入）。
- **外推边界写死**：n=2 皆 wide/主摄 → GREEN 仅对"wide 族 × 所测偏移带"成立，不外推。窄域 GREEN 解锁**小规模扩样闸**（§1.2），非完整 harness。

### 5.2 偏移臂 + 天花板三态（轮3 testability major）

- **甜区臂**：EFL +10~15%。**天花板臂（负向对照）**：EFL +30~40% 或跨族。
- **天花板臂三态判读**（每态唯一下一步）：
  - `RED`(有数据但不收敛/像质不达=有效负结果)：算"机制到边界"，定可收敛半径上界。
  - `INVALID`(fail-closed 无数据)：回退中间偏移(+20~25%)重定天花板；**回退臂再 INVALID（轮5）→ tooling-blocked**（上界证据缺失、非 RED 非 no-go，交资深判是否投工具链，不无限回退）。
  - `意外GREEN`（负向对照意外收敛，轮6 补终态）：记**可收敛半径下界 ≥ 天花板臂偏移量**，派生更远天花板臂(+50%/跨族)重定真边界；**拿到 RED 拐点前不得据意外GREEN 单独判 go**。
  - 可收敛半径由多点 `|post−target|` 曲线定，非单点。

### 5.3 分阶 + Stage C YELLOW 决策分支

| Stage | 改动 |
|---|---|
| **baseline-lock 对照** | EFL=seed 自身。**措辞降级（轮3）**：仅"AUT 通用改善量级**参照**，差量含路径依赖噪声、**非净代价干净归因**"；仅两臂 EFL 收敛后像质同量级才允许资深参照 |
| **A（核心）** | 仅接缝1 EFL→target |
| **B** | +`fno`/EPD（E1 分支）；**实测 F# 漂移** |
| **C** | +场重建 target IMH（E2/E5/E8）；ANG→IMG 折算**由 target FOV+target EFL 同源导出**，禁 seed 角度×seed EFL |

**Stage C 硬约束 + defer/RED 分桶（轮3-4）**：
- **分桶判据机器化（轮4-5 · validity 闸先行）**："宏产没产出 IMH 数"不可靠（`^maximh` 预初始化 0、失败仍写 `image_height_y_mm=0`）。改用**宏侧显式 reconstruction-success 标志**：场重建块 emit `imh_field_valid`（成功锚定 target 场计数>0 且实追迹 `actual_imh_mm>0` 有限→1，否则 0）作 required_key。**判桶顺序（先 validity 后光学 · 轮5：防工具链失败误判 RED）**：① `validity_pass=False`（必需场/ray/WFE/distortion/E8 守卫任一失败）或 `imh_field_valid=0` → **INVALID/tooling-blocked（带 reason），非 RED**；② `imh_field_valid=1 且 validity 全过`后，IMH 实追迹出容差/像质崩 → **(b) RED**；③ NaN/缺键 → INVALID（第三条明确路径）。"fiddly"= `imh_field_valid=0`（工具链），不是自由声明、也不吞光学 RED。
- **(a) fiddly-defer** = **场转换工具链阻塞**：对"target convergence go/no-go"= **blocked/未解（非 go）**；至多派生"field-conversion debug spike candidate"作为**已识别的下一 blocker**。**禁称 conditional go**（轮4 Codex R4-C3：与 §1.2 no-go 触发自相矛盾）。A/B 结果单独命名"EFL(+F#) partial signal"。
- **(b) Stage C 真跑但 IMH 不达/像质崩** → RED 级 IMH 负结果，不被 defer 掩盖。
- 整体 **GREEN 要求 ≥1 seed Stage C 真成功**：场转换 + 真实 ray 覆盖 + 必过证据①派生FOV合理②必需场追迹成功③实测真实IMH落容差④**逐场物理视场角取 AUT 后实追迹主光线角（real chief ray，RSI 真实落点反算），禁用注入折算锚反算**（轮4：折算/校验同源无畸变会自抵消致假绿）；报告分列"注入折算像高"与"实追迹像高"，差即畸变项交资深。
- **最小闸条件展开**：先跑 Seed-1 baseline-lock + Stage A + 天花板臂（3 run）出首信号；B/C+Seed-2 **A 通过才展开**。**甜区 Stage A 若 INVALID（轮4）**：先按 §4.4 排查快照/宏失败根因重跑一次；仍 INVALID→记 **tooling-blocked（非 RED 非 no-go）**，交资深判是否值得投工具链（导入/度量）——与天花板臂 INVALID 回退（找可收敛半径）区分。

### 5.4 复现定向（轮3 minor）

**落 2% 阈 ±0.5% 带内的所有 case 必须重跑、要求逐位/同色一致**；无 borderline 时至少甜区 GREEN + 天花板臂各重跑一次（非"任取一颗"）。

## 6. 判据（机器客观维 · verdict 资深填）

1. **前置 fail-closed（§4.4）**：INVALID 出局。
2. **EFL 收敛 `efl_converged`**：`|post_aut.efl−target|/target < 2%` **且**方向对（朝 target 移动）。**（轮4：删"移动阈=应移动量1/3"——在 ≥10% 偏移的所有臂上数值恒不 binding=零判别力假守卫；≥10% 偏移下"落 target 2% 内"已隐含 EFL 真移动 ≥8%。**注**：通用 Mode3 客户可选任意 target，届时需一般移动判据，非本 spike 受控矩阵之责。）**天花板臂 partial-move**：`efl_converged` 只认"落 target 2% 内"。
3. **F#/IMH 几何达成 `f_number_converged`/`imh_converged`**（客观 bool，非像质判定 §1.1）：落**预设几何容差**内→converged=true。容差预定死：**F# 默认 8%、IMH 默认 2%**（run 前可改，不得留空——留空该维 fail-closed 判 INVALID）。
   - **constructed IMH 的 imh_converged 口径（轮5-6 调和）**：Stage C IMH 是 `source=constructed`（设 yim=target）。其 `imh_converged` **不是**"含畸变实追迹像高落 2% 硬阈"（轮6：那会把正常 barrel 畸变的真实镜头误判/误弹），而是 **"构造成功锚定 target 近轴像高 + 该场真实主光线可追迹（validity）"**——即构造守住且真实。**畸变项（实追迹像高 vs 近轴 target 之差）另出裸数字键**，喂资深报告（§6.4）、不进 imh_converged 硬阈、不进 validity。**自抵消假绿由 source-gate 挡（轮5）**：constructed 维不计 GREEN attainment，故 imh_converged=构造+可追迹 恒真也不冒领优化收敛、不虚抬 GREEN。（`^maximh=efy·tanF` 近轴仅作场排序/注入折算报告列，非达成硬阈源。）
   - **source 感知（轮5 major · 构造维≠优化达成）**：converged bool 的 **GREEN 达成贡献 gate 在 `source ∈ {optimized, measured}`**。`source=constructed`（Stage C IMH 设 yim=target、FNO-lock F#——由构造恒真、零优化信息）的维，converged 仅作**"几何 pin + 实追迹验证其守住"标注、不计入 GREEN attainment**（与 §4.5 `seed_hold 不计 achieved` 同构）。防"1 维优化 + 2 维构造 pin 伪装成三维达成"。
   - **per-stage 通过谓词（轮5 major · 消未定义"A 通过"/"甜区 GREEN"）**：`Stage A 通过 := efl_converged=true`（不看 seed_hold 的 F#/IMH）；`封顶 YELLOW` 仅当 **status=applied 且 converged=false** 的维触发（seed_hold 维豁免，与 §4.5 一致）；整体 GREEN 要求"所有 **applied 且 source∈{optimized,measured}** 维 converged=true + Stage C 真成功 + validity_pass"。converged 进 §4.5 per-dim 对象、允许 `not_applicable`（seed_hold 维）。
4. **裸像质（无阈无 bool）**：三快照双向倍率数字（post_aut vs seed_baseline **和** vs config_pre_aut **和** vs baseline-lock 参照）+ 畸变绝对值。
5. **资深填**：像质值不值得看、灾难与否、整体 verdict、良品率。

## 7. 非目标（YAGNI / 红线）

- ❌ 接缝4-6；不建 C1 harness；**不改 C1 spec**（§2.2 仅记录建议给 C1 owner，不执行）。
- ❌ 不碰玻璃可变（接缝2）。**F# 约束区分（轮4 reconcile）**：❌ 禁 **merit 加 F# 操作数**（与 EFL/像质在优化循环里打架的过约束，§2.2 判错）；✅ 允许 **FNO-mode aperture-solve 保 F#**（E1 分支：这是 aperture 系统定义、CODE V 几何重解 EPD 保 F#，非 merit 操作数、不与其他 target 打架），provenance 标 `constructed`。二者机制不同：前者塞进 merit 争自由度，后者是光圈定义。本 spike 走后者（若 E1 探针确认 FNO 锁 F#）或前者的对立面（EPD 模式实测漂移），**都不加 merit F# 操作数**。
- ❌ AI 不判**像质**良品、不 emit 三色 verdict、不 emit **像质**阈 bool（[EXPERT] 红线）；**几何 target 达成 `*_converged` bool 可 emit（§1.1，非像质判定）**。物理上机/Verify·Backplot/真值卡代填=红线上交。
- ❌ 不重启无人值守夜车。

## 8. 交付物

1. **闸2 Step-0 探针**（§3）+ 行为报告（**E1-E8**，每 Ex 结果列 probe-report required key；**E8 未产出不得进 v6/宏实现**）。
2. 宏改造（加法式三参数 + mode + 三快照 + per-stage 契约 + 全度量 fail-closed + AUT/快照兜底 + 双路径零回归）+ target 解析契约。
3. target 模式测试（mock 层，无 CODE V 亦绿；三快照/per-stage 契约/fail-closed 含 distortion 守卫/F# 活算/AUT 兜底/required_keys 缺失→INVALID 锚）；**现有 7 测保持绿**。
4. 离线 spike 脚本：最小闸条件展开（§5.3）真机 run + 复现定向 + 三态天花板。
5. **资深报告**：三快照+对照偏差表 + 有效字段 fail-closed 标注 + 可收敛半径 + 客观裸数字 flag + **go/no-go 决策框架（供资深，§1.2）**；三色 verdict 栏留空。

## 9. 对抗审查修订记录

- **轮1**（codex）4 findings → v2（fail-closed/三快照/ANG 转换/FOV gate）。
- **轮2**（codex R2 + 4 棱镜）5 blocker+7 major → v3（F# 经验测定/全度量/零回归不矛盾/Stage C 封顶/天花板对照/exit-gate 扩/三色分层等）。
- **轮3**（codex R3 + 5 棱镜）~10 blocker/major 全采纳 → **v4**：
  - `[BLK]` IMH 镜像错（同 F# 会漂）→ §2.1 IMH 改经验测定。
  - `[BLK]` F# 手柄自相矛盾（发 fno 反锁 F# 测不到漂移）→ §3-E1 分两支探针。
  - `[BLK]` 分母锁 seed_baseline vs 含 rel 1.0 时序互斥 + 抽象分数无宏支撑 → §4.4 用离散场"最大像高场"机器可判 + 分母随重锚切换。
  - `[BLK]` @dstpct 守卫无判据、DIX/DIY 或无 err 出口 → §3-E3 探针 + §4.4 守卫写死。
  - `[MAJ]` catastrophic_flag N× 阈越 [EXPERT] 线（三棱镜）→ §1.1 删 flag、只出裸倍率。
  - `[MAJ]` F# 加约束后门 vs §2.2.2 打架 → §7 明禁本 spike 加 F# 约束。
  - `[MAJ]` constructed vs converged 语义冲突 → §2.2 建议 C1 引 achieved_by 第三态。
  - `[MAJ]` exit-gate 越界改 C1 → §2.2 降为纯记录建议。
  - `[MAJ]` run 路径 required_keys(:356) 漏改 → §4.1 双路径零回归。
  - `[MAJ]` per-stage 契约缺失 → §4.3。
  - `[MAJ]` F# 失守无封顶（对比 Stage C）→ §6 F#/IMH 出容差封顶 YELLOW。
  - `[MAJ]` 天花板臂多落 INVALID 非 RED → §5.2 三态判读。
  - `[MAJ]` Stage C YELLOW 两桶混（fiddly-defer vs 真不达）→ §5.3 拆桶。
  - `[MAJ]` baseline-lock 差量归因谬误 → §5.3 措辞降级。
  - `[MAJ]` 窄域 GREEN 与投 harness 证据鸿沟 → §1.2 go 解锁小规模扩样闸。
  - `[MAJ]` AUT 不收敛/快照崩无兜底 → §4.4 aut_converged + 快照守卫。
  - `[MAJ]` 移动阈固定 2% 未逐 seed 自洽 → §6 改相对偏移量 1/3。
  - `[min]` GSD session Current Focus stale（我漏更新）→ 同步；复现定向；go/no-go 聚合框架；run 数膨胀最小闸。
- **v4 新增方法论（§0/§3）**：识别 7 条经验盲区（E1-E7）无法文档解，改为闸2 Step-0 探针 + 决策分支。
- **轮4**（codex R4 + 5 棱镜，带 A/B/C 分类）：**双方确认设计脊梁 + 经验 parking(E1-E7) 攻不动**（"§3 park 合理"/"方法论转变诚实"）；仅剩 ~15 项 A 类**契约/机器精度**尾巴，全采纳 → **v5**：
  - `[A]` F#/IMH 封顶=带阈 bool 与删 catastrophic 冲突 → §1.1 区分几何达成 `*_converged` bool(客观可 emit) vs 像质阈(资深)；§6.3 封顶归客观 bool。
  - `[A]` IMH 容差"待定"致 GREEN 不可执行 → §6.3 预定死 IMH 默认 2%（非经验盲区，纯设计常量），留空 fail-closed。
  - `[A-blk]` post_aut 分母切 target 场集无边缘下界→可注软场甩难场 → §4.4.2 加"含 ≥1 场归一像高 ≥ target_imh×(1−tol) 且有效"机器判据。
  - `[A]` Stage C 折算/校验同源无畸变自抵消 → §5.3 GREEN④ 改 AUT 后实追迹主光线角(RSI)，报告分列注入折算 vs 实追迹像高。
  - `[A]` E6 只写乐观分支(有收敛标志) → §3-E6 补最坏分支 fallback(机器代理 aut_diverged / \|post−target\| 曲线)。
  - `[A]` §4.1 二元 required_keys vs §4.3 三元 per-stage 矛盾 → §4.1 改按 stage 组装。
  - `[A]` per-stage INVALID 需 stage 但 §4.5 无 stage 判别键 → §4.5 加 stage 键 + per-dim {actual/target/deviation/source/status} 对象。
  - `[A]` §7 禁 F# 约束 vs E1 FNO 锁 F# 打架 → §7 区分 merit 操作数(禁) vs FNO aperture-solve(允, constructed)。
  - `[A]` Stage C "fiddly" 无 owner=可自由声明逃 RED → §5.3 机器化(产 IMH 数→(b)RED桶；只有宏没产 IMH 才 defer)。
  - `[A]` Stage C defer 同时是 §1.2 no-go 触发和 §5.3 conditional-go → §5.3 defer=blocked 非 go。
  - `[A]` 移动阈 1/3 在所有臂恒不 binding=假守卫 → §6.2 删。
  - `[A]` §4.4.1 distortion 无条件必需 vs §4.4.3 未定前不计入矛盾 → §4.4.1 distortion 改条件必需(E3 后并入)。
  - `[A]` 甜区 Stage A INVALID 无下一步 → §5.3 补 tooling-blocked 分支。
  - `[A]` target 参数无非法值校验 → §4 加 >0 有限校验契约。
  - `[A]` GSD session 顶部"已定决策"仍写构造即达(我第二次漏更)→ 同步。
  - `[B]` 漏 park 经验盲区：场重建后渐晕重解 → §3 增 E8。
  - `[C]` §0 "~10" 计数低估 → 状态行改。

- **轮5**（codex R5 + 5 棱镜）：**契约一致性棱镜首判 design-converged**；余 9 条 A 收敛到少数精确主题，全采纳 → **v6**：
  - `[A-blk]` converged bool 自抵消假绿（Stage C IMH 读近轴 `^maximh` 恒真、构造维当优化达成）→ §6.3/§4.4.2 实测像高绑 RSI 实追迹、converged GREEN 贡献 gate 在 `source∈{optimized,measured}`、§2.1 Stage C IMH 标 constructed。
  - `[A-blk]` §5.3 fiddly 判据用"产没产 IMH"不可靠（`^maximh` 初始 0）+ 工具链失败误判 RED → §5.3 改显式 `imh_field_valid` 标志 + validity 闸先行（失败=INVALID/tooling，非 RED）。
  - `[A]` §4.4.2 边缘下界量纲 bug（无量纲 vs mm）→ 改 `actual_imh_mm ≥ target_imh_mm×(1−tol)`。
  - `[A]` converged bool 缺 per-stage/not_applicable 语义、seed_hold vs 封顶矛盾 → §6.3 per-stage 通过谓词 + seed_hold 豁免封顶。
  - `[A]` §1.2 no-go 触发 vs §5.3 defer=blocked 互斥 → §1.2 三态裁决对齐（全 defer=blocked 非 no-go）。
  - `[A-min]` 中间场成分替换（N 守恒难场稀释）→ §4.4.1 逐档覆盖 seed_baseline 分档。
  - `[A-min]` 天花板回退臂再 INVALID 无收口 → §5.2 tooling-blocked 终止。
  - `[A/C]` §8 交付物漏 E8、§9 parking 计数、§4.5 parser locus 命名、探针自身失败/环境一致性 → §8/§3/§4.5 补。

- **轮6**（codex R6 + 5 棱镜）：**2 棱镜判 design-converged**（物理+provenance、整体一致性）；余 6 条 A 精确尾全采纳 → **v7**：
  - `[A-blk]` §4.4.2 把含畸变 RSI 塞进硬 validity 闸 → 正常 barrel 畸变(2~4%)真实镜头被误弹 INVALID（对偶洞）→ validity 用近轴+宽松容差 distortion-insensitive，畸变项另出裸数字喂资深、永不进 validity。
  - `[A]` §4.4.2 IMH 边缘下界未 per-stage 化 → Stage A/B 无 target_imh 却被判假 INVALID、最小闸首信号误路由 → 仅 Stage C 施加下界，A/B 用 seed-native 分母。
  - `[A]` constructed IMH 的 imh_converged 用含畸变 2% 硬阈会误判 → §6.3 改"构造+可实追迹"、畸变裸数字，自抵消假绿由 source-gate 挡。
  - `[A]` §4.4.1 中间场 ±tol 未定义 → 预定死默认 10% + 留空 fail-closed。
  - `[A]` §1.2 no-go"天花板臂无 RED 拐点" vs §5.2 回退 tooling-blocked 撞车 → §1.2 限定"真跑出数据但无拐点=no-go"、排除 INVALID/tooling=blocked。
  - `[A-min]` 天花板臂"意外GREEN"无终态 + Stage C 跨 seed mixed 无规则 → §5.2 意外GREEN 定义、§1.2 mixed 分 seed 裁决。
  - `[C]` §2.1 行号锚（codev_readout.py vs codev_optimize.py 宏 readout 块）→ 精确化。

**状态**：轮6 **2/5 棱镜判收敛**，余为纯精确尾（§4.4.2 per-stage+畸变出 validity、状态机裁决对齐），**无核心设计错**。**待轮7 验 A 类补净**——仅剩 B(经验-parked E1-E8)+C(cosmetic)即**设计层收敛**，转闸2 Step-0 探针（真机定 E1-E8）→ 探针回灌经验落地版。收敛判定=某轮双方仅剩 B/C 残留。
