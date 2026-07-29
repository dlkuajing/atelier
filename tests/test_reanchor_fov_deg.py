"""The migration must move only ``fov_deg``, and must be able to say "already done"."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.reanchor_fov_deg import apply_plan, plan_reanchor, render_fov

_ZMX = "\r\n".join(
    [
        "VERS 190513",
        "MODE SEQ",
        "FTYP 0 0 3 3 0 0 0",
        "XFLN 0 0 0",
        "YFLN 0 {half:g} {edge:g}",
        "SURF 0",
        "",
    ]
)


def _corpus(tmp_path: Path, rows: list[tuple[str, float, float]]) -> tuple[Path, Path]:
    """rows = (case_id, stored fov_deg, ZMX half angle)."""
    cases_dir = tmp_path / "cases"
    zmx_dir = tmp_path / "zmx"
    cases_dir.mkdir()
    zmx_dir.mkdir()
    index = []
    for case_id, fov, theta in rows:
        zmx_name = f"{case_id}.zmx"
        (zmx_dir / zmx_name).write_bytes(
            _ZMX.format(half=theta / 2.0, edge=theta).encode("latin-1")
        )
        index.append({"case_id": case_id, "source_zmx": zmx_name, "fov_deg": fov})
        (cases_dir / f"{case_id}.json").write_text(
            f'{{\n  "metadata": {{\n    "case_id": "{case_id}",\n    "fov_deg": {fov},\n'
            f'    "nominal_efl_mm": 3.5\n  }}\n}}\n',
            encoding="utf-8",
        )
    (cases_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    return cases_dir, zmx_dir


def test_a_half_angle_row_is_doubled_and_a_full_row_is_left_alone(tmp_path: Path) -> None:
    cases_dir, zmx_dir = _corpus(tmp_path, [("HALF", 40.0, 40.0), ("FULL", 80.0, 40.0)])
    plan = plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir)
    assert set(plan.changed) == {"HALF"}
    apply_plan(plan, cases_dir=cases_dir)
    index = {e["case_id"]: e["fov_deg"] for e in json.loads((cases_dir / "index.json").read_text())}
    assert index == {"HALF": 80.0, "FULL": 80.0}
    per_case = json.loads((cases_dir / "HALF.json").read_text())
    assert per_case["metadata"]["fov_deg"] == pytest.approx(80.0)


def test_the_per_case_file_moves_too_because_that_is_what_routing_reads(
    tmp_path: Path,
) -> None:
    """`load_case_library` reads the per-case JSON, never index.json."""
    cases_dir, zmx_dir = _corpus(tmp_path, [("HALF", 40.0, 40.0)])
    apply_plan(plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir), cases_dir=cases_dir)
    text = (cases_dir / "HALF.json").read_text(encoding="utf-8")
    assert '"fov_deg": 80.0' in text
    assert '"nominal_efl_mm": 3.5' in text


def test_nothing_but_the_fov_line_changes(tmp_path: Path) -> None:
    cases_dir, zmx_dir = _corpus(tmp_path, [("HALF", 40.0, 40.0)])
    before = (cases_dir / "HALF.json").read_text(encoding="utf-8").splitlines()
    apply_plan(plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir), cases_dir=cases_dir)
    after = (cases_dir / "HALF.json").read_text(encoding="utf-8").splitlines()
    differing = [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
    assert len(differing) == 1
    assert "fov_deg" in before[differing[0]]


def test_a_second_run_changes_nothing(tmp_path: Path) -> None:
    """`--check` is only usable as a gate if the migration is idempotent."""
    cases_dir, zmx_dir = _corpus(tmp_path, [("HALF", 40.0, 40.0), ("ODD", 16.8885802, 16.8885802)])
    apply_plan(plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir), cases_dir=cases_dir)
    snapshot = {p.name: p.read_bytes() for p in sorted(cases_dir.iterdir())}
    second = plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir)
    assert second.is_clean
    apply_plan(second, cases_dir=cases_dir)
    assert {p.name: p.read_bytes() for p in sorted(cases_dir.iterdir())} == snapshot


def test_a_case_with_no_angle_is_skipped_not_guessed(tmp_path: Path) -> None:
    cases_dir, zmx_dir = _corpus(tmp_path, [("RIH", 40.0, 40.0)])
    zmx = zmx_dir / "RIH.zmx"
    zmx.write_bytes(zmx.read_bytes().replace(b"FTYP 0 ", b"FTYP 3 "))
    plan = plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir)
    assert plan.targets == {}
    assert "RIH" in plan.skipped
    apply_plan(plan, cases_dir=cases_dir)
    assert json.loads((cases_dir / "index.json").read_text())[0]["fov_deg"] == 40.0


def test_render_keeps_the_field_a_json_float() -> None:
    assert render_fov(80.0) == "80.0"
    assert render_fov(77.4) == "77.4"
    assert json.loads(f'{{"v": {render_fov(140.0)}}}')["v"] == pytest.approx(140.0)


def test_the_shipped_corpus_is_anchored() -> None:
    """This is the gate: a newly generated case in the wrong unit fails here."""
    assert plan_reanchor().is_clean
