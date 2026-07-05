"""CODE V installation probing.

The real batch adapter is a later slice. This module only discovers the local
CODE V installation and reports enough paths for the registry and diagnostics.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

CODE_V_HOME_ENV_VARS = ("CODEV_HOME", "CODE_V_HOME", "CV_EXEC")
CODE_V_EXECUTABLE_ENV_VARS = (
    "CODEV_EXECUTABLE",
    "CODE_V_EXECUTABLE",
    "CODEV_EXE",
    "CODE_V_EXE",
)
CODE_V_EXECUTABLE_NAMES = ("codev.exe", "codev", "cv.exe")
CODE_V_COMMAND_EXECUTABLE_NAMES = ("cvcommand.exe", "cvcommand")
CODE_V_ENGINE_NAME = "codev"

CODE_V_MANUAL_FILENAMES = (
    "Macro-PLUS.pdf",
    "APIReferenceGuide.pdf",
    "CVSetup&OperationRM.pdf",
    "IntroductoryUG.pdf",
    "LensSystemSetupRM.pdf",
    "Optimization.pdf",
    "ReleaseNotes.pdf",
)

_REGISTRY_CODE_V_ROOTS = (
    (r"HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Optical Research Associates\CODE V"),
    (r"HKEY_LOCAL_MACHINE", r"SOFTWARE\Optical Research Associates\CODE V"),
    (r"HKEY_CURRENT_USER", r"SOFTWARE\Optical Research Associates\CODE V"),
    (r"HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Synopsys, Inc.\CODE V"),
    (r"HKEY_LOCAL_MACHINE", r"SOFTWARE\Synopsys, Inc.\CODE V"),
)


@dataclass(frozen=True)
class CodeVInstallation:
    """Serializable facts about one detected CODE V installation."""

    home: Path
    source: str
    version: str | None = None
    executables: Mapping[str, Path] = field(default_factory=dict)
    macro_dir: Path | None = None
    macro_samples: tuple[Path, ...] = ()
    doc_dir: Path | None = None
    manual_paths: tuple[Path, ...] = ()

    @property
    def codev_executable(self) -> Path | None:
        return self.executables.get("codev.exe") or self.executables.get("codev")

    @property
    def command_executable(self) -> Path | None:
        return self.executables.get("cvcommand.exe") or self.executables.get("cvcommand")

    def describe(self) -> dict[str, object]:
        return {
            "home": str(self.home),
            "source": self.source,
            "version": self.version,
            "executables": {name: str(path) for name, path in self.executables.items()},
            "macro_dir": str(self.macro_dir) if self.macro_dir is not None else None,
            "macro_samples": [str(path) for path in self.macro_samples],
            "doc_dir": str(self.doc_dir) if self.doc_dir is not None else None,
            "manual_paths": [str(path) for path in self.manual_paths],
        }


def _clean_env_path(value: str) -> Path:
    return Path(value.strip().strip('"')).expanduser()


def _path_from_executable_env(value: str) -> Path:
    candidate = _clean_env_path(value)
    if candidate.is_file():
        return candidate.parent
    return candidate


def _find_named_file(directory: Path, names: Sequence[str]) -> Path | None:
    for name in names:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def _collect_root_executables(home: Path) -> dict[str, Path]:
    if not home.is_dir():
        return {}
    return {path.name.lower(): path for path in sorted(home.glob("*.exe")) if path.is_file()}


def _collect_macro_samples(home: Path) -> tuple[Path | None, tuple[Path, ...]]:
    macro_dir = home / "macro"
    if not macro_dir.is_dir():
        return None, ()
    return macro_dir, tuple(sorted(macro_dir.glob("*.seq"))[:10])


def _collect_manuals(home: Path) -> tuple[Path | None, tuple[Path, ...]]:
    doc_dir = home / "doc"
    if not doc_dir.is_dir():
        return None, ()

    manuals: list[Path] = []
    for filename in CODE_V_MANUAL_FILENAMES:
        manual = doc_dir / filename
        if manual.is_file():
            manuals.append(manual)
    if not manuals:
        manuals.extend(sorted(doc_dir.glob("*.pdf"))[:10])
    return doc_dir, tuple(manuals)


def _version_from_home_name(home: Path) -> str | None:
    match = re.search(r"codev(?P<major>\d{2})(?P<minor>\d)", home.name, re.IGNORECASE)
    if match is None:
        return None
    return f"{int(match.group('major'))}.{match.group('minor')}"


def _read_windows_file_version(path: Path) -> str | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        version = ctypes.WinDLL("version", use_last_error=True)
        size = version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
            return None

        pointer = ctypes.c_void_p()
        length = wintypes.UINT()
        if not version.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
            return None

        class _FixedFileInfo(ctypes.Structure):
            _fields_ = (
                ("dwSignature", wintypes.DWORD),
                ("dwStrucVersion", wintypes.DWORD),
                ("dwFileVersionMS", wintypes.DWORD),
                ("dwFileVersionLS", wintypes.DWORD),
                ("dwProductVersionMS", wintypes.DWORD),
                ("dwProductVersionLS", wintypes.DWORD),
                ("dwFileFlagsMask", wintypes.DWORD),
                ("dwFileFlags", wintypes.DWORD),
                ("dwFileOS", wintypes.DWORD),
                ("dwFileType", wintypes.DWORD),
                ("dwFileSubtype", wintypes.DWORD),
                ("dwFileDateMS", wintypes.DWORD),
                ("dwFileDateLS", wintypes.DWORD),
            )

        info = ctypes.cast(pointer, ctypes.POINTER(_FixedFileInfo)).contents
        if info.dwSignature != 0xFEEF04BD:
            return None
        return ".".join(
            str(part)
            for part in (
                info.dwFileVersionMS >> 16,
                info.dwFileVersionMS & 0xFFFF,
                info.dwFileVersionLS >> 16,
                info.dwFileVersionLS & 0xFFFF,
            )
        )
    except Exception:  # noqa: BLE001 - version metadata is diagnostic only.
        return None


def _installation_from_home(
    home: Path,
    *,
    source: str,
    executable_names: Sequence[str],
    command_executable_names: Sequence[str],
) -> CodeVInstallation | None:
    home = home.expanduser()
    if not home.is_dir():
        return None

    codev_executable = _find_named_file(home, executable_names)
    if codev_executable is None:
        return None

    executables = _collect_root_executables(home)
    if codev_executable.name.lower() not in executables:
        executables[codev_executable.name.lower()] = codev_executable
    command_executable = _find_named_file(home, command_executable_names)
    if command_executable is not None:
        executables[command_executable.name.lower()] = command_executable

    macro_dir, macro_samples = _collect_macro_samples(home)
    doc_dir, manual_paths = _collect_manuals(home)
    version = _read_windows_file_version(codev_executable) or _version_from_home_name(home)

    return CodeVInstallation(
        home=home,
        source=source,
        version=version,
        executables=executables,
        macro_dir=macro_dir,
        macro_samples=macro_samples,
        doc_dir=doc_dir,
        manual_paths=manual_paths,
    )


def _explicit_env_home(runtime_env: Mapping[str, str]) -> tuple[str, Path] | None:
    for env_var in CODE_V_HOME_ENV_VARS:
        value = runtime_env.get(env_var)
        if value:
            return env_var, _clean_env_path(value)
    for env_var in CODE_V_EXECUTABLE_ENV_VARS:
        value = runtime_env.get(env_var)
        if value:
            return env_var, _path_from_executable_env(value)
    return None


def _registry_hive(root_name: str):
    import winreg

    return {
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
    }[root_name]


def _registry_values(root_name: str, subkey: str) -> Iterator[tuple[str, str]]:
    if os.name != "nt":
        return
    try:
        import winreg

        with winreg.OpenKey(_registry_hive(root_name), subkey) as key:
            index = 0
            while True:
                try:
                    name, value, _value_type = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                if isinstance(value, str) and value.strip():
                    yield name, value
    except OSError:
        return


def _registry_subkeys(root_name: str, subkey: str) -> Iterator[str]:
    if os.name != "nt":
        return
    try:
        import winreg

        with winreg.OpenKey(_registry_hive(root_name), subkey) as key:
            index = 0
            while True:
                try:
                    yield winreg.EnumKey(key, index)
                except OSError:
                    break
                index += 1
    except OSError:
        return


def _iter_registry_homes() -> Iterator[tuple[str, Path]]:
    value_names = {"CV_EXEC", "InstallDir", "InstallPath", "Path"}
    for root_name, root_subkey in _REGISTRY_CODE_V_ROOTS:
        candidates = [root_subkey]
        candidates.extend(f"{root_subkey}\\{version}" for version in _registry_subkeys(root_name, root_subkey))
        for candidate in candidates:
            for value_name, value in _registry_values(root_name, candidate):
                if value_name in value_names:
                    yield f"registry:{root_name}\\{candidate}:{value_name}", _clean_env_path(value)
            directories = f"{candidate}\\Directories"
            for value_name, value in _registry_values(root_name, directories):
                if value_name == "CV_EXEC":
                    yield f"registry:{root_name}\\{directories}:CV_EXEC", _clean_env_path(value)


def _default_common_roots() -> Iterator[Path]:
    for drive in ("C", "D", "E"):
        root = Path(f"{drive}:/")
        for dirname in ("CODEV115", "CODEV114", "CODEV113", "CODEV112", "CODEV111"):
            yield root / dirname
        if root.is_dir():
            yield from sorted(root.glob("CODEV*"))
            yield from sorted((root / "Program Files").glob("CODEV*"))
            yield from sorted((root / "Program Files" / "Synopsys").glob("CODEV*"))


def _iter_common_homes(common_roots: Sequence[Path | str] | None) -> Iterator[Path]:
    roots = _default_common_roots() if common_roots is None else (Path(root) for root in common_roots)
    for root in roots:
        yield root
        if root.is_dir() and not root.name.upper().startswith("CODEV"):
            yield from sorted(root.glob("CODEV*"))


def _dedupe_candidates(candidates: Iterator[tuple[str, Path]]) -> Iterator[tuple[str, Path]]:
    seen: set[str] = set()
    for source, path in candidates:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        yield source, path


def _iter_path_homes(
    *,
    search_path: str | None,
    executable_names: Sequence[str],
) -> Iterator[tuple[str, Path]]:
    if search_path is None:
        return
    for executable_name in executable_names:
        found = shutil.which(executable_name, path=search_path)
        if found:
            yield f"path:{executable_name}", Path(found).parent


def probe_code_v_installation(
    *,
    env: Mapping[str, str] | None = None,
    search_path: str | None = None,
    executable_names: Sequence[str] = CODE_V_EXECUTABLE_NAMES,
    command_executable_names: Sequence[str] = CODE_V_COMMAND_EXECUTABLE_NAMES,
    scan_registry: bool = True,
    common_roots: Sequence[Path | str] | None = None,
) -> CodeVInstallation | None:
    """Probe CODE V in priority order: env home, registry, common roots, fallback."""

    runtime_env = env if env is not None else os.environ
    explicit_home = _explicit_env_home(runtime_env)
    if explicit_home is not None:
        env_var, home = explicit_home
        return _installation_from_home(
            home,
            source=f"env:{env_var}",
            executable_names=executable_names,
            command_executable_names=command_executable_names,
        )

    candidates: list[tuple[str, Path]] = []
    if scan_registry:
        candidates.extend(_iter_registry_homes())
    candidates.extend((f"common:{path}", path) for path in _iter_common_homes(common_roots))
    candidates.extend(_iter_path_homes(search_path=search_path, executable_names=executable_names))

    for source, home in _dedupe_candidates(iter(candidates)):
        installation = _installation_from_home(
            home,
            source=source,
            executable_names=executable_names,
            command_executable_names=command_executable_names,
        )
        if installation is not None:
            return installation
    return None
