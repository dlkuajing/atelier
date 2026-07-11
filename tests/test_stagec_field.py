from __future__ import annotations

import hashlib
import itertools
import math
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.core.case_library import build_sample_from_optic, load_case_library
from app.core.engines.stagec_field import (
    FieldTargetStatus,
    StageCFieldEvidence,
    reconstruct_image_fields,
    resolve_field_target,
)


def test_resolver_requires_positive_finite_efl() -> None:
    for efl in (None, 0.0, -1.0, math.nan, math.inf):
        result = resolve_field_target(efl_mm=efl, image_height_mm=2.0, full_fov_deg=None)
        assert result.status is FieldTargetStatus.UNAVAILABLE


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


def _zmx(num_fields: int, *, nonzero_vig: bool = False, x_edge: float = 0.0) -> bytes:
    fractions = [i / (num_fields - 1) for i in range(num_fields)]
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
        source_zmx=source, output_zmx=output, target_image_height_mm=3.2
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


def test_reconstruction_rejects_nonzero_x_field(tmp_path: Path) -> None:
    source = tmp_path / "seed.zmx"
    source.write_bytes(_zmx(3, x_edge=0.2))
    result = reconstruct_image_fields(
        source_zmx=source, output_zmx=tmp_path / "out.zmx", target_image_height_mm=3.0
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
        source_zmx=source, output_zmx=output, target_image_height_mm=3.0
    )
    assert result.status == "unverified"
    assert result.vignetting_status == "nonzero-unverified"
    assert not output.exists()


def _evidence_for_flags(flags: tuple[bool, bool, bool, bool]) -> dict[str, object]:
    reconstruction, imh, efl, ray = flags
    return {
        "reconstruction_status": "constructed-verified" if imh else (
            "constructed" if reconstruction else "not-applied"
        ),
        "imh_source": "constructed" if reconstruction else "unavailable",
        "fov_source": "derived" if reconstruction else "unavailable",
        "efl_constraint_status": "held" if efl else "unverified",
        "ray_metrics_status": "valid" if ray else "pending",
        "real_chief_ray_status": "verified" if imh else "pending",
        "rsi_status": "verified" if imh else "pending",
        "target_image_height_mm": 3.0 if reconstruction else None,
        "nominal_image_height_mm": 3.0 if reconstruction else None,
        "derived_full_fov_deg": 70.0 if reconstruction else None,
        "measured_full_fov_deg": None,
        "reconstruction_applied": reconstruction,
        "imh_field_valid": imh,
        "efl_constraint_held": efl,
        "ray_metrics_valid": ray,
        "note": "quantitative evidence only; [EXPERT] review remains blank",
    }


@pytest.mark.parametrize("flags", itertools.product((False, True), repeat=4))
def test_four_condition_schema_accepts_all_16_internally_consistent_combinations(
    flags: tuple[bool, bool, bool, bool],
) -> None:
    if flags[1] and not flags[0]:
        # IMH validity entails a reconstruction. This is a typed contradiction,
        # not one of the realizable four-condition states.
        with pytest.raises(ValidationError):
            StageCFieldEvidence.model_validate(_evidence_for_flags(flags))
    else:
        evidence = StageCFieldEvidence.model_validate(_evidence_for_flags(flags))
        assert evidence.image_height_achieved is all(flags)


def test_typed_evidence_rejects_spoofed_positive_flags() -> None:
    raw = _evidence_for_flags((True, False, True, True))
    raw["imh_field_valid"] = True
    with pytest.raises(ValidationError):
        StageCFieldEvidence.model_validate(raw)


def test_constructed_without_real_chief_ray_and_rsi_cannot_close() -> None:
    raw = _evidence_for_flags((True, True, True, True))
    raw["real_chief_ray_status"] = "pending"
    raw["rsi_status"] = "pending"
    with pytest.raises(ValidationError):
        StageCFieldEvidence.model_validate(raw)


def test_fov_is_derived_or_measured_never_optimized_or_converged() -> None:
    evidence = StageCFieldEvidence.model_validate(_evidence_for_flags((True, False, True, False)))
    assert evidence.fov_attainment_label == "derived"
    assert "optimized" not in evidence.model_dump_json()
    assert "converged" not in evidence.model_dump_json()


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
    assert sample.metadata.image_height_source == "provided"
    assert sample.metadata.fov_deg == target.full_fov_deg
    assert sample.metadata.fov_source == "derived"
