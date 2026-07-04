from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_project_package_name_is_atelier() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "atelier"


def test_lockfile_virtual_root_package_name_is_atelier() -> None:
    lockfile = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))

    root_packages = [
        package
        for package in lockfile["package"]
        if package.get("source") == {"virtual": "."}
    ]

    assert [package["name"] for package in root_packages] == ["atelier"]
