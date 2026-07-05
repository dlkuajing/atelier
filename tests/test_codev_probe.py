from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.core.engines import EngineRegistry, NullDeepEngine, probe_code_v_installation


@dataclass(frozen=True)
class FakeCodeVEngine:
    name: str = "codev"

    def is_available(self) -> bool:
        return True

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "available": True}

    def submit(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        return {"accepted": True, "payload": dict(payload)}


def _make_codev_home(root: Path) -> Path:
    home = root / "CODEV115"
    (home / "macro").mkdir(parents=True)
    (home / "doc").mkdir()
    (home / "codev.exe").write_text("", encoding="utf-8")
    (home / "cvcommand.exe").write_text("", encoding="utf-8")
    (home / "macro" / "sample.seq").write_text("! sample", encoding="utf-8")
    (home / "doc" / "Macro-PLUS.pdf").write_text("manual", encoding="utf-8")
    return home


def test_probe_uses_codev_home_before_common_roots(tmp_path: Path) -> None:
    env_home = _make_codev_home(tmp_path / "env")
    common_home = _make_codev_home(tmp_path / "common")

    installation = probe_code_v_installation(
        env={"CODEV_HOME": str(env_home)},
        scan_registry=False,
        common_roots=(common_home,),
    )

    assert installation is not None
    assert installation.home == env_home
    assert installation.source == "env:CODEV_HOME"
    assert installation.codev_executable == env_home / "codev.exe"
    assert installation.command_executable == env_home / "cvcommand.exe"
    assert installation.macro_samples == (env_home / "macro" / "sample.seq",)
    assert installation.manual_paths == (env_home / "doc" / "Macro-PLUS.pdf",)


def test_probe_scans_common_roots_when_env_is_absent(tmp_path: Path) -> None:
    home = _make_codev_home(tmp_path)

    installation = probe_code_v_installation(
        env={},
        scan_registry=False,
        common_roots=(tmp_path,),
    )

    assert installation is not None
    assert installation.home == home
    assert installation.source == f"common:{tmp_path / 'CODEV115'}"


def test_registry_uses_probe_before_resolving_registered_codev(tmp_path: Path) -> None:
    home = _make_codev_home(tmp_path)
    registry = EngineRegistry([FakeCodeVEngine()])

    engine = registry.probe_runtime(
        env={"CODEV_HOME": str(home)},
        scan_registry=False,
        common_roots=(),
    )

    assert engine.name == "codev"
    assert engine.is_available() is True
    assert not isinstance(engine, NullDeepEngine)


def test_registry_degrades_when_codev_home_is_invalid(tmp_path: Path) -> None:
    registry = EngineRegistry([FakeCodeVEngine()])

    engine = registry.probe_runtime(
        env={"CODEV_HOME": str(tmp_path / "missing")},
        scan_registry=False,
        common_roots=(),
    )

    assert isinstance(engine, NullDeepEngine)
    assert engine.describe()["reason"] == "code_v_executable_not_found"


@pytest.mark.skipif(not Path("D:/CODEV115").is_dir(), reason="CODE V is not installed here")
def test_real_codev115_installation_probe() -> None:
    installation = probe_code_v_installation(
        env={"CODEV_HOME": "D:/CODEV115"},
        scan_registry=False,
        common_roots=(),
    )

    assert installation is not None
    assert installation.home == Path("D:/CODEV115")
    assert installation.codev_executable == Path("D:/CODEV115/codev.exe")
    assert installation.command_executable == Path("D:/CODEV115/cvcommand.exe")
    assert installation.version is not None
    assert installation.version.startswith("11.5")
    assert any(path.name.lower().endswith(".seq") for path in installation.macro_samples)
    assert Path("D:/CODEV115/doc/Macro-PLUS.pdf") in installation.manual_paths
