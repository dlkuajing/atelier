---
quick_id: 260712-p18-night-audit
status: complete
owner: Codex
---

# Summary: Phase18 night-20260711 晨检收口

## Shipped

- 增加只读、可复跑的 `scripts/audit_p18_archive.py`，从外部锚定 50-target acceptance contract，验证 batch/targets/jobs 连续性、current attempt/pointer/artifact、Pydantic CandidateSet、summary/mode 真值与全部 current ZMX 结构。
- 将 job-0020/job-0021 attempt-1 按事故 trust disposition 永久排除；current exact attempt-2、job-0020 retry receipt/保全账本 SHA、排除目录 manifest 均 fail-closed。
- `[EXPERT]` 本批强制 0 文件（递归含 non-JSON）；机器 RMS/EFL 只接受有限真实数值，类型漂移/NaN/Inf 不得吞警告；F# accepted_final 必须与 delivered ZMX 同源。
- 生成哈希绑定的 `.planning/loop/phase18-night-20260711-morning-audit.{json,md}`。

## Result

- structural/provenance `PASS`，errors=[]。
- 50 targets / 50 jobs / 50 valid CandidateSets；29 succeeded / 21 degraded / 0 failed。
- 243 candidates：200 retrieved / 43 target-converged；84 current-attempt ZMX 全部结构有效，其中 43 由 CandidateSet 引用、41 未发布。
- 0 `[EXPERT]` verdict；10 个 F# ladder 候选均 `target_achieved=0`、`accepted_final=0`。
- 如实保留 5 项显著机器质量观察：3 项 AUT termination + RMS 缺测；job-0023 AUT=0 且 EFL deviation=36.0802%；job-0030 AUT=0 且 RMS=1.154158e21 µm。
- 结论只证明流水线交付完整，不构成光学合格、良品率或量产可用 verdict。

## Verification

- 本地：88 passed / 4 real deselected；ruff PASS；`git diff --check` PASS。
- 独立只读对抗终审：PASS；审查者独立复跑 101 passed / 4 real deselected，JSON 全字段、Markdown 与 audit-script SHA 均一致。
- 运行时静默门：2026-07-12 20:31:40 +08:00 再核验 owner absent，P18 runner/CODE V/codevm process count=0。
