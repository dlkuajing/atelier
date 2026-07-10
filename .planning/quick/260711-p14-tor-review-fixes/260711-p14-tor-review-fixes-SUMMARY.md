---
quick_id: 260711-p14-tor-review-fixes
date: 2026-07-11
status: complete
---

# Summary: P14 TOR 设计对抗审修复与真机证据接入

## Shipped

- builder 使用真机确认的 `WBF B1 PER` + `WBF B2 MC` + 单 `GO` + 双 `BUF EXP`。
- provenance、命令、metric、MTF 方位、路径、ZMX 输入、DEF TOL 面范围均 fail closed；删除
  未生效的 seed，补偿器配置增加量产装调假设。
- parser 严格解析 CODE V 11.5 PER/MC fixture 的声明、表头和数据行，返回 MC 结构化原料；
  PER 语义和良率口径未 ratify，状态仍封闭为 unavailable。
- 设计文档逐项关闭 B1-B2、M1-M8、m1-m3，并补齐阳性矩阵、联合事件、无效 trial、
  Wilson 样本计划、补偿器 gate 与 proxy/TOR 展示约束。

## Verification

- `PYTHONUTF8=1 uv run pytest tests/test_codev_tolerance.py -q`：26 passed。
- `uv run ruff check app/core/engines/codev_tolerance.py tests/test_codev_tolerance.py`：passed。
- `git diff --check`：passed（仅 Windows autocrlf 提示）。
