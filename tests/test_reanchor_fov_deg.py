"""The migration must move ``fov_deg`` and its ``scenario`` label together, and nothing else."""

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


def _corpus(
    tmp_path: Path, rows: list[tuple[str, float, float, float, str]]
) -> tuple[Path, Path]:
    """rows = (case_id, stored fov_deg, ZMX half angle, efl_mm, stored scenario)."""
    cases_dir = tmp_path / "cases"
    zmx_dir = tmp_path / "zmx"
    cases_dir.mkdir()
    zmx_dir.mkdir()
    index = []
    for case_id, fov, theta, efl, scenario in rows:
        zmx_name = f"{case_id}.zmx"
        (zmx_dir / zmx_name).write_bytes(
            _ZMX.format(half=theta / 2.0, edge=theta).encode("latin-1")
        )
        index.append(
            {
                "case_id": case_id,
                "source_zmx": zmx_name,
                "scenario": scenario,
                "efl_mm": efl,
                "fov_deg": fov,
            }
        )
        (cases_dir / f"{case_id}.json").write_text(
            f'{{\n  "metadata": {{\n    "case_id": "{case_id}",\n'
            f'    "scenario": "{scenario}",\n    "fov_deg": {fov},\n'
            f'    "nominal_efl_mm": {efl}\n  }}\n}}\n',
            encoding="utf-8",
        )
    (cases_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    return cases_dir, zmx_dir


#: A 40-degree half angle is an 80-degree full FOV: wide, not ultrawide (>= 85).
_WIDE = ("HALF", 40.0, 40.0, 3.5, "smartphone-wide")
#: Already carries the full FOV and the label the classifier would give it.
_DONE = ("FULL", 80.0, 40.0, 3.5, "smartphone-wide")
#: 46-degree half angle -> 92-degree full FOV, which crosses into ultrawide.
_CROSSES = ("CROSS", 46.0, 46.0, 3.5, "smartphone-wide")


def test_a_half_angle_row_is_doubled_and_a_full_row_is_left_alone(tmp_path: Path) -> None:
    cases_dir, zmx_dir = _corpus(tmp_path, [_WIDE, _DONE])
    plan = plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir)
    assert set(plan.changed) == {"HALF"}
    apply_plan(plan, cases_dir=cases_dir)
    index = {e["case_id"]: e["fov_deg"] for e in json.loads((cases_dir / "index.json").read_text())}
    assert index == {"HALF": 80.0, "FULL": 80.0}


def test_the_scenario_label_moves_with_the_fov_it_is_derived_from(tmp_path: Path) -> None:
    """Moving the FOV alone leaves the corpus disagreeing with its own classifier."""
    cases_dir, zmx_dir = _corpus(tmp_path, [_CROSSES])
    apply_plan(plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir), cases_dir=cases_dir)
    entry = json.loads((cases_dir / "index.json").read_text())[0]
    assert entry["fov_deg"] == pytest.approx(92.0)
    assert entry["scenario"] == "smartphone-ultrawide"
    per_case = json.loads((cases_dir / "CROSS.json").read_text())
    assert per_case["metadata"]["scenario"] == "smartphone-ultrawide"


def test_a_stale_label_alone_is_enough_to_make_a_case_dirty(tmp_path: Path) -> None:
    """The FOV can already be anchored while the label it implies is not."""
    cases_dir, zmx_dir = _corpus(
        tmp_path, [("STALE", 92.0, 46.0, 3.5, "smartphone-wide")]
    )
    plan = plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir)
    assert set(plan.changed) == {"STALE"}
    apply_plan(plan, cases_dir=cases_dir)
    assert plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir).is_clean


def test_the_per_case_file_moves_too_because_that_is_what_routing_reads(
    tmp_path: Path,
) -> None:
    """`load_case_library` reads the per-case JSON, never index.json."""
    cases_dir, zmx_dir = _corpus(tmp_path, [_WIDE])
    apply_plan(plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir), cases_dir=cases_dir)
    text = (cases_dir / "HALF.json").read_text(encoding="utf-8")
    assert '"fov_deg": 80.0' in text
    assert '"nominal_efl_mm": 3.5' in text


def test_nothing_but_the_two_fields_changes(tmp_path: Path) -> None:
    cases_dir, zmx_dir = _corpus(tmp_path, [_CROSSES])
    before = (cases_dir / "CROSS.json").read_text(encoding="utf-8").splitlines()
    apply_plan(plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir), cases_dir=cases_dir)
    after = (cases_dir / "CROSS.json").read_text(encoding="utf-8").splitlines()
    differing = [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
    assert len(differing) == 2
    assert {"fov_deg", "scenario"} == {
        "fov_deg" if "fov_deg" in before[i] else "scenario" for i in differing
    }


def test_a_second_run_changes_nothing(tmp_path: Path) -> None:
    """`--check` is only usable as a gate if the migration is idempotent."""
    cases_dir, zmx_dir = _corpus(
        tmp_path,
        [_WIDE, ("ODD", 16.8885802, 16.8885802, 6.0, "smartphone-telephoto")],
    )
    apply_plan(plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir), cases_dir=cases_dir)
    snapshot = {p.name: p.read_bytes() for p in sorted(cases_dir.iterdir())}
    second = plan_reanchor(cases_dir=cases_dir, zmx_dir=zmx_dir)
    assert second.is_clean
    apply_plan(second, cases_dir=cases_dir)
    assert {p.name: p.read_bytes() for p in sorted(cases_dir.iterdir())} == snapshot


def test_a_case_with_no_angle_is_skipped_not_guessed(tmp_path: Path) -> None:
    cases_dir, zmx_dir = _corpus(tmp_path, [("RIH", 40.0, 40.0, 3.5, "smartphone-wide")])
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


def test_the_shipped_corpus_labels_agree_with_the_classifier() -> None:
    """No case may carry a scenario its own FOV/EFL would not produce."""
    from app.core.lens_system import _classify_scenario

    cases = json.loads(
        (Path(__file__).resolve().parents[1] / "app/data/optical_cases/index.json").read_text(
            encoding="utf-8"
        )
    )
    disagreeing = [
        row["case_id"]
        for row in cases
        if _classify_scenario(float(row["fov_deg"]), float(row["efl_mm"])).value
        != row["scenario"]
    ]
    assert disagreeing == []
