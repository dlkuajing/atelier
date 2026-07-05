from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core import case_library
from scripts.rebase_seed_imh import rebase_seed_imh


def test_rebase_seed_imh_uses_mocked_codev_readout_and_writes_report(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    zmx_dir = tmp_path / "zmx"
    report_path = tmp_path / "seed-imh-rebase-report.md"
    zmx_dir.mkdir()
    (zmx_dir / "US100.zmx").write_text("fake", encoding="ascii")
    (zmx_dir / "US200.zmx").write_text("fake", encoding="ascii")
    index_path.write_text(
        json.dumps(
            [
                {
                    "case_id": "US100",
                    "source_zmx": "US100.zmx",
                    "image_height_mm": 1.0,
                },
                {
                    "case_id": "US200",
                    "source_zmx": "US200.zmx",
                    "image_height_mm": 2.0,
                },
                {
                    "case_id": "not-a-patent",
                    "source_zmx": "not-a-patent.zmx",
                    "image_height_mm": 9.0,
                },
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    measured = {"US100.zmx": 1.2345678, "US200.zmx": 2.5}
    calls: list[tuple[Path, Path]] = []

    def fake_readout_runner(**kwargs: object) -> SimpleNamespace:
        source_zmx = Path(kwargs["source_zmx"])
        work_dir = Path(kwargs["work_dir"])
        calls.append((source_zmx, work_dir))
        return SimpleNamespace(
            batch=SimpleNamespace(duration_seconds=0.01),
            readout=SimpleNamespace(image_height_y_mm=measured[source_zmx.name]),
        )

    rows = rebase_seed_imh(
        index_path=index_path,
        zmx_dir=zmx_dir,
        report_path=report_path,
        work_root=tmp_path / "work",
        readout_runner=fake_readout_runner,
        generated_at=datetime(2026, 7, 5, tzinfo=UTC),
    )

    rewritten = json.loads(index_path.read_text(encoding="utf-8"))
    by_id = {record["case_id"]: record for record in rewritten}
    assert by_id["US100"]["image_height_mm"] == pytest.approx(1.234568)
    assert by_id["US200"]["image_height_mm"] == pytest.approx(2.5)
    assert by_id["not-a-patent"]["image_height_mm"] == pytest.approx(9.0)
    assert [row.case_id for row in rows] == ["US100", "US200"]
    assert [call[0].name for call in calls] == ["US100.zmx", "US200.zmx"]
    assert calls[0][1].name == "US100"

    report = report_path.read_text(encoding="utf-8")
    assert "SEED-01a 真 IMH 重锚报告" in report
    assert "| US100 | 1.000000 | 1.234568 | +0.234568 |" in report
    assert "| US200 | 2.000000 | 2.500000 | +0.500000 |" in report


def test_case_image_height_prefers_metadata_then_index_then_case_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "index.json").write_text(
        json.dumps(
            [
                {
                    "case_id": "US_INDEX",
                    "source_zmx": "US_INDEX.zmx",
                    "image_height_mm": 3.75,
                },
                {
                    "case_id": "US_SOURCE",
                    "source_zmx": "US_SOURCE.zmx",
                    "image_height_mm": 4.25,
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(case_library, "CASES_DIR", cases_dir)
    case_library._case_index_image_height_mm_by_id.cache_clear()

    metadata_case = SimpleNamespace(
        metadata=SimpleNamespace(
            case_id="US_INDEX_IMH1.0",
            source_zmx="US_INDEX.zmx",
            image_height_mm=5.5,
        )
    )
    index_case = SimpleNamespace(
        metadata=SimpleNamespace(case_id="US_INDEX_IMH1.0", source_zmx="US_INDEX.zmx")
    )
    source_index_case = SimpleNamespace(
        metadata=SimpleNamespace(case_id="missing-id", source_zmx="US_SOURCE.zmx")
    )
    fallback_case = SimpleNamespace(
        metadata=SimpleNamespace(case_id="LEGACY_IMH2.6_TTL4.0", source_zmx="legacy.zmx")
    )

    try:
        assert case_library._case_image_height_mm(metadata_case) == pytest.approx(5.5)
        assert case_library._case_image_height_mm(index_case) == pytest.approx(3.75)
        assert case_library._case_image_height_mm(source_index_case) == pytest.approx(4.25)
        assert case_library._case_image_height_mm(fallback_case) == pytest.approx(2.6)
    finally:
        case_library._case_index_image_height_mm_by_id.cache_clear()
