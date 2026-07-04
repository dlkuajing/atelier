"""Registry and runtime probing for pluggable deep optical engines."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from app.core.engines.base import DeepEngine
from app.core.engines.null import NullDeepEngine

CODE_V_EXECUTABLE_ENV_VARS = (
    "CODEV_EXECUTABLE",
    "CODE_V_EXECUTABLE",
    "CODEV_EXE",
    "CODE_V_EXE",
)
CODE_V_EXECUTABLE_NAMES = ("codev.exe", "codev", "cv.exe")
CODE_V_ENGINE_NAME = "codev"


def _engine_key(name: str) -> str:
    key = "".join(ch for ch in name.lower() if ch.isalnum())
    if not key:
        raise ValueError("engine name must contain at least one alphanumeric character")
    return key


def _existing_file(path: str | os.PathLike[str]) -> Path | None:
    candidate = Path(path).expanduser()
    if candidate.is_file():
        return candidate
    return None


def find_code_v_executable(
    *,
    env: Mapping[str, str] | None = None,
    search_path: str | None = None,
    executable_names: Sequence[str] = CODE_V_EXECUTABLE_NAMES,
) -> Path | None:
    """Find a CODE V executable from explicit env vars or PATH.

    The real CODE V adapter lands later; this probe only answers whether a
    plausible executable is present so the registry can fall back cleanly.
    """
    runtime_env = env if env is not None else os.environ
    for env_var in CODE_V_EXECUTABLE_ENV_VARS:
        value = runtime_env.get(env_var)
        if not value:
            continue
        executable = _existing_file(value)
        if executable is not None:
            return executable
        return None

    path_value = search_path if search_path is not None else runtime_env.get("PATH")
    for executable_name in executable_names:
        found = shutil.which(executable_name, path=path_value)
        if found:
            return Path(found)
    return None


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
        code_v_engine_name: str = CODE_V_ENGINE_NAME,
    ) -> DeepEngine:
        executable = find_code_v_executable(
            env=env,
            search_path=search_path,
            executable_names=executable_names,
        )
        if executable is None:
            return NullDeepEngine(reason="code_v_executable_not_found")

        engine = self.get(code_v_engine_name)
        if engine is None:
            return NullDeepEngine(
                reason="code_v_engine_not_registered",
                details={"executable": str(executable)},
            )
        if not engine.is_available():
            return NullDeepEngine(
                reason="code_v_engine_unavailable",
                details={"engine": engine.name, "executable": str(executable)},
            )
        return engine


default_registry = EngineRegistry()


def register_engine(engine: DeepEngine, *, replace: bool = False) -> DeepEngine:
    return default_registry.register(engine, replace=replace)


def get_engine(name: str) -> DeepEngine | None:
    return default_registry.get(name)


def get_deep_engine() -> DeepEngine:
    return default_registry.probe_runtime()
