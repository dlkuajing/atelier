---
quick_id: 260711-p14-tor-review-fixes
date: 2026-07-11
status: in-progress
---

# Quick Task: P14 TOR 设计对抗审修复与真机证据接入

## Inputs

- `scratch_diag/p14-design-adversarial-review.md`：2 BLOCKER、8 MAJOR、3 MINOR。
- `.planning/loop/p14-tor-probe-evidence.md` 与 `tests/data/codev_tor/real_sample_*.txt`：
  CODE V 11.5 真机语法和逐字节导出样本。

## Tasks

1. 修正 builder 为 `WBF B1 PER` / `WBF B2 MC`、单次 `GO`、双 buffer 导出；收紧
   ZMX、路径、metric、azimuth、seed、公差命令和 provenance 边界。
2. 将 parser 状态封闭为 enum；严格解析 PER/MC 真机结构，返回 MC 结构化样本，但保持
   yield unavailable。
3. 用真机 fixture、注入负例和非法输入矩阵扩充定向测试。
4. 按 B1-B2、M1-M8、m1-m3 修订设计文档并增加修订记录。

## Verify

- `PYTHONUTF8=1 uv run pytest tests/test_codev_tolerance.py -q`
- `uv run ruff check app/core/engines/codev_tolerance.py tests/test_codev_tolerance.py`
- 不修改 golden 与 `.planning/decisions.log`。
