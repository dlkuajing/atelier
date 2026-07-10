# 生产可用路线 Phase 提案（Phase 11–19）

> 2026-07-10 立案（自主 loop 起手首铲，orchestrator=Fable 5）。
> 基线：main=e69b540（loop3 收官：PR#49-54，Mode3 解锁 17 颗真实设计 seed / C1 进浏览器 /
> 候选卡可视化 / 底库 436 / handoff+SOP）。
> 北极星：专家级量产设计论证——AI 批量产出量产级候选 + 量化数据，良品/合格判定权
> 永远在资深（[EXPERT] 红线）。诚实红线全链适用：数据真算、degraded/proxy/fictitious
> 如实展示、禁估算值冒充真值。
> 顺序可据发现重排，重排必须留痕 decisions.log。[C]=适合 Codex 车道（接口锚死+pytest 可判）。

## 当前命门（起手判断）

loop3 已把「客户需求→检索+优化双模→scorecard→资深筛」端到端管线打通，但**量产可信度
有三处资深一眼看穿的缺口**：

1. **Mode3 只有 EFL 真收敛**（F# 锁 native、IMH/FOV 未落地——Stage B/C）；
2. **fictitious 玻璃未落真实目录**（塑料域 GLA 内 model glass，GLASSFIT 未接）；
3. **公差良率是 proxy 非真 TOR**（CODE V 原生 Monte-Carlo+补偿器+良率未接）。

同时**甜区覆盖率未量化**——seed 匹配方向不对称（ΔEFL 缩焦全收敛/拉焦+25%起挂，
opt3 N=24 实锤）意味着"库内有多少客户 spec 能产出可看候选"是个没算过的数。先算它，
它决定补库方向与良品率闸选题集。

## Phase 11 甜区覆盖率热图（半天级，指导一切）

对 wide/tele/ultrawide 各铺典型客户 spec 网格（EFL×F#×FOV×IMH），用现成
`rank_seeds` + `seed_target_score` 算每格点库内最佳匹配（方向不对称：ΔEFL 在
-15%~0 带内才算甜区原料），输出覆盖率数字 + 空洞清单 + 热图报告。

- **车道**：Sonnet executor（纯 Optiland，无 CODE V 依赖）。
- **验收**：三场景覆盖率落盘 `.planning/loop/`；产出良品率闸选题集（有覆盖 target）
  与定向补库清单（空洞）；测试+CI 绿。

## Phase 12 底库定向填洞 [C]（与 13/14 并行，Optiland 侧）

按 Phase 11 空洞清单定向：

1. Genius(30)/SEKONIX(18)/NEWMAX(15) ≈63 颗未普查家族普查+解析器扩展（沿 DATA-10b
   模式；解析器家族=接口锚死的理想 Codex 铲）；
2. `patent_crawler` 按空洞 EFL/FOV 段定向爬（USPTO 扩池）；
3. staging 109 颗=主公侧外部依赖，**NEED 主公**跳过不阻塞。

- **验收**：甜区覆盖率相对基线提升量化上报（**口径=覆盖率非总数**）；六闸拒收有账；
  golden 循先例重锚；全量+真机双闸绿；CI 绿。
- 参考账本：loop3 handoff §三（死池 ≈223 颗有据勿再投入；10b 颗良率 ~16%、
  ~3.4 embodiment/颗，本波预期 +30~40）。

## Phase 13 落真实玻璃 [C 宏/解析层]（P0，数周级）

接 GLASSFIT.SEQ / Glass Expert（LensSetupRM p.423 / Opt RM Ch.9），候选玻璃 snap 到
真实目录牌号；GLA 越界收口（opt3 限制#4）；顺修 H-LAK53A 表值不一致工单
（Python 1.678 vs CODE V ≈1.755，loop3 遗留#3）。真机联调由 orchestrator 排窗执行。

- **验收**：真机 e2e 候选 ZMX 全真实牌号；snap 前后 EFL/RMS/WFE 偏差量化上报
  （不许静默劣化）；provenance fictitious→real-catalog 如实分档；回归+双闸+CI 绿。

## Phase 14 真公差良率 TOR [C 宏/解析层]（P0/C2，数周级）

CODE V TOR（Monte-Carlo+补偿器+良率）宏批处理接入；scorecard 新增真良率维（带
provenance 与 fail-closed：TOR 不可用如实 unavailable，**绝不 proxy 冒充**）；proxy
与真值对照报告。真机联调排窗。

- **验收**：真机 e2e 候选带真良率；对照报告落盘；mock 链全绿；CI 绿。

## Phase 15 Stage B：F# 达 target（P0，月级引擎难活）

起点：显式 FNO 致宽视场主光线追迹失败（opt3 spike 实锤，限制#1），需 CRA/ray-aiming
工程。Sonnet 主力 + orchestrator 排真机窗 + Codex rescue 第二意见。

- **验收**：真机矩阵（≥8 seed×多 F# target）量化收敛率与像质代价；
  `CONVERGED_FIELDS` 扩 fnum **仅当真机证据支撑**（证据不足不扩，如实上报）；
  双闸+CI 绿。

## Phase 16 Stage C：IMH/FOV 场重建（P0，月级，与 15 同族同分工）

- **验收**：同 15 口径扩 imh/fov；真机 e2e 出现 ≥3 维真收敛候选（或诚实上报做不到
  哪维）。

## Phase 17 迭代回路+交付物闭环（P1，web/编排侧，Sonnet 车道，与 13-16 并行不抢 CODE V）

1. 资深反馈→约束调整→重优化回路（候选页"调整重跑"，走既有 job 分道）；
2. 规格书级导出（PDF/Excel）+ .seq 一键载入包；
3. 重复性维度进 scorecard（≥2 次跑分布，引 opt3 限制#8）;
4. Mode3 候选 RI 修复（临时目录路径，loop3 遗留#4）。

- **验收**：浏览器 preview 全链实测+截图留证；导出物可开且与页面一致；重复性列
  fail-closed；mock+CI 绿。

## Phase 18 批量生产模式（P2，Sonnet 车道）

夜批队列（50 target/晚，codev 道串行）、结果归档管理页、[EXPERT] 判定回写存储层
（持久化+可导出，反哺打分留接口）。

- **验收**：50 target 无人值守真跑一晚，成功率/归档/失败账本如实上报；存储 CRUD
  测试绿；浏览器实测；CI 绿。

## Phase 19 收尾：总验收 handoff（外部闸标注）

终版 handoff（完成定义对照/全部 PR 清单/良品率 go/no-go 备料定版/诚实缺口清单/SOP
更新）+ memory 更新 + 停 loop 报主公。

## 编队与纪律（摘要，全文见任务书）

- **三层编队**：Fable 5 orchestrator（决策/排程/终审/合并权）+ Sonnet executor
  （探索性/真机密集/浏览器验证铲）+ Codex gpt-5.6（接口锚死纯后端铲 + 全 PR 对抗
  审查外脑 + rescue 第二意见）。
- **交叉审查矩阵**：谁写的谁不当终审；Sonnet PR→Codex adversarial-review 必审；
  Codex PR→Claude 多角度 finder+verify；合并权只在 orchestrator。
- **CODE V 单实例纪律**：全局唯一真机窗口由 orchestrator 排程，任何车道勿并行双跑；
  全仓测试与真机实验勿同时跑。
- **发布**：PR→CI 绿→自审留证→merge（AI Release Authority），禁直 push main。
- **红线必停项**：良品率/合格判定、改北极星、LLM 碰数值坐标、改全局配置、不可逆无
  回滚、伪造/美化数值、proxy 冒充真值、提前标注未验证能力——命中写 NEED 主公。

## 外部依赖挂起清单（NEED 主公，不阻塞其他线）

- staging 109 颗手机镜头 ZMX（另一台电脑）同步；
- 良品率 go/no-go 资深实测判定（备料指引：loop3 handoff §四）；
- 主公决策项：商用/合规定位调整（AGENTS.md 已记）。
