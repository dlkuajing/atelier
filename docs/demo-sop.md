# Atelier 演示操作手册（SOP）

> 适用：Windows 演示机（本机跑后端 + 浏览器访问 localhost）。
> 版本锚：main ≥ `211a26a`（2026-07-10，C1 候选集 web 路径 + 候选卡可视化已合入）。
> 诚实铁律：页面上所有数值都是真算产物；degraded/proxy/fictitious 状态由系统如实展示，演示时**不要口头替系统承诺页面没有声明的能力**。

## 一、启动前检查

1. `.env` 在仓库根，含有效 `OPENAI_API_KEY` 与 `OPENAI_BASE_URL`（LLM relay，wizard 提取与双语摘要用）。缺失/为空时启动脚本直接退出并提示。
2. CODE V（可选但演示优化路径必需）：安装于 `D:\CODEV115`。无 CODE V 时系统自动降级（见 §四）。
3. （可选，推荐）预热演示缓存：`uv run python scripts/precompute_demo_cache.py`
   —— 给两个内置示例场景烘焙 CODE V 对比工件（结果页 codev-compare 区块的 `codev-run` 证据链来源）。

## 二、启动

```
scripts\start_demo.bat
```

- 自动设 `PYTHONUTF8=1`、解析 `.venv`、起 uvicorn 于 `http://127.0.0.1:8000`。
- 浏览器打开 `http://127.0.0.1:8000`。
- 关闭：控制台 Ctrl+C。

## 三、两条演示路径

### 路径 A：经典即时设计（秒级，主路径）

1. 首页输入自然语言需求（或点 Sample wide / Sample ultrawide 示例按钮）→ **Draft design**。
2. Wizard 确认页：LLM 提取的场景 + 参数表（含 clamped bounds）→ **Continue**。
3. SSE 进度页自动跳转结果页：光路图 SVG / MTF / 点列 / 场曲 / 波前五卡（provenance 徽章标注计算来源）+ CODE V 对比区块（precompute 缓存命中时带 `codev-run` 证据链，未命中时如实显示 `optiland-estimate` 空心徽章或不可用）+ 双语执行摘要（LLM 生成，失败自动回退确定性摘要并注明）。

### 路径 B：C1 候选集编排（分钟级后台，量产设计引擎演示）

1. 同路径 A 走到 Wizard 确认页 → 点 **生成候选集（检索+优化双模，后台深度计算）**。
2. SSE 进度页（engine=candidate-orchestration）。真机 CODE V 优化约 **4–10 分钟**（受机器负载影响）；页面自动跳转。
3. 候选集页（`/candidates/{job_id}`）讲解要点：
   - **批次摘要**：Retrieved (Mode1) 检索候选 + Target-converged (Mode3) CODE V 真优化候选的徽章计数。
   - **逐候选卡**：光路图截面（Mode3 卡显示的是**优化后设计**）+ MTF 图表（恒定 0–1 全幅刻度 + 真实频率范围 + 衍射极限参考线——像质差的候选曲线会很难看，**这是特性不是缺陷**：诚实呈现是资深信任的基础）+ 5 维 target 偏差表（**只有 EFL 会标 converged=Yes**，F#/IMH/FOV 如实标 No——Stage B/C 未落地）+ 像质/制造性 proxy + rank 结果。
   - **CODE V post-AUT 区块**：红字警示"裁瞳口径快照，不可与满口径直接横比"——这是 CODE V 侧真机数字，仅供 provenance 核对。
   - **[EXPERT] 留白栅格**：页面底部的良品率判定表 AI 永不填写——判定权在资深（演示时明确说这一点，这是产品的核心设计而非未完成）。
4. 候选集 job 在独立 codev 通道排队：**同一时间只跑一个候选集 job**（第二个会 queued——CODE V 单实例纪律）；路径 A 不受影响（分道，实测候选集跑批时经典任务 3 秒完成）。
5. **调整重跑**（2026-07-11 P17 新增）：候选集页底部表单预填本批 target 数值，资深改 EFL/F#/FOV/IMH/TTL 后提交 → 走同一 codev 道串行 job → 新候选集页。越界/非有限值会 400 并如实列 violations——这是 parameter_guards 在挡，不是 bug。
6. **规格书导出**（P17 新增）：候选集页可下载 xlsx（数值与页面同一格式化真相源；小于显示精度的非零值显示 `<0.001` 而非 0.000）与 ZMX/.seq 复现包（zip；Mode3 候选的复现宏若缺 autovig 证据会如实标注不交付，README 有账）。[EXPERT] 判定列不进导出物——导出的是数据不是结论。
7. **候选卡新列**（P17 新增）：重复性列 `Unavailable`=该候选未做多跑重复性验证（如实标注非 bug）；Mode3 候选 RI 现为真算 per-field 值（满口径口径，与 post-AUT 裁瞳快照不可直接横比，页面有标注）。

## 四、无 CODE V 降级行为（如实演示）

- Mode3 自动缺席 → 候选集页顶部出现**诚实横幅**（说明无 target-converged 候选），检索候选照常渲染。
- 结果页 codev-compare 区块显示不可用或 `optiland-estimate`（空心徽章，与实心的 `codev-run` 视觉可区分）。
- 全链路（wizard/检索/光路图/MTF）纯 Optiland 照常工作。

## 五、故障排查

| 症状 | 处置 |
|---|---|
| 启动即退出提示 .env | 补 `OPENAI_API_KEY`（非空、非引号包裹空串） |
| wizard 提取报错 | LLM relay 不通——查 `OPENAI_BASE_URL` 网络与 key 余额；看 uvicorn 控制台日志 |
| 候选集 job 卡 queued | 前一个候选集 job 未结束（codev 道串行）；等待或重启服务 |
| 候选集 job failed | 看控制台日志；常见为 CODE V 超时（机器负载）——重试一次 |
| 页面数字出现 N/A | 特性：该数值不可得/追迹失败哨兵，fail-closed 如实标注，不要解读为 bug |

## 六、演示话术红线

- 不说"AI 判定这个设计合格/可量产"——AI 只产候选与量化数据，判定权在资深（[EXPERT] 留白栅格就是这个承诺的界面化）。
- 不说 F#/IMH/FOV "已优化到 target"——当前只有 EFL 真收敛（页面偏差表如实标注）。
- 公差良率是 proxy（页面有"非真公差良率"标注），真 TOR 是 roadmap 项（C2）。
