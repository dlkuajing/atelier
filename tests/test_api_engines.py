"""Tests for /api/optical/engines."""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)

_CODE_V_ENV_VARS = (
    "CODEV_EXECUTABLE",
    "CODE_V_EXECUTABLE",
    "CODEV_EXE",
    "CODE_V_EXE",
)


def _clear_code_v_runtime(monkeypatch) -> None:
    for env_var in _CODE_V_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setenv("PATH", "")


def test_engines_endpoint_returns_inventory_shape(monkeypatch):
    _clear_code_v_runtime(monkeypatch)

    r = client.get("/api/optical/engines")

    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"available", "default_engine", "engines"}
    assert data["available"] is False
    assert data["default_engine"] == "null"
    assert isinstance(data["engines"], list)
    assert len(data["engines"]) == 1


def test_engines_endpoint_degrades_without_code_v(monkeypatch):
    _clear_code_v_runtime(monkeypatch)

    r = client.get("/api/optical/engines")

    assert r.status_code == 200
    engine = r.json()["engines"][0]
    assert engine["name"] == "null"
    assert engine["engine"] == "NullDeepEngine"
    assert engine["available"] is False
    assert engine["reason"] == "code_v_executable_not_found"
    assert engine["details"] == {}
    assert engine["capabilities"] == []
