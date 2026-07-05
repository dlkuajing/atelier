"""Pluggable deep optical engine interfaces."""

from app.core.engines.base import DeepEngine
from app.core.engines.codev import (
    CODE_V_ENGINE_NAME,
    CODE_V_EXECUTABLE_ENV_VARS,
    CODE_V_EXECUTABLE_NAMES,
    CODE_V_HOME_ENV_VARS,
    CodeVInstallation,
    probe_code_v_installation,
)
from app.core.engines.null import NullDeepEngine
from app.core.engines.registry import (
    EngineRegistry,
    find_code_v_executable,
    get_deep_engine,
    get_engine,
    register_engine,
)
from app.core.engines.sleep import SleepEngine

__all__ = [
    "CODE_V_ENGINE_NAME",
    "CODE_V_EXECUTABLE_ENV_VARS",
    "CODE_V_EXECUTABLE_NAMES",
    "CODE_V_HOME_ENV_VARS",
    "CodeVInstallation",
    "DeepEngine",
    "EngineRegistry",
    "NullDeepEngine",
    "SleepEngine",
    "find_code_v_executable",
    "get_deep_engine",
    "get_engine",
    "probe_code_v_installation",
    "register_engine",
]
