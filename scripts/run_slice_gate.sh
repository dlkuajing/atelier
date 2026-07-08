#!/bin/bash
# 切片 gate：只跑本轮 codex 改动相关的测试文件，无相关则跑核心冒烟集。
# 全量回归留给 CI（合并 main 时）兜底。2026-07-08 主公授权 gate 全量→切片提速。
# 相关性推断：① 改动的 tests/test_*.py 直接跑；② 改动的 app/scripts 模块 → 对应 tests/test_<module>.py。
cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 1
export PATH="$HOME/.local/bin:$PATH"
export PYTHONUTF8=1
LOG=.planning/loop/gate-last.log

CHANGED=$(git diff --name-only HEAD 2>/dev/null)
T=$(echo "$CHANGED" | grep -E '^tests/.*test_.*\.py$')
for f in $(echo "$CHANGED" | grep -E '^(app|scripts)/.*\.py$'); do
  c="tests/test_$(basename "$f" .py).py"
  [ -f "$c" ] && T="$T
$c"
done
T=$(printf '%s\n' $T | sort -u | grep .)

# 兜底：无可推断的相关 test → 跑核心冒烟集（证 env/核心路径没崩，仍远快于全量）
if [ -z "$T" ]; then
  T="tests/test_case_library.py tests/test_optical_engine.py tests/test_optical_calc_extensions.py tests/test_health.py"
fi

echo "[切片gate $(date '+%H:%M:%S')] 跑: $(echo $T | tr '\n' ' ')" > "$LOG"
# shellcheck disable=SC2086
./.venv/Scripts/python.exe -m pytest -q $T >> "$LOG" 2>&1
