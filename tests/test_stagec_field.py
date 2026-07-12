from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.core.case_library import build_sample_from_optic, load_case_library
from app.core.engines.stagec_field import (
    FieldTargetStatus,
    MachineRayClassification,
    ResolvedFieldTarget,
    StageCFieldEvidence,
    StageCMachineFieldEvidence,
    StageCMachineReadback,
    build_stagec_machine_evidence,
    build_stagec_machine_readback,
    reconstruct_image_fields,
    resolve_field_target,
    restore_stagec_machine_evidence,
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


_MACHINE_COLUMNS = (
    "record\tfield_index\tnormalized_fraction\tfield_type\tdefinition_x_ri_mm\t"
    "definition_y_ri_mm\trsi_actual_x_mm\trsi_actual_y_mm\trsi_direction_l\t"
    "rsi_direction_m\trsi_direction_n\trayrsi_return_code\trer\tbls\t"
    "rms_spot_radius_um\trms_wfe_waves\trsi_valid\trsi_attempted\tchief_valid\t"
    "chief_attempted\tspot_valid\tspot_attempted\twfe_valid\twfe_attempted\t"
    "vuy\tvly\tvux\tvlx"
)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _machine_inputs(
    reconstruction,
    *,
    measured_efl_mm: float | None = None,
    field_overrides: dict[int, dict[str, object]] | None = None,
    metrics_meta_overrides: dict[str, str] | None = None,
    listing_lines_override: list[str] | None = None,
) -> dict[str, bytes]:
    source_bytes = Path(reconstruction.source_path).read_bytes()
    reconstructed_bytes = Path(reconstruction.output_path).read_bytes()
    run_id = "stagec-synthetic-run-001"
    config = {
        "field_type": "RIH",
        "field_count": len(reconstruction.normalized_fractions),
        "expected_samples_per_metric": 16,
        "vignetting_mode": "zero-only",
    }
    config_fingerprint = hashlib.sha256(_canonical_json(config)).hexdigest()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    reconstructed_sha = hashlib.sha256(reconstructed_bytes).hexdigest()
    sequence_bytes = (
        "! synthetic Stage C contract fixture; never executable\n"
        f"! run={run_id} source={source_sha} reconstructed={reconstructed_sha} "
        f"config={config_fingerprint}\n"
    ).encode()
    manifest = {
        "schema_id": "atelier-stagec-machine-manifest-v1",
        "run_id": run_id,
        "source_zmx_sha256": source_sha,
        "reconstructed_zmx_sha256": reconstructed_sha,
        "sequence_sha256": hashlib.sha256(sequence_bytes).hexdigest(),
        "config": config,
        "config_fingerprint": config_fingerprint,
    }
    manifest_bytes = _canonical_json(manifest)
    listing_lines = [
        f"ATELIER_STAGEC_RUN_BEGIN\t{run_id}",
        "SCHEMA\tatelier-stagec-listing-v1",
        f"SOURCE_ZMX_SHA256\t{manifest['source_zmx_sha256']}",
        f"RECONSTRUCTED_ZMX_SHA256\t{manifest['reconstructed_zmx_sha256']}",
        f"CONFIG_FINGERPRINT\t{config_fingerprint}",
        "TYP_FLD\tRIH",
    ]
    for index in range(config["field_count"]):
        listing_lines += [f"FIELD_BEGIN\t{index}", f"FIELD_OK\t{index}", f"FIELD_END\t{index}"]
    listing_lines.append(f"ATELIER_STAGEC_RUN_END\t{run_id}")
    if listing_lines_override is not None:
        listing_lines = listing_lines_override
    listing_bytes = ("\n".join(listing_lines) + "\n").encode()
    meta = {
        "schema_id": "atelier-stagec-machine-metrics-v1",
        "run_id": run_id,
        "source_zmx_sha256": manifest["source_zmx_sha256"],
        "reconstructed_zmx_sha256": manifest["reconstructed_zmx_sha256"],
        "config_fingerprint": config_fingerprint,
        "field_type": "RIH",
        "field_count": str(config["field_count"]),
        "expected_samples_per_metric": "16",
        "measured_efl_mm": str(
            reconstruction.target_efl_mm * 1.019
            if measured_efl_mm is None
            else measured_efl_mm
        ),
    }
    meta.update(metrics_meta_overrides or {})
    rows = [f"META\t{key}\t{value}" for key, value in meta.items()]
    rows.append(_MACHINE_COLUMNS)
    for index, fraction in enumerate(reconstruction.normalized_fractions):
        values: dict[str, object] = {
            "field_index": index,
            "normalized_fraction": fraction,
            "field_type": "RIH",
            "definition_x_ri_mm": 0,
            "definition_y_ri_mm": fraction * reconstruction.target_image_height_mm,
            "rsi_actual_x_mm": 0,
            "rsi_actual_y_mm": fraction * reconstruction.target_image_height_mm,
            "rsi_direction_l": 0,
            "rsi_direction_m": 0,
            "rsi_direction_n": 1,
            "rayrsi_return_code": 0,
            "rer": 0,
            "bls": 0,
            "rms_spot_radius_um": 1 + index,
            "rms_wfe_waves": 0.1 + index / 100,
            "rsi_valid": 16,
            "rsi_attempted": 16,
            "chief_valid": 16,
            "chief_attempted": 16,
            "spot_valid": 16,
            "spot_attempted": 16,
            "wfe_valid": 16,
            "wfe_attempted": 16,
            "vuy": 0,
            "vly": 0,
            "vux": 0,
            "vlx": 0,
        }
        values.update((field_overrides or {}).get(index, {}))
        rows.append("FIELD\t" + "\t".join(str(values[column]) for column in _MACHINE_COLUMNS.split("\t")[1:]))
    return {
        "listing_bytes": listing_bytes,
        "metrics_bytes": ("\n".join(rows) + "\n").encode(),
        "source_zmx_bytes": source_bytes,
        "reconstructed_zmx_bytes": reconstructed_bytes,
        "sequence_bytes": sequence_bytes,
        "manifest_bytes": manifest_bytes,
    }


def _machine_readback(reconstruction, **fixture_options: object) -> StageCMachineReadback:
    return build_stagec_machine_readback(**_machine_inputs(reconstruction, **fixture_options))


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
    assert payload["readback"]["field_type"] == "RIH"
    assert payload["readback"]["fields"][2]["spot_samples"] == {
        "valid": 16,
        "attempted": 16,
    }
    assert payload["readback"]["config_fingerprint"] == readback.config_fingerprint
    assert payload["reconstruction_artifact_sha256"] == reconstruction.output_sha256
    assert payload["readback"]["listing_artifact"]["sha256"] == readback.listing_sha256
    assert payload["readback"]["metrics_artifact"]["sha256"] == readback.metrics_artifact_sha256


def test_arbitrary_listing_and_metrics_bytes_are_rejected(tmp_path: Path) -> None:
    reconstruction, readback, _ = _machine_evidence(tmp_path)
    inputs = _machine_inputs(reconstruction)
    for name in ("listing_bytes", "metrics_bytes"):
        forged = {**inputs, name: b"arbitrary but self-hashable bytes"}
        with pytest.raises(ValueError):
            build_stagec_machine_readback(**forged)
    assert readback.field_type == "RIH"


def test_machine_x_readback_requires_proven_zero_even_on_axis(tmp_path: Path) -> None:
    reconstruction, _, _ = _machine_evidence(tmp_path)
    forged = _machine_readback(reconstruction, field_overrides={0: {"definition_x_ri_mm": 0.001}})
    evidence = build_stagec_machine_evidence(
        reconstruction=reconstruction,
        readback=forged,
    )
    assert evidence.imh_field_valid is False
    assert evidence.image_height_achieved is False


def test_nonzero_vignetting_remains_fail_closed(tmp_path: Path) -> None:
    reconstruction, _, _ = _machine_evidence(tmp_path)
    readback = _machine_readback(reconstruction, field_overrides={2: {"vuy": 0.1}})
    contradiction = build_stagec_machine_evidence(reconstruction=reconstruction, readback=readback)
    assert contradiction.ray_metrics_valid is False
    assert contradiction.image_height_achieved is False


def test_all_four_raw_vignetting_columns_are_mapped_and_zero_gate_is_derived(
    tmp_path: Path,
) -> None:
    reconstruction, _, _ = _machine_evidence(tmp_path)
    readback = _machine_readback(
        reconstruction,
        field_overrides={2: {"vuy": 0.1, "vly": 0.2, "vux": 0.3, "vlx": 0.4}},
    )
    edge = readback.fields[2]
    assert (edge.vuy, edge.vly, edge.vux, edge.vlx) == (0.1, 0.2, 0.3, 0.4)
    assert not build_stagec_machine_evidence(
        reconstruction=reconstruction, readback=readback
    ).ray_metrics_valid


def test_machine_evidence_cannot_be_rehydrated_from_claimed_gate_booleans(
    tmp_path: Path,
) -> None:
    _, _, evidence = _machine_evidence(tmp_path)
    forged = evidence.model_dump()
    forged["imh_field_valid"] = False
    with pytest.raises(TypeError, match="must be built"):
        StageCMachineFieldEvidence.model_validate(forged)


@pytest.mark.parametrize(
    ("raw", "classification"),
    [
        ({"rayrsi_return_code": 1}, MachineRayClassification.RAY_TRACE_FAILURE),
        ({"rer": 5}, MachineRayClassification.RAY_TRACE_FAILURE),
        ({"bls": -3}, MachineRayClassification.OBSCURATION),
        ({"bls": 4}, MachineRayClassification.CLEAR_APERTURE_BLOCK),
    ],
)
def test_ray_classification_is_derived_from_raw_outcomes(
    tmp_path: Path, raw: dict[str, object], classification: MachineRayClassification
) -> None:
    reconstruction, _, _ = _machine_evidence(tmp_path)
    readback = _machine_readback(reconstruction, field_overrides={2: raw})
    assert readback.fields[2].ray_classification is classification
    assert not build_stagec_machine_evidence(
        reconstruction=reconstruction, readback=readback
    ).image_height_achieved


def test_rih_definition_and_rsi_actual_cannot_be_transposed(tmp_path: Path) -> None:
    reconstruction, _, _ = _machine_evidence(tmp_path)
    readback = _machine_readback(
        reconstruction,
        field_overrides={2: {"definition_y_ri_mm": 2.9, "rsi_actual_y_mm": 3.0}},
    )
    evidence = build_stagec_machine_evidence(reconstruction=reconstruction, readback=readback)
    assert evidence.imh_field_valid is False


def test_parser_keeps_rih_definition_and_rsi_actual_in_distinct_columns(tmp_path: Path) -> None:
    reconstruction, _, _ = _machine_evidence(tmp_path)
    readback = _machine_readback(
        reconstruction,
        field_overrides={1: {"definition_y_ri_mm": 1.5, "rsi_actual_y_mm": 1.49}},
    )
    assert readback.fields[1].definition_y_ri_mm == 1.5
    assert readback.fields[1].rsi_actual_y_mm == 1.49


@pytest.mark.parametrize("impersonated", ["IMG", "ANG", "rih"])
def test_img_or_ang_cannot_impersonate_rih(tmp_path: Path, impersonated: str) -> None:
    reconstruction, _, _ = _machine_evidence(tmp_path)
    with pytest.raises(ValueError, match="exact RIH"):
        _machine_readback(reconstruction, field_overrides={0: {"field_type": impersonated}})


def test_listing_requires_one_complete_error_free_run_segment(tmp_path: Path) -> None:
    reconstruction, _, _ = _machine_evidence(tmp_path)
    good = _machine_inputs(reconstruction)
    text = good["listing_bytes"].decode().splitlines()
    for bad_lines in (text[:-1], text + text, [*text[:9], "CODEV_ERROR\tbad", *text[9:]]):
        # Rebuilding metrics is intentionally not attempted: listing parser must reject first.
        with pytest.raises(ValueError, match="listing"):
            build_stagec_machine_readback(**{**good, "listing_bytes": ("\n".join(bad_lines) + "\n").encode()})
    foreign = [
        "ATELIER_STAGEC_RUN_BEGIN\tstale-run",
        "ATELIER_STAGEC_RUN_END\tstale-run",
        *text,
    ]
    with pytest.raises(ValueError, match="stale, foreign, or partial"):
        build_stagec_machine_readback(
            **{**good, "listing_bytes": ("\n".join(foreign) + "\n").encode()}
        )


def test_all_six_raw_artifacts_reject_byte_swaps(tmp_path: Path) -> None:
    reconstruction, _, _ = _machine_evidence(tmp_path)
    good = _machine_inputs(reconstruction)
    for key in (
        "listing_bytes",
        "metrics_bytes",
        "source_zmx_bytes",
        "reconstructed_zmx_bytes",
        "sequence_bytes",
        "manifest_bytes",
    ):
        swapped = (
            good[key].replace(b"TYP_FLD\tRIH", b"TYP_FLD\tIMG")
            if key == "listing_bytes"
            else good[key] + b"swap"
        )
        with pytest.raises(ValueError):
            build_stagec_machine_readback(**{**good, key: swapped})


def test_legacy_schema_duplicate_meta_and_duplicate_field_rows_are_rejected(
    tmp_path: Path,
) -> None:
    reconstruction, _, _ = _machine_evidence(tmp_path)
    good = _machine_inputs(reconstruction)
    manifest = json.loads(good["manifest_bytes"])
    manifest["schema_id"] = "atelier-stagec-machine-manifest-v0"
    with pytest.raises(ValidationError):
        build_stagec_machine_readback(**{**good, "manifest_bytes": _canonical_json(manifest)})

    metrics = good["metrics_bytes"].decode().splitlines()
    with pytest.raises(ValueError, match="unique"):
        build_stagec_machine_readback(
            **{**good, "metrics_bytes": ("\n".join([metrics[0], *metrics]) + "\n").encode()}
        )
    with pytest.raises(ValueError, match="row count"):
        build_stagec_machine_readback(
            **{**good, "metrics_bytes": ("\n".join([*metrics, metrics[-1]]) + "\n").encode()}
        )


def test_restore_reparses_artifacts_and_model_copy_facts_have_no_authority(
    tmp_path: Path,
) -> None:
    reconstruction, readback, evidence = _machine_evidence(tmp_path)
    payload = evidence.model_dump(mode="json")
    payload["readback"]["fields"][2]["definition_y_ri_mm"] = 999
    restored = restore_stagec_machine_evidence(payload)
    assert restored.image_height_achieved is True
    assert restored.readback.fields[2].definition_y_ri_mm == 3.0

    forged_field = readback.fields[2].model_copy(update={"definition_y_ri_mm": 999})
    forged = readback.model_copy(update={"fields": (*readback.fields[:2], forged_field)})
    assert build_stagec_machine_evidence(
        reconstruction=reconstruction, readback=forged
    ).image_height_achieved is False


def test_machine_efl_gate_is_strictly_below_existing_two_percent(tmp_path: Path) -> None:
    reconstruction, _, _ = _machine_evidence(tmp_path)
    exact_boundary = _machine_readback(
        reconstruction, measured_efl_mm=reconstruction.target_efl_mm * 1.02
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
    boundary = _machine_readback(reconstruction, measured_efl_mm=5.1)
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
