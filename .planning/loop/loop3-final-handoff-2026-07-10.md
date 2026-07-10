# Loop3 终版 handoff（2026-07-10 · Mode3 产能 + 底库 + 演示/前端 三线自主 loop）

> **边界声明**：本报告只出量化数据、候选设计与机器可判事实。良品/合格判定全部留给资深（[EXPERT] 红线）。
> 真值来源：git/pytest/真机 CODE V tsv/CI/浏览器实测——非 AI 自报。
> 交接起点 main=ad40f03 → 终点 main=15c4158（PR#49/#50/#51/#52/#53 五连合，全部 PR CI 绿 + main CI 绿）。

## 一、完成定义对照（任务书四项）

| 项 | 状态 | 证据 |
|---|---|---|
| ① rebuild -inf EFL 根因修好 + Mode3 产出率回升 | ✅ | PR#49（f9b0b22）：根因=17 颗遗留真实设计 seed GLAS 编码 CODE V 不可解析→导入即全空气（baseline EFL=1e35 铁证）；修数据锚+全库回归测试+预检守卫；真机 e2e Mode3 首次从 5P seed 产出 2 个 target-converged 候选；**17 颗真实设计 seed 全部解锁 Mode3**（此前 Mode3 事实只吃专利系） |
| ② 底库达标或诚实缺口清单 | ⚠️ 436/500 + 量化余量账本 | PR#51（+8, DATA-10a）+ PR#53（+75, DATA-10b 解析器旗族扩展）：353→**436**（wide 224 / tele 134 / **ultrawide 78 翻倍**）；缺口 64 颗，余量账本见 §三 |
| ③ 浏览器端到端全链可演示 | ✅ | PR#50（c2a5120）：wizard→生成候选集按钮→SSE 进度→候选集页（真机 CODE V 全链浏览器实证 3 轮）；SOP=docs/demo-sop.md |
| ④ 前端达可自证最佳态 | ✅ | PR#52（211a26a）：候选卡光路图 SVG+诚实 MTF 图表（恒 0-1 全幅/真频率范围/真衍射极限公式）+provenance 徽章区分+N/A 弱化；浏览器截图实证 5/5 卡渲染 |

全部 PR：CI 绿 → 合并 → main CI 绿（AI Release Authority 自审自批，证据在各 PR 描述 + decisions.log）。

## 二、主线落地清单（4 个已合 PR + 1 个在途）

1. **PR#49 rebuild -inf EFL 根因结案**：`GLAS <商品名> 0`→`<商品名>_BLANK 1 0 nd vd`（宏按 BLANK 子串判 model glass，L1523 真机实证；nd/vd 取 Optiland fallback 同一查表零杜撰）；tests/test_zmx_glass_resolvability.py 全库闸；baseline EFL 预检守卫（坏 seed 14 次真机 run→1）；writer 对标记名写 flag=1（交付物在真 Zemax 不退化空气）。8 角度对抗审查 21 候选→9 修。
2. **PR#50 C1 候选集进浏览器**：CandidateOrchestrationEngine（job store 后台层，**座位分道**：codev 道与 demo 道互不阻塞——实测 C1 跑批时经典任务 3s 完成）+ POST /candidates + candidate_set.html（诚实横幅/5 维偏差 per-field converged/[EXPERT] 留白栅格）+ post_aut 追迹失败哨兵 0.0→None 源头修复（离线报告同愈）。
3. **PR#51 DATA-10a（+8）**：本地池挖掘诚实天花板实锤（87.5% 失败=无支持表格式）；库内 4 颗挂死 seed 修复（有界超时+回退安全网）；FOV 合理性防御闸。
4. **PR#52 候选卡可视化**：光路图+MTF 双可视化（聚焦审查零缺陷：真衍射极限公式/刻度几何同源/注入面安全）。
5. **PR#53 DATA-10b（+75，已合 15c4158）**：Sunny Optics+Ability Opto 解析器家族；2 个数据完整性 bug 落库前抓修；死池有据（LARGAN 172/Samsung 28/Corephotonics 23≈223 颗无解析可能）；audit 挂死根因修复（DATA-10 补 payload-bounded 归类 + 30s 防御超时）。

## 三、底库诚实账本（436/500，缺口 64）

- **可行余量（量化）**：Genius(30)+SEKONIX(18)+NEWMAX(15)≈63 颗未普查家族；Sunny 元数据子变体 ~105 embodiment（部分值未公开，产出不确定）；Sunny 潜望 P-row 2 颗（telephoto 相关）；8 颗挂死专利（Optiland 追迹根因未修）
- **死池（有据，勿再投入）**：≈223 颗（机械专利无处方/无文本表/参数区间表）
- **判断**：下一波普查（Genius/SEKONIX/NEWMAX）若良率与 10b 相当（22/138≈16% 颗良率、~3.4 embodiment/颗），预期 +30~40——**500 门槛需要约再 2 波解析器工作或新原料采集**（patent_crawler 再爬 USPTO 扩池）。
- 场景覆盖：AR/DSLR/microscope 仍空（AR=北极星已划外部工具链例外格；DSLR/microscope 需新数据源+ingest 扩展，非解析器问题）。

## 四、良品率 go/no-go 备料指引（判在资深）

数据已备齐，资深实测建议路径：
1. 浏览器走 SOP §三路径 B（或离线 `uv run python scripts/c1_orchestrate.py --out <dir>`）对若干真实客户 target 产候选集。
2. 每个候选集看：[EXPERT] 栅格逐候选填"值得细看/不值得/需补数据"；候选卡光路图+MTF+5 维偏差+err_f_ratio 是判断输入。
3. 良品率 = 值得细看数 / 总候选数；经济性判据 = 资深筛 1 个的时间 ≪ 初中级从头做 1 个。
4. 已知输入质量限制（判读时须知）：Mode3 只 EFL 真收敛（F# 锁 native/IMH/FOV Stage C 未落地）；玻璃 fictitious（塑料域 GLA 内，未落真实目录）；候选重复性维度未进 scorecard（handoff-0709 限制#8）；公差良率是 proxy 非真 TOR。

## 五、遗留 backlog（新增于本 loop，均已留痕）

1. e2_intake 入库时 CODE V 可解析性预检（现靠 CI 全库测试兜底，返工提前到入库前）
2. baseline 优化路径（run_codev_optimize/precompute_demo_cache）守卫与 target 路径对齐
3. H-LAK53A Python 表值(1.678)与 CODE V 目录(≈1.755)不一致——4P_F1.9_FOV60.0 跨引擎一致性独立工单
4. Mode3 候选 RI 结构性 unavailable（优化 ZMX 在临时目录，RI 复算管线按 ZMX_AMMO_DIR 解析）
5. 8 颗挂死专利的 Optiland 追迹根因
6. 下一波解析器普查（Genius/SEKONIX/NEWMAX）或 patent_crawler 扩池
7. 历史遗留（handoff-0709）：Stage B（F# 优化）/ Stage C（IMH/FOV 场重建）/ 落真实玻璃 GLASSFIT / 重复性进 scorecard

## 六、演示机操作

见 `docs/demo-sop.md`（启动/两条路径/降级行为/故障排查/话术红线）。
