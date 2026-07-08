---
status: investigating
trigger: "③优化落地最小可行性 spike（北极星 go/no-go 命门）：改 CODE V AUT 优化宏的接缝1（EFL 解锁朝 target）+ 接缝3（加客户 F#/IMH 目标），验证优化能在真实 seed 上朝一个≠seed自身的客户 target 收敛且像质不崩。"
created: 2026-07-08
updated: 2026-07-08
mode: attended-spike
note: "本 session 由主公 attended 驱动，非自主 session-manager 循环（红线：引擎级难活+需资深判断）。每闸口停等主公/Codex。"
---

# Debug/Spike Session: codev-target-convergence

## 待验假设（Hypothesis）

改 `app/core/engines/codev_optimize.py` 的 AUT 优化宏：
- **接缝1**（`:230` `EFL = ^baseline_efl_y_mm`）解锁 → `EFL = {target_efl_mm}`（朝客户 target，非 seed 自身焦距）；
- **接缝3**（merit/系统配置，现仅横向色差+RMS点列）加客户 **F#（光圈）+ IMH（视场/像高）** 目标；

能让 CODE V AUT 在 1-2 颗真实 ZMX seed 上，真正朝一个 **≠seed自身** 的客户 target 收敛（EFL/F#/IMH 独立、FOV 派生），且像质（RMS点列/波前/畸变/MTF）不崩溃。

## 已定决策（主公 ratify · 2026-07-08）

1. **独立目标集 = {EFL, F#, IMH}，FOV 派生**（手机主摄惯例：传感器 IMH 硬给定）。
   - 物理耦合事实：`F# = EFL/EPD`；`IMH ≈ EFL·tan(半FOV)·畸变映射` → 四量只 3 独立。
   - **落地手柄 + provenance（轮2-4 修正，supersede 下方旧措辞）**：EFL=AUT 一阶约束（**唯一确定的优化收敛维**）｜**F#=经验测定**（aperture 模式定是否漂，E1 探针；用 EFL_real/EPD_real 活算实测，不假设构造即达≈0）｜**IMH=经验测定**（ANG 场随 EFL 漂，Stage C 场重建后才锚，E2/E5/E8；实测真实 IMH）｜FOV=派生量只测量。
   - ⚠️ **已废旧措辞**："F#/IMH=系统光圈/场定义**构造即达**"是 v1-v2 说法，轮2-3 对抗证其为一阶物理错（AUT 拉 EFL 时 F#/IMH 同因同源地漂），**已 supersede，勿按旧措辞起手**。达成一律以 post_aut 实测 + spec §6 预设几何容差（F# 8%/IMH 2%）判。
2. **2 颗真实 seed（不同片数/规格）+ 受控偏移 target**（AUT 是局部优化器，target 太远不收敛；"多近还能收敛"本身是良品率的一部分）。

## 范围铁律

- 只做接缝1+3；**不碰接缝4-6**（applied_to_payload / checklist 自动 apply / payload delivery）。
- **加法式改造**：新增可选 target 参数；提供时切 target 模式，**不提供则保持现有 baseline-lock 行为**（现有测试全绿，默认路径零回归）。
- LLM 禁碰数值坐标（优化=CODE V 宏 + 确定性解析）。
- 良品率最终判断权在资深（[EXPERT] 红线，AI 只产候选出数据，不下"合格/良品"判定）。
- 物理上机 / 师傅 Verify·Backplot / 真值卡代填 = 红线，必上交主公。

## 工作流闸门（attended）

1. **闸1（当前）**：出接缝设计 spec（耦合决策 + 宏改造方式 + 受控实验矩阵）→ 主公 ratify + 独立单发后台 Codex adversarial-review（复核"是否真朝客户 target 而非 seed 自身收敛"）。**不先碰引擎代码。**
2. 闸2：过闸后改宏（加法式）+ 加 target 模式测试（mock 层，无 CODE V 亦绿）。
3. 闸3：真跑 CODE V（D:\CODEV115）抓 before/after 数据。
4. 闸4：出资深 go/no-go 报告（AI 只出数据不代判）。

## Current Focus

- hypothesis: 见上（接缝1+3 使 AUT 朝客户 target 收敛）
- next_action: 对抗轮4 验 spec v4 设计层补净 → **待主公 ratify v4** → 闸2 Step-0 CODE V 行为探针（E1-E7）→ 改宏
- test: （闸2 后）最小闸条件展开：Seed-1 baseline-lock+Stage A+天花板臂 3 run 出首信号，A 通过才展开 B/C+Seed-2；三快照量 EFL/F#/IMH/FOV/像质 vs target + fail-closed
- expecting: **EFL 是唯一确定真优化收敛维**（落 target 2% 内+移动达阈+方向对）；**F# 与 IMH 均经验测定、须实测漂移/达成，不假设构造即达≈0**（轮2-3 修正）；像质裸倍率数字，值不值得看由资深填（AI 不判良品）

## Evidence

- 2026-07-08: 本地 main 曾落后 origin/main 21 commit，已 pull 对齐至 7177325；spike worktree D:\atelier-opt3 从此切出。
- 2026-07-08: 代码核实 `codev_optimize.py:230` 确为 `EFL = ^baseline_efl_y_mm`（锁 seed 自身焦距）；merit 仅横向色差(`:231-233`)+RMS点列(`:234-236`)；光圈/视场继承自导入 ZMX，宏未碰。
- 2026-07-08: 现有真机冒烟测试 `tests/test_codev_optimize.py:319` 断言 `after.efl ≈ before.efl (rel 2%)` = 把"锁 seed 焦距"写死为正确行为 → target 模式需新路径+新测试，不污染默认。
- 2026-07-08: CODE V 在位（D:\CODEV115\codev.exe）；data/zmx/ 348 颗 seed，文件名编码自身规格。
- 2026-07-08: worktree 依赖装好，`tests/test_codev_optimize.py` **7 passed 含真机 CODE V 冒烟**（回归基线绿 + CODE V 端到端可跑证实）。
- 2026-07-08: Codex adversarial-review 轮1（job b1rtn65b6）verdict=needs-attention，4 findings（3 high+1 medium）全"防假绿"，亲验代码后全采纳 → spec v2 加固（三快照/fail-closed 有效字段/ANG 场转换/FOV exit gate）。
- 2026-07-09: 对抗轮2（Codex R2 job bl5g71zkm + 4棱镜 workflow wauwwqu8c）双方 needs-attention，共 5 blocker+7 major+4 minor 全采纳 → spec v3。最深一刀=**F# "构造即达≈0" 是一阶物理错**（AUT 拉 EFL 时 F# 会漂），推翻 v2 断言，改经验测定。另修：fail-closed 漏畸变/波前、§3.1↔§3.3 零回归自相矛盾、Stage C defer 仍出 GREEN、无天花板对照、三色 label 越 [EXPERT] 线等。
- 2026-07-09: 对抗轮3 进行中（Codex R3 bzlpx4p8x + 5棱镜 wcqpdz56i，攻 v3 修复本身+完整性）。

## Eliminated

- 2026-07-08 [设计层] "把 before 快照放在 target 配置后" → 会把配置损伤藏进 before 致假绿（Codex F2）→ 改三快照。
- 2026-07-08 [设计层] "IMH 直接 yim 覆盖" → ANG 场下只证明字段被重定义非收敛（Codex F3）→ 显式场类型转换 + 必过证据。
- 2026-07-08 [设计层] "复用现有度量直接判像质" → 追迹失败被伪装成 RMS=0/MTF=1 假完美（Codex F1）→ fail-closed 有效字段计数。
