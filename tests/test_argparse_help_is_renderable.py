"""`--help` must not crash.

Found 2026-08-05 while trying to read `p2_crosssource_trial.py --help`: it died
with ``ValueError: unsupported format character 'p'``. argparse renders every
``help=`` string through ``%``-formatting (``HelpFormatter._expand_help`` does
``self._get_help_string(action) % params``), so a literal percent sign inside a
help string is a format spec, and ``"the 0% par rate"`` reads as ``%p``.

Two scripts were broken this way -- both entry points a human types when they
are trying to learn the tool, and both broken for as long as the sentence had
been there, because nothing ever rendered them.

This test is static rather than "run every CLI with --help": importing every
script pulls the whole optical stack, and the rule argparse applies is exact,
so it can be checked without executing anything. The rule: inside a ``help=``
string every ``%`` must be followed by ``%`` (an escaped percent) or ``(``
(the start of ``%(default)s`` and friends).

``description=``/``epilog=`` are deliberately not checked -- argparse does not
%-format those, so a percent sign in them is harmless.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCH_ROOTS = ("scripts", "app")


def _bare_percent_index(text: str) -> int | None:
    """Index of the first `%` argparse would choke on, or None."""
    i = 0
    while i < len(text):
        if text[i] == "%":
            following = text[i + 1] if i + 1 < len(text) else ""
            if following not in {"%", "("}:
                return i
            i += 1  # skip the escaped percent / opening paren
        i += 1
    return None


def _help_strings() -> list[tuple[Path, int, str]]:
    out: list[tuple[Path, int, str]] = []
    for root in SEARCH_ROOTS:
        for path in sorted((ROOT / root).rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if getattr(node.func, "attr", None) not in {"add_argument", "add_parser"}:
                    continue
                for keyword in node.keywords:
                    if keyword.arg != "help":
                        continue
                    try:
                        value = ast.literal_eval(keyword.value)
                    except (ValueError, TypeError, SyntaxError):
                        continue  # computed at runtime; out of scope
                    if isinstance(value, str):
                        out.append((path, node.lineno, value))
    return out


def test_the_scan_finds_help_strings_at_all() -> None:
    """Guard the guard: a scan that silently matches nothing always passes."""
    found = _help_strings()
    assert len(found) > 50, f"only {len(found)} help strings found -- the scan is broken"


def test_no_argparse_help_string_has_a_bare_percent() -> None:
    offenders = []
    for path, lineno, value in _help_strings():
        index = _bare_percent_index(value)
        if index is not None:
            offenders.append(
                f"{path.relative_to(ROOT)}:{lineno} ...{value[max(0, index - 40):index + 15]}..."
            )
    assert not offenders, (
        "argparse %-formats help strings, so a literal percent must be written "
        "'%%' or the whole --help crashes:\n  " + "\n  ".join(offenders)
    )


def test_bare_percent_detector_matches_argparse_semantics() -> None:
    """The detector itself, against what argparse actually accepts."""
    assert _bare_percent_index("plain text") is None
    assert _bare_percent_index("escaped 50%% is fine") is None
    assert _bare_percent_index("default is %(default)s") is None
    assert _bare_percent_index("mixed %(default)s and 50%%") is None
    assert _bare_percent_index("the 0% par rate") == 5
    assert _bare_percent_index("trailing %") == 9
    # A real conversion spec argparse would try to apply and fail on.
    assert _bare_percent_index("%s") == 0
