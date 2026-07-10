# Phase 13 铲 1：真实玻璃 snap 设计

日期：2026-07-11
状态：设计 + 纯 Python 离线 spike；**不接** `codev_optimize` 主链

## 1. 目标与边界

把 AUT 在塑料 GLA 域内产生的 fictitious model glass，确定性映射为真实材料**候选提议**。
AI/LLM 不参与牌号、坐标或数值计算。离线核不是牌号写回授权器：无论候选距离多近，均须
通过真机校准后的阈值、material-region identity 硬闸和写回后回验才可落真实牌号。（B1、B2）

本铲只交付算法契约和离线核。固定真实玻璃、短 AUT、三快照、ZMX 写回及 scorecard
接线属于铲 2，须在真机窗口验证后实现。

## 2. 已证实事实与证据边界

| 事实 | 证据 |
|---|---|
| GLASSFIT 用 `Nd` 与 `dn=(Nd-1)/Vd` 的接近度，不考虑 stain、bubbles、partial dispersion、availability 等 | `D:\CODEV115\macro\glassfit.seq:16-23` |
| 宏参数 `disp_factor` 表示色散差相对 Nd 差的权重；宏按当前波长把它换算成 `dispFac` | `glassfit.seq:68-77,107-112` |
| 宏实际计算 `dispFac = ((wl w1)-(wl wl))/170.14 * (disp_factor*50)`；标准 F/C 跨度下默认参数 1 的有效色散权重约 50，FGW 改变时还会随首末波长变化 | `glassfit.seq:20-23,107-112`（B1） |
| 实际排序距离为 `sqrt(delta_Nd² + (delta_dn*dispFac)²)` | `glassfit.seq:666-687` |
| 官方宏需要选目录、任务、面范围并回答提示，是交互式流程，不能原样塞进无人批跑 | `glassfit.seq:156-200,303-330,421-423,534-580` |
| CODE V 目录名称不是跨目录唯一；目录可列索引/可用性，停产材料仍可能为兼容旧设计而保留 | `LensSystemSetupRM.pdf` 印刷页 406、409（PDF 页序约 420、423） |
| fictitious 与 real 即使 Nd/Vd 相近，partial dispersion 差异仍可能显著影响二级色差 | `LensSystemSetupRM.pdf` 印刷页 410（PDF 页序约 424） |
| 当前仓库批跑以 `.seq → codev.exe /B → BUF EXP → Python parse` 取结构化结果，不抓 stdout 数值 | `app/core/engines/codev_batch.py:1-4,142-188` |
| 当前 target AUT 用 `GLC S^s 0` 放开玻璃，并注入 GLA 凸包 | `app/core/engines/codev_optimize.py:604,687-711` |
| 当前读数已有 EFL 与 RMS WFE 结构；RMS WFE 调 `RMSWE` | `app/core/engines/codev_optimize.py:54-81,1686-1742` |
| 仓库确定性材料表及 H-LAK53A 的 Python 值 | `app/core/zmx_materials.py:27-52`（H-LAK53A 在 46 行） |

`Optimization.pdf` 第 9 章/印刷页 201 起含 Glass Expert；本铲没有据此推断可直接批跑的
Glass Expert 命令。如何用批处理冻结目录玻璃、如何设置短 AUT 周期，均列为**待真机验证**。

## 3. Python 确定性 snap

### 3.1 输入目录

默认候选目录从 `MATERIAL_ND_VD` 中显式筛出手机镜头塑料域真实牌号：ZEONEX、OKP、
EP、APEL、SP3810。不能把 GLA 探边点、PMMA/PC 抽象角点或未知 placeholder 当真实牌号。
spike 用 frozen `CatalogEntry(catalog_id, glass_name, version, nd, vd)`，结果携带完整 entry；
字符串 mapping 接口已删除，同名跨目录可表达，唯一身份是 `(catalog_id, glass_name, version)`。
未来目录还必须携带独立的 spectral-definition provenance；因 CODE V 名称跨目录不唯一，
最终标识不能只有 glass name（手册印刷页 406）。（M4）

### 3.2 距离与确定性

对 target 与每个目录材料计算：

```text
dn = (Nd - 1) / Vd
D  = sqrt((Nd_target - Nd_real)^2
          + (disp_factor * (dn_target - dn_real))^2)
```

这是 **Atelier metric**：借用 GLASSFIT 的 `(Nd,dn)` 坐标系，但不声称同款距离；权重与
阈值均待真机校准。官方宏的有效默认色散权重约 50，而非 spike 默认 1。反例为 target
`(1.53,20)`：权重 1 最近邻是 `ZEONEX-E48R`（D≈0.0170472），权重 50 最近邻是
`SP3810`（D≈0.1201734），足以翻转牌号。若未来逐字节复刻 GLASSFIT，必须捕获同一 CODE V
run 的 FGW/波长并复刻上述 `dispFac`，不得沿用 Atelier 参数名冒充等价。（B1）

`dn=(Nd-1)/Vd=nF-nC` 只在 target 与 catalog 使用同一 C-d-F/FGW 三线定义时成立；两者
必须带非空且完全一致的 spectral-definition provenance，不一致或缺失即 fail closed。

输入、目录值和权重必须有限；`Nd>1`、`Vd>0`、`disp_factor>=0`。距离相同按牌号字典序
打破平局，保证跨运行稳定。`D <= 0.01` 仅作 spike 提议注记，严格包含等号且不使用
`isclose` 暗扩边界。五牌号 dn 跨度为 0.02079693，0.01 已占 **48.1%**；两轴虽无量纲却
无相同像质敏感度，因此该值不是 CODE V 容差或写回安全线。须以 per-element perturbation /
整机响应分布（至少按谱域/材料族分层）ratify 权重和阈值；此前只产 nearest proposal。（M1、M5）

### 3.3 material-region 原子单位与写回硬闸

1. snap 原子单位是**材料区间/元件**，不是裸 surface。铲 2 写回前必须由相邻界面、厚度/
   介质区间、cemented/air gap、dummy、NSS、zoom position 建立并测试唯一 identity。
2. identity 建不起来即 `withheld`；禁止先试写再靠整机指标兜底。同一 identity 在写回计划中
   必须且只能对应一个 `(catalog_id, glass_name, version)`，冲突即 withheld。
3. 写回后须由 CODE V 完整材料 readback 核对 identity 与 catalog ID；不一致为
   `catalog-conflict`，不得授予 snapped 身份。（B2）
4. 离线核对每个 identity 只提议最近邻，保留完整目录身份、`delta_Nd/delta_dn/distance/weight`。
5. 所有 identity 选择完成后才进入整机冻结与全局回验；局部距离小不代表整机像质可接受，尤其
   GLASSFIT 明确未考虑 partial dispersion（`glassfit.seq:16-23`；手册印刷页 410）。

## 4. snap 后处理链（铲 2 目标）

```text
before-fictitious
  → material-region identity 硬闸 → 每元件候选提议
  → 固定真实目录玻璃（GLC 关闭）
  → after-snap-frozen 快照
  → 短 AUT：只放半径/已授权非球面 DOF，玻璃保持冻结
  → after-snap-reopt 快照
  → 三快照差异 + per-surface snap ledger + provenance
```

三快照必须共享 prescription hash、session-run ID 和机器可比配置指纹，并至少输出 EFL 及
per-field × per-wavelength 的 spot/WFE、横向/轴向色差；max 只能是附加聚合，不能替代明细：

| 指标 | before-fictitious | after-snap-frozen | after-snap-reopt |
|---|---:|---:|---:|
| EFL (mm) | 值 | 值、绝对/相对偏差 | 值、相对 before 偏差 |
| per-field/per-wavelength RMS spot (µm) | 明细+max | 明细、绝对/相对偏差 | 明细、相对 before 偏差 |
| per-field/per-wavelength RMS WFE (waves) | 明细+max | 明细、绝对/相对偏差 | 明细、相对 before 偏差 |
| 横向/轴向色差 | 明细 | 明细、偏差 | 明细、偏差 |

任一快照缺失、非数或设置不一致，整颗候选 snap verification 为 unavailable/withheld，
不得用另外两列冒充完整验证。短 AUT 的具体 cycle/IMP、玻璃冻结命令、目录限定语法与
快照宏拼接方式均**待真机验证**。现有 `BUF EXP`/readout 只证明结构化导出路径可复用，
不证明上述新宏已经可运行（`codev_batch.py:142-188`; `codev_readout.py:183-343`）。

## 5. 跨引擎表值冲突

H-LAK53A 已知 Python 表为 `(1.678,55.5)`（`zmx_materials.py:46`），而任务锚记录 CODE V
目录约为 `Nd≈1.755`。本铲没有运行 CODE V GLD 实测，故后者仍标**待真机验证**。

处理原则：

1. 最终 CODE V 设计与三快照以当前安装版本、明确 catalog 的 CODE V 目录实测值为运行时
   真值；输出 `catalog_id/version` 和实测 Nd/Vd。
2. Python 表只做离线候选检索。与 CODE V 超出数值容差时添加
   `catalog-value-conflict`，禁止无声覆盖、禁止宣称两引擎一致。
3. 冲突材料在同步表值前不得取得 `catalog-snapped`；可保留 fictitious，或在 CODE V
   真值反哺并有来源版本后重新 snap。
4. 不自动“修正”仓库材料表；另开有证据的资料更新工单，避免影响 Optiland 既有基线。

## 6. provenance 与 scorecard 接缝

provenance 拆为两条互不覆盖的运行时派生轴（M2）：

- `material_identity`: `fictitious / catalog-native / catalog-snapped / catalog-conflict`，只由
  写前计划、CODE V 写后 readback、catalog ID/version 派生；快照缺失不得把真实处方谎报为 fictitious。
- `snap_verification_status`: `complete / unavailable / inconsistent / aut-failed`，只由三快照、
  配置指纹和 AUT 轨迹派生；complete 不表示可接受或量产合格。

铲 2 必须采用 Pydantic closed model/enum（`extra='forbid'`）、不可变 per-element ledger、
`computed_field` 派生候选汇总及显式 `model_validator`（不得用 `assert`）；序列化入口拒绝未知
字段和外部伪造升级标签，scorecard 必须校验 ledger/readback 一致。仍不增加 pass/fail，
[EXPERT] 保留最终判断权；机制对齐 C1 honesty invariant。

## 7. 真机验证矩阵（orchestrator 排窗）

至少选择 3 颗已交付、`extra_dof=both` 且含 fictitious 玻璃的候选；必须包含
`US20170003482A1 × 3.797` 旗舰候选，其余两颗覆盖不同 EFL/玻璃域位置。每颗执行：

| 试验 | 变量 | 必收证据 |
|---|---|---|
| A 基线 | 原 fictitious | prescription hash/session ID、完整材料 readback、per-field/per-wavelength 指标、配置摘要 |
| B 冻结 | 最近邻真实牌号，GLC 关 | 同上 readback；catalog ID/version/实测 Nd/Vd、每元件距离与 identity 核对 |
| C 恢复 | B + 短 AUT 半径/非球面 | 同上 readback；merit operands+权重、variables、constraints、MXC/MNC/IMP、cycle/termination/error/ERR.F 轨迹 |
| D 冲突 | 至少 H-LAK53A 或另一跨表冲突 | Python 值、CODE V GLD 值、冲突标签与 fail-closed 行为 |
| E no-op AUT | fictitious 冻结玻璃、与 C 相同几何 DOF/预算 | AUT 自身恢复/改善量、完整轨迹与配置指纹 |
| F 预算对照 | C 的短预算 vs 足量/收敛预算或重复起点 | 区分材料不可恢复、预算不足与局部极小 |

机器可比配置摘要必须覆盖 focus/refocus、aperture、field、wavelength/weight、vignetting/
ray aiming、zoom position；A/B/C 各阶段材料 readback 要证明 C 未重开玻璃。仅文本写“相同”
无效，D 冲突实验也不能替代 E/F 光学归因控制。（M3）

矩阵只产数据，不预设 EFL/RMS/WFE 合格阈值。三颗完成后由资深根据偏差分布 ratify：snap
距离阈值、disp_factor、短 AUT 预算，以及是否进入铲 2 主链。

## 8. 开放问题（16 项，供铲 2 ratify）

1. `D<=0.01` 是否能同时覆盖低折高阿贝与高折低阿贝塑料，还是应按域分层？
2. Python 的归一化 `disp_factor` 是否需完全复刻 `glassfit.seq:107-112` 的 FGW 换算？
3. 目录应只含在产牌号，还是允许 discontinued 但强制 availability 标签？
4. 如何稳定表达 `catalog_id + glass_name`，避免同名跨目录歧义？
5. 同一实体元件前后两面如何从 readout 建立 identity，并保证只选一个材料？
6. CODE V 批处理下冻结真实玻璃、限定目录的准确命令序列是什么？**待真机验证。**
7. 短 AUT 放哪些曲率/非球面 DOF、cycle/IMP 预算多大才不把 snap 劣化藏进过拟合？
8. RMS spot/WFE 的三快照应取哪些字段/波长/视场聚合，才能严格可比？
9. partial dispersion、供应状态、注塑可得性何时进入二阶段筛选，而不污染本阶段距离？
10. H-LAK53A 差异来自错表、同名异目录还是波长/牌号版本？需 GLD/GPR 实测归因。
11. Nd/Vd spectral definition 与 FGW provenance 如何在 target/catalog/readback 间强制同源？
12. NSS、zoom、cemented component 下 material-region identity 的准确边界与跨 zoom 稳定性是什么？
13. 同名/版本/温度和折射率条件如何与 CODE V readback 组成唯一目录身份？
14. partial dispersion 是否应成为写回前硬筛，而非仅在整机回验中发现二级光谱差异？
15. 多元件采用贪心、top-k/beam 还是全局组合；如何证明误差不会同向累积？
16. 回验失败如何保证处方、ledger、provenance 与产物原子回滚，不留下半提交状态？（m2）

## 9. 本铲验收

- `glass_snap.py` 是纯 Python、确定性、无 LLM/CODE V/Optiland 依赖。
- 单测覆盖度量、权重、容差等号、超界 fail-closed、真实塑料牌号往返。
- 不修改 `codev_optimize`、golden、既有候选产物或 `decisions.log`。

## 10. 修订记录

- 2026-07-11：采纳对抗审 B1/B2、M1-M5、m1/m2；撤回 GLASSFIT 同款距离声明，将离线核降级
  为 Atelier metric 候选提议器；新增谱线同源与 material-region 写回硬闸、双轴 provenance、
  强类型 catalog、严格边界、真机控制矩阵及开放问题 11-16。
