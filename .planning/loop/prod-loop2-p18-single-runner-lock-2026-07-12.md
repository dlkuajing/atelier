# prod-loop2 · Phase18 single-runner lock

## GSD quick entry

- 事故：2026-07-12 Phase18 resume 可由两个进程同时进入，原有 `running` job
  拒重试只保护同一 job，不能阻止两个 runner 在 job 创建/账本快照之间竞态，也不能
  保护 CODE V 单实例席位。
- 范围：仅离线实现与测试；未启动、attach、终止或操作 CODE V，未触碰
  `D:\atelier-wt-ctl` 活 runner。
- 目标：Windows/Linux 原子互斥；锁覆盖完整 `run_batch`；竞争者在任何 batch/job
  创建或 engine 启动前 fail-closed；异常退出只走明确且可审计的恢复流程。

## Module / seam

`app/core/batch_run_lock.py::batch_runner_lock` 是深 module：调用方只有一个 context-manager
interface，内部隐藏 Windows `msvcrt.locking`、POSIX `fcntl.flock`、owner metadata、进程静默
检查和 recovery receipt。

权威性分层：

1. OS byte-range lock 是活跃 runner 的唯一权威互斥事实；PID/hostname 只作诊断，绝不据此
   误杀、删锁或判死。
2. owner JSON 在干净退出时由持锁者删除；进程异常退出时 OS 自动释锁，但 owner 保留，
   普通启动拒绝继续。
3. `--recover-stale-lock` 先非阻塞取得 OS 锁，再确认无其他 Phase18 Python runner、
   `codev`、`codevm` 进程；任一检查不可执行或发现活跃进程均 fail-closed。
4. 恢复成功前先原子写入 `.p18-runner-recoveries/*.json`，保留旧 owner、新 owner、时间与
   两重证明；无 stale owner 时 recovery flag 也拒绝，避免它退化成日常 bypass。
5. 永不替换/删除 lock inode；只锁永久 lock file 的 byte 0，确保 Windows/Linux 进程看到
   同一锁对象。

## Operator recovery

仅当普通 resume 报 `RecoveryRequired` 时：

1. 先人工确认原 runner 已退出且 CODE V/codevm 均归零；不要按 owner PID kill 或直接删除
   owner/lock 文件。
2. 使用原 resume 命令追加 `--recover-stale-lock`。
3. CLI 会再次用 OS 锁和全局进程快照验证；不满足即拒绝且不创建 job。
4. 成功后检查 archive 根的 recovery receipt，再按正常账本/attempt-N 规程继续。

## Offline verification

- 子进程持锁时，第二个 `run_batch` 在 batch/job 创建前拒绝。
- 两个并发 CLI resume 中，第二个退出 2；账本始终只有 `job-0000 attempt-1`。
- `os._exit(23)` 模拟崩溃：普通 run 拒绝；发现 `codevm` 时 recovery 仍拒绝；显式且
  静默验证通过后恢复并写 receipt。
- 干净退出删除 owner；无 stale owner 的 recovery flag 拒绝。
- 所有 pytest 均设置 `PYTHONUTF8=1` 且显式 `-k "not real"`。

## Independent review hardening

独立审查复现初版恢复扫描存在 MAJOR：runner carrier 仅匹配少数固定 Python 名，且
POSIX `/proc` 读取异常会被当成“进程退出”静默跳过。修复后：

- process snapshot 带 PPID，显式排除 recovery 当前进程及其 ancestor chain，避免
  `uv run python ...` 把自己的 `uv` launcher 误报为另一 runner；
- 其它 `uv/uv.exe`、`py/py.exe`、任意 `python*` 载体只要 command line 指向
  `p18_night_batch.py` 均算活跃 runner；
- 潜在 runner carrier 的 command line 缺失/空白即 fail-closed；
- POSIX 只有 `ENOENT/ESRCH`（枚举后进程自然退出）可跳过，EACCES、解码错误及其它
  I/O 异常全部拒绝恢复；Windows snapshot 缺字段、异常类型或解码异常同样拒绝。
- 第二轮独立审查指出 malformed/non-object owner 会让显式恢复不可达；现改为在 OS 锁
  已持有时读取原始 bytes，普通启动仍拒绝，显式恢复在严格进程归零后把 SHA-256、长度、
  安全 parse-error 写入 receipt（不记录/回显原内容）并原子替换 owner。PermissionError
  或其它真实读取 I/O 失败仍 fail-closed。
