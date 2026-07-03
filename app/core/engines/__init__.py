"""Pluggable deep optical engine interfaces."""

from app.core.engines.base import DeepEngine
from app.core.engines.null import NullDeepEngine
from app.core.engines.registry import (
    CODE_V_ENGINE_NAME,
    CODE_V_EXECUTABLE_ENV_VARS,
    CODE_V_EXECUTABLE_NAMES,
    EngineRegistry,
    find_code_v_executable,
    get_deep_engine,
    get_engine,
    register_engine,
)

__all__ = [
    "CODE_V_ENGINE_NAME",
    "CODE_V_EXECUTABLE_ENV_VARS",
    "CODE_V_EXECUTABLE_NAMES",
    "DeepEngine",
    "EngineRegistry",
    "NullDeepEngine",
    "find_code_v_executable",
    "get_deep_engine",
    "get_engine",
    "register_engine",
]
