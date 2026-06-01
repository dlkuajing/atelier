from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_production_docker_image_includes_runtime_zmx_data() -> None:
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (BACKEND_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "COPY data ./data" in dockerfile
    assert "data/" not in {
        line.strip()
        for line in dockerignore.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_runtime_zmx_seed_referenced_by_smoke_is_checked_in() -> None:
    seed = BACKEND_ROOT / "data/zmx/4P_F2.2_FOV74.7_EFL2.9_IMH2.2_TTL3.90.zmx"

    assert seed.is_file()
