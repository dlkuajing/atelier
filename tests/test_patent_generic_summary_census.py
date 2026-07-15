from pathlib import Path

from app.core.patent_replay import canonical_json_bytes
from scripts.patent_generic_summary_census import GenericSummaryCensus, _layout_evidence

ROOT = Path(__file__).resolve().parents[1]
CENSUS = (
    ROOT
    / "data"
    / "patent-ledger"
    / "replay"
    / "local-uncovered"
    / "census"
    / "generic-summary-before.json"
)


def test_generic_summary_before_census_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(CENSUS.read_bytes())

    assert census.affected_items == 294
    assert census.affected_roots == 294
    assert census.result_set_sha256 == (
        "2e0a9ceb2e8b930393168dc7f9cda50c1659aebeacab6afe98f0b96dfea5d506"
    )
    assert len(census.layout_signature_counts) == 179
    assert canonical_json_bytes(census) == CENSUS.read_bytes()


def test_generic_summary_layout_signature_ignores_numeric_values() -> None:
    first = """
    EXAMPLE 1 effective focal length f=3.20 mm; Fno=2.10; HFOV=40.0 deg.
    TABLE-US-00001 TABLE 1 Surface Radius Thickness
    1 2.0 0.2 2 -3.0 0.3
    """
    second = first.replace("3.20", "3.40").replace("2.0 0.2", "4.0 0.4")

    assert _layout_evidence(first)[0] == _layout_evidence(second)[0]
