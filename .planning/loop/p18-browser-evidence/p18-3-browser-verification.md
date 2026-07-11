# P18-3 浏览器实测留痕（四链路）

日期：2026-07-11。预览服务：`atelier-demo-p18`（`D:\atelier-wt-e\.venv`，端口 8004，
`BATCH_ARCHIVE_DIR`/`JOB_ARTIFACTS_DIR` 显式指向 `D:\atelier-wt-e\var\...` 绝对路径，
`PYTHONUTF8=1`）。测试数据：`scripts/p18_night_batch.py --engine fake` 产的两批
（一批 6/6 全成功抽样批，一批 4 target 含 1 preflight + 1 engine 注入失败的手工批）。

工具限制说明：本环境的 `preview_screenshot` 工具不提供截图文件落盘路径（无法从
对话内联图像桥接到磁盘文件），因此本文件以精确的页面状态描述 + 实际下载的
xlsx 产物（`sample-export.xlsx`，同目录）作为留痕，截图本身在执行过程的对话
记录里可见。

## 链路 1：批次列表 `/batches`

- 首页导航新增 "Batches" 链接，点击可达。
- 空态：`data-empty-batch-list` 段落 + CLI 使用提示（`empty` archive dir 时验证）。
- 有数据态：两行批次，`data-batch-row data-batch-id="..."` 均渲染，列出
  Created/Engine/Target source/Attempted-total/Succeeded/Status（badge）。
  截图确认：`4 / 4` `2/4` `COMPLETED`（绿底）与 `6 / 6` `6/6` `COMPLETED` 两行
  均正确渲染，无机器合格/良品字样。

## 链路 2：批次详情 `/batches/{batch_id}`

批次 `20260711T033445Z-49f48b67`（4 target：2 成功 + 1 engine 失败 + 1 preflight 失败）：

- 顶部 summary：Status=COMPLETED（绿badge）、Engine=fake、Attempted/total=4/4、
  Succeeded=2/4、[EXPERT] verdicts recorded=2/8（提交 2 条 verdict 后从 0/8 变化，
  验证计数器正确联动磁盘状态）。
- Jobs 表：
  - `job-0000 flagship-wide SUCCEEDED — 4 (4 ranked) 2/4`
  - `job-0001 midrange-wide SUCCEEDED — 4 (4 ranked) 0/4`
  - `job-0002 injected-engine-failure FAILED Engine "batch produced 0 candidates for this target" 0 (0 ranked) 0/0`
  - `job-0003 injected-preflight-failure FAILED Preflight (invalid target spec) "1 validation error for TargetSpec fnum Field required..." — 0/0`
  - 失败分类文案如实展示（真实 pydantic 校验错误原文 / 真实 0-candidate 原因），
    无 pass/fail 字样，无合格/良品字样（`test_batch_detail_never_shows_machine_pass_fail_wording`
    同步覆盖此断言）。
- 逐 job 候选 verdict 录入表：job-0000 的 4 颗候选逐行渲染 [EXPERT] 表单
  （Verdict/Reviewer/Note + 提交按钮），已录入的 2 行显示为只读
  `verdict_text` + `— reviewer, recorded_at` + note，未录入的 2 行仍是空表单
  （无预填、无默认值）。

## 链路 3：[EXPERT] verdict 提交

两种方式均验证提交-落盘-回显全链路：

1. `fetch(POST /batches/{id}/jobs/job-0000/verdicts, redirect: 'manual')`
   → 服务端返回 opaqueredirect（303），磁盘立即出现
   `var/batch-archive/.../verdicts/job-0000__3P_F2.5_..._cost_variant.json`。
2. 页面内真实 `<form>` 的 `form.requestSubmit()`（原生浏览器表单提交，非
   AJAX）→ network 记录一次导航（GET 同 URL 200，中间 POST 由浏览器处理未单独
   列出属预期）→ 重新渲染的页面该候选行从空表单变为已录入展示，
   `[EXPERT] verdicts recorded` 计数器 0/8 → 1/8 → 2/8 正确递增。

（附注：`preview_click` 工具对该按钮两次点击均未触发原生提交——无 console
错误、无网络请求，怀疑是本自动化环境对深嵌套 `<table><td><form><button>`
结构的点击合成限制；已用 `form.requestSubmit()` 交叉验证同一按钮对应的
真实 `<form>` 在原生浏览器语义下完全正确，判定为工具侧问题而非产品 bug。）

- 拒绝路径验证（见 `tests/test_web_batches.py`，非浏览器交互但同路由）：
  空白 verdict_text → 400；缺失必填字段 → 422；未知 job_id → 404；
  未知 batch_id → 404。

## 链路 4：批次导出 `.xlsx`

- 页面 `[data-export-batch-workbook]` 链接 `href` 正确指向
  `/batches/{batch_id}/export.xlsx`。
- 实际下载确认：`content-type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`，
  `content-disposition: attachment; filename="atelier-batch-....xlsx"`，7397 bytes。
- 下载产物（`sample-export.xlsx`，与本文件同目录）三张表：
  - `Summary`：批次元信息 + 状态计数 + 失败分类计数 + 非代判 banner。
  - `Jobs`（纯机器列，13 列）：4 行，与页面 jobs 表逐字段一致（含失败分类/消息、
    candidate_set_pointer 绝对路径、artifact_dir 绝对路径）。
  - `Expert verdicts`（纯 [EXPERT] 列）：仅 2 行（已录入的 2 条），未录入候选
    **没有**占位行——验证"未录入=不出现"而非"N/A/0 冒充"。

## 附带修复（浏览器验证过程中发现并修复的真实 bug）

1. **h1 溢出**：`batch_id`（约 25 字符）继承站点默认营销标题字号
   （`clamp(3.5rem, 13vw, 8.5rem)`），导致横向溢出。修复：
   `.batch-detail-page h1 { overflow-wrap: anywhere; font-size: clamp(1.6rem, 4vw, 2.6rem); }`。
2. **相对路径跨进程失效**（真实产品 bug，非仅验证环境问题）：
   `batch_runner.run_batch` 原先把 `job.artifact_dir`/`candidate_set_pointer`
   存成相对路径（相对 `settings.job_artifacts_dir` 的默认相对值），若写入进程
   （CLI 夜批脚本）与读取进程（web 服务）cwd 不同，指针会静默解析失败。
   修复：`resolved_artifacts_root = (...).resolve()`，落盘前转绝对路径；已补
   回归测试 `test_run_batch_fake_engine_five_targets_one_injected_failure` 内
   新增的绝对路径断言。

## 对抗审修复轮补充实测（2026-07-11，Codex 审后 5 fix）

浏览器 + xlsx 复核 BLOCKER-1（degraded 可见性）三面落地，方法同上
（`atelier-demo-p18` 端口 8004，注入 1 条 `status=degraded` 演示 job）：

- **详情页**：job 表 STATUS 列渲染 `DEGRADED (MISSING MODES)` badge
  （`preview_inspect` 实测背景 `rgba(181,132,56,0.22)` 琥珀色，与
  succeeded 绿/failed 红明确区分）；`FAILURE / DEGRADATION` 列完整显示
  degradation 原文（含 missing mode 名与 "results below cover only:
  retrieved"）。
- **列表页 + 详情 summary**：SUCCEEDED 栏显示 `0/1 (1 degraded)`——
  degraded 不计入成功。
- **xlsx**：Jobs 表实测新列 `engine=real / attempt=1 / status=degraded /
  degradation=原文 / modes_requested=retrieved, target-converged /
  modes_present=retrieved / missing_modes=target-converged /
  mode_counts=retrieved=2` 全部落盘。
- **CLI**：fake 批冒烟输出 `2 succeeded, 0 degraded, 0 failed`，
  ledger JSON 实测含 `engine/attempt/modes_requested/modes_present/
  missing_modes/mode_counts` 全部新字段；`--engine real --job-timeout-sec`
  与 resume 引擎不一致均 exit 2 且零副作用（测试断言归档目录不存在）。
