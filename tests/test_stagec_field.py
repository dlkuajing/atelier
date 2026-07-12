from __future__ import annotations

import hashlib
import math
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.core.case_library import build_sample_from_optic, load_case_library
from app.core.engines.stagec_field import (
    FieldTargetStatus,
    MachineMetricCount,
    MachineRayClassification,
    ResolvedFieldTarget,
    StageCFieldEvidence,
    StageCMachineFieldEvidence,
    StageCMachinePerFieldReadback,
    StageCMachineReadback,
    build_stagec_machine_evidence,
    build_stagec_machine_readback,
    reconstruct_image_fields,
    resolve_field_target,
    validate_reconstructed_field_artifact,
)


def test_resolver_requires_positive_finite_efl() -> None:
    unavailable = resolve_field_target(efl_mm=None, image_height_mm=2.0, full_fov_deg=None)
    assert unavailable.status is FieldTargetStatus.UNAVAILABLE
    for efl in (0.0, -1.0, math.nan, math.inf):
        result = resolve_field_target(efl_mm=efl, image_height_mm=2.0, full_fov_deg=None)
        assert result.status is FieldTargetStatus.INVALID


@pytest.mark.parametrize("invalid", [0.0, -1.0, math.nan, math.inf])
def test_explicit_invalid_dimension_is_not_overridden_by_other_valid_dimension(
    invalid: float,
) -> None:
    assert resolve_field_target(
        efl_mm=4.0, image_height_mm=invalid, full_fov_deg=60.0
    ).status is FieldTargetStatus.INVALID
    assert resolve_field_target(
        efl_mm=4.0, image_height_mm=2.0, full_fov_deg=invalid
    ).status is FieldTargetStatus.INVALID


def test_resolved_target_model_rejects_nonfinite_or_status_spoof() -> None:
    with pytest.raises(ValidationError):
        ResolvedFieldTarget(
            status="resolved", efl_mm=4.0, image_height_mm=math.nan,
            full_fov_deg=60.0, image_height_source="provided", fov_source="provided",
            consistency="exact", reason="spoof",
        )
    with pytest.raises(ValidationError):
        ResolvedFieldTarget(
            status="invalid", efl_mm=4.0, image_height_mm=2.0,
            full_fov_deg=60.0, image_height_source="provided", fov_source="provided",
            consistency="exact", reason="spoof",
        )


def test_resolver_derives_fov_from_imh_only() -> None:
    result = resolve_field_target(efl_mm=4.0, image_height_mm=2.0, full_fov_deg=None)
    assert result.status is FieldTargetStatus.RESOLVED
    assert result.image_height_source == "provided"
    assert result.fov_source == "derived"
    assert result.full_fov_deg == pytest.approx(2 * math.degrees(math.atan(0.5)))


def test_resolver_derives_imh_from_fov_only() -> None:
    result = resolve_field_target(efl_mm=4.0, image_height_mm=None, full_fov_deg=60.0)
    assert result.status is FieldTargetStatus.RESOLVED
    assert result.image_height_source == "derived"
    assert result.fov_source == "provided"
    assert result.image_height_mm == pytest.approx(4 * math.tan(math.radians(30)))


def test_resolver_both_values_are_exact_constraint_not_tolerance() -> None:
    imh = 4 * math.tan(math.radians(30))
    exact = resolve_field_target(efl_mm=4.0, image_height_mm=imh, full_fov_deg=60.0)
    assert exact.status is FieldTargetStatus.RESOLVED
    conflict = resolve_field_target(
        efl_mm=4.0, image_height_mm=imh + 1e-8, full_fov_deg=60.0
    )
    assert conflict.status is FieldTargetStatus.CONFLICT
    assert conflict.image_height_mm is None
    assert conflict.full_fov_deg is None
    assert conflict.image_height_delta_mm == pytest.approx(1e-8)
    assert conflict.fov_delta_deg is not None


def _zmx(
    num_fields: int, *, nonzero_vig: bool = False, x_edge: float = 0.0,
    signed_fields: bool = False,
) -> bytes:
    fractions = [i / (num_fields - 1) for i in range(num_fields)]
    if signed_fields:
        fractions = [-1.0 + 2.0 * i / (num_fields - 1) for i in range(num_fields)]
    y = " ".join(str(value * 40) for value in fractions)
    x = " ".join(str(x_edge if i else 0.0) for i in range(num_fields))
    zero = [0.0] * num_fields
    if nonzero_vig:
        zero[-1] = 0.1
    vig = " ".join(str(value) for value in zero)
    lines = [
        f"FTYP 0 0 {num_fields} 0 0 0 0 {num_fields}",
        f"XFLN {x}",
        f"YFLN {y}",
        f"VDXN {vig}",
        f"VDYN {' '.join('0' for _ in range(num_fields))}",
        f"VCXN {' '.join('0' for _ in range(num_fields))}",
        f"VCYN {' '.join('0' for _ in range(num_fields))}",
        "SURF 0",
    ]
    return ("\r\n".join(lines) + "\r\n").encode()


def _resolved_target(*, efl_mm: float = 4.0, image_height_mm: float = 3.0):
    target = resolve_field_target(
        efl_mm=efl_mm, image_height_mm=image_height_mm, full_fov_deg=None
    )
    assert target.status is FieldTargetStatus.RESOLVED
    return target


@pytest.mark.parametrize("num_fields", [2, 3, 12])
def test_reconstruction_preserves_field_count_fractions_source_and_lf(
    tmp_path: Path, num_fields: int
) -> None:
    source = tmp_path / "seed.zmx"
    output = tmp_path / "temporary.zmx"
    source.write_bytes(_zmx(num_fields))
    source_bytes = source.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()

    result = reconstruct_image_fields(
        source_zmx=source, output_zmx=output,
        resolved_target=_resolved_target(image_height_mm=3.2),
    )

    assert result.status == "constructed"
    assert result.num_fields == num_fields
    assert len(result.normalized_fractions) == num_fields
    assert result.normalized_fractions[0] == 0
    assert result.normalized_fractions[-1] == 1
    assert source.read_bytes() == source_bytes
    assert result.source_sha256_before == result.source_sha256_after == source_hash
    payload = output.read_bytes()
    assert b"\r" not in payload
    text = payload.decode()
    assert text.startswith(f"FTYP 3 0 {num_fields}")
    yfln = next(line for line in text.splitlines() if line.startswith("YFLN "))
    assert float(yfln.split()[-1]) == 3.2


def test_reconstruction_preserves_signed_field_fractions(tmp_path: Path) -> None:
    source = tmp_path / "signed.zmx"
    output = tmp_path / "out.zmx"
    source.write_bytes(_zmx(3, signed_fields=True))
    result = reconstruct_image_fields(
        source_zmx=source, output_zmx=output, resolved_target=_resolved_target(),
    )
    assert result.normalized_fractions == (-1.0, 0.0, 1.0)
    yfln = next(
        line for line in output.read_text(encoding="utf-8").splitlines()
        if line.startswith("YFLN ")
    )
    assert tuple(float(value) for value in yfln.split()[1:]) == (-3.0, 0.0, 3.0)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda text: text + "FTYP 3 0 3 0 0 0 0 3\n", "exactly one FTYP"),
        (lambda text: text.replace("FTYP 3 0 3", "FTYP 3.5 0 3"), "FTYP3"),
        (
            lambda text: text.replace("FTYP 3 0 3", "FTYP 3 0 999"),
            "FTYP field-count slots",
        ),
        (lambda text: text.replace("VDYN 0 0 0", "VDYN 0 0 0.1"), "VDYN"),
        (lambda text: text.replace("XFLN 0.0 0.0 0.0", "XFLN 0.0 0.0"), "count"),
        (lambda text: text.replace("YFLN 0 1.5 3", "YFLN 0 1.4 3"), "fractions"),
    ],
)
def test_artifact_validator_rejects_bytes_that_disagree_with_declared_profile(
    tmp_path: Path, mutation, message: str,
) -> None:
    source = tmp_path / "seed.zmx"
    output = tmp_path / "out.zmx"
    source.write_bytes(_zmx(3))
    result = reconstruct_image_fields(
        source_zmx=source, output_zmx=output, resolved_target=_resolved_target(),
    )
    output.write_text(mutation(output.read_text(encoding="ascii")), encoding="ascii", newline="\n")
    with pytest.raises(ValueError, match=message):
        validate_reconstructed_field_artifact(
            output,
            expected_num_fields=result.num_fields,
            expected_fractions=result.normalized_fractions,
            target_image_height_mm=result.target_image_height_mm,
        )


def test_reconstruction_rejects_same_resolved_path_without_touching_source(tmp_path: Path) -> None:
    source = tmp_path / "seed.zmx"
    source.write_bytes(_zmx(3))
    before = source.read_bytes()
    with pytest.raises(ValueError, match="different paths"):
        reconstruct_image_fields(
            source_zmx=source, output_zmx=source, resolved_target=_resolved_target(),
        )
    assert source.read_bytes() == before


def test_atomic_publish_failure_preserves_existing_output_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.engines.stagec_field as stagec

    source = tmp_path / "seed.zmx"
    output = tmp_path / "out.zmx"
    source.write_bytes(_zmx(3))
    output.write_bytes(b"existing-output")
    monkeypatch.setattr(stagec.os, "replace", Mock(side_effect=OSError("publish failed")))
    with pytest.raises(OSError, match="publish failed"):
        reconstruct_image_fields(
            source_zmx=source, output_zmx=output, resolved_target=_resolved_target(),
        )
    assert output.read_bytes() == b"existing-output"
    assert not list(tmp_path.glob(".*.tmp"))


def test_reconstruction_rejects_nonzero_x_field(tmp_path: Path) -> None:
    source = tmp_path / "seed.zmx"
    source.write_bytes(_zmx(3, x_edge=0.2))
    result = reconstruct_image_fields(
        source_zmx=source, output_zmx=tmp_path / "out.zmx",
        resolved_target=_resolved_target(),
    )
    assert result.status == "rejected"
    assert not (tmp_path / "out.zmx").exists()


def test_reconstruction_nonzero_vignetting_is_unverified_and_emits_nothing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "seed.zmx"
    source.write_bytes(_zmx(3, nonzero_vig=True))
    output = tmp_path / "out.zmx"
    result = reconstruct_image_fields(
        source_zmx=source, output_zmx=output, resolved_target=_resolved_target(),
    )
    assert result.status == "unverified"
    assert result.vignetting_status == "nonzero-unverified"
    assert not output.exists()


def _offline_evidence(*, reconstruction: bool = True) -> dict[str, object]:
    return {
        "reconstruction_status": "constructed" if reconstruction else "not-applied",
        "imh_source": "constructed" if reconstruction else "unavailable",
        "fov_source": "derived" if reconstruction else "unavailable",
        "efl_constraint_status": "unverified",
        "ray_metrics_status": "pending",
        "real_chief_ray_status": "pending",
        "rsi_status": "pending",
        "target_image_height_mm": 3.0 if reconstruction else None,
        "target_efl_mm": 4.0 if reconstruction else None,
        "nominal_image_height_mm": 3.0 if reconstruction else None,
        "derived_full_fov_deg": (
            2 * math.degrees(math.atan(3.0 / 4.0)) if reconstruction else None
        ),
        "measured_full_fov_deg": None,
        "reconstruction_applied": reconstruction,
        "imh_field_valid": False,
        "efl_constraint_held": False,
        "ray_metrics_valid": False,
        "note": "quantitative evidence only; [EXPERT] review remains blank",
    }


def test_offline_evidence_is_machine_blocked_and_never_achieved() -> None:
    evidence = StageCFieldEvidence.model_validate(_offline_evidence())
    assert evidence.reconstruction_applied is True
    assert evidence.image_height_achieved is False


def test_typed_evidence_rejects_spoofed_positive_flags() -> None:
    for key, value in (
        ("imh_field_valid", True), ("efl_constraint_held", True),
        ("ray_metrics_valid", True), ("real_chief_ray_status", "verified"),
        ("rsi_status", "verified"), ("reconstruction_status", "constructed-verified"),
    ):
        raw = _offline_evidence()
        raw[key] = value
        with pytest.raises(ValidationError):
            StageCFieldEvidence.model_validate(raw)


def test_fov_is_derived_or_measured_never_optimized_or_converged() -> None:
    evidence = StageCFieldEvidence.model_validate(_offline_evidence())
    assert evidence.fov_attainment_label == "derived"
    assert "optimized" not in evidence.model_dump_json()
    assert "converged" not in evidence.model_dump_json()


def _machine_readback(reconstruction) -> StageCMachineReadback:
    count = MachineMetricCount(valid=16, attempted=16)
    fields = tuple(
        StageCMachinePerFieldReadback(
            field_index=index,
            normalized_fraction=fraction,
            field_readback_x_mm=0.0,
            field_readback_mm=fraction * reconstruction.target_image_height_mm,
            rsi_image_height_mm=fraction * reconstruction.target_image_height_mm,
            chief_ray_image_height_mm=fraction * reconstruction.target_image_height_mm,
            rms_spot_radius_um=1.0 + index,
            rms_wfe_waves=0.1 + index / 100,
            rsi_samples=count,
            chief_ray_samples=count,
            spot_samples=count,
            wfe_samples=count,
            ray_classification=MachineRayClassification.VALID,
        )
        for index, fraction in enumerate(reconstruction.normalized_fractions)
    )
    return build_stagec_machine_readback(
        field_coordinate_classification="image-height",
        measured_efl_mm=reconstruction.target_efl_mm * 1.019,
        expected_samples_per_metric=16,
        fields=fields,
        vignetting_classification="zero-verified",
        vignetting_provenance="machine-readback",
        vignetting_profile=tuple(0.0 for _ in fields),
        listing_bytes=b"structured listing fixture",
        metrics_bytes=b"structured metrics fixture",
        config_snapshot={
            "expected_samples_per_metric": 16,
            "field_count": len(fields),
            "field_coordinate_classification": "image-height",
        },
        reconstructed_zmx_sha256=reconstruction.output_sha256,
    )


def _machine_evidence(tmp_path: Path):
    source = tmp_path / "machine-seed.zmx"
    output = tmp_path / "machine-reconstructed.zmx"
    source.write_bytes(_zmx(3))
    reconstruction = reconstruct_image_fields(
        source_zmx=source,
        output_zmx=output,
        resolved_target=_resolved_target(),
    )
    readback = _machine_readback(reconstruction)
    return reconstruction, readback, build_stagec_machine_evidence(
        reconstruction=reconstruction, readback=readback
    )


def _rebind_readback(readback: StageCMachineReadback, **updates) -> StageCMachineReadback:
    """Adversarial helper: recompute fingerprints after a semantically bad mutation."""

    import app.core.engines.stagec_field as stagec

    mutated = readback.model_copy(update=updates)
    if "config_snapshot" in updates:
        mutated = mutated.model_copy(
            update={"config_fingerprint": stagec._config_fingerprint(mutated.config_snapshot)}
        )
    return mutated.model_copy(
        update={"readback_fingerprint": stagec._readback_fingerprint(mutated)}
    )


def test_machine_evidence_factory_derives_complete_four_condition_gate(tmp_path: Path) -> None:
    reconstruction, readback, evidence = _machine_evidence(tmp_path)

    assert evidence.evidence_kind == "machine"
    assert evidence.reconstruction_applied is True
    assert evidence.imh_field_valid is True
    assert evidence.efl_constraint_held is True
    assert evidence.ray_metrics_valid is True
    assert evidence.image_height_achieved is True
    assert evidence.fov_source == "derived"
    assert evidence.measured_full_fov_deg is None
    assert evidence.target_efl_mm == reconstruction.target_efl_mm
    assert evidence.target_image_height_mm == reconstruction.target_image_height_mm
    payload = evidence.model_dump(mode="json")
    assert payload["readback"]["fields"][2]["spot_samples"] == {
        "valid": 16,
        "attempted": 16,
    }
    assert payload["readback"]["config_fingerprint"] == readback.config_fingerprint
    assert payload["reconstruction_artifact_sha256"] == reconstruction.output_sha256
    assert payload["readback"]["listing_artifact"]["sha256"] == readback.listing_sha256
    assert payload["readback"]["metrics_artifact"]["sha256"] == readback.metrics_artifact_sha256


@pytest.mark.parametrize("artifact_name", ["listing_artifact", "metrics_artifact"])
def test_machine_raw_artifact_sha_is_bound_to_actual_bytes_and_participates_in_gate(
    tmp_path: Path, artifact_name: str,
) -> None:
    reconstruction, readback, _ = _machine_evidence(tmp_path)
    artifact = getattr(readback, artifact_name).model_copy(
        update={"content_base64": "dGFtcGVyZWQ="}
    )
    forged = _rebind_readback(readback, **{artifact_name: artifact})
    evidence = build_stagec_machine_evidence(
        reconstruction=reconstruction,
        readback=forged,
    )
    assert evidence.image_height_achieved is False
    assert evidence.imh_field_valid is False
    assert evidence.efl_constraint_held is False
    assert evidence.ray_metrics_valid is False


def test_config_snapshot_is_canonically_bound_and_semantics_participate_in_gate(
    tmp_path: Path,
) -> None:
    reconstruction, readback, _ = _machine_evidence(tmp_path)
    config = {**readback.config_snapshot, "field_count": 999}
    forged = _rebind_readback(readback, config_snapshot=config)
    evidence = build_stagec_machine_evidence(
        reconstruction=reconstruction,
        readback=forged,
    )
    assert evidence.image_height_achieved is False
    assert evidence.imh_field_valid is False
    assert evidence.ray_metrics_valid is False


def test_self_consistent_one_of_one_counts_cannot_pass(tmp_path: Path) -> None:
    reconstruction, readback, _ = _machine_evidence(tmp_path)
    one = MachineMetricCount(valid=1, attempted=1)
    fields = tuple(
        field.model_copy(
            update={
                "rsi_samples": one,
                "chief_ray_samples": one,
                "spot_samples": one,
                "wfe_samples": one,
            }
        )
        for field in readback.fields
    )
    config = {**readback.config_snapshot, "expected_samples_per_metric": 1}
    forged = _rebind_readback(
        readback,
        fields=fields,
        expected_samples_per_metric=1,
        config_snapshot=config,
    )
    evidence = build_stagec_machine_evidence(
        reconstruction=reconstruction,
        readback=forged,
    )
    assert evidence.image_height_achieved is False
    assert evidence.imh_field_valid is False
    assert evidence.ray_metrics_valid is False


def test_machine_x_readback_requires_proven_zero_even_on_axis(tmp_path: Path) -> None:
    reconstruction, readback, _ = _machine_evidence(tmp_path)
    fields = (
        readback.fields[0].model_copy(update={"field_readback_x_mm": 0.001}),
        *readback.fields[1:],
    )
    forged = _rebind_readback(readback, fields=fields)
    evidence = build_stagec_machine_evidence(
        reconstruction=reconstruction,
        readback=forged,
    )
    assert evidence.imh_field_valid is False
    assert evidence.image_height_achieved is False


def test_vignetting_provenance_binds_source_and_rejects_nonzero_contradiction(
    tmp_path: Path,
) -> None:
    reconstruction, readback, _ = _machine_evidence(tmp_path)
    artifact_readback = build_stagec_machine_readback(
        field_coordinate_classification="image-height",
        measured_efl_mm=reconstruction.target_efl_mm,
        expected_samples_per_metric=16,
        fields=readback.fields,
        vignetting_classification="zero-verified",
        vignetting_provenance="artifact",
        vignetting_profile=(0.0, 0.0, 0.0),
        listing_bytes=b"artifact provenance listing",
        metrics_bytes=b"artifact provenance metrics",
        config_snapshot=readback.config_snapshot,
        reconstructed_zmx_sha256=reconstruction.output_sha256,
    )
    assert build_stagec_machine_evidence(
        reconstruction=reconstruction, readback=artifact_readback
    ).image_height_achieved is True

    wrong_vignetting = artifact_readback.vignetting.model_copy(
        update={"artifact_sha256": artifact_readback.metrics_artifact_sha256}
    )
    wrong_source = _rebind_readback(artifact_readback, vignetting=wrong_vignetting)
    assert build_stagec_machine_evidence(
        reconstruction=reconstruction, readback=wrong_source
    ).ray_metrics_valid is False

    wrong_machine_vignetting = readback.vignetting.model_copy(
        update={"artifact_sha256": reconstruction.output_sha256}
    )
    wrong_machine_source = _rebind_readback(
        readback, vignetting=wrong_machine_vignetting
    )
    assert build_stagec_machine_evidence(
        reconstruction=reconstruction, readback=wrong_machine_source
    ).ray_metrics_valid is False

    nonzero = build_stagec_machine_readback(
        field_coordinate_classification="image-height",
        measured_efl_mm=reconstruction.target_efl_mm,
        expected_samples_per_metric=16,
        fields=readback.fields,
        vignetting_classification="nonzero-verified",
        vignetting_provenance="machine-readback",
        vignetting_profile=(0.0, 0.0, 0.1),
        listing_bytes=b"nonzero contradiction listing",
        metrics_bytes=b"nonzero contradiction metrics",
        config_snapshot=readback.config_snapshot,
        reconstructed_zmx_sha256=reconstruction.output_sha256,
    )
    contradiction = build_stagec_machine_evidence(
        reconstruction=reconstruction, readback=nonzero
    )
    assert contradiction.ray_metrics_valid is False
    assert contradiction.image_height_achieved is False


def test_machine_evidence_cannot_be_rehydrated_from_claimed_gate_booleans(
    tmp_path: Path,
) -> None:
    _, _, evidence = _machine_evidence(tmp_path)
    forged = evidence.model_dump()
    forged["imh_field_valid"] = False
    with pytest.raises(TypeError, match="must be built"):
        StageCMachineFieldEvidence.model_validate(forged)


@pytest.mark.parametrize(
    ("mutation", "failed_gate"),
    [
        (lambda r: r.model_copy(update={"measured_efl_mm": None}), "efl"),
        (lambda r: r.model_copy(update={"measured_efl_mm": math.nan}), "efl"),
        (lambda r: r.model_copy(update={"measured_efl_mm": 0.0}), "efl"),
        (
            lambda r: r.model_copy(update={"field_coordinate_classification": "unknown"}),
            "imh",
        ),
        (
            lambda r: r.model_copy(
                update={"fields": r.fields[:-1]}
            ),
            "profile",
        ),
        (
            lambda r: r.model_copy(
                update={
                    "fields": (
                        *r.fields[:-1],
                        r.fields[-1].model_copy(update={"rms_spot_radius_um": 0.0}),
                    )
                }
            ),
            "rays",
        ),
        (
            lambda r: r.model_copy(
                update={
                    "fields": (
                        *r.fields[:-1],
                        r.fields[-1].model_copy(
                            update={"ray_classification": MachineRayClassification.UNKNOWN}
                        ),
                    )
                }
            ),
            "rays",
        ),
        (
            lambda r: r.model_copy(
                update={
                    "vignetting": r.vignetting.model_copy(
                        update={"classification": "unknown"}
                    )
                }
            ),
            "rays",
        ),
        (
            lambda r: r.model_copy(
                update={
                    "vignetting": r.vignetting.model_copy(
                        update={"profile": (0.0, 0.0, 0.1)}
                    )
                }
            ),
            "rays",
        ),
    ],
)
def test_machine_evidence_missing_sentinel_unknown_and_profile_mismatch_fail_closed(
    tmp_path: Path, mutation, failed_gate: str,
) -> None:
    reconstruction, readback, _ = _machine_evidence(tmp_path)
    evidence = build_stagec_machine_evidence(
        reconstruction=reconstruction,
        readback=mutation(readback),
    )
    assert evidence.image_height_achieved is False
    if failed_gate == "efl":
        assert evidence.efl_constraint_held is False
    elif failed_gate == "imh":
        assert evidence.imh_field_valid is False
    elif failed_gate == "profile":
        assert evidence.imh_field_valid is False
        assert evidence.ray_metrics_valid is False
    else:
        assert evidence.ray_metrics_valid is False


def test_machine_efl_gate_is_strictly_below_existing_two_percent(tmp_path: Path) -> None:
    reconstruction, readback, _ = _machine_evidence(tmp_path)
    exact_boundary = readback.model_copy(
        update={"measured_efl_mm": reconstruction.target_efl_mm * 1.02}
    )
    evidence = build_stagec_machine_evidence(
        reconstruction=reconstruction,
        readback=exact_boundary,
    )
    assert evidence.efl_constraint_held is False
    assert evidence.image_height_achieved is False


def test_machine_efl_decimal_boundary_target_five_measured_five_point_one_fails(
    tmp_path: Path,
) -> None:
    source = tmp_path / "efl-boundary-seed.zmx"
    output = tmp_path / "efl-boundary-reconstructed.zmx"
    source.write_bytes(_zmx(3))
    reconstruction = reconstruct_image_fields(
        source_zmx=source,
        output_zmx=output,
        resolved_target=_resolved_target(efl_mm=5.0),
    )
    readback = _machine_readback(reconstruction)
    boundary = _rebind_readback(readback, measured_efl_mm=5.1)
    evidence = build_stagec_machine_evidence(
        reconstruction=reconstruction,
        readback=boundary,
    )
    assert evidence.efl_constraint_held is False
    assert evidence.image_height_achieved is False


def test_build_sample_uses_one_resolved_field_source_without_reverting_to_angle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.case_library as library

    template = next(case for case in load_case_library() if case.metadata is not None)
    target = resolve_field_target(efl_mm=4.0, image_height_mm=3.0, full_fov_deg=None)
    regularize = Mock(side_effect=AssertionError("Stage C IMG fields reverted to ANGLE"))
    monkeypatch.setattr(library, "regularize_fields_to_angle", regularize)
    monkeypatch.setattr(library, "compute_paraxial_summary", lambda _: template.paraxial.model_copy(deep=True))
    monkeypatch.setattr(library, "extract_surface_descriptors", lambda _: [s.model_copy(deep=True) for s in template.surfaces])
    monkeypatch.setattr(library, "trace_optic", lambda *_, **__: template.trace.model_copy(deep=True))
    monkeypatch.setattr(library, "_fast_layout_svg_from_surfaces", lambda _: template.layout_svg.model_copy(deep=True))
    monkeypatch.setattr(library, "_lightweight_mtf", lambda *_: (template.mtf.model_copy(deep=True), 1.0))
    monkeypatch.setattr(library, "_classify_surfaces", lambda _: (4, 1))
    monkeypatch.setattr(library, "_materials_from_zmx", lambda *_, **__: ["TEST-GLASS"])

    sample = build_sample_from_optic(
        object(),
        source_zmx="temporary-stagec.zmx",
        n_pieces=4,
        nominal_efl_mm=4.0,
        nominal_fov_deg=1.0,
        lightweight_artifacts=True,
        resolved_field_target=target,
    )
    regularize.assert_not_called()
    assert sample.metadata is not None
    assert sample.metadata.image_height_mm == 3.0
    assert sample.metadata.image_height_source == "constructed"
    assert sample.metadata.fov_deg == target.full_fov_deg
    assert sample.metadata.fov_source == "derived"
