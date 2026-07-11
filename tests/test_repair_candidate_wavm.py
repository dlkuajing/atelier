from __future__ import annotations

from pathlib import Path

import pytest

from scripts.repair_candidate_wavm import main, repair_wavm_file


def test_pads_three_slot_file_only_when_write_is_enabled(tmp_path: Path) -> None:
    path = tmp_path / "candidate.zmx"
    original = "VERS 1\r\nWAVM 1 0.486 1\r\nWAVM 2 0.588 1\r\nWAVM 3 0.656 1\r\nPWAV 2\r\n"
    path.write_text(original, encoding="ascii", newline="")
    assert repair_wavm_file(path) == (21, True)
    with path.open(encoding="ascii", newline="") as handle:
        assert handle.read() == original
    assert repair_wavm_file(path, write=True) == (21, True)
    with path.open(encoding="ascii", newline="") as handle:
        text = handle.read()
    # CRLF endings break ZEMAXOS_TO_CV's WAVM parsing (real-machine proof
    # 2026-07-11: byte-identical A/B import) — output must be LF-only.
    assert "\r" not in text
    lines = text.splitlines()
    wavm = [line for line in lines if line.startswith("WAVM ")]
    assert len(wavm) == 24
    assert wavm[:3] == ["WAVM 1 0.486 1", "WAVM 2 0.588 1", "WAVM 3 0.656 1"]
    assert wavm[3:] == [f"WAVM {slot} 0.55 1" for slot in range(4, 25)]


def test_already_24_slot_file_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "complete.zmx"
    content = "".join(f"WAVM {slot} 0.55 1\n" for slot in range(1, 25))
    path.write_text(content, encoding="ascii", newline="")
    assert repair_wavm_file(path, write=True) == (0, False)
    with path.open(encoding="ascii", newline="") as handle:
        assert handle.read() == content


def test_already_24_slot_crlf_file_gets_eol_normalized(tmp_path: Path) -> None:
    path = tmp_path / "complete_crlf.zmx"
    content = "".join(f"WAVM {slot} 0.55 1\r\n" for slot in range(1, 25))
    path.write_text(content, encoding="ascii", newline="")
    assert repair_wavm_file(path, write=True) == (0, True)
    with path.open(encoding="ascii", newline="") as handle:
        text = handle.read()
    assert "\r" not in text
    assert text == content.replace("\r\n", "\n")


def test_refuses_and_reports_file_without_wavm(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "missing.zmx"
    path.write_text("VERS 1\nPWAV 1\n", encoding="ascii")
    assert main([str(path), "--write"]) == 1
    assert "refused" in capsys.readouterr().out
    assert path.read_text(encoding="ascii") == "VERS 1\nPWAV 1\n"
