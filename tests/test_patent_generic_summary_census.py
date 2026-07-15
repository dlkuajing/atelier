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
AFTER_FIRST_LAYOUT = CENSUS.with_name("generic-summary-after-first-layout.json")
AFTER_SECOND_LAYOUT = CENSUS.with_name("generic-summary-after-second-layout.json")
AFTER_THIRD_LAYOUT = CENSUS.with_name("generic-summary-after-third-layout.json")


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


def test_generic_summary_after_first_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_FIRST_LAYOUT.read_bytes())

    assert census.affected_items == 286
    assert census.affected_roots == 286
    assert census.result_set_sha256 == (
        "f0e4e3c1a0a0600fea49c276ce51cfe7a84558228d55bb0f404509bebe6f4dc8"
    )
    assert len(census.layout_signature_counts) == 171
    assert canonical_json_bytes(census) == AFTER_FIRST_LAYOUT.read_bytes()


def test_generic_summary_after_second_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_SECOND_LAYOUT.read_bytes())

    assert census.affected_items == 283
    assert census.affected_roots == 283
    assert census.result_set_sha256 == (
        "3aab024784036d6f268f741deb0396d68438300226b20e9805f0c20f05d48bd6"
    )
    assert len(census.layout_signature_counts) == 168
    assert canonical_json_bytes(census) == AFTER_SECOND_LAYOUT.read_bytes()


def test_generic_summary_after_third_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_THIRD_LAYOUT.read_bytes())

    assert census.affected_items == 281
    assert census.affected_roots == 281
    assert census.result_set_sha256 == (
        "099a5180a6237899947be146612b2117666b55b859dcbcdac116bd6aa03e64ad"
    )
    assert len(census.layout_signature_counts) == 166
    assert canonical_json_bytes(census) == AFTER_THIRD_LAYOUT.read_bytes()
