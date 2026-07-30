"""`generate_cases.py --only` decides which designs get rebuilt.

A wrong answer here is expensive in one direction and silent in the other: too wide and
a manifest edit churns all 442 designs through Optiland (and through the build hazard
documented at ``BUILD_TIMEOUT_S``); too narrow and a case the edit *did* move keeps a
stale artifact that still looks committed and reviewed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.generate_cases import _read_only_list
from tests.data.zmx_manifest import ZMX_AMMO

_KNOWN_ID = ZMX_AMMO[0]["filename"].rsplit(".", 1)[0]
_KNOWN_FILENAME = ZMX_AMMO[0]["filename"]


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "only.txt"
    path.write_text(body, encoding="utf-8")
    return path


def test_bare_case_ids_and_zmx_filenames_name_the_same_design(tmp_path: Path) -> None:
    """Both spellings appear in practice -- index.json stores ``source_zmx``, the
    per-case JSON is named by ``case_id`` -- so a list mixing them must not silently
    resolve to two different things."""

    assert _read_only_list(_write(tmp_path, f"{_KNOWN_FILENAME}\n")) == {_KNOWN_ID}
    assert _read_only_list(_write(tmp_path, f"{_KNOWN_ID}\n")) == {_KNOWN_ID}


def test_blank_lines_and_comments_are_not_case_ids(tmp_path: Path) -> None:
    body = f"# why this subset\n\n  {_KNOWN_ID}  \n\n"
    assert _read_only_list(_write(tmp_path, body)) == {_KNOWN_ID}


def test_an_empty_list_selects_nothing_rather_than_everything(tmp_path: Path) -> None:
    """Fail-safe direction: an empty ``--only`` holds every design at its committed
    JSON. The opposite default would turn a typo into a full-library rebuild."""

    assert _read_only_list(_write(tmp_path, "# nothing\n")) == set()


def test_a_case_id_the_manifest_does_not_know_is_refused(tmp_path: Path) -> None:
    """A misspelled id would otherwise select nothing and report success, leaving the
    case it was meant to rebuild stale."""

    with pytest.raises(SystemExit) as excinfo:
        _read_only_list(_write(tmp_path, f"{_KNOWN_ID}\nNO-SUCH-CASE\n"))
    assert "NO-SUCH-CASE" in str(excinfo.value)
