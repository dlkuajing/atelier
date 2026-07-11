# 生产可用 loop 终版 handoff（2026-07-11 · 三层混合编队 · Phase 11-19）

> **边界声明**：本报告只出量化数据、候选设计与机器可判事实。良品/合格判定全部留给资深（[EXPERT] 红线）。
> 真值来源：git/pytest/真机 CODE V listing·tsv/CI/浏览器实测——非 AI 自报（含 Codex 自报，一律磁盘复核）。
> 交接起点 main=e69b540（loop3 收官）→ 终点 main=a9359c2（PR#55-66 十二连合，全部 PR CI 绿 + main CI 绿）。
> 编队：Fable 5 orchestrator（排程/终审/合并权/真机窗）+ Sonnet executor（P11/漏斗/P17）+ Codex gpt-5.6-sol/ultra（普查/解析器/转换入库/P13/P14 + 全 PR 对抗审外脑）。

## 一、完成定义对照（提案 Phase 11-19，`.planning/proposals/production-readiness-phases.md`）

| Phase | 状态 | 证据 |
|---|---|---|
| 11 甜区覆盖率热图 | ✅ | PR#60：900 格点三场景基线（36.0/34.3/45.3%）+ 对抗审 2 BLOCKER 修复（存在性扫描反证真空洞=0）；选题集落盘 |
| 12 底库定向填洞 | ✅（含判死账） | PR#56 普查 + #58/#59 SEKONIX/NEWMAX 解析器 + #61 转换入库：底库 436→442（tele+5）；覆盖率 delta 口径达成（tele 甜区 34.3→40.3%）；SEKONIX 真实产量 0/61 判死有据（PPUBS 无实例元数据，双源证死）；census 上限 141→真转换 18=解析器 ROI 真实锚点 |
| 12.5 漏斗调优（P11 派生，计划外最高杠杆） | ✅ | PR#63：cap 锚定旧真机席位（对抗审 v1 极值敏感 BLOCKER 修复）；★甜区 wide 36.0→**55.7%**/tele→**43.3%**/uw 45.3%，miss -54.7%，top-2 席位 FOV 回退 900 格点 max=+0.00°★；真机 e2e 实证新 seed 产 target-converged 候选 |
| 13 落真实玻璃 | 铲1✅ 铲2✅ 铲3留窗 | PR#62 设计（对抗审 2B/5M：dispFac≈50 实锤/候选提议器定位）+ PR#65 链实现（identity 硬闸/冻结=不声明玻璃变量终审修正）；真机冒烟两实锤待修（dot-dir 路径炸导入/readout vd 解码缺口，任务#14 有账）后跑矩阵 |
| 14 真公差良率 TOR | 铲1✅ 铲2留窗 | PR#64 设计+spike+★真机语法采样（DEF TOL 带面范围/WBF Bk PER/单 GO 双 buffer/NTR20 仅 2.3s，逐字节样本入 tests/data/codev_tor/）★；PER 概率位口径未钉死前 yield 恒 unavailable；铲2=orchestration 接线+真机矩阵 |
| 15 Stage B（F# 达 target） | ⛔ 未启动（月级留窗） | 起点证据在案：opt3 spike 实锤显式 FNO 致宽视场主光线追迹失败（handoff-0709 限制#1），需 CRA/ray-aiming 工程；建议下一 loop 首铲=失败模式真机采证矩阵 |
| 16 Stage C（IMH/FOV 场重建） | ⛔ 未启动（月级留窗） | 同 15 族；CONVERGED_FIELDS 仍诚实缩窄 {"efl"} |
| 17 迭代回路+交付物 | ✅ | PR#66：①调整重跑回路（isfinite 全字段守卫）②xlsx/zip 导出（单一格式化真相源，绝不假零，缺件复现宏 fail-closed 不冒充）③重复性维 mock 链（run_count=1 恒 unavailable）④Mode3 候选 RI 修复（真机实证 N/A→5/5 真算）；浏览器三 job 真机实证+截图 |
| 18 批量生产模式 | ⛔ 未启动（P2 留窗） | 依赖 17 已就绪（job 分道+归档接口就位）；夜批队列+归档页+[EXPERT] 回写存储=下一 loop 可直接开工 |
| 19 总验收 handoff | ✅ 本篇 | + demo-sop 增补 + memory 终更 + decisions.log 全程留痕 |

## 二、全部 PR 清单（12 个，全 CI 绿合入）

#55 提案落盘｜#56 三家族普查｜#57 ruff 债 42 清零｜#58 SEKONIX 解析器（对抗审 4 实锤修复：Forbes Qcon fail-closed/玻璃码 6 位解码）｜#59 NEWMAX 解析器（2 正例 embodiment+字母序 G+ 歧义守卫）｜#60 甜区热图（存在性扫描修复）｜#61 转换+入库波（442）｜#62 P13 设计｜#63 漏斗调优｜#64 P14 TOR 设计+真机采样｜#65 P13 链实现｜#66 P17 迭代回路+交付物

## 三、良品率 go/no-go 备料更新（判在资深）

- **选题集**：365 条甜区覆盖 target（`.planning/loop/sweet-zone-topic-set.json`，漏斗调优后口径）；甜区覆盖率 wide 55.7%/tele 43.3%/uw 45.3%
- **产候选路径**：浏览器 SOP 路径 B（现支持资深改约束「调整重跑」+ xlsx/zip 规格书导出带走）或离线 `scripts/c1_orchestrate.py`
- **判读须知增量**（在 loop3 handoff §四基础上）：Mode3 候选 RI 现为真算（满口径口径，与裁瞳快照不可横比，worst-field 小值显示 <0.001 非零）；重复性列=unavailable 表示未做多跑验证（真机 repeat 引擎留窗）；玻璃仍 fictitious（P13 链就绪待矩阵校准后落真实牌号）

## 四、诚实缺口清单（全部有账，无静默）

1. Mode3 优化 ZMX 持久化（bundle 的 Mode3 ZMX 下载依赖此）——P17 记账
2. repeat_runs>1 真机引擎未实现（显式 NotImplementedError，不假装多跑）
3. RI 满口径口径标注（与 CODE V 裁瞳快照不可横比）
4. P13 铲3 两修复：dot-dir 路径守卫 + readout 玻璃码 vd 解码（真机冒烟实锤，`scratchpad` 证据已转述任务#14）
5. P14 PER 概率位数值口径未钉死（超 [0,1] 值语义待手册对照）→ yield 恒 unavailable
6. Stage B/C（F#/IMH/FOV 达 target）未落地——候选仍只 EFL 真收敛
7. 公差良率仍 proxy（真 TOR 铲2 留窗）；玻璃仍 fictitious（矩阵校准留窗）
8. P17 全量套件真机测试与其 Job 3 曾时间重叠（单实例纪律小违规，无失败，已记录）
9. uw 第三锚（US-12210213-B2-e3）非漏斗缺陷但主口径未覆盖（边界已钉测试）

## 五、真机窗待办队列（下一窗顺序建议）

1. P13 铲3 两修复后：freeze 序列语法冒烟 → 全矩阵（4 候选 A-F+对照组）→ 阈值/权重资深 ratify
2. P14 铲2：TOR orchestration 接线 + 真机矩阵（阳性对照+交叉核验）+ PER 口径钉死
3. Stage B 失败模式采证矩阵（显式 FNO×宽视场 seed 的 .lis 证据分类）
4. P17 repeat_runs 真机引擎 + Mode3 ZMX 持久化

## 六、外部依赖挂起（NEED 主公，不阻塞）

- staging 109 颗 ZMX 同步（另一台电脑）
- 良品率 go/no-go 资深实测（备料见 §三）
- 商用/合规定位决策项（AGENTS.md 记）
- Phase 15/16/18 与铲3/铲2 系列的下一 loop 发车令
