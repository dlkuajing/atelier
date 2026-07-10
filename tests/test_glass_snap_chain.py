from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.engines.glass_snap import build_plastic_catalog
from app.core.engines.glass_snap_chain import (
    ElementSnapLedger,
    MaterialIdentity,
    MaterialIntervalClaim,
    SnapshotMetrics,
    SnapVerification,
    SnapVerificationStatus,
    build_glass_freeze_reopt_sequence,
    build_material_region_identities,
    propose_material_snaps,
)


def _claim(start: int, name: str = "___BLANK") -> MaterialIntervalClaim:
    return MaterialIntervalClaim(start, start + 1, 1.0, name, 1.544, 56.0, "ASP")


def _proposals(tolerance: float = 1.0):
    claims = (
        MaterialIntervalClaim(1, 2, 1.0, "___BLANK", 1.55, 40.0, "ASP"),
        MaterialIntervalClaim(2, 3, 1.0, "___BLANK", 1.55, 40.0, "ASP"),
    )
    identity = build_material_region_identities(claims)
    return propose_material_snaps(
        identity,
        build_plastic_catalog(),
        spectral_definition="C-d-F/runtime-placeholder",
        catalog_spectral_definition="C-d-F/runtime-placeholder",
        tolerance=tolerance,
    )


def test_identity_builds_adjacent_cemented_regions():
    result = build_material_region_identities((_claim(1), _claim(2)))
    assert result.writable
    assert result.regions[0].cemented_after
    assert result.regions[1].cemented_before


def test_identity_withholds_same_element_two_material_declarations():
    result = build_material_region_identities((_claim(1, "GLASS-A"), _claim(1, "GLASS-B")))
    assert not result.writable
    assert "conflicting material declarations" in result.withheld_reasons[0]


@pytest.mark.parametrize("claim", [
    MaterialIntervalClaim(1, 3, 1.0, "G", 1.5, 50),
    MaterialIntervalClaim(1, 2, 0.0, "G", 1.5, 50),
    MaterialIntervalClaim(1, 2, 1.0, "G", None, 50),
    MaterialIntervalClaim(1, 2, 1.0, "G", 1.5, 50, "NSS"),
])
def test_identity_malformed_claims_withheld(claim):
    assert not build_material_region_identities((claim,)).writable


def test_snap_pipeline_once_per_region_and_full_catalog_identity():
    proposals = _proposals()
    assert len(proposals) == 2
    assert proposals[0].result.entry is not None
    assert proposals[0].result.entry.catalog_id == "atelier-plastics"
    assert proposals[0].spectral_definition == "C-d-F/runtime-placeholder"


def test_snap_pipeline_over_tolerance_keeps_fictitious():
    proposals = _proposals(tolerance=0.0)
    assert {p.disposition for p in proposals} == {"keep-fictitious"}


def test_snap_pipeline_spectral_mismatch_fails_closed():
    identity = build_material_region_identities((_claim(1),))
    with pytest.raises(ValueError, match="spectral definitions must match"):
        propose_material_snaps(
            identity,
            build_plastic_catalog(),
            spectral_definition="A",
            catalog_spectral_definition="B",
        )


def test_builder_has_assign_freeze_short_aut_and_three_snapshots(tmp_path):
    sequence = build_glass_freeze_reopt_sequence(
        source_zmx=tmp_path / "in.zmx",
        result_path=tmp_path / "out.tsv",
        proposals=_proposals(),
        session_run_id="fixture-run-not-codev",
        configuration_fingerprint="fixture-config-not-codev",
        max_cycles=7,
        min_cycles=2,
    )
    assert sequence.count("! SNAPSHOT ") == 3
    assert "before-fictitious" in sequence
    assert "after-snap-frozen" in sequence
    assert "after-snap-reopt" in sequence
    assert "GLC S1 100" in sequence
    aut = sequence.split("AUT", 1)[1]
    assert "GLC S" not in aut
    assert "MXC 7" in sequence and "MNC 2" in sequence
    assert "RMSWE" in sequence
    assert "pending real-machine verification" in sequence


def _snapshot(stage: str, *, fingerprint: str = "same") -> SnapshotMetrics:
    # Structural placeholders only; these are not represented as CODE V measurements.
    return SnapshotMetrics(
        stage=stage,
        session_run_id="fixture-run",
        prescription_hash="fixture-prescription",
        configuration_fingerprint=fingerprint,
        efl_mm=1.0,
        rms_spot_um=(1.0,),
        rms_wfe_waves=(1.0,),
        lateral_color_um=(1.0,),
        axial_color_mm=(1.0,),
    )


def _ledger(match: bool = True) -> ElementSnapLedger:
    identity = ("cat", "glass", "v1")
    return ElementSnapLedger(
        region_id="z1:s1-s2",
        planned_catalog_identity=identity,
        readback_catalog_identity=identity if match else ("cat", "other", "v1"),
        readback_matches=match,
    )


def test_verification_complete_derives_catalog_snapped():
    verification = SnapVerification(
        source_was_fictitious=True,
        aut_completed=True,
        ledger=(_ledger(),),
        snapshots=tuple(_snapshot(x) for x in ("before-fictitious", "after-snap-frozen", "after-snap-reopt")),
    )
    assert verification.snap_verification_status is SnapVerificationStatus.COMPLETE
    assert verification.material_identity is MaterialIdentity.CATALOG_SNAPPED


def test_missing_snapshot_is_unavailable_and_cannot_be_catalog_snapped():
    verification = SnapVerification(
        source_was_fictitious=True,
        aut_completed=True,
        ledger=(_ledger(),),
        snapshots=(_snapshot("before-fictitious"), _snapshot("after-snap-frozen")),
    )
    assert verification.snap_verification_status is SnapVerificationStatus.UNAVAILABLE
    assert verification.material_identity is MaterialIdentity.FICTITIOUS


def test_config_mismatch_and_readback_conflict_are_separate_axes():
    verification = SnapVerification(
        source_was_fictitious=True,
        aut_completed=True,
        ledger=(_ledger(False),),
        snapshots=(
            _snapshot("before-fictitious"),
            _snapshot("after-snap-frozen"),
            _snapshot("after-snap-reopt", fingerprint="different"),
        ),
    )
    assert verification.snap_verification_status is SnapVerificationStatus.INCONSISTENT
    assert verification.material_identity is MaterialIdentity.CATALOG_CONFLICT


def test_verification_closed_model_rejects_unknown_and_nonfinite():
    with pytest.raises(ValidationError):
        SnapVerification(source_was_fictitious=True, aut_completed=True, ledger=(), snapshots=(), forged=True)
    with pytest.raises(ValidationError):
        _snapshot("before-fictitious").model_copy(update={"efl_mm": float("nan")}).model_validate(
            {**_snapshot("before-fictitious").model_dump(), "efl_mm": float("nan")}
        )
