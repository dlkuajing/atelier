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
AFTER_FOURTH_LAYOUT = CENSUS.with_name("generic-summary-after-fourth-layout.json")
AFTER_FIFTH_LAYOUT = CENSUS.with_name("generic-summary-after-fifth-layout.json")
AFTER_SIXTH_LAYOUT = CENSUS.with_name("generic-summary-after-sixth-layout.json")
AFTER_SEVENTH_LAYOUT = CENSUS.with_name("generic-summary-after-seventh-layout.json")
AFTER_EIGHTH_LAYOUT = CENSUS.with_name("generic-summary-after-eighth-layout.json")
AFTER_NINTH_LAYOUT = CENSUS.with_name("generic-summary-after-ninth-layout.json")
AFTER_TENTH_LAYOUT = CENSUS.with_name("generic-summary-after-tenth-layout.json")
AFTER_ELEVENTH_LAYOUT = CENSUS.with_name("generic-summary-after-eleventh-layout.json")
AFTER_TWELFTH_LAYOUT = CENSUS.with_name("generic-summary-after-twelfth-layout.json")
AFTER_THIRTEENTH_LAYOUT = CENSUS.with_name("generic-summary-after-thirteenth-layout.json")
AFTER_FOURTEENTH_LAYOUT = CENSUS.with_name("generic-summary-after-fourteenth-layout.json")


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


def test_generic_summary_after_fourth_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_FOURTH_LAYOUT.read_bytes())

    assert census.affected_items == 279
    assert census.affected_roots == 279
    assert census.result_set_sha256 == (
        "846ec2bb7bdd342281532daf5b31975838eec4e1908837162c3dd290e12f5e9e"
    )
    assert len(census.layout_signature_counts) == 165
    assert canonical_json_bytes(census) == AFTER_FOURTH_LAYOUT.read_bytes()


def test_generic_summary_after_fifth_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_FIFTH_LAYOUT.read_bytes())

    assert census.affected_items == 278
    assert census.affected_roots == 278
    assert census.result_set_sha256 == (
        "18a0a3102b5b3c8fedfff26b1500db893e931b3bd0068893133ce9071ef4f036"
    )
    assert len(census.layout_signature_counts) == 164
    assert canonical_json_bytes(census) == AFTER_FIFTH_LAYOUT.read_bytes()


def test_generic_summary_after_sixth_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_SIXTH_LAYOUT.read_bytes())

    assert census.affected_items == 277
    assert census.affected_roots == 277
    assert census.result_set_sha256 == (
        "d989da868801c39202dc943d636f5684b8ef7082f3f27f2bc2607cd0097eda47"
    )
    assert len(census.layout_signature_counts) == 163
    assert canonical_json_bytes(census) == AFTER_SIXTH_LAYOUT.read_bytes()


def test_generic_summary_after_seventh_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_SEVENTH_LAYOUT.read_bytes())

    assert census.affected_items == 276
    assert census.affected_roots == 276
    assert census.result_set_sha256 == (
        "53ccc5108b5a6e92656adfea1229a4f9438fdb327fecd712f7afedbb80f929bf"
    )
    assert len(census.layout_signature_counts) == 162
    assert canonical_json_bytes(census) == AFTER_SEVENTH_LAYOUT.read_bytes()


def test_generic_summary_after_eighth_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_EIGHTH_LAYOUT.read_bytes())

    assert census.affected_items == 275
    assert census.affected_roots == 275
    assert census.result_set_sha256 == (
        "07e1ebda99d49d480c96bd5260e894c5e26386d2aef2b6672d4f0303d00cd795"
    )
    assert len(census.layout_signature_counts) == 161
    assert canonical_json_bytes(census) == AFTER_EIGHTH_LAYOUT.read_bytes()


def test_generic_summary_after_ninth_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_NINTH_LAYOUT.read_bytes())

    assert census.affected_items == 272
    assert census.affected_roots == 272
    assert census.result_set_sha256 == (
        "06a3d4b592f5842c54ae702d08cd309c22e0b9a1c8f255e6364ffa6ede89b669"
    )
    assert len(census.layout_signature_counts) == 158
    assert canonical_json_bytes(census) == AFTER_NINTH_LAYOUT.read_bytes()


def test_generic_summary_after_tenth_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_TENTH_LAYOUT.read_bytes())

    assert census.affected_items == 270
    assert census.affected_roots == 270
    assert census.result_set_sha256 == (
        "3907d3680a24f06b388b158ed8fb286e6ba09bb0c4873fa0bc5b76d3fad9a811"
    )
    assert len(census.layout_signature_counts) == 156
    assert canonical_json_bytes(census) == AFTER_TENTH_LAYOUT.read_bytes()


def test_generic_summary_after_eleventh_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_ELEVENTH_LAYOUT.read_bytes())

    assert census.affected_items == 269
    assert census.affected_roots == 269
    assert census.result_set_sha256 == (
        "a53e735db0867e6fe352f71b22f1c58b6ca065029a6cd8f942531572a5fd4c1e"
    )
    assert len(census.layout_signature_counts) == 155
    assert canonical_json_bytes(census) == AFTER_ELEVENTH_LAYOUT.read_bytes()


def test_generic_summary_after_twelfth_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_TWELFTH_LAYOUT.read_bytes())

    assert census.affected_items == 268
    assert census.affected_roots == 268
    assert census.result_set_sha256 == (
        "9149666fd16e422ead35413b1ef271f512f215bba6d025b3d2bda12df77e8182"
    )
    assert len(census.layout_signature_counts) == 154
    assert canonical_json_bytes(census) == AFTER_TWELFTH_LAYOUT.read_bytes()


def test_generic_summary_after_thirteenth_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_THIRTEENTH_LAYOUT.read_bytes())

    assert census.affected_items == 267
    assert census.affected_roots == 267
    assert census.result_set_sha256 == (
        "49332a57b7888eda04118ab704c042a56a27de66cdfc46fd04630a70176d4e49"
    )
    assert len(census.layout_signature_counts) == 153
    assert canonical_json_bytes(census) == AFTER_THIRTEENTH_LAYOUT.read_bytes()


def test_generic_summary_after_fourteenth_layout_is_strict_and_canonical() -> None:
    census = GenericSummaryCensus.model_validate_json(AFTER_FOURTEENTH_LAYOUT.read_bytes())

    assert census.affected_items == 266
    assert census.affected_roots == 266
    assert census.result_set_sha256 == (
        "53652aa9fbad3a49960de0736c8415df00f5df919bb2d8934278dac245c40dc5"
    )
    assert len(census.layout_signature_counts) == 152
    assert canonical_json_bytes(census) == AFTER_FOURTEENTH_LAYOUT.read_bytes()
