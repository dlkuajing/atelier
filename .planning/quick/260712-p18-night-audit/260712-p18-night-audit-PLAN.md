---
quick_id: 260712-p18-night-audit
status: complete
owner: Codex
---

# Quick Task: Phase18 night-20260711 晨检收口

## Inputs

- 只读账本：`D:\atelier-wt-ctl\var\batch-archive\night-20260711`
- 只读工件：`D:\atelier-wt-ctl\var\job-artifacts\batches\night-20260711`
- 事故证据：`resume-incident-20260712.json`、job-0020 retry receipt 与污染账本保全件
- 基线：`origin/main@9c2bc80`

## Tasks

1. 增加可复跑、只读的 P18 archive audit，严格验证 batch/targets/jobs、连续 50 target、Pydantic CandidateSet、current attempt/pointer/artifact 绑定和 ZMX 结构。
2. 永久排除 job-0020 attempt-1 与 job-0021 attempt-1，并验证 current attempts 均为 attempt-2；保留事故工件，不删除、不改写运行目录。
3. 分开统计 succeeded/degraded/failed、retrieved/target-converged，并如实列出 AUT、EFL、RMS 与缺测警告；不得把 pipeline delivery 写成光学合格或 [EXPERT] verdict。
4. 生成绑定源文件哈希的 JSON + Markdown 晨检报告，运行离线测试与 lint。
5. 独立对抗审查通过后按 PR → CI → merge → main CI 收 E。

## Verify

- batch=`completed`、targets/jobs/current CandidateSet 各 50，job id/index 连续且全终态。
- job-0020/job-0021 current attempt=2；两份 attempt-1 只作永久排除证据。
- 50/50 CandidateSet 可经当前模型回读，summary/mode/candidate 数量自洽。
- current artifact/pointer 均锁在对应 `job-NNNN/attempt-N`；所有引用 ZMX 存在且通过非空、解码、`VERS/WAVM/SURF` 结构检查。
- `[EXPERT]` verdict 目录缺失/为空只报告“未录入”，不生成占位结论。
- 审计 exit code 0 只代表结构/溯源完整；质量警告单列，不被吞成假绿。
