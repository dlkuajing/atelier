# Phase18 night-20260711 晨检

- 结构/溯源审计：**PASS**
- 生成时间（UTC）：`2026-07-12T12:33:22+00:00`
- 边界：本报告只证明流水线账本、指针、工件与机器数据的完整性；不判定光学合格、良品率、量产可用性，也不代填 `[EXPERT]`。

## 账本与交付

| 项目 | 结果 |
|---|---:|
| targets（actual / expected） | 50 / 50 |
| jobs / valid CandidateSets | 50 / 50 |
| jobs succeeded / degraded / failed | 29 / 21 / 0 |
| candidates retrieved / target-converged | 200 / 43 |
| current-attempt ZMX / CandidateSet 引用 / 未发布 | 84 / 43 / 41 |
| post-AUT snapshots | 43 |
| `[EXPERT]` verdicts | 0（留白） |

全部 50 个 job id/index 连续、终态，job target 与冻结 targets 一致；current CandidateSet 均经当前 Pydantic 模型回读，summary/mode/count 自洽。全部 current-attempt 与引用 ZMX 通过非空、解码及 `VERS/WAVM/SURF` 结构检查。

## 重跑事故信任边界

- job-0020/attempt-1 永久排除并保全；current=`attempt-2`。
- job-0021/attempt-1 永久排除并保全；current=`attempt-2`。
- `resume-incident-20260712.json` 的 trust disposition 为排除真值；job-0020 保全账本 SHA-256 与 retry receipt 一致。

## 机器质量观察（非 verdict）

- AUT converged 分布：`{'false': 2, 'true': 41}`。
- AUT termination 分布：`{'<missing>': 3, 'max_cycle_limit': 8, 'normal_completion': 22, 'unable_to_scale_pupil_field': 4, 'unstable_condition': 6}`。
- F# ladder：10 个候选，`target_achieved=0`，`accepted_final=0`。
- 下表只列缺测或显著异常机器数值；不把其余候选推断为合格。

| job | candidate | observation |
|---|---|---|
| job-0008 | `5P_F2.0_FOV78.7_EFL3.8_IMH3.3_TTL4.35::target-converged-asphere` | AUT termination missing；post-AUT RMS missing |
| job-0012 | `5P_F2.0_FOV78.7_EFL3.8_IMH3.3_TTL4.35::target-converged-asphere` | AUT termination missing；post-AUT RMS missing |
| job-0018 | `5P_F2.0_FOV78.7_EFL3.8_IMH3.3_TTL4.35::target-converged-asphere` | AUT termination missing；post-AUT RMS missing |
| job-0023 | `US-12248126-B2-e5::target-converged-both` | aut_converged=false；EFL deviation=36.0802% |
| job-0030 | `US-11719917-B2-e2::target-converged-asphere` | aut_converged=false；post-AUT RMS extreme=1.154158e+21 um |

## Degraded 分类

| count | reason |
|---:|---|
| 21 | requested generation mode(s) produced no candidates: target-converged — batch degraded (e.g. CODE V unavailable => Mode3 silently skipped); results below cover only: retrieved |

## 证据绑定

- current manifest SHA-256：`55eecdd56742b843d8b7cb503db327566fdb67ca2ad7ca50693805408253fb29` （134 files）
- excluded-attempt manifest SHA-256：`ffffc756b9b0e6a82b909e01a8235e75d10418f5c5679279ed6cba4e40b3841c` （3 files）
- audit script SHA-256：`0ddfba4ca2abd874e619316cdf4f42aac1cbf3223f05df9653869e4a3811ecd0`
- `batch.json`：`898bfafe7b09a99edd5370a12ab57320fc01023d5eeee206b0b6f39267e8d951`
- `targets.json`：`057b001c0ff21250aad9de660dbb718f5001c9065b67448d65df0ae364004d7e`
- `resume-incident-20260712.json`：`4b32a06b6dbf415a31739fd91517b97469a176e035d290f936edd37415330c73`
- `job-0020-retry-receipt-20260712.json`：`2d0a9a8675a986a2d43eb56311e82460f4c344daf2ebcd7fe50cf8a03449fa90`
- `job-0020-attempt-1-contaminated-ledger.json`：`46e942a03c5182c747bed3ad16e83f6193f17e92e1c19033d22171c7adc618bc`
- 50 份 job ledger 的逐文件 SHA-256 收录于同名 JSON 报告（expected=50）。

> `succeeded` 仅表示流水线交付；`degraded` 如实表示请求模式缺失。量产可用性与 `[EXPERT]` 背书仍由资深设计师决定。
