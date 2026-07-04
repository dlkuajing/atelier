#!/usr/bin/env python3
"""redline_compile.py — L2 红线单源零 LLM 确定性编译器（jiangren-cnc）。

读 .planning/loop/redline.source.yaml（flat 行式指令 DSL）→ 编译到内存 →
与 .planning/loop/ 下 5 份消费件逐字节比对（--check）或覆写（--write）。

DSL 指令集（逐行处理，仅剥行尾换行）：
    # <text>          源级注释，解析器忽略
    <空行>            解析器忽略（源文件排版用）
    @file <name>      切换当前输出目标；<name> 必须 in CONSUMER_FILES；每目标恰一段
    @c                向当前目标发射一个空行
    @c <text>         向当前目标发射 <text> 逐字节
    @line <id> <token> 向当前目标发射 <token> 逐字节（按首个空格切 id 与 token）
    @reg <id>[,<id>...] | ps=<0|1> dc=<0|1> cg=<0|1> te=<0|1> | <reason>
                      元数据登记，不发射；供 --audit 校验覆盖率

fail-closed：未知指令、@line/@c 出现在 @file 之前、非法/重复 @file 名、
发射内容以 @ 开头（防未来与指令前缀碰撞）→ 抛 SourceError（CLI 侧转 exit 2）。

同输入必同输出：零时间戳/随机/环境依赖；纯 stdlib（禁 import yaml）。
"""
# ---------------------------------------------------------------------------
# 模板副本 · loop-init 项目脚手架（dotfiles claude/loop-harness/project-template）
# 上游真源 = jiangren-cnc 仓库同名文件；落项目后本文件归项目所有，升级需手动对账。
# ---------------------------------------------------------------------------

from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import sys
from pathlib import Path

CONSUMER_FILES: tuple[str, ...] = (
    "redline-paths.txt",
    "forbidden-paths.txt",
    "redline-symbols.txt",
    "redline-symbol-tooling-paths.txt",
    "redline-symbol-tooling-exempt.txt",
)

SOURCE_NAME = "redline.source.yaml"


class SourceError(Exception):
    """真源解析/校验失败（fail-closed，语义见模块 docstring）。"""


class RegEntry:
    __slots__ = ("ids", "flags", "reason", "lineno")

    def __init__(self, ids: list[str], flags: dict[str, str], reason: str, lineno: int) -> None:
        self.ids = ids
        self.flags = flags
        self.reason = reason
        self.lineno = lineno


class ParsedSource:
    __slots__ = ("targets", "line_ids", "registry")

    def __init__(
        self,
        targets: dict[str, list[str]],
        line_ids: set[str],
        registry: list[RegEntry],
    ) -> None:
        self.targets = targets
        self.line_ids = line_ids
        self.registry = registry


def _guard_no_at(token: str, lineno: int) -> None:
    if token.startswith("@"):
        raise SourceError(
            f"line {lineno}: 发射内容以 @ 开头，与指令前缀碰撞，拒绝: {token!r}"
        )


def parse_source(text: str) -> ParsedSource:
    """解析 flat 指令 DSL 文本，返回逐目标发射行 + @line id 集合 + @reg 登记表。"""
    targets: dict[str, list[str]] = {}
    seen_ids_by_target: dict[str, set[str]] = {}
    token_by_id: dict[str, str] = {}
    line_ids: set[str] = set()
    registry: list[RegEntry] = []
    current: str | None = None

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # 文件末尾恰一个结尾换行 → split 产出的幽灵空尾元素丢弃

    for lineno, raw in enumerate(lines, start=1):
        if raw == "":
            continue
        if raw.startswith("#"):
            continue
        if not raw.startswith("@"):
            raise SourceError(
                f"line {lineno}: 非法源行(非 @ 指令/# 注释/空行): {raw!r}"
            )

        if raw.startswith("@file "):
            name = raw[len("@file ") :]
            if name not in CONSUMER_FILES:
                raise SourceError(f"line {lineno}: 非法 @file 名: {name!r}")
            if name in targets:
                raise SourceError(f"line {lineno}: @file 重复: {name!r}")
            targets[name] = []
            seen_ids_by_target[name] = set()
            current = name
            continue

        if raw == "@c" or raw.startswith("@c "):
            if current is None:
                raise SourceError(f"line {lineno}: @c 出现在 @file 之前")
            token = "" if raw == "@c" else raw[len("@c ") :]
            _guard_no_at(token, lineno)
            targets[current].append(token)
            continue

        if raw.startswith("@line "):
            if current is None:
                raise SourceError(f"line {lineno}: @line 出现在 @file 之前")
            remainder = raw[len("@line ") :]
            reg_id, sep, token = remainder.partition(" ")
            if not sep or not reg_id:
                raise SourceError(f"line {lineno}: @line 缺 id 或 token: {raw!r}")
            # 同一 id 允许跨不同 @file 段复用（单源语义：两文件共享同 token 的红线
            # 用同一 id，一条 @reg 登记覆盖两处发射）；同一 @file 段内重复 = 真错误。
            if reg_id in seen_ids_by_target[current]:
                raise SourceError(f"line {lineno}: @line id 在同一 @file 段内重复: {reg_id!r}")
            _guard_no_at(token, lineno)
            prev = token_by_id.get(reg_id)
            if prev is not None and prev != token:
                raise SourceError(
                    f"line {lineno}: @line id {reg_id!r} 跨目标 token 不一致"
                    f"(此前为 {prev!r})"
                )
            token_by_id[reg_id] = token
            seen_ids_by_target[current].add(reg_id)
            line_ids.add(reg_id)
            targets[current].append(token)
            continue

        if raw.startswith("@reg "):
            remainder = raw[len("@reg ") :]
            parts = remainder.split(" | ")
            if len(parts) != 3:
                raise SourceError(f"line {lineno}: @reg 格式错误(需 3 段 '|' 分隔): {raw!r}")
            ids_part, flags_part, reason_part = parts
            ids = [x.strip() for x in ids_part.split(",")]
            if not ids or not all(ids):
                raise SourceError(f"line {lineno}: @reg id 列表非法: {raw!r}")
            flags: dict[str, str] = {}
            for tok in flags_part.split():
                k, eq, v = tok.partition("=")
                if not eq or v not in ("0", "1"):
                    raise SourceError(f"line {lineno}: @reg flag 非法: {tok!r}")
                if k not in ("ps", "dc", "cg", "te"):
                    raise SourceError(f"line {lineno}: @reg 未知 flag: {k!r}")
                if k in flags:
                    raise SourceError(f"line {lineno}: @reg flag 重复: {k!r}")
                flags[k] = v
            for required in ("ps", "dc", "cg", "te"):
                if required not in flags:
                    raise SourceError(f"line {lineno}: @reg 缺 flag {required}")
            if not reason_part.strip():
                raise SourceError(f"line {lineno}: @reg reason 为空")
            registry.append(RegEntry(ids, flags, reason_part, lineno))
            continue

        raise SourceError(f"line {lineno}: 未知指令: {raw!r}")

    return ParsedSource(targets, line_ids, registry)


def emit(target_lines: list[str]) -> bytes:
    """每目标 = 输出行以 \\n 连接 + 追加恰好一个结尾 \\n（byte_facts 契约）。"""
    if not target_lines:
        return b""
    return ("\n".join(target_lines) + "\n").encode("utf-8")


def find_repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(out.stdout.strip())


def load_parsed(root: Path) -> ParsedSource:
    source_path = root / ".planning" / "loop" / SOURCE_NAME
    if not source_path.is_file():
        raise SourceError(f"真源不存在: {source_path}")
    text = source_path.read_bytes().decode("utf-8")
    parsed = parse_source(text)
    missing = [name for name in CONSUMER_FILES if name not in parsed.targets]
    if missing:
        raise SourceError(f"真源缺失消费件段: {missing}")
    return parsed


def cmd_check(root: Path) -> int:
    parsed = load_parsed(root)
    loop_dir = root / ".planning" / "loop"
    mismatched = False
    for name in CONSUMER_FILES:
        expected = emit(parsed.targets[name])
        target_path = loop_dir / name
        actual = target_path.read_bytes() if target_path.is_file() else None
        if actual == expected:
            continue
        mismatched = True
        expected_text = expected.decode("utf-8", errors="replace")
        actual_text = (actual or b"").decode("utf-8", errors="replace")
        diff = difflib.unified_diff(
            actual_text.splitlines(keepends=True),
            expected_text.splitlines(keepends=True),
            fromfile=f"{name} (磁盘现状)",
            tofile=f"{name} (真源编译结果)",
        )
        sys.stdout.writelines(diff)
    if mismatched:
        return 1
    print(f"--check OK: {len(CONSUMER_FILES)} 份消费件字节 diff=0")
    return 0


def cmd_write(root: Path) -> int:
    parsed = load_parsed(root)
    loop_dir = root / ".planning" / "loop"
    for name in CONSUMER_FILES:
        dest = loop_dir / name
        tmp = dest.with_name(dest.name + ".tmp-redline-compile")
        tmp.write_bytes(emit(parsed.targets[name]))
        os.replace(tmp, dest)
    print(f"--write OK: 已覆写 {len(CONSUMER_FILES)} 份消费件")
    return 0


def cmd_audit(root: Path) -> int:
    parsed = load_parsed(root)
    covered: dict[str, int] = {}
    problems: list[str] = []
    for entry in parsed.registry:
        for reg_id in entry.ids:
            if reg_id not in parsed.line_ids:
                problems.append(
                    f"@reg(line {entry.lineno}) 登记了不存在的 id: {reg_id!r}"
                )
                continue
            if reg_id in covered:
                problems.append(
                    f"id {reg_id!r} 被多条 @reg 重复覆盖"
                    f"(line {covered[reg_id]} 与 line {entry.lineno})"
                )
                continue
            covered[reg_id] = entry.lineno
    uncovered = sorted(parsed.line_ids - covered.keys())
    for reg_id in uncovered:
        problems.append(f"@line id 未被任何 @reg 登记: {reg_id!r}")
    if problems:
        for p in problems:
            print(f"AUDIT FAIL: {p}")
        return 1
    print(f"--audit OK: {len(parsed.line_ids)} 个 @line id 恰各被一条 @reg 覆盖")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="编译到内存并与磁盘 5 份消费件逐字节比对")
    mode.add_argument("--write", action="store_true", help="确定性覆写 5 份消费件")
    mode.add_argument("--audit", action="store_true", help="校验 @line id 恰被一条 @reg 覆盖")
    parser.add_argument("--root", type=Path, default=None, help="repo root（默认 git rev-parse --show-toplevel）")
    args = parser.parse_args(argv)

    try:
        root = args.root if args.root is not None else find_repo_root()
        root = root.resolve()
        if args.check:
            return cmd_check(root)
        if args.write:
            return cmd_write(root)
        return cmd_audit(root)
    except SourceError as exc:
        print(f"SOURCE ERROR: {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"git rev-parse 失败: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
