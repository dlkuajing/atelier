from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    REPO_ROOT
    / ".planning"
    / "quick"
    / "260727-patent-saturation-repository-slimming"
    / "lfs-evidence-manifest.json"
)
EVIDENCE_ROOTS = (
    REPO_ROOT / ".planning" / "quick",
    REPO_ROOT / "data" / "patent-lake",
)
LFS_EVIDENCE_SUFFIXES = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def _repo_path(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def test_lfs_evidence_manifest_matches_hydrated_checkout() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = manifest["files"]
    expected = {entry["path"]: entry for entry in entries}
    actual_paths = {
        _repo_path(path): path
        for root in EVIDENCE_ROOTS
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in LFS_EVIDENCE_SUFFIXES
    }

    assert manifest["schema_version"] == 1
    assert manifest["storage"] == "git-lfs"
    assert manifest["oid_algorithm"] == "sha256"
    assert manifest["file_count"] == len(entries) == len(expected)
    assert set(expected) == set(actual_paths)

    unique_sizes: dict[str, int] = {}
    errors: list[str] = []
    total_bytes = 0
    for repo_path, entry in expected.items():
        path = actual_paths[repo_path]
        expected_size = int(entry["bytes"])
        oid = entry["oid_sha256"]
        actual_size = path.stat().st_size
        total_bytes += actual_size

        prior_size = unique_sizes.setdefault(oid, expected_size)
        if prior_size != expected_size:
            errors.append(
                f"{repo_path}: object {oid} has conflicting sizes "
                f"{prior_size} and {expected_size}"
            )
        if actual_size != expected_size:
            errors.append(
                f"{repo_path}: expected {expected_size} bytes, got {actual_size}"
            )
            continue
        actual_hash = _sha256(path)
        if actual_hash != oid:
            errors.append(f"{repo_path}: expected sha256 {oid}, got {actual_hash}")

    assert not errors, "\n".join(errors[:20])
    assert manifest["total_bytes"] == total_bytes
    assert manifest["unique_object_count"] == len(unique_sizes)
    assert manifest["unique_object_bytes"] == sum(unique_sizes.values())
