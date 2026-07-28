"""Guards for the pre-push impact slice.

The tool exists because of one concrete, expensive miss (2026-07-28): a
`zmx_writer` change broke `tests/test_patent_to_zmx.py`, which reaches it
through `scripts/patent_to_zmx.py` via an import written *inside a function*.
The tests below pin that exact edge, so the tool cannot silently regress into
missing it again.
"""

from __future__ import annotations

from pathlib import Path

from scripts.impact_slice import (
    ROOT,
    affected_modules,
    build_reverse_graph,
    imported_names,
    module_name_for,
    select_test_files,
)


def test_function_level_imports_are_seen(tmp_path: Path) -> None:
    """Module-level-only parsing is what let the 2026-07-28 miss through."""
    source = tmp_path / "m.py"
    source.write_text(
        "def f():\n    from app.core.engines.zmx_writer import build_zmx_from_codev_readout\n",
        encoding="utf-8",
    )
    names = imported_names(source)
    assert "app.core.engines.zmx_writer" in names


def test_a_syntax_error_does_not_abort_the_scan(tmp_path: Path) -> None:
    broken = tmp_path / "broken.py"
    broken.write_text("def (\n", encoding="utf-8")
    assert imported_names(broken) == set()


def test_module_name_for_maps_repo_paths_and_rejects_outsiders() -> None:
    assert module_name_for(ROOT / "app/core/engines/zmx_writer.py") == "app.core.engines.zmx_writer"
    assert module_name_for(ROOT / "tests/test_impact_slice.py") is None
    assert module_name_for(ROOT / "README.md") is None


def test_patent_to_zmx_is_a_reverse_dependency_of_zmx_writer() -> None:
    """The exact edge that cost ~114 minutes of CI when it was missed."""
    reverse = build_reverse_graph()
    assert "scripts.patent_to_zmx" in reverse["app.core.engines.zmx_writer"]


def test_zmx_writer_change_surfaces_the_patent_test_file() -> None:
    """End-to-end version of the same lesson, at the level the caller uses."""
    modules = affected_modules([ROOT / "app/core/engines/zmx_writer.py"])
    assert "scripts.patent_to_zmx" in modules
    names = {path.name for path in select_test_files(modules)}
    assert "test_patent_to_zmx.py" in names
    assert "test_zmx_writer.py" in names


def test_transitive_importers_are_included_not_just_direct_ones() -> None:
    modules = affected_modules([ROOT / "app/core/engines/zmx_import_prep.py"])
    # zmx_import_prep <- codev_readout <- codev_optimize is a two-hop path.
    assert "app.core.engines.codev_readout" in modules
    assert "app.core.engines.codev_optimize" in modules


def test_a_leaf_script_yields_a_small_slice_not_the_whole_suite() -> None:
    """If every change returned everything the tool would be worthless."""
    modules = affected_modules([ROOT / "scripts/p2_crosssource_trial.py"])
    tests = select_test_files(modules)
    all_tests = list((ROOT / "tests").rglob("test_*.py"))
    assert len(tests) < len(all_tests) / 4
    assert {path.name for path in tests} == {"test_p2_crosssource_trial.py"}


def test_matching_is_by_import_not_substring() -> None:
    """A first cut matched bare module names anywhere in the text and returned
    75 of 106 test files for one change, because hub names like `config` appear
    as ordinary words. Selection must follow imports."""
    tests = select_test_files({"app.core.config"})
    names = {path.name for path in tests}
    # Plenty of test files mention configuration in prose or fixtures; only the
    # ones that actually import the module may be selected.
    assert "test_p2_crosssource_trial.py" not in names


def test_no_changed_source_files_selects_nothing() -> None:
    assert affected_modules([ROOT / "README.md"]) == set()
    assert select_test_files(set()) == []
