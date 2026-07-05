"""Registry and runtime probing for pluggable deep optical engines."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from app.core.engines.base import DeepEngine
from app.core.engines.codev import (
    CODE_V_ENGINE_NAME,
    CODE_V_EXECUTABLE_NAMES,
    probe_code_v_installation,
)
from app.core.engines.null import NullDeepEngine


def _engine_key(name: str) -> str:
    key = "".join(ch for ch in name.lower() if ch.isalnum())
    if not key:
        raise ValueError("engine name must contain at least one alphanumeric character")
    return key

def find_code_v_executable(
    *,
    env: Mapping[str, str] | None = None,
    search_path: str | None = None,
    executable_names: Sequence[str] = CODE_V_EXECUTABLE_NAMES,
    scan_registry: bool = True,
    common_roots: Sequence[Path | str] | None = None,
) -> Path | None:
    """Find the CODE V executable via the installation probe."""
    installation = probe_code_v_installation(
        env=env,
        search_path=search_path,
        executable_names=executable_names,
        scan_registry=scan_registry,
        common_roots=common_roots,
    )
    if installation is None:
        return None
    return installation.codev_executable


class EngineRegistry:
    """Mutable registry for deep optical engine implementations."""

    def __init__(self, engines: Iterable[DeepEngine] = ()) -> None:
        self._engines: dict[str, DeepEngine] = {}
        for engine in engines:
            self.register(engine)

    def register(self, engine: DeepEngine, *, replace: bool = False) -> DeepEngine:
        key = _engine_key(engine.name)
        if key in self._engines and not replace:
            raise ValueError(f"deep engine already registered: {engine.name}")
        self._engines[key] = engine
        return engine

    def get(self, name: str) -> DeepEngine | None:
        return self._engines.get(_engine_key(name))

    def names(self) -> tuple[str, ...]:
        return tuple(engine.name for engine in self._engines.values())

    def resolve(self, name: str) -> DeepEngine:
        engine = self.get(name)
        if engine is None:
            return NullDeepEngine(reason="deep_engine_not_registered", details={"requested": name})
        if not engine.is_available():
            return NullDeepEngine(reason="deep_engine_unavailable", details={"requested": name})
        return engine

    def probe_runtime(
        self,
        *,
        env: Mapping[str, str] | None = None,
        search_path: str | None = None,
        executable_names: Sequence[str] = CODE_V_EXECUTABLE_NAMES,
        scan_registry: bool = True,
        common_roots: Sequence[Path | str] | None = None,
        code_v_engine_name: str = CODE_V_ENGINE_NAME,
    ) -> DeepEngine:
        installation = probe_code_v_installation(
            env=env,
            search_path=search_path,
            executable_names=executable_names,
            scan_registry=scan_registry,
            common_roots=common_roots,
        )
        if installation is None:
            return NullDeepEngine(reason="code_v_executable_not_found")

        engine = self.get(code_v_engine_name)
        if engine is None:
            return NullDeepEngine(
                reason="code_v_engine_not_registered",
                details={"installation": installation.describe()},
            )
        if not engine.is_available():
            return NullDeepEngine(
                reason="code_v_engine_unavailable",
                details={"engine": engine.name, "installation": installation.describe()},
            )
        return engine


default_registry = EngineRegistry()


def register_engine(engine: DeepEngine, *, replace: bool = False) -> DeepEngine:
    return default_registry.register(engine, replace=replace)


def get_engine(name: str) -> DeepEngine | None:
    return default_registry.get(name)


def get_deep_engine() -> DeepEngine:
    return default_registry.probe_runtime()
