# FNO 阶梯引擎真机试点判读（2026-07-11 · 2 seed · 全矩阵 go/no-go 输入）

> 边界：只出数据与工程判读，良品/合格判定在资深（[EXPERT] 红线）。
> 证据：本目录 per-seed `ladder-result.json` + per-rung 子目录（seq/tsv/lis 全文）。
> 配置：rung_count=3（几何级距）、fnum_tolerance_pct=8.0（spec §6）、timeout 120s/CODE V 调用、EFL 锁 native（隔离 F# 维）。

## 试点结果总表

### 收紧臂：US20170003482A1（native 2.32 → target 2.0，-14%；对照臂唯一干净归因 seed）

| rung | target F# | measured F#（EFL/EPD 活算） | param 达值(8%) | ray_grid | EFL dev | RMS(µm) | edge |
|---|---|---|---|---|---|---|---|
| 0 (native) | — | 2.319991 | — | ok | ~1e-10 | 3.90 | 0 |
| 1 | 2.208009 | 2.208012 | ✅ | ok | ~1e-14 | 4.11 | 0 |
| 2 | 2.101432 | 2.101432 | ✅ | ok | ~1e-11 | 10.88 | 0 |
| 3 | 2.000000 | 1.999994 | ✅ | **chief-ray-missing (MISS 4)** | ~1e-13 | 28.68 | 0 |

**`target_achieved = False`**（accepted_final=None；last_measured_rung=3 如实回答"爬到了末级"）。

### 放松臂：US-20260160979-A1-e3（native 1.68 → target 2.68，+60%；全绿 seed）

| rung | target F# | measured F# | param 达值 | ray_grid | EFL dev | RMS(µm) | edge |
|---|---|---|---|---|---|---|---|
| 0 (native) | — | 1.680001 | — | ok | ~1e-11 | 7.08 | 0 |
| 1 | 1.962989 | 1.962991 | ✅ | ok | ~1e-14 | 6.17 | 0 |
| 2 | 2.293646 | 2.293649 | ✅ | ok | ~1e-11 | 3.95 | 0 |
| 3 | 2.680000 | 2.680002 | ✅ | ok | ~1e-12 | 3.72 | 0 |

**`target_achieved = True`**（accepted_final=rung3，measured 2.6800025）——**首个真机 F# 达 target 且四条件全绿的完整案例**。像质随放松同步改善（RMS 7.08→3.72µm，裸数字供资深）。

## 四个验证点逐条判读

1. **per-rung 双维记录真机成立** ✅：收紧臂 rung3 就是活案例——`fno_param_achieved=True`（measured 1.999994 vs target 2.0）+ `aut_converged=True`（EFL dev ~1e-13）+ `ray_traceable=False`（chief-ray-missing）。若无双维拆分，这一级会被读成"完美达标"（Stage 2 采证预言的双重假阳性形态，真机原样复现）。
2. **ray_grid 分类落盘** ✅：每 rung 的 `ladder-result.json` 含完整分类 dict（category/refl/miss/normal_completion/abnormal），与该 rung 子目录 .lis 全文对得上。
3. **target_achieved 判定与 .lis 证据一致** ✅：人工核验 rung3 .lis 实含 4 条 `RAY ERROR: MISS`、0 条 REFL——ray_grid=(chief-ray-missing, 0, 4) 逐位一致；且与 Stage 2 探针同格（tighten 2.0 → MISS 4）**跨 harness 复现**（探针短 AUT 2 cycle vs 阶梯完整 AUT 25 cycle，同一失败模式同一计数）。
4. **超时/吞并续爬** ⚠️ 试点未触发（两颗 seed 全 rung 成功，无 error/timeout rung）——该路径仅有 mock 覆盖（4 个 mock 测试），真机触发要等全矩阵里的难 seed（如 95° 超广角）。如实标注：试点不证明该路径真机行为。

## 试点带出的新发现（工程判读）

1. **收紧失败边界被阶梯精确定位**：US20170003482A1 在 2.10 光栅仍干净、2.00 出 MISS——"可干净收紧下限"落在 (2.00, 2.10) 区间。阶梯天然是二分定位工具，全矩阵可产出 per-seed 收紧下限数据（资深判断"这颗 seed 能收多紧"的直接证据）。
2. **★引擎真实缺口：autovig 判据与 ray 维脱钩★**：全部 8 个 rung edge=0——autovig 只在 EFL 不收敛时爬渐晕，而 rung3 EFL 收敛（dev~1e-13）所以渐晕从未启动，chief-ray-missing 光栅未被清理。**渐晕本是裁病灶光线的工具，但 autovig 不知道光栅带伤**。改进方向（下一铲，加法式）：ladder 检测到目标 rung `ray_traceable=False` 时，可选对该 rung 用非零渐晕重试（复用既有 vig ladder，判据从 EFL-hit 扩为 EFL-hit AND ray-clean）。这可能直接把收紧臂救成 target_achieved——但需真机验证，不提前背书。
3. 收紧臂像质恶化梯度（3.9→4.1→10.9→28.7µm）与光栅病灶出现同步——像质与 ray 维互为佐证。

## 全矩阵 go/no-go 建议（判在 orchestrator/主公）

**建议：GO，但矩阵设计按试点新知调整。**理由与预算：

- 引擎四条件判据真机成立、证据链完整可复核（json+lis 全文）、无 tooling 故障。
- 试点耗时实测：收紧臂 4 rungs ~3 分钟、放松臂 4 rungs ~2 分钟（全部 edge0 一次通过）。**预算模型**：干净 seed ≈ (1+rung_count) × ~40s；带伤 seed 每 rung 最坏爬满 7 级渐晕 × 120s ≈ 14 分钟/rung。
- **矩阵建议**（≥8 seed）：放松臂优先（native 对照 §8 显示放松可"免费"达标甚至清病灶，预期高 target_achieved 率=快速积累正面证据）；收紧臂选 native 对照干净/轻伤的 seed（US20170003482A1/US8908290B1/US-11940597-B2-e6/US20210165194A1）；95° 超广角（US20180143405A1）若入列需 rung 级 timeout ≥180s 且预期 blocked=真实负对照。粗估 8 seed × 双方向 ≈ 40-90 分钟真机窗。
- **前置决策项（NEED orchestrator）**：是否先落"ray-aware autovig 重试"（上述缺口 2）再烧全矩阵——不落则收紧臂预期大量 `target_achieved=False`（如实数据，也有价值：定位各 seed 收紧下限）；落则多一铲工程+mock 测试（~1 commit），矩阵产出的"达标率"会更好看但引擎改动需再过一轮对抗审查。
