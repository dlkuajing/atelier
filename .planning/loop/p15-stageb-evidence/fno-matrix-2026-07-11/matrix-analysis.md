# P15 FNO 阶梯全矩阵 — 失败维度分析与判读（2026-07-11）

> 边界：只出数据/分类/工程判读，良品判定在资深（[EXPERT] 红线）。逐格证据：本目录 per-seed `ladder-result.json` + per-rung seq/tsv/lis 全文（含 ray_retry/ 子目录逐 edge 证据）。

## 0. 总表（14 ladder / 12 seed，ray-retry 0.2→0.5 开启）

| 组 | 达标 | 明细 |
|---|---|---|
| 放松臂 | **3/9** | ✅165194→2.4 ✅3482→2.4 ✅8908290→2.4 ｜ ❌11940597→4.0 ❌12443014→4.0 ❌12372756→4.0 ❌10281683→3.0 ❌111876→3.0 ❌330891→2.4 |
| 收紧臂 | **2/4** | ✅**3482→2.0（试点失败格翻正）** ✅8908290→1.8 ｜ ❌165194→1.8 ❌11940597→2.0 |
| 95° 负对照 | blocked=True ✓ 如预期 | 143405 rung0 timeout（180s）→ fail-closed 停梯 |

## 1. ★试点失败格翻正 = ray-aware retry 修复直接验证★

US20170003482A1 tighten→2.0（与试点逐参数同格）：试点 rung3 chief-ray-missing（MISS 4）失败；本矩阵同 rung3 **retry e0.2 一发即中**（`e0.2:ok/conv`）→ `target_achieved=True`，accepted_final measured 2.0000、effective_edge_used=0.2、quality_note 裁瞳口径在案。**引擎缺口（autovig 与 ray 维脱钩）的修复在真机上闭环。**同样值得记录：8908290_tighten rung3 爬满 retry 阶梯到 **e0.5 才清**（e0.2/0.3/0.4 全 TIR）——证明 retry 阶梯逐级设计必要，0.5 上限刚好够用。

## 2. 逐格失败维度归因（9 个 False 格，coordinator 点名）

四条件 = status·measured / fno_param / aut_conv(EFL) / ray_traceable。**逐格读数后的分维统计：param 维失败 0 格、EFL 维失败 0 格；7 格卡 ray 维（目标 rung TIR）、2 格卡 rung-未到（timeout error rung）**。所有可解析目标 rung 的 measured F# 均逐位达 target（param=True）且 EFL 保持（conv=True）——失败 100% 不在 F# retarget 机制本身。

| 格 | 目标 rung 状态 | 卡在哪一维 | retry attempts 轨迹显示什么 |
|---|---|---|---|
| 11940597_loosen→4.0 | param✓ conv✓ **ray✗ TIR R3** | ray | e0.2-0.5 全试：TIR↔chief-ray-missing 交替，渐晕改变病灶形态但清不净（注意 r2=F/3.85 曾天然 clean——**非单调**） |
| 12443014_loosen→4.0 | param✓ conv✓ **ray✗ TIR R4** | ray | 4 档全 TIR；REFL 随放松单调降（53→4）但不归零；r0 retry 还见 e0.2 timeout（吞并续爬真机第三例） |
| 12372756_loosen→4.0 | param✓ conv✓ **ray✗ TIR R20** | ray | 4 档全 TIR，MISS 恒 5（native 对照同值=固有份额），渐晕对该份额零效果 |
| 10281683_loosen→3.0 | param✓ conv✓ **ray✗ TIR R1/M1** | ray | 4 档全 TIR；但 **r2(F/2.47) retry e0.4 曾清到 ok 被采纳**——同 seed 更松的 r3 反而清不掉=非单调第二例 |
| 111876_loosen→3.0 | param✓ conv✓ **ray✗ TIR R1** | ray | 4 档全 TIR，残余仅 R1 |
| 330891_loosen→2.4 | param✓ conv✓ **ray✗ TIR R1** | ray | 4 档全 TIR，残余仅 R1 |
| 11940597_tighten→2.0 | param✓ conv✓ **ray✗ TIR R39** | ray | 4 档全 TIR（R14→48→39 随收紧爆增，探针预言的 45 倍放大复现） |
| 165194_tighten→1.8 | r3=**error(timeout 120s)** | rung 未到 | r0-r2 全部 retry 采纳（e0.2/0.2/0.3）后全绿，末级 AUT+渐晕重解拖时超 120s——**建议 180s 重跑单格** |
| 143405_loosen（负对照） | r0=error(timeout 180s) | rung 未到（native 基点失败） | 预期行为：TIR-flood seed，fail-closed 停梯不猜测续爬 ✓ |

**retry 采纳 0 的格共同点**：全部是 native 对照即带伤的 seed（§8 固有病灶），且渐晕 0.2-0.5 四档下 REFL 计数变化小或形态漂移不归零——**离轴均匀渐晕裁不到这些病灶光线**（native 对照 MISS/REFL 固定份额 + 非单调残余 R1-2 两个证据都指向：病灶不在被裁的离轴上/下缘光锥内，可能在轴上/全瞳光线或三快照度量段的 SPOTDATA/RMSWE 全瞳追迹里——**当前 ray_grid 按 .lis 全文分类，无法区分"AUT 优化光栅病灶"与"快照度量段病灶"**，这是下一步定位工作的明确切口）。

## 3. 放松臂 3/9 低达标：本征还是工程可解？（对照任务书 ≥90% 判据）

**结论：不是 F# 机制本征，是 seed 固有光栅病灶的清理能力问题——按 native 固有伤情分层后规律干净：**

| native 对照伤情（§8） | 放松臂达标 | seed |
|---|---|---|
| clean / 轻伤（REFL 0-6 或 MISS≤6） | **3/3 = 100%** | 3482(ok) 165194(R3) 8908290(M6) |
| 中伤（REFL 11-13） | 0/2 | 330891(R13) 111876(R11) ——目标 rung 残余仅 **R1** |
| 重伤（REFL ≥44） | 0/4* | 12443014 12372756 10281683 11940597*(R4 但收紧爆增) |

任务书"放松 ≥90%"的隐含前提是光栅可清理；native 对照（§8，矩阵设计前已知 10/12 固有带伤）本就预示全池达标率会被固有病灶压低。**量化边界（本矩阵 N=9 实测）：放松达标率 = 100%（native REFL≤6）/ 0%（native REFL≥11）**，分界带窄且干净。工程可解性分层：
- **330891/111876/10281683-r3（残余 R1-2）**：一步之遥。需要的不是更大渐晕，而是病灶光线**定位**（.lis 归段：把分类器从全文升级为按宏段归属——AUT 段 vs 三快照段；若在快照段，属度量口径而非优化光栅问题）+ 针对性裁剪（XY 非对称/per-field 差异化）或 ray-aiming（WRX/WRY pupil shift，手册 p41 指向的正路）。**判断：工程可解，1-2 铲量级，未验证。**
- **重伤 seed（残余 R4-39）**：渐晕工具天花板已到。需要 ray-aiming/孔径重建级别工具，性质接近"seed 数据修复"（与 P17 exact-source_zmx、repair_legacy_zmx_glass 同族），不是 F# 引擎的职责边界。**判断：本矩阵范围内如实不可达，另立工单。**

## 4. CONVERGED_FIELDS 扩 fnum 建议（判在主公——红线事项，证据已备）

**建议：带条件扩（gate 在编排层），不做无条件扩。**

- 支持扩的证据：①F# 系统参数达值维 100%（全部可解析目标 rung measured 逐位达 target）②EFL 维 100% 保持 ③四条件 gate 在 14 ladder 真机上 **0 假阳性**（所有 achieved=True 格的 lis 证据人工核验一致；所有带伤格被如实拦下）④试点失败格被 retry 翻正=引擎修复闭环。
- 反对无条件扩的证据：全池达标 5/14——"fnum 可收敛"对固有带伤 seed 不成立，无条件标注=对 64% 的池提前标注未验证能力（诚实红线）。
- **条件扩形态**：CONVERGED_FIELDS 增 "fnum"，但仅对 `run_codev_target_fno_ladder` 产出且 `target_achieved=True`（即 accepted_final 非 None）的候选生效——gate 本身已被本矩阵证明 fail-closed 可靠。C1/scorecard 侧按 accepted_final 的 per-rung 证据（measured_fnum/effective_edge_used/ray_grid/quality_note）如实展示。
- 备选（更保守）：暂不扩，等 §3 的残余病灶定位铲落地、达标池扩大后再议。

## 5. 建议后续（按杠杆排序，供 orchestrator 排铲）

1. **165194_tighten→1.8 单格 180s 重跑**（~5 分钟）：大概率翻正 → 收紧臂 3/4。
   **→ 已执行（2026-07-11 同日，证据 `US20210165194A1_tighten_180s/`）：预测被证伪**——180s 仍 rung3 timeout（r0-r2 与原矩阵一致全绿，retry e0.2/0.2/0.3 采纳）。结论修正：不是 timeout 预算问题，是该 seed（95° 超广角）在 F/1.8 收紧下 AUT 本身拖死（TIR-flood 家族行为）。**负结果的正面产出：该 seed 可达标收紧下限被阶梯定位到 (1.80, 1.864]**（r2 F/1.864 四条件达标）。收紧臂维持 2/4；若后续要精确下限可在该区间内加密 rung（非本铲）。
2. **.lis 归段分类**（离线铲）：ray_grid 增加病灶宏段归属（AUT vs 快照度量）——直接决定残余 R1-2 格是"优化光栅真伤"还是"度量口径噪声"，是 §3 分界的关键证据。
3. **ray-aiming（WRX/WRY）探针**（下一真机窗）：对残余 R1-2 的 3 格试 pupil-shift，验证"一步之遥"判断。
4. 重伤 seed 光栅修复立独立工单（seed 数据修复族，非 P15 范围）。
