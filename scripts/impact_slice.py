"""Which test files can your change actually break?

The expensive failure mode this exists to stop: you change a production module,
run "the tests that look related", push, and 57 minutes later CI tells you a
file you never considered imports it. That happened on 2026-07-28 -- a
`zmx_writer` change broke `tests/test_patent_to_zmx.py`, which reaches it
through `scripts/patent_to_zmx.py` via a *function-level* import. The failed run
plus its replacement cost ~114 minutes of wall clock; the grep that would have
found it costs under a second.

The rule this encodes: **run the reverse-dependency slice, not the slice you
guessed.** Guessing is what failed.

How it works: parse every `app/**` and `scripts/**` module with `ast` (so
imports inside functions count -- that is exactly the case that was missed),
invert the graph, take the transitive closure over the changed modules, then
report every test file that references anything in that closure.

Deliberately biased toward over-reporting. A test file you did not need to run
costs seconds; one you needed and skipped costs a CI round trip.

Usage::

    uv run python scripts/impact_slice.py                    # vs origin/main
    uv run python scripts/impact_slice.py --base HEAD~1
    uv run python scripts/impact_slice.py --files app/core/engines/zmx_writer.py
    uv run python scripts/impact_slice.py --pytest           # ready-to-run command
"""

from __future__ import annotations

import argparse
import ast
import subprocess
from collections import defaultdict, deque
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("app", "scripts")
TEST_DIR = ROOT / "tests"


def module_name_for(path: Path) -> str | None:
    """Dotted module name for a repo-relative source file, or None if outside."""

    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return None
    if relative.suffix != ".py" or relative.parts[0] not in SOURCE_DIRS:
        return None
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imported_names(path: Path) -> set[str]:
    """Every dotted name this file imports, including inside functions.

    Walking the whole tree rather than just module-level statements is the
    entire point: the 2026-07-28 miss was a `from ... import ...` sitting inside
    a function body.
    """

    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def source_files() -> list[Path]:
    files: list[Path] = []
    for directory in SOURCE_DIRS:
        files.extend(sorted((ROOT / directory).rglob("*.py")))
    return [f for f in files if "__pycache__" not in f.parts]


@cache
def build_reverse_graph() -> dict[str, set[str]]:
    """module -> modules that import it (directly).

    Cached: parsing every source file costs seconds, mostly on the ~90k-line
    `scripts/patent_to_zmx.py`, and callers ask for several slices in a row. A
    pre-push check nobody waits for is a pre-push check nobody runs.
    """

    known = {module_name_for(f): f for f in source_files()}
    known.pop(None, None)
    reverse: dict[str, set[str]] = defaultdict(set)
    for module, path in known.items():
        for name in imported_names(path):  # type: ignore[arg-type]
            # `from app.core.engines.zmx_writer import build_zmx_from_codev_readout`
            # yields both the module and the symbol; trim back to the longest
            # prefix that is a real module.
            parts = name.split(".")
            while parts:
                candidate = ".".join(parts)
                if candidate in known and candidate != module:
                    reverse[candidate].add(module)  # type: ignore[arg-type]
                    break
                parts.pop()
    return reverse


def affected_modules(changed: list[Path]) -> set[str]:
    """Changed modules plus everything that transitively imports them."""

    reverse = build_reverse_graph()
    seen: set[str] = set()
    queue: deque[str] = deque()
    for path in changed:
        module = module_name_for(path)
        if module is not None:
            seen.add(module)
            queue.append(module)
    while queue:
        for importer in reverse.get(queue.popleft(), ()):
            if importer not in seen:
                seen.add(importer)
                queue.append(importer)
    return seen


def select_test_files(modules: set[str]) -> list[Path]:
    """Test files that *import* any affected module.

    Matching on imports rather than substrings matters: a first cut matched bare
    module names anywhere in the file and returned 75 of ~80 test files for a
    `zmx_writer` change, because affected hubs like `config` appear as a word in
    almost every test. That is not a slice, it is the full suite with extra
    steps.
    """

    if not modules:
        return []
    hits: list[Path] = []
    for path in sorted(TEST_DIR.rglob("test_*.py")):
        imported = imported_names(path)
        # `sys.path` puts `scripts/` on the path in some tests, so a bare
        # `import patent_to_zmx` means `scripts.patent_to_zmx`.
        for name in list(imported):
            imported.add(f"scripts.{name}")
        if any(
            name == module or name.startswith(f"{module}.")
            for name in imported
            for module in modules
        ):
            hits.append(path)
    return hits


def changed_files(base: str) -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Fall back to the working tree when the base ref is unknown (fresh
        # worktree, detached history) rather than silently reporting nothing.
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"], cwd=ROOT, capture_output=True, text=True
        )
    return [ROOT / line for line in result.stdout.split("\n") if line.strip()]


def _anchor(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--files", nargs="*", help="explicit paths instead of a git diff")
    parser.add_argument("--pytest", action="store_true", help="print a ready-to-run command")
    args = parser.parse_args(argv)

    # Relative paths are the natural thing to type, so anchor them at the repo
    # root rather than the caller's cwd.
    changed = [_anchor(f) for f in args.files] if args.files else changed_files(args.base)
    source_changed = [f for f in changed if module_name_for(f) is not None]
    modules = affected_modules(source_changed)
    tests = select_test_files(modules)

    if args.pytest:
        if not tests:
            print("# no source modules changed -- nothing to run")
            return 0
        rel = " ".join(str(t.relative_to(ROOT)).replace("\\", "/") for t in tests)
        print(f'uv run pytest -q -m "not real_machine" {rel}')
        return 0

    print(f"changed source modules ({len(source_changed)}):")
    for path in source_changed:
        print(f"  {path.relative_to(ROOT)}")
    print(f"\naffected modules incl. transitive importers ({len(modules)}):")
    for module in sorted(modules):
        print(f"  {module}")
    print(f"\ntest files to run ({len(tests)}):")
    for path in tests:
        print(f"  {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
