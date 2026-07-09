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

- **status: 闸2 Step-0 探针完成 · v10 经验落地版（2026-07-09）**——8 轮对抗设计层收敛（workflow 5/5 + Codex approve）后，主公 ratify 转闸2 Step-0；`scripts/codev_behavior_probe.py` 真机跑 D:\CODEV115 **E1-E8 全定死**（§3.5 回灌）。**go-signal：EFL 拉 +12% 收敛 0.04%=③核心机制真机验通**（机制级、未测良品率）。
- hypothesis: 见上（接缝1+3 使 AUT 朝客户 target 收敛；EFL 唯一真优化维，F#/IMH 经验测定/构造）
- **探针关键结论**：E1 FNO 模式锁 F#（取"锁"支=constructed）｜E2 ANG 场 IMH 漂+12%｜E3 DIX/DIY 无 err→SPOTDATA 守卫｜E4 (FNO) 活算安全｜E5 ANG/FNO/渐晕0｜E6 无收敛码→EFL-hit 代理｜E7 确定性｜E8 此 seed trivial
- next_action: **实现完整宏改造**（加法式三 target 参数 + 三快照 + fail-closed + FNO 锁 F# + SPOTDATA 畸变守卫 + EFL-hit aut_converged + per-stage 契约，零回归保 7 测）+ mock 层测试 + 跑实验矩阵 → 资深 go/no-go 报告（良品率，[EXPERT] 判）
- test: （闸2 后）最小闸条件展开：Seed-1 baseline-lock+Stage A+天花板臂 3 run 出首信号，A 通过才展开 B/C+Seed-2；三快照量 EFL/F#/IMH/FOV/像质 vs target + fail-closed
- expecting: **EFL 是唯一确定真优化收敛维**（落 target 2% 内+移动达阈+方向对）；**F# 与 IMH 均经验测定、须实测漂移/达成，不假设构造即达≈0**（轮2-3 修正）；像质裸倍率数字，值不值得看由资深填（AI 不判良品）

## 实验矩阵 go/no-go 数据（2026-07-09 · 机器客观，良品率判断留资深）

`scripts/codev_target_experiment.py` 跑 5 颗原始专利 seed × (baseline-lock + Stage A/B 甜区 + 天花板)：
- **收敛率（机器客观）**：Stage A 甜区 +12% → **仅 1/5 seed 干净收敛**（US20170003482A1 dev~0）；3 颗 conv=0(dev 4-10%)；1 颗 tooling-blocked(hang)。
- **收敛半径**：Seed-1 +12% 收敛 / +35% 不收敛（dev 12%）。
- **像质（裸数字，资深判）**：即便 Seed-1 收敛，畸变 2%→8.4%、RMS ×2.5（冻结玻璃下）；多颗 seed 像质灾难(RMS 100-370µm)。
- **诚实信号**：**裸冻结玻璃 ③（只动曲率/厚度、玻璃冻结）良品率低**——收敛率不高、成功也劣化到量产线下，指向需玻璃可变(接缝2)/更多 DOF(非球面)/更好 seed-target 匹配。**machinery 通、naive 良品率低**=决定性 go/no-go 数据。
- **已修 bug**：`codev_batch` subprocess `text=True` 读 CODE V 非 UTF-8 输出崩 reader 线程→管道满→hang（改二进制读，24 测绿）。
- **待办 finding**：Stage B 显式 `FNO` 命令致宽视场主光线追迹失败(需 CRA/ray-aiming)；部分 dashed staging seed AUT hang(tooling-blocked)。

## 诊断：EFL 收敛"拉不动"=SETUP 非本征（2026-07-09 · 决定性）

主公令诊断 conv=0 seed 为何 EFL 拉不动。AUT .lis + 决定性对照实验：
- **EFL 约束是硬的、active**（.lis：`EFL target 5.263 value 4.699 active **`）——非软约束被淹没。
- **从 CYCLE 0 就 `RAY ERROR: REFL 4/14`（全反射）** + `Ray aiming not used` + `Frozen Thickness Violations`——快镜头(F/1.68)边缘光线 TIR → merit 从起点残废 → 拉不动 EFL。手册(LensSystemSetupRM p41)证："resetting the vignetting may be necessary"、优化时需 reference ray aiming。
- **决定性对照（US10281683B2 同 seed 同 target 只差光阑）**：原生 F/1.68 → dev 9.52% conv=❌；**缩到 EPD 1.5(F/3.1) → dev 0.00% conv=✅ 完美收敛**。
- **结论**：**"拉不动"100% 是 AUT/导入 setup 问题（边缘 ray TIR 挡住 merit），不是本征**。AUT 拉 EFL 的能力完全在。naive-macro 的低收敛率是 setup 假象。
- **对 go/no-go**：crux（可靠 EFL 收敛）是**可解工程问题**（光阑/渐晕/ray-aiming setup），非研究墙——探路阶展望改善。真良品率须在**修好 ray setup 的宏**上重测。

## 真良品率重测（2026-07-09 · 自动渐晕修好 ray-setup 后 · 主公 ratify 方案）

`run_codev_target_autovig`（宏加 `vignetting` 参数 + Python 爬梯搜最小收敛离轴渐晕，保 F#）重跑 5 seed × 4 臂（报告 `.planning/loop/codev-target-experiment-report-autovig.md`）：

- **收敛机制=已修好且可靠**：**甜区(+12%) 4/4 可追迹 seed 全收敛**（vs naive 旧 1/5）——US10281683B2 渐晕0.3/dev1.9%、US20140111876A1 渐晕0.2/0.72%、US20170003482A1 渐晕0/~0、US20170045714A1 渐晕0.3/1.2%；baseline-lock 4/4；天花板(+35%) 1/4 收敛（负对照成立，收敛半径真实）。**setup 假象已除，crux(可靠 EFL 收敛到客户 target)确认=可解工程，非研究墙。**
- **★但真良品率(冻结玻璃)依然低★**（[EXPERT] 判，裸数字）：收敛≠好设计。甜区收敛臂像质多数灾难——US10281683B2 RMS 16→153µm/WFE 0.2→8.2 波/畸变→8.2%；US20170045714A1 RMS 10→**553µm**/WFE→**49.6 波**；仅 US20170003482A1(原生收敛渐晕0) RMS→23.6µm/WFE→0.50 波 勉强"值得看"。**且 RMS 是在裁掉 20-30% 离轴瞳后测的=已偏乐观。**
- **结论（去掉 setup 噪声后的真信号）**：③ **machinery 可靠**、**naive 冻结玻璃良品率仍低**——指向下一杠杆（接缝2 玻璃可变 / 非球面 DOF / seed-target 匹配），与 spike 早前 "machinery通·naive良品率低" 一致但现在是**真值**（非 setup 低估）。良品率 go/no-go 最终判在资深。
- **tooling 修复（2026-07-09 · 主公 ratify 三项之一）**：US20180143405A1 全 4 臂 timeout 的真根因=**该 seed 在 v=0 时 S14 TIR flood**（.lis 洪水般 `ERROR - Total reflection at surface 14`，AUT 每轮重追失败光栅→CPU 拖过 180s），而 autovig rung-0(v=0) 超时把整个搜索 abort → 全臂 blocked。两修：① `codev_batch._kill_process_tree` 的 taskkill 由 text=True 改二进制读（中文 Windows taskkill 打 GBK 0xb3 会让 reader 线程 UnicodeDecodeError 崩，清理超时进程树时观测；`_coerce_output` errors='replace' 兜底）；② `run_codev_target_autovig` 加 `num_fields` 注入 + **每级超时/失败即吞并续爬**（rung-0 flood 超时不再 abort，高渐晕裁掉 TIR→跑得快）。**真机验证：US20180143405A1 recovered**（`e0.00:timeout e0.30:4.4% e0.50:4.9% e0.70:conv✅ dev~0 RMS 86µm`）——**甜区收敛 4/5→5/5**（该 seed 需重渐晕 0.7=弃 70% 离轴瞳，edge_used 已上报供资深判）。33 测绿+ruff 绿。

## 诊断 v2（2026-07-09 · 真机证伪 checkpoint 假设，根因更深）

主公 checkpoint 假设"reset vignetting + SET VIG"修收敛 → 真机实测**证伪**：

- **控制种子 US10281683B2 = 宽角快镜**：ZMX `FNUM 1.68`(像方 F#)、`FTYP` 角度场、`YFLN 0/20/40.5°`、`VDYN/VDXN/... 全 0`(**设计本身零渐晕**)、**无 `DIAM`**(无物理孔径)。其 Zemax 形态靠 **ray aiming** 维持宽+快光束物理性；`ZEMAXOS_TO_CV` 导入丢弃 ray-aiming/渐晕/MEMA → CODE V 追全瞳 → **离轴边缘光线在 S4/S14 TIR**(`RAY ERROR: REFL 4`)。
- **`SET VIG`/`SET VIY` = no-op**(真机 dev 9.97%＝baseline 逐位相同)：零渐晕+无用户孔径→无可裁剪基准。`SET APE`/`SET CAP`+`SET VIG` 仅部分改善(6.76%/7.92% 仍不收敛)——孔径由已失败 reference ray 派生=循环。
- **真 lever = 显式渐晕因子裁剪优化光栅**(真机实测，**F# 全程保持 1.68 不变**——渐晕裁的是优化 ray grid≠光圈)：`VUY/VLY/VUX/VLX 0.40 全场`→**conv✅ dev~0**；`0 0.50 0.50`(仅离轴 2/3 场)→**conv✅ dev~0**(**证 TIR=离轴宽角光线**，on-axis F1 裁剪=0 仍收敛)；`0.30` 离轴 / `0.20` 全场→不足未收敛。
- **结论**：机制(AUT 拉 EFL→target)光线可追迹时可靠；native-F# 收敛**可达**。但渐晕量须 per-seed 有原则地定——种子无渐晕/孔径/ray-aiming 数据可派生→**无 seed-data 驱动的自动量**。**checkpoint 假设的实质修正，方法论 fork 待主公裁**(固定标准化渐晕 / 自动搜索至光线追迹 / 孔径分级 optimize)。
- **像质另议**([EXPERT])：+12% EFL 冻结玻璃即便收敛 RMS 点列 56–232µm、畸变 8–10%——良品率判分项，非本收敛机制问题。
- 探针留痕：`scratch_diag/probe_setvig.py`(SET VIG no-op)、`probe_field.py`(渐晕 lever+离轴定位)、`probe_ape.py`(SET APE/CAP+无 DIAM)。

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
