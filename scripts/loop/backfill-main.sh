#!/usr/bin/env bash
# backfill-main.sh — 班车合并 main 后，把 origin/main 回灌进各活跃车道分支。
# ─────────────────────────────────────────────────────────────────────────────
# 目的：车道分支在两次班车之间会漂离 main（旧合约测试没跟上新语义 → gate 假红，
#       实例：车道c UI-06a 曾败于 test_unknown_job_progress_page_returns_404）。
#       班车合并后立即回灌，把 drift 消灭在下一轮开跑之前。
# 安全前提（每车道逐一检查，任一不满足即跳过该车道，绝不强行 merge）：
#   1. worktree 存在且无 .planning/loop/.orchestrator.lock（loop 未在跑）
#   2. 工作树 + index 全 clean（无未提交变更）
#   3. merge 产生冲突 → 立即 `git merge --abort`，标记 CONFLICT 交还 attended
# 只做 merge 不做 push：车道分支的远端推送仍由 loop 自身/班车流程负责。
# 用法：bash scripts/loop/backfill-main.sh [--lanes "dir1 dir2 ..."] [--dry-run]
# 退出码：0=全部成功或跳过 | 1=存在 CONFLICT 车道（已 abort，需人工）
# ─────────────────────────────────────────────────────────────────────────────
set -u

LANES="/d/atelier-loop /d/atelier-loop-b /d/atelier-loop-c /d/atelier-loop-d /d/atelier-loop-e"
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --lanes) LANES="${2:-}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAILED=0
for LANE in ${LANES}; do
  TAG="[backfill:$(basename "${LANE}")]"
  if [ ! -d "${LANE}/.git" ] && [ ! -f "${LANE}/.git" ]; then
    echo "${TAG} SKIP worktree 不存在"
    continue
  fi
  # 锁是【目录】 .orchestrator.lock/pid（atomic mkdir 锁），必须用 -e 而非 -f
  # （-f 对目录判 false → 会漏检活跃锁、误在驱动器 mid-round 时合并，2026-07-07 实测踩坑）。
  if [ -e "${LANE}/.planning/loop/.orchestrator.lock" ]; then
    echo "${TAG} SKIP loop 正在跑（.orchestrator.lock 存在）"
    continue
  fi
  if ! git -C "${LANE}" diff --quiet || ! git -C "${LANE}" diff --cached --quiet; then
    echo "${TAG} SKIP 工作树不 clean（有未提交变更）"
    continue
  fi
  git -C "${LANE}" fetch origin main --quiet
  BEHIND="$(git -C "${LANE}" rev-list --count HEAD..origin/main)"
  if [ "${BEHIND}" = "0" ]; then
    echo "${TAG} OK 已含 origin/main，无需回灌"
    continue
  fi
  if [ "${DRY}" = "1" ]; then
    echo "${TAG} DRY 落后 origin/main ${BEHIND} 个提交，将执行 merge"
    continue
  fi
  if git -C "${LANE}" merge --no-edit origin/main >/dev/null 2>&1; then
    echo "${TAG} MERGED origin/main（落后 ${BEHIND} 提交已回灌）"
  else
    git -C "${LANE}" merge --abort >/dev/null 2>&1 || true
    echo "${TAG} CONFLICT 已 abort，留给 attended 人工处理"
    FAILED=1
  fi
done
exit "${FAILED}"
