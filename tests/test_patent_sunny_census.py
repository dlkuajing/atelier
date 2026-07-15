from pathlib import Path

from app.core.patent_replay import canonical_json_bytes
from scripts.patent_sunny_census import SunnyMetadataCensus, _layout_evidence

ROOT = Path(__file__).resolve().parents[1]
CENSUS = (
    ROOT
    / "data"
    / "patent-ledger"
    / "replay"
    / "local-uncovered"
    / "census"
    / "sunny-metadata-before.json"
)


def test_frozen_sunny_metadata_census_is_strict_and_canonical() -> None:
    census = SunnyMetadataCensus.model_validate_json(CENSUS.read_bytes())

    assert census.affected_items == 299
    assert census.affected_roots == 64
    assert census.result_set_sha256 == (
        "3bc0bbee88906ff3b6c40e276addbb6bd3336e0dc73dd987706f5b90393776df"
    )
    assert census.missing_field_counts == {"Fno": 246, "Semi-FOV": 206, "f": 77}
    assert canonical_json_bytes(census) == CENSUS.read_bytes()


def test_sunny_layout_signature_ignores_numeric_values_but_keeps_semantics() -> None:
    first = """
    FOV is a maximum field of view.
    TABLE-US-00001 TABLE 1 Example Condition 1 2 f/EPD 1.2 1.3 FOV(deg) 100 102
    TABLE-US-00002 TABLE 2 OBJ spherical infinite infinite S1 aspheric 2.0 0.2
    S2 aspheric 3.0 0.3 S3 aspheric 4.0 0.4
    """
    second = first.replace("1.2 1.3", "1.4 1.5").replace("100 102", "104 106")

    assert _layout_evidence(first)[0] == _layout_evidence(second)[0]
