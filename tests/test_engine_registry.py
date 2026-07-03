from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from app.core.engines import (
    EngineRegistry,
    NullDeepEngine,
    find_code_v_executable,
    get_deep_engine,
)


@dataclass(frozen=True)
class FakeDeepEngine:
    name: str = "codev"
    available: bool = True

    def is_available(self) -> bool:
        return self.available

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "available": self.available}

    def submit(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        return {"accepted": True, "payload": dict(payload)}


def _make_executable(tmp_path):
    executable = tmp_path / ("codev.exe" if os.name == "nt" else "codev")
    executable.write_text("", encoding="utf-8")
    if os.name != "nt":
        executable.chmod(0o755)
    return executable


def test_registry_registers_and_resolves_available_engine():
    registry = EngineRegistry()
    engine = FakeDeepEngine(name="mock-codev")

    assert registry.register(engine) is engine
    assert registry.get("mock_codev") is engine
    assert registry.resolve("mock codev") is engine
    assert registry.names() == ("mock-codev",)
    assert engine.submit({"case_id": "demo"})["accepted"] is True

    with pytest.raises(ValueError, match="already registered"):
        registry.register(engine)


def test_runtime_probe_returns_registered_code_v_engine_when_executable_exists(tmp_path):
    executable = _make_executable(tmp_path)
    env = {"CODEV_EXECUTABLE": str(executable)}
    registry = EngineRegistry([FakeDeepEngine()])

    assert find_code_v_executable(env=env, search_path="") == executable
    engine = registry.probe_runtime(env=env, search_path="")

    assert engine.name == "codev"
    assert engine.is_available() is True
    assert not isinstance(engine, NullDeepEngine)


def test_runtime_probe_degrades_to_null_without_code_v_executable():
    registry = EngineRegistry([FakeDeepEngine()])

    engine = registry.probe_runtime(
        env={},
        search_path="",
        executable_names=("definitely-missing-code-v",),
    )

    assert isinstance(engine, NullDeepEngine)
    assert engine.name == "null"
    assert engine.is_available() is False
    assert engine.describe()["reason"] == "code_v_executable_not_found"
    with pytest.raises(RuntimeError, match="Deep engine unavailable"):
        engine.submit({"case_id": "demo"})


def test_default_deep_engine_is_null_when_code_v_is_not_detected(monkeypatch):
    monkeypatch.delenv("CODEV_EXECUTABLE", raising=False)
    monkeypatch.delenv("CODE_V_EXECUTABLE", raising=False)
    monkeypatch.delenv("CODEV_EXE", raising=False)
    monkeypatch.delenv("CODE_V_EXE", raising=False)
    monkeypatch.setenv("PATH", "")

    engine = get_deep_engine()

    assert isinstance(engine, NullDeepEngine)
