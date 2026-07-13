from __future__ import annotations

import base64
import copy
import csv
import io
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.engines import stageb_authority as stageb_authority
from app.core.engines import stagec_attested as attested

_OFFICIAL_MACRO_RAW = b"official zemax macro fixture\n"
_OFFICIAL_CODEV_RAW = b"offline codev executable fixture\n"
_PINNED_EXE_SHA256 = attested._sha(_OFFICIAL_CODEV_RAW)
_PINNED_EXE_SIZE_BYTES = len(_OFFICIAL_CODEV_RAW)
_PINNED_CODEV_VERSION = "11.5-test"
_PRODUCTION_STAGEC_CODEV_VERSION = attested.TRUSTED_CODEV_FILE_VERSION
_PRODUCTION_STAGEB_CODEV_VERSION = stageb_authority.TRUSTED_CODEV_FILE_VERSION


@pytest.fixture(autouse=True)
def _trusted_test_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = tmp_path / "attestation.key"
    key.write_bytes(b"k" * 32)
    executable = tmp_path / "toolchain" / "codev.exe"
    macro = tmp_path / "toolchain" / "macro" / "zemaxos_to_cv.seq"
    macro.parent.mkdir(parents=True)
    executable.write_bytes(_OFFICIAL_CODEV_RAW)
    macro.write_bytes(_OFFICIAL_MACRO_RAW)
    p18_global = tmp_path / "p18-global-window"
    codev_lock = tmp_path / "codev-execution-lock"

    monkeypatch.setattr(stageb_authority, "OFFICIAL_EXECUTABLE", executable)
    monkeypatch.setattr(stageb_authority, "OFFICIAL_MACRO", macro)
    monkeypatch.setattr(stageb_authority, "TRUSTED_CODEV_SHA256", _PINNED_EXE_SHA256)
    monkeypatch.setattr(stageb_authority, "TRUSTED_CODEV_SIZE_BYTES", _PINNED_EXE_SIZE_BYTES)
    monkeypatch.setattr(
        stageb_authority,
        "TRUSTED_MACRO_SHA256",
        attested._sha(_OFFICIAL_MACRO_RAW),
    )
    monkeypatch.setattr(stageb_authority, "TRUSTED_CODEV_FILE_VERSION", _PINNED_CODEV_VERSION)
    monkeypatch.setattr(stageb_authority, "P18_GLOBAL_WINDOW_ROOT", p18_global)
    monkeypatch.setattr(stageb_authority, "CODEV_LOCK_ROOT", codev_lock)

    monkeypatch.setattr(attested, "_TRUSTED_RUN_ROOT", tmp_path)
    monkeypatch.setattr(attested, "_ATTESTATION_KEY_PATH", key)
    monkeypatch.setattr(attested, "_OFFICIAL_ZEMAX_MACRO", macro)
    monkeypatch.setattr(attested, "_TRUSTED_CODEV_EXECUTABLE", executable)
    monkeypatch.setattr(attested, "_TRUSTED_CODEV_SHA256", _PINNED_EXE_SHA256)
    monkeypatch.setattr(attested, "_TRUSTED_CODEV_SIZE_BYTES", _PINNED_EXE_SIZE_BYTES)
    monkeypatch.setattr(
        attested,
        "_read_windows_file_version",
        lambda _path: _PINNED_CODEV_VERSION,
    )
    monkeypatch.setattr(
        attested,
        "_TRUSTED_ZEMAX_MACRO_SHA256",
        attested._sha(_OFFICIAL_MACRO_RAW),
    )
    monkeypatch.setattr(attested, "TRUSTED_CODEV_FILE_VERSION", _PINNED_CODEV_VERSION)


def test_stagec_reuses_full_stageb_codev_file_version_pin() -> None:
    assert _PRODUCTION_STAGEC_CODEV_VERSION == _PRODUCTION_STAGEB_CODEV_VERSION
    assert len(_PRODUCTION_STAGEC_CODEV_VERSION.split(".")) == 4


def test_trusted_codev_identity_binds_exact_file_version_to_selected_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[Path] = []

    def exact_version(path: Path) -> str:
        observed.append(path.resolve())
        return _PINNED_CODEV_VERSION

    monkeypatch.setattr(attested, "_read_windows_file_version", exact_version)
    executable, version = attested._trusted_codev_identity()
    assert executable == attested._TRUSTED_CODEV_EXECUTABLE
    assert version == _PINNED_CODEV_VERSION
    assert observed == [attested._TRUSTED_CODEV_EXECUTABLE.resolve()]

    monkeypatch.setattr(
        attested,
        "_read_windows_file_version",
        lambda _path: "11.5",
    )
    with pytest.raises(ValueError, match="file version"):
        attested._trusted_codev_identity()


def test_pinned_codev_file_version_rejects_post_run_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[Path] = []
    versions = iter((_PINNED_CODEV_VERSION, "11.5-drift"))

    def changing_version(path: Path) -> str:
        observed.append(path.resolve())
        return next(versions)

    monkeypatch.setattr(attested, "_read_windows_file_version", changing_version)
    executable = attested._TRUSTED_CODEV_EXECUTABLE
    assert attested._pinned_codev_file_version(executable) == _PINNED_CODEV_VERSION
    with pytest.raises(ValueError, match="file version"):
        attested._pinned_codev_file_version(executable)
    assert observed == [executable.resolve(), executable.resolve()]


def _descriptor(path: Path | str, raw: bytes) -> dict[str, object]:
    return {
        "path": str(Path(path).resolve()),
        "sha256": attested._sha(raw),
        "size": len(raw),
    }


def _accepted_rung(optimized_zmx_path: str) -> dict[str, object]:
    return {
        "rung_index": 3,
        "target_fnum": 2.4,
        "status": "measured",
        "measured_fnum": 2.4,
        "fnum_target_deviation_pct": 0.0,
        "fno_param_achieved": True,
        "ray_traceable": True,
        "ray_grid": {
            "category": "ok",
            "refl_count": 0,
            "miss_count": 0,
            "ray_aiming_warning": False,
            "aperture_conflict_matched": None,
            "excerpt": None,
            "note": "positive measured listing evidence",
            "normal_completion": True,
            "abnormal_completion_matched": None,
        },
        "efl_target_deviation_pct": 0.0,
        "post_aut.max_rms_spot_diameter_um": 1.0,
        "post_aut.max_rms_wavefront_error_waves": 0.1,
        "err_f_ratio": 0.0,
        "aut_termination": "normal_completion",
        "aut_converged": True,
        "autovig.edge_used": "0.3",
        "autovig.converged": "1",
        "effective_edge_used": 0.3,
        "quality_note": "measured on accepted pupil",
        "optimized_zmx_path": optimized_zmx_path,
        "ray_retry": None,
        "error": None,
    }


def _accepted_ladder(*, source_zmx: str, optimized_zmx_path: str) -> dict[str, object]:
    accepted = _accepted_rung(optimized_zmx_path)
    return {
        "schema": "atelier-p15-fno-ladder-v1",
        "source_zmx": source_zmx,
        "stage": "B",
        "target_efl_mm": 3.6,
        "fnum_target": 2.4,
        "rung_count": 3,
        "fnum_tolerance_pct": stageb_authority.FNUM_TOLERANCE_PCT,
        "vig_ladder": list(stageb_authority.VIG_LADDER),
        "ray_retry_vig_ladder": list(stageb_authority.RAY_RETRY_VIG_LADDER),
        "num_fields": 3,
        "extra_dof": "both",
        "native_fnum_measured": 2.4,
        "rungs": [copy.deepcopy(accepted)],
        "last_measured_rung_index": 3,
        "last_measured_rung": copy.deepcopy(accepted),
        "target_achieved": True,
        "accepted_final": accepted,
        "blocked": False,
    }


def _metrics(
    run_id: str,
    *,
    field_type: str = "RIH",
    override: dict[str, str] | None = None,
) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(attested._METRICS_HEADERS)
    for index, definition_y in ((1, 0.0), (2, 2.9)):
        values = {
            "record": "FIELD",
            "run_id": run_id,
            "field_index": str(index),
            "field_type": field_type,
            "definition_x_ri_mm": "0",
            "definition_y_ri_mm": str(definition_y),
            "rsi_actual_x_mm": "0",
            "rsi_actual_y_mm": str(definition_y),
            "rsi_direction_l": "0",
            "rsi_direction_m": "0",
            "rsi_direction_n": "1",
            "rayrsi_return_code": "0",
            "rer": "0",
            "bls": "0",
            "spotdata_return_code": "0",
            "rms_spot_diameter_um": "10.25",
            "rmswe_return_value": "1",
            "rms_wfe_waves": "0.25",
            "vuy": "0",
            "vly": "0",
            "vux": "0",
            "vlx": "0",
            "measured_efl_mm": "3.6",
        }
        if override and index == 2:
            values.update(override)
        writer.writerow([values[name] for name in attested._METRICS_HEADERS])
    return output.getvalue().encode()


def _plan_cell(
    *,
    case_id: str,
    arm: str,
    reconstruction: dict[str, object],
    include_stageb_hashes: bool = False,
    accepted_zmx_sha256: str | None = None,
    source_zmx_sha256: str | None = None,
    cache_scope: str = "pre-run-bound",
    pre_run_bound: bool = True,
    cache_record_path: str = "D:/stageb/cache-record.json",
    cache_record_sha256: str = "d" * 64,
    raw_ladder_result_path: str | None = "D:/stageb/raw-ladder-result.json",
    raw_ladder_result_sha256: str | None = "e" * 64,
) -> dict[str, object]:
    cell: dict[str, object] = {
        "cell_id": f"{case_id}--{arm}",
        "case_id": case_id,
        "arm": arm,
        "target_efl_mm": 3.6,
        "target_image_height_mm": 2.9,
        "reconstruction": dict(reconstruction),
        "cache_scope": cache_scope,
        "pre_run_bound": pre_run_bound,
        "cache_record_path": str(Path(cache_record_path).resolve()),
        "cache_record_sha256": cache_record_sha256,
        "raw_ladder_result_path": (
            str(Path(raw_ladder_result_path).resolve())
            if raw_ladder_result_path is not None
            else None
        ),
        "raw_ladder_result_sha256": raw_ladder_result_sha256,
    }
    if include_stageb_hashes:
        assert accepted_zmx_sha256 is not None
        assert source_zmx_sha256 is not None
        cell["accepted_zmx_sha256"] = accepted_zmx_sha256
        cell["source_zmx_sha256"] = source_zmx_sha256
    return cell


def _real_matrix_cells(
    reconstruction: dict[str, object],
    *,
    accepted_zmx_sha256: str,
    source_zmx_sha256: str,
    accepted_entries: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        _plan_cell(
            case_id=f"seed-{index:04d}",
            arm=arm,
            reconstruction=reconstruction,
            include_stageb_hashes=True,
            accepted_zmx_sha256=accepted_zmx_sha256,
            source_zmx_sha256=source_zmx_sha256,
            cache_scope=str(accepted_entries[index - 1]["cache_scope"]),
            pre_run_bound=bool(accepted_entries[index - 1]["pre_run_bound"]),
            cache_record_path=str(accepted_entries[index - 1]["cache_record_path"]),
            cache_record_sha256=str(accepted_entries[index - 1]["cache_record_sha256"]),
            raw_ladder_result_path=accepted_entries[index - 1].get("raw_ladder_result_path"),
            raw_ladder_result_sha256=accepted_entries[index - 1].get("raw_ladder_result_sha256"),
        )
        for index in range(1, 9)
        for arm in (
            "native-imh-reconstructed-control",
            "target-low",
            "target-high",
        )
    ]


def _seal(
    run_dir: Path,
    *,
    metrics: bytes | None = None,
    plan_kind: str = "real-matrix",
    repeat_index: int = 1,
    cache_scope: str = "pre-run-bound",
) -> Path:
    run_id = run_dir.name
    case_id = "seed-0001"
    arm = "production-target" if plan_kind == "production" else "native-imh-reconstructed-control"
    run_dir.mkdir()
    accepted_source = (
        b"FTYP 0 0 2 0 0 0 0 2\nXFLN 0 0\nYFLN 0 40\nVDXN 0 0\nVDYN 0 0\nVCXN 0 0\nVCYN 0 0\n"
    )
    source_path = run_dir / "source.zmx"
    reconstructed_path = run_dir / "reconstructed.zmx"
    source_path.write_bytes(accepted_source)
    (run_dir / "official_zemaxos_to_cv.seq").write_bytes(_OFFICIAL_MACRO_RAW)
    resolved_target = attested.resolve_field_target(
        efl_mm=3.6,
        image_height_mm=2.9,
        full_fov_deg=None,
    )
    reconstruction = attested.reconstruct_image_fields(
        source_zmx=source_path,
        output_zmx=reconstructed_path,
        resolved_target=resolved_target,
        allow_nonzero_vignetting_for_machine=True,
    )
    if reconstruction.status != "constructed":
        raise AssertionError("fixture reconstruction must be constructed")
    reconstruction_payload = reconstruction.model_dump(mode="json")
    reconstructed = reconstructed_path.read_bytes()
    accepted_source_sha256 = attested._sha(accepted_source)
    external_root = (run_dir.parent / f"{run_id}-external-stageb").resolve()
    accepted_path = str((external_root / case_id / "candidate.zmx").resolve())
    original_source_path = str((external_root / "source" / "seed-0001.zmx").resolve())
    raw_emitted_path = str((external_root / "raw" / "seed-0001.zmx").resolve())
    retained_cache_record_path = (run_dir / "stageb-cache-record.json").resolve()
    attempt_id = "a" * 32
    cache_record_path = (
        external_root / "stageb-cache" / attempt_id / "intent.json"
        if cache_scope == "pre-run-bound"
        else external_root / "adoptions-v1" / f"{case_id}.json"
    ).resolve()
    ladder_path = (run_dir / "stageb-ladder-result.json").resolve()
    runner_kind = (
        stageb_authority.BATCH_RUNNER_KIND
        if plan_kind == "real-matrix" or cache_scope == "retrospective-current-state-adoption"
        else stageb_authority.PRODUCTION_RUNNER_KIND
    )
    p18_archive_root = (external_root / "p18-archive").resolve()
    lock_authority = {
        "mode": ("pre-run-held" if cache_scope == "pre-run-bound" else "retrospective-observation"),
        "order": (
            ["output", "p18-global", "p18-archive", "codev-per-call"]
            if runner_kind == stageb_authority.BATCH_RUNNER_KIND
            else ["output", "p18-global", "codev-per-call"]
        ),
        "roots": {
            "output": str((external_root / "output-lock").resolve()),
            "p18_global": str(stageb_authority.P18_GLOBAL_WINDOW_ROOT.resolve()),
            "p18_archive": (
                str(p18_archive_root) if runner_kind == stageb_authority.BATCH_RUNNER_KIND else None
            ),
            "codev": str(stageb_authority.CODEV_LOCK_ROOT.resolve()),
        },
    }
    job = {
        "case_id": case_id,
        "rationale": "fixture cache authority",
        "index_record": {
            "case_id": case_id,
            "scenario": "smartphone-wide",
            "source_zmx": "seed-0001.zmx",
            "efl_mm": 3.6,
            "image_height_mm": 2.9,
        },
        "scenario": "smartphone-wide",
        "native_image_height_mm": 2.9,
    }
    runner_files = {
        name: {"sha256": "a" * 64, "size": 1}
        for name in stageb_authority._REQUIRED_RUNNER_SOURCES[runner_kind]
    }
    python_payload = {"version": "fixture"}
    parameters: dict[str, object] = {
        "target_efl_mm": 3.6,
        "fnum_target": 2.4,
        "target_imh_mm": (2.9 if runner_kind == stageb_authority.BATCH_RUNNER_KIND else None),
        "stage": "B",
        "rung_count": 3,
        "fnum_tolerance_pct": stageb_authority.FNUM_TOLERANCE_PCT,
        "vig_ladder": list(stageb_authority.VIG_LADDER),
        "ray_retry_vig_ladder": list(stageb_authority.RAY_RETRY_VIG_LADDER),
        "num_fields": 3,
        "extra_dof": "both",
        "glass_bounds_nd_vd": None,
        "emit_optimized_zmx": True,
        "timeout_seconds": 180.0,
        "platform_name": os.name,
    }
    if cache_scope == "pre-run-bound":
        parameters["work_dir"] = str(
            (
                cache_record_path.parent
                / ("work" if runner_kind == stageb_authority.BATCH_RUNNER_KIND else "runner-work")
            ).resolve()
        )
    identity = {
        "runner_kind": runner_kind,
        "lock_authority": lock_authority,
        "job": job,
        "job_sha256": attested._sha(attested._canonical_json(job)),
        "source": _descriptor(original_source_path, accepted_source),
        "codev": {
            **_descriptor(stageb_authority.OFFICIAL_EXECUTABLE, _OFFICIAL_CODEV_RAW),
            "version": _PINNED_CODEV_VERSION,
        },
        "official_macro": _descriptor(stageb_authority.OFFICIAL_MACRO, _OFFICIAL_MACRO_RAW),
        "runner_sources": {
            "files": runner_files,
            "aggregate_sha256": attested._sha(attested._canonical_json(runner_files)),
        },
        "python_environment": {
            **python_payload,
            "aggregate_sha256": attested._sha(attested._canonical_json(python_payload)),
        },
        "parameters": parameters,
    }
    raw_ladder = _accepted_ladder(source_zmx="seed-0001.zmx", optimized_zmx_path=raw_emitted_path)
    if cache_scope == "pre-run-bound":
        raw_ladder_raw = attested._canonical_json(raw_ladder)
        raw_ladder_path = (cache_record_path.parent / "raw-ladder-result.json").resolve()
        cache_record = {
            "schema_id": attested._CACHE_INTENT_SCHEMA,
            "scope": "pre-run-intent",
            "attempt_id": attempt_id,
            "created_at": "2026-07-12T00:00:00+00:00",
            "identity": identity,
            "lock_owner_ids": {
                "output": "b" * 32,
                "p18_global": "c" * 32,
                "p18_archive": (
                    "d" * 32 if runner_kind == stageb_authority.BATCH_RUNNER_KIND else None
                ),
                "codev": None,
            },
        }
        cache_record_raw = attested._canonical_json(cache_record)
        retained_cache_record_path.write_bytes(cache_record_raw)
        ladder = copy.deepcopy(raw_ladder)
        stageb_authority._rebind_accepted_path(ladder, accepted_path)
        ladder["cache_provenance"] = {
            "scope": "pre-run-bound",
            "pre_run_bound": True,
            "intent_sha256": attested._sha(cache_record_raw),
            "raw_result_sha256": attested._sha(raw_ladder_raw),
            "post_run_identity_sha256": attested._sha(attested._canonical_json(identity)),
            "accepted_artifact": {
                "raw_emitted": _descriptor(raw_emitted_path, accepted_source),
                "published": _descriptor(accepted_path, accepted_source),
            },
        }
        pre_run_bound = True
    elif cache_scope == "retrospective-current-state-adoption":
        pre_run_bound = False
        raw_ladder_raw = stageb_authority.no_pre_run_raw_bytes()
        raw_ladder_path = None
        ladder = copy.deepcopy(raw_ladder)
        assert isinstance(ladder["accepted_final"], dict)
        stageb_authority._rebind_accepted_path(ladder, accepted_path)
        ladder_raw = attested._canonical_json(ladder)
        ladder_path.write_bytes(ladder_raw)
        legacy_manifest_raw = attested._canonical_json(
            {
                "schema_id": "atelier-stagec-stageb-input-manifest-v1",
                "created_at": "2026-07-12T00:00:00+00:00",
                "required_count": 8,
                "accepted_count": 8,
                "complete": True,
                "accepted": [{"case_id": f"seed-{index:04d}"} for index in range(1, 9)],
                "outcomes": [],
                "expert_verdict": None,
                "truth_notice": stageb_authority.LEGACY_STAGEB_TRUTH_NOTICE,
            }
        )
        legacy_manifest_path = str((external_root / "legacy-manifest.json").resolve())
        p18_archive_root.mkdir(parents=True, exist_ok=True)
        p18_lock_path = p18_archive_root / ".p18-runner.lock"
        p18_lock_raw = b"\0"
        p18_lock_path.write_bytes(p18_lock_raw)
        p18_batch_path = p18_archive_root / "night-20260711" / "batch.json"
        p18_batch_path.parent.mkdir()
        p18_batch_raw = attested._canonical_json(
            {
                "batch_id": "night-20260711",
                "created_at": "2026-07-11T00:00:00+00:00",
                "updated_at": "2026-07-12T00:00:00+00:00",
                "target_source": "offline fixture",
                "target_count": 50,
                "status": "completed",
                "engine": "real",
                "notes": [],
            }
        )
        p18_batch_path.write_bytes(p18_batch_raw)
        p18_terminal_authority = {
            "archive_root": str(p18_archive_root),
            "lock_file": {
                "path": str(p18_lock_path.resolve()),
                "protocol": "atelier-batch-runner-os-byte-range-v1",
                "content_observed": False,
            },
            "terminal_batch": _descriptor(p18_batch_path, p18_batch_raw),
            "batch_id": "night-20260711",
            "status": "completed",
            "target_count": 50,
        }
        cache_record = {
            "schema_id": attested._CACHE_ADOPTION_SCHEMA,
            "scope": "retrospective-current-state-adoption",
            "pre_run_bound": False,
            "run_time_identity_verified": False,
            "adopted_at": "2026-07-12T00:00:00+00:00",
            "case_id": case_id,
            "legacy_result": _descriptor(ladder_path, ladder_raw),
            "legacy_manifest": _descriptor(legacy_manifest_path, legacy_manifest_raw),
            "legacy_manifest_base64": base64.b64encode(legacy_manifest_raw).decode("ascii"),
            "current_identity": identity,
            "referenced_artifacts": [_descriptor(accepted_path, accepted_source)],
            "p18_terminal_authority": p18_terminal_authority,
            "claims_match_current": True,
        }
        cache_record_raw = attested._canonical_json(cache_record)
        retained_cache_record_path.write_bytes(cache_record_raw)
    else:
        raise ValueError(f"unsupported cache scope fixture: {cache_scope}")
    ladder_raw = attested._canonical_json(ladder)
    ladder_path.write_bytes(ladder_raw)
    (run_dir / "stageb-raw-ladder-result.json").write_bytes(raw_ladder_raw)
    accepted_final = ladder["accepted_final"]
    assert isinstance(accepted_final, dict)
    manifest_seed_count = 1 if plan_kind == "production" else 8
    accepted_entries = []
    for index in range(1, manifest_seed_count + 1):
        entry_case = f"seed-{index:04d}"
        entry_accepted = accepted_final if index == 1 else {**accepted_final}
        entry_scope = cache_scope if index == 1 else "pre-run-bound"
        entry_pre_run = entry_scope == "pre-run-bound"
        accepted_entries.append(
            {
                "case_id": entry_case,
                "scenario": "smartphone-wide",
                "source_zmx": (
                    original_source_path
                    if index == 1
                    else str((external_root / "source" / f"{entry_case}.zmx").resolve())
                ),
                "source_zmx_sha256": accepted_source_sha256,
                "accepted_zmx": (
                    accepted_path
                    if index == 1
                    else str((external_root / entry_case / "candidate.zmx").resolve())
                ),
                "accepted_zmx_sha256": accepted_source_sha256,
                "target_efl_mm": 3.6,
                "native_image_height_mm": 2.9,
                "fnum_target": 2.4,
                "accepted_final": entry_accepted,
                "ladder_result": (
                    str(ladder_path)
                    if index == 1
                    else str((external_root / entry_case / "ladder-result.json").resolve())
                ),
                "ladder_result_sha256": attested._sha(ladder_raw),
                "raw_ladder_result_path": (
                    str(raw_ladder_path)
                    if index == 1 and raw_ladder_path is not None
                    else (
                        None
                        if entry_scope == "retrospective-current-state-adoption"
                        else str((external_root / entry_case / "raw-ladder-result.json").resolve())
                    )
                ),
                "raw_ladder_result_sha256": (
                    attested._sha(raw_ladder_raw) if entry_pre_run else None
                ),
                "cache_scope": entry_scope,
                "pre_run_bound": entry_pre_run,
                "cache_record_path": (
                    str(cache_record_path)
                    if index == 1
                    else str((external_root / entry_case / "intent.json").resolve())
                ),
                "cache_record_sha256": (
                    attested._sha(cache_record_raw) if index == 1 else f"{index:x}" * 64
                ),
            }
        )
    stageb_manifest = {
        "schema_id": stageb_authority.STAGEB_MANIFEST_SCHEMA,
        "created_at": "2026-07-12T00:00:00+00:00",
        "required_count": manifest_seed_count,
        "accepted_count": manifest_seed_count,
        "complete": True,
        "accepted": accepted_entries,
        "cache_scope_counts": {
            scope: sum(entry["cache_scope"] == scope for entry in accepted_entries)
            for scope in sorted({str(entry["cache_scope"]) for entry in accepted_entries})
        },
        "all_inputs_pre_run_bound": all(bool(entry["pre_run_bound"]) for entry in accepted_entries),
        "expert_verdict": None,
        "truth_notice": stageb_authority.STAGEB_TRUTH_NOTICE,
    }
    if plan_kind == "real-matrix":
        stageb_manifest["outcomes"] = [
            {
                "case_id": entry["case_id"],
                "fnum_target": entry["fnum_target"],
                "accepted": True,
                "reason": None,
                "cache_scope": entry["cache_scope"],
                "cache_record_path": entry["cache_record_path"],
                "cache_record_sha256": entry["cache_record_sha256"],
                "pre_run_bound": entry["pre_run_bound"],
                "result_sha256": entry["ladder_result_sha256"],
            }
            for entry in accepted_entries
        ]
        stageb_manifest["incomplete_attempts"] = []
    manifest_raw = attested._canonical_json(stageb_manifest)
    stageb_manifest_path = (run_dir / "stageb-manifest.json").resolve()
    stageb_manifest_path.write_bytes(manifest_raw)
    reconstructed_sha256 = attested._sha(reconstructed)
    if plan_kind == "real-matrix":
        execution_plan = {
            "schema_id": "atelier-stagec-real-matrix-plan-v1",
            "matrix_id": "matrix-001",
            "created_at": "2026-07-12T00:00:00+00:00",
            "stageb_manifest": str(stageb_manifest_path),
            "stageb_manifest_sha256": attested._sha(manifest_raw),
            "seed_count": 8,
            "cell_count": 24,
            "repeat_count": 2,
            "expected_run_count": 48,
            "stageb_cache_scope_counts": stageb_manifest["cache_scope_counts"],
            "all_inputs_pre_run_bound": stageb_manifest["all_inputs_pre_run_bound"],
            "retrospective_seed_ids": [
                str(entry["case_id"])
                for entry in accepted_entries
                if entry["cache_scope"] == "retrospective-current-state-adoption"
            ],
            "cells": _real_matrix_cells(
                reconstruction_payload,
                accepted_zmx_sha256=accepted_source_sha256,
                source_zmx_sha256=accepted_source_sha256,
                accepted_entries=accepted_entries,
            ),
            "expert_verdict": None,
        }
    elif plan_kind == "production":
        execution_plan = {
            "schema_id": "atelier-stagec-production-execution-plan-v1",
            "matrix_id": "matrix-001",
            "stageb_manifest": str(stageb_manifest_path),
            "stageb_manifest_sha256": attested._sha(manifest_raw),
            "seed_count": 1,
            "cell_count": 1,
            "repeat_count": 1,
            "expected_run_count": 1,
            "stageb_cache_scope_counts": stageb_manifest["cache_scope_counts"],
            "all_inputs_pre_run_bound": stageb_manifest["all_inputs_pre_run_bound"],
            "retrospective_seed_ids": [
                case_id
                for entry in accepted_entries
                if entry["cache_scope"] == "retrospective-current-state-adoption"
            ],
            "cells": [
                _plan_cell(
                    case_id=case_id,
                    arm=arm,
                    reconstruction=reconstruction_payload,
                    cache_scope=cache_scope,
                    pre_run_bound=pre_run_bound,
                    cache_record_path=str(cache_record_path),
                    cache_record_sha256=attested._sha(cache_record_raw),
                    raw_ladder_result_path=accepted_entries[0].get("raw_ladder_result_path"),
                    raw_ladder_result_sha256=accepted_entries[0].get("raw_ladder_result_sha256"),
                )
            ],
            "expert_verdict": None,
        }
    else:
        raise ValueError(f"unsupported fixture plan kind: {plan_kind}")
    execution_plan_raw = attested._canonical_json(execution_plan)
    (run_dir / "execution-plan.json").write_bytes(execution_plan_raw)
    spec = {
        "schema_id": attested.SPEC_SCHEMA,
        "run_id": run_id,
        "field_type": "RIH",
        "field_count": 2,
        "normalized_fractions": [0.0, 1.0],
        "expected_vignetting_profile": [[0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]],
        "target_efl_mm": 3.6,
        "target_image_height_mm": 2.9,
        "stageb_case_id": case_id,
        "stageb_manifest_path": str(stageb_manifest_path),
        "stageb_manifest_sha256": attested._sha(manifest_raw),
        "stageb_ladder_result_sha256": attested._sha(ladder_raw),
        "stageb_cache_scope": cache_scope,
        "stageb_pre_run_bound": pre_run_bound,
        "stageb_cache_record_sha256": attested._sha(cache_record_raw),
        "stageb_raw_ladder_result_sha256": accepted_entries[0].get("raw_ladder_result_sha256"),
        "matrix_id": "matrix-001",
        "cell_id": f"{case_id}--{arm}",
        "arm": arm,
        "repeat_index": repeat_index,
        "official_zemax_macro_sha256": attested._sha(_OFFICIAL_MACRO_RAW),
        "execution_plan_sha256": attested._sha(execution_plan_raw),
        "reconstruction_recipe": "ftyp3-rih-nonzoom-vig-retained-v1",
        "source_zmx_sha256": attested._sha((run_dir / "source.zmx").read_bytes()),
        "reconstructed_zmx_sha256": reconstructed_sha256,
    }
    spec_raw = attested._canonical_json(spec)
    (run_dir / "spec.json").write_bytes(spec_raw)
    sequence = attested.build_attested_sequence(
        reconstructed_zmx=Path("reconstructed.zmx"),
        metrics_path=Path("metrics.tsv"),
        run_id=run_id,
        spec_sha256=attested._sha(spec_raw),
    ).encode("ascii")
    (run_dir / "stagec.seq").write_bytes(sequence)
    command = [str(stageb_authority.OFFICIAL_EXECUTABLE.resolve()), "/B", "stagec.seq"]
    launch = {
        "schema_id": attested.LAUNCH_SCHEMA,
        "run_id": run_id,
        "spec_sha256": attested._sha(spec_raw),
        "sequence_sha256": attested._sha(sequence),
        "codev_executable_sha256": _PINNED_EXE_SHA256,
        "codev_executable_size_bytes": _PINNED_EXE_SIZE_BYTES,
        "codev_version": _PINNED_CODEV_VERSION,
        "official_zemax_macro_sha256": attested._sha(_OFFICIAL_MACRO_RAW),
        "command": command,
    }
    (run_dir / "launch.json").write_bytes(attested._canonical_json(launch))
    (run_dir / "stdout.bin").write_bytes(b"\xffraw stdout")
    (run_dir / "stderr.bin").write_bytes(b"")
    listing = "\n".join(
        (
            f"STAGEC_ATTESTED_BEGIN {run_id} {attested._sha(spec_raw)}",
            f"STAGEC_ATTESTED_END {run_id} {attested._sha(spec_raw)}",
            "",
        )
    ).encode()
    (run_dir / "listing.lis").write_bytes(listing)
    metrics_raw = metrics if metrics is not None else _metrics(run_id)
    (run_dir / "metrics.tsv").write_bytes(metrics_raw)
    parsed = attested._parse_metrics(
        metrics_raw,
        run_id=run_id,
        field_count=2,
        normalized_fractions=(0.0, 1.0),
    )
    normalized = {
        "schema_id": attested.METRICS_SCHEMA,
        "run_id": run_id,
        "measured_efl_mm": parsed.measured_efl_mm,
        "fields": [field.model_dump(mode="json") for field in parsed.fields],
    }
    (run_dir / "normalized-metrics.json").write_bytes(attested._canonical_json(normalized))
    artifacts = {
        name: attested._artifact_digest((run_dir / name).read_bytes())
        for name in attested._ARTIFACT_NAMES
    }
    receipt = attested._attach_local_attestation(
        {
            "schema_id": attested.RECEIPT_SCHEMA,
            "run_id": run_id,
            "created_at": "2026-07-12T00:00:00+00:00",
            "process": {
                "returncode": 0,
                "duration_seconds": 1.0,
                "executable_post_sha256": _PINNED_EXE_SHA256,
                "official_zemax_macro_post_sha256": attested._sha(_OFFICIAL_MACRO_RAW),
                "codev_version": _PINNED_CODEV_VERSION,
                "lock_owner": {
                    "schema_version": 1,
                    "lock_id": "a" * 32,
                    "details": {
                        "purpose": "codev-process",
                        "command": command,
                        "work_dir": str(run_dir.with_name(f"{run_id}.inflight")),
                    },
                },
            },
            "artifacts": artifacts,
            "stageb_cache": {
                "scope": cache_scope,
                "pre_run_bound": pre_run_bound,
                "record_sha256": attested._sha(cache_record_raw),
                "raw_result_sha256": accepted_entries[0].get("raw_ladder_result_sha256"),
            },
            "truth_notice": "machine facts only",
            "attestation_scope": attested._ATTESTATION_SCOPE,
        }
    )
    receipt_path = run_dir / "post-run-receipt.json"
    receipt_path.write_bytes(attested._canonical_json(receipt))
    return receipt_path


def _prepare_attested_runner_inputs(tmp_path: Path) -> tuple[Path, Path]:
    fixture_receipt = _seal(tmp_path / "runner-inputs", plan_kind="production")
    fixture_dir = fixture_receipt.parent
    manifest_path = fixture_dir / "stageb-manifest.json"
    manifest = attested._strict_json(manifest_path.read_bytes(), "runner input manifest")
    accepted = manifest.get("accepted")
    assert isinstance(accepted, list) and len(accepted) == 1
    entry = accepted[0]
    assert isinstance(entry, dict)

    external_bindings = {
        "accepted_zmx": fixture_dir / "source.zmx",
        "cache_record_path": fixture_dir / "stageb-cache-record.json",
        "raw_ladder_result_path": fixture_dir / "stageb-raw-ladder-result.json",
    }
    for key, retained_path in external_bindings.items():
        external_path = entry.get(key)
        assert isinstance(external_path, str)
        resolved = Path(external_path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_bytes(retained_path.read_bytes())
    return manifest_path, fixture_dir / "execution-plan.json"


def _mock_attested_codev_run(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[list[str]],
) -> None:
    def mocked_run(
        command: list[str],
        *,
        work_dir: Path,
        timeout_seconds: float,
    ) -> SimpleNamespace:
        del timeout_seconds
        calls.append(list(command))
        spec_raw = (work_dir / "spec.json").read_bytes()
        spec = attested._strict_json(spec_raw, "mock runner spec")
        run_id = spec.get("run_id")
        assert isinstance(run_id, str)
        (work_dir / "stagec.lis").write_bytes(
            (
                f"STAGEC_ATTESTED_BEGIN {run_id} {attested._sha(spec_raw)}\n"
                f"STAGEC_ATTESTED_END {run_id} {attested._sha(spec_raw)}\n"
            ).encode("ascii")
        )
        (work_dir / "metrics.tsv").write_bytes(_metrics(run_id))
        return SimpleNamespace(
            process=SimpleNamespace(returncode=0),
            stdout_bytes=b"mock stdout",
            stderr_bytes=b"",
            duration_seconds=0.25,
            lock_owner={
                "schema_version": 1,
                "lock_id": "f" * 32,
                "details": {
                    "purpose": "codev-process",
                    "command": list(command),
                    "work_dir": str(work_dir.resolve()),
                },
            },
        )

    monkeypatch.setattr(attested, "run_codev_process_bytes", mocked_run)


def test_runner_observes_exact_file_version_twice_on_the_same_pinned_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, plan = _prepare_attested_runner_inputs(tmp_path)
    observed: list[Path] = []

    def exact_version(path: Path) -> str:
        observed.append(path.resolve())
        return _PINNED_CODEV_VERSION

    monkeypatch.setattr(attested, "_read_windows_file_version", exact_version)
    run_calls: list[list[str]] = []
    _mock_attested_codev_run(monkeypatch, run_calls)

    receipt_path = attested.run_stagec_attested(
        stageb_manifest=manifest,
        execution_plan=plan,
        stageb_case_id="seed-0001",
        matrix_id="matrix-001",
        arm="production-target",
        repeat_index=1,
        target_image_height_mm=2.9,
        run_id="version-exact",
    )

    executable = attested._TRUSTED_CODEV_EXECUTABLE.resolve()
    assert observed == [executable, executable]
    assert run_calls == [[str(executable), "/B", "stagec.seq"]]
    launch = attested._strict_json(
        (receipt_path.parent / "launch.json").read_bytes(), "runner launch"
    )
    receipt = attested._strict_json(receipt_path.read_bytes(), "runner receipt")
    process = receipt.get("process")
    assert isinstance(process, dict)
    assert launch["codev_version"] == _PINNED_CODEV_VERSION
    assert process["codev_version"] == _PINNED_CODEV_VERSION


@pytest.mark.parametrize("invalid_pre_version", [None, "11.5"])
def test_runner_rejects_invalid_pre_version_before_launching_codev(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_pre_version: str | None,
) -> None:
    manifest, plan = _prepare_attested_runner_inputs(tmp_path)
    monkeypatch.setattr(
        attested,
        "_read_windows_file_version",
        lambda _path: invalid_pre_version,
    )
    run_calls: list[list[str]] = []
    _mock_attested_codev_run(monkeypatch, run_calls)

    with pytest.raises(ValueError, match="file version"):
        attested.run_stagec_attested(
            stageb_manifest=manifest,
            execution_plan=plan,
            stageb_case_id="seed-0001",
            matrix_id="matrix-001",
            arm="production-target",
            repeat_index=1,
            target_image_height_mm=2.9,
            run_id="version-pre-invalid",
        )

    assert run_calls == []
    assert not (tmp_path / "version-pre-invalid" / "post-run-receipt.json").exists()
    assert not (tmp_path / "version-pre-invalid.inflight" / "post-run-receipt.json").exists()


def test_runner_rechecks_executable_after_reconstruction_before_any_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, plan = _prepare_attested_runner_inputs(tmp_path)
    original_builder = attested.build_attested_sequence
    executable = attested._TRUSTED_CODEV_EXECUTABLE
    replaced = False

    def replace_after_reconstruction(**kwargs: object) -> str:
        nonlocal replaced
        sequence = original_builder(**kwargs)
        if not replaced:
            executable.write_bytes(b"replacement inserted after reconstruction\n")
            replaced = True
        return sequence

    monkeypatch.setattr(attested, "build_attested_sequence", replace_after_reconstruction)
    run_calls: list[list[str]] = []
    _mock_attested_codev_run(monkeypatch, run_calls)

    with pytest.raises(ValueError, match="executable differs"):
        attested.run_stagec_attested(
            stageb_manifest=manifest,
            execution_plan=plan,
            stageb_case_id="seed-0001",
            matrix_id="matrix-001",
            arm="production-target",
            repeat_index=1,
            target_image_height_mm=2.9,
            run_id="post-reconstruction-exe-replacement",
        )

    assert replaced is True
    assert run_calls == []
    assert not (tmp_path / "post-reconstruction-exe-replacement" / "post-run-receipt.json").exists()
    assert not (
        tmp_path / "post-reconstruction-exe-replacement.inflight" / "post-run-receipt.json"
    ).exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing semantics are production-only")
def test_windows_executable_lease_denies_write_delete_and_replace(tmp_path: Path) -> None:
    executable = attested._TRUSTED_CODEV_EXECUTABLE
    replacement = tmp_path / "replacement-codev.exe"
    replacement.write_bytes(_OFFICIAL_CODEV_RAW)

    with attested._trusted_codev_executable_lease() as lease:
        with pytest.raises(OSError):
            executable.write_bytes(b"mutated while leased\n")
        with pytest.raises(OSError):
            executable.unlink()
        with pytest.raises(OSError):
            os.replace(replacement, executable)
        post = lease.post_snapshot()

    assert post == lease.pre
    assert executable.read_bytes() == _OFFICIAL_CODEV_RAW
    assert replacement.read_bytes() == _OFFICIAL_CODEV_RAW


def test_runner_rejects_post_version_drift_after_one_launch_without_final_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, plan = _prepare_attested_runner_inputs(tmp_path)
    versions = iter((_PINNED_CODEV_VERSION, "11.5-drift"))
    observed: list[Path] = []

    def changing_version(path: Path) -> str:
        observed.append(path.resolve())
        return next(versions)

    monkeypatch.setattr(attested, "_read_windows_file_version", changing_version)
    run_calls: list[list[str]] = []
    _mock_attested_codev_run(monkeypatch, run_calls)

    with pytest.raises(ValueError, match="file version"):
        attested.run_stagec_attested(
            stageb_manifest=manifest,
            execution_plan=plan,
            stageb_case_id="seed-0001",
            matrix_id="matrix-001",
            arm="production-target",
            repeat_index=1,
            target_image_height_mm=2.9,
            run_id="version-post-drift",
        )

    executable = attested._TRUSTED_CODEV_EXECUTABLE.resolve()
    assert observed == [executable, executable]
    assert len(run_calls) == 1
    assert not (tmp_path / "version-post-drift" / "post-run-receipt.json").exists()
    assert not (tmp_path / "version-post-drift.inflight" / "post-run-receipt.json").exists()


def _resign_receipt(receipt_path: Path) -> None:
    receipt = attested._strict_json(receipt_path.read_bytes(), "test receipt")
    payload = {key: value for key, value in receipt.items() if key != "attestation"}
    payload["artifacts"] = {
        name: attested._artifact_digest((receipt_path.parent / name).read_bytes())
        for name in attested._ARTIFACT_NAMES
    }
    spec = attested._strict_json((receipt_path.parent / "spec.json").read_bytes(), "test spec")
    payload["stageb_cache"] = {
        "scope": spec["stageb_cache_scope"],
        "pre_run_bound": spec["stageb_pre_run_bound"],
        "record_sha256": spec["stageb_cache_record_sha256"],
        "raw_result_sha256": spec["stageb_raw_ladder_result_sha256"],
    }
    receipt_path.write_bytes(attested._canonical_json(attested._attach_local_attestation(payload)))


def _rebind_package(receipt_path: Path) -> None:
    """Re-sign a coherent package so semantic validators, not stale hashes, decide."""

    run_dir = receipt_path.parent
    spec = attested._strict_json((run_dir / "spec.json").read_bytes(), "test spec")
    spec["stageb_manifest_sha256"] = attested._sha((run_dir / "stageb-manifest.json").read_bytes())
    spec["stageb_ladder_result_sha256"] = attested._sha(
        (run_dir / "stageb-ladder-result.json").read_bytes()
    )
    spec["stageb_cache_record_sha256"] = attested._sha(
        (run_dir / "stageb-cache-record.json").read_bytes()
    )
    spec["stageb_raw_ladder_result_sha256"] = (
        None
        if spec["stageb_cache_scope"] == "retrospective-current-state-adoption"
        else attested._sha((run_dir / "stageb-raw-ladder-result.json").read_bytes())
    )
    spec["execution_plan_sha256"] = attested._sha((run_dir / "execution-plan.json").read_bytes())
    spec["official_zemax_macro_sha256"] = attested._sha(
        (run_dir / "official_zemaxos_to_cv.seq").read_bytes()
    )
    spec["source_zmx_sha256"] = attested._sha((run_dir / "source.zmx").read_bytes())
    spec["reconstructed_zmx_sha256"] = attested._sha((run_dir / "reconstructed.zmx").read_bytes())
    spec_raw = attested._canonical_json(spec)
    (run_dir / "spec.json").write_bytes(spec_raw)

    sequence = attested.build_attested_sequence(
        reconstructed_zmx=Path("reconstructed.zmx"),
        metrics_path=Path("metrics.tsv"),
        run_id=str(spec["run_id"]),
        spec_sha256=attested._sha(spec_raw),
    ).encode("ascii")
    (run_dir / "stagec.seq").write_bytes(sequence)

    launch = attested._strict_json((run_dir / "launch.json").read_bytes(), "test launch")
    launch["spec_sha256"] = attested._sha(spec_raw)
    launch["sequence_sha256"] = attested._sha(sequence)
    (run_dir / "launch.json").write_bytes(attested._canonical_json(launch))
    listing = "\n".join(
        (
            f"STAGEC_ATTESTED_BEGIN {spec['run_id']} {attested._sha(spec_raw)}",
            f"STAGEC_ATTESTED_END {spec['run_id']} {attested._sha(spec_raw)}",
            "",
        )
    ).encode()
    (run_dir / "listing.lis").write_bytes(listing)
    _resign_receipt(receipt_path)


def _rebind_cache_dag(receipt_path: Path) -> None:
    """Propagate fixture cache bytes/claims so semantic validation sees coherent tamper."""

    run_dir = receipt_path.parent
    manifest_path = run_dir / "stageb-manifest.json"
    manifest = attested._strict_json(manifest_path.read_bytes(), "test Stage B manifest")
    spec = attested._strict_json((run_dir / "spec.json").read_bytes(), "test spec")
    entries = manifest.get("accepted")
    assert isinstance(entries, list)
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("case_id") == spec["stageb_case_id"]
    ]
    assert len(matches) == 1
    entry = matches[0]
    entry["cache_record_sha256"] = attested._sha(
        (run_dir / "stageb-cache-record.json").read_bytes()
    )
    entry["ladder_result_sha256"] = attested._sha(
        (run_dir / "stageb-ladder-result.json").read_bytes()
    )
    if entry.get("cache_scope") == "pre-run-bound":
        entry["raw_ladder_result_sha256"] = attested._sha(
            (run_dir / "stageb-raw-ladder-result.json").read_bytes()
        )
    outcomes = manifest.get("outcomes")
    if isinstance(outcomes, list):
        matching_outcomes = [
            outcome
            for outcome in outcomes
            if isinstance(outcome, dict) and outcome.get("case_id") == entry.get("case_id")
        ]
        assert len(matching_outcomes) == 1
        matching_outcomes[0].update(
            {
                "cache_scope": entry["cache_scope"],
                "pre_run_bound": entry["pre_run_bound"],
                "cache_record_path": entry["cache_record_path"],
                "cache_record_sha256": entry["cache_record_sha256"],
                "result_sha256": entry["ladder_result_sha256"],
            }
        )
    manifest_raw = attested._canonical_json(manifest)
    manifest_path.write_bytes(manifest_raw)

    plan_path = run_dir / "execution-plan.json"
    plan = attested._strict_json(plan_path.read_bytes(), "test execution plan")
    plan["stageb_manifest_sha256"] = attested._sha(manifest_raw)
    cells = plan.get("cells")
    assert isinstance(cells, list)
    for cell in cells:
        if isinstance(cell, dict) and cell.get("case_id") == entry["case_id"]:
            cell["cache_scope"] = entry["cache_scope"]
            cell["pre_run_bound"] = entry["pre_run_bound"]
            cell["cache_record_path"] = entry["cache_record_path"]
            cell["cache_record_sha256"] = entry["cache_record_sha256"]
            cell["raw_ladder_result_path"] = entry.get("raw_ladder_result_path")
            cell["raw_ladder_result_sha256"] = entry.get("raw_ladder_result_sha256")
    accepted_by_case = {str(item["case_id"]): item for item in entries if isinstance(item, dict)}
    plan["stageb_cache_scope_counts"] = {
        scope: sum(item["cache_scope"] == scope for item in accepted_by_case.values())
        for scope in sorted({str(item["cache_scope"]) for item in accepted_by_case.values()})
    }
    plan["all_inputs_pre_run_bound"] = all(
        bool(item["pre_run_bound"]) for item in accepted_by_case.values()
    )
    plan["retrospective_seed_ids"] = sorted(
        case_id
        for case_id, item in accepted_by_case.items()
        if item["cache_scope"] == "retrospective-current-state-adoption"
    )
    plan_path.write_bytes(attested._canonical_json(plan))

    spec["stageb_cache_scope"] = entry["cache_scope"]
    spec["stageb_pre_run_bound"] = entry["pre_run_bound"]
    spec["stageb_cache_record_sha256"] = entry["cache_record_sha256"]
    spec["stageb_raw_ladder_result_sha256"] = entry.get("raw_ladder_result_sha256")
    (run_dir / "spec.json").write_bytes(attested._canonical_json(spec))
    _rebind_package(receipt_path)


def test_restore_derives_attested_facts_from_raw_package(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_001")

    evidence = attested.restore_stagec_attested_evidence(receipt)

    assert evidence.receipt_attested is True
    assert evidence.process_returncode_observed == 0
    assert evidence.process_duration_seconds == 1.0
    assert evidence.matrix_id == "matrix-001"
    assert evidence.seed_id == "seed-0001"
    assert evidence.repeat_index == 1
    assert evidence.stageb_cache_scope == "pre-run-bound"
    assert evidence.stageb_pre_run_bound is True
    assert evidence.stageb_cache_record_sha256 == attested._sha(
        (receipt.parent / "stageb-cache-record.json").read_bytes()
    )
    assert evidence.field_type == "RIH"
    assert evidence.all_rays_valid is True
    assert evidence.all_metrics_valid is True
    assert evidence.zero_vignetting is True
    assert evidence.image_height_achieved is True
    assert evidence.efl_constraint_held is True
    assert evidence.expert_verdict is None
    assert evidence.attempted_sample_count == 2
    assert evidence.valid_ray_sample_count == 2


def test_fsync_package_preserves_file_bytes(tmp_path: Path) -> None:
    package = tmp_path / "fsync-package"
    package.mkdir()
    first = package / "first.bin"
    second = package / "second.bin"
    first.write_bytes(b"first\x00bytes")
    second.write_bytes(b"second\xffbytes")
    before = {path.name: path.read_bytes() for path in package.iterdir()}

    attested._fsync_package(package)

    assert {path.name: path.read_bytes() for path in package.iterdir()} == before


def test_publish_stagec_inflight_recovers_without_rerunning_codev(tmp_path: Path) -> None:
    final = tmp_path / "run_publish_recovery"
    receipt = _seal(final)
    inflight = final.with_name(f"{final.name}.inflight")
    final.replace(inflight)

    published = attested._publish_stagec_inflight(inflight=inflight, final=final)

    assert published == final / receipt.name
    assert final.is_dir()
    assert not inflight.exists()
    evidence = attested.restore_stagec_attested_evidence(published)
    assert evidence.receipt_attested is True


def test_empirical_codev_exit_one_is_retained_and_can_deliver(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_rc1")
    receipt_payload = attested._strict_json(receipt.read_bytes(), "test receipt")
    process = receipt_payload.get("process")
    assert isinstance(process, dict)
    process["returncode"] = 1
    receipt.write_bytes(attested._canonical_json(receipt_payload))
    _resign_receipt(receipt)

    evidence = attested.restore_stagec_attested_evidence(receipt)

    assert evidence.process_returncode_observed == 1
    assert evidence.image_height_achieved is True


def test_empirical_codev_exit_one_does_not_override_missing_artifact(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_rc1_missing")
    receipt_payload = attested._strict_json(receipt.read_bytes(), "test receipt")
    process = receipt_payload.get("process")
    assert isinstance(process, dict)
    process["returncode"] = 1
    receipt.write_bytes(attested._canonical_json(receipt_payload))
    _resign_receipt(receipt)
    (receipt.parent / "metrics.tsv").unlink()

    with pytest.raises(ValueError, match="missing, extra, or non-canonical"):
        attested.restore_stagec_attested_evidence(receipt)


def test_restore_exposes_retrospective_cache_scope_without_upgrading_provenance(
    tmp_path: Path,
) -> None:
    receipt = _seal(
        tmp_path / "run_retro",
        cache_scope="retrospective-current-state-adoption",
    )

    evidence = attested.restore_stagec_attested_evidence(receipt)

    assert evidence.stageb_cache_scope == "retrospective-current-state-adoption"
    assert evidence.stageb_pre_run_bound is False


def test_stageb_fresh_attempt_helper_roundtrips_into_stagec_matrix_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import p16_stagec_real_matrix as matrix
    from scripts import p16_stagec_stageb_inputs as stageb_inputs

    output_dir = tmp_path / "stageb"
    source_root = tmp_path / "sources"
    source_root.mkdir()
    executable = stageb_authority.OFFICIAL_EXECUTABLE
    official_macro = stageb_authority.OFFICIAL_MACRO
    monkeypatch.setattr(stageb_inputs, "ZMX_DIR", source_root)
    monkeypatch.setattr(stageb_inputs, "OFFICIAL_EXECUTABLE", executable)
    monkeypatch.setattr(stageb_inputs, "OFFICIAL_MACRO", official_macro)
    monkeypatch.setattr(
        stageb_inputs,
        "P18_GLOBAL_WINDOW_ROOT",
        stageb_authority.P18_GLOBAL_WINDOW_ROOT,
    )
    monkeypatch.setattr(stageb_inputs, "CODEV_LOCK_ROOT", stageb_authority.CODEV_LOCK_ROOT)
    angular_source = (
        b"FTYP 0 0 2 0 0 0 0 2\nXFLN 0 0\nYFLN 0 40\nVDXN 0 0\nVDYN 0 0\nVCXN 0 0\nVCYN 0 0\n"
    )
    runner_files = {
        name: {"sha256": "a" * 64, "size": 1}
        for name in stageb_authority._REQUIRED_RUNNER_SOURCES[stageb_authority.BATCH_RUNNER_KIND]
    }
    python_payload = {"version": "cross-module-fixture"}

    p18_root = tmp_path / "p18-archive"
    p18_root.mkdir()
    (p18_root / ".p18-runner.lock").write_bytes(b"\0")
    p18_batch = p18_root / "night-20260711" / "batch.json"
    p18_batch.parent.mkdir()
    p18_batch.write_bytes(
        attested._canonical_json(
            {
                "batch_id": "night-20260711",
                "created_at": "2026-07-11T00:00:00+00:00",
                "updated_at": "2026-07-12T00:00:00+00:00",
                "target_source": "cross-module fixture",
                "target_count": 50,
                "status": "completed",
                "engine": "real",
                "notes": [],
            }
        )
    )
    p18_terminal_authority = stageb_inputs._p18_terminal_authority(
        archive_root=p18_root,
        batch_id="night-20260711",
    )
    lock_authority = stageb_inputs._lock_authority(
        output_root=tmp_path / "stageb-output-lock",
        p18_archive_root=p18_root,
        mode="pre-run-held",
    )
    lock_owner_ids = {
        "output": "1" * 32,
        "p18_global": "2" * 32,
        "p18_archive": "3" * 32,
        "codev": None,
    }

    def descriptor(path: Path) -> dict[str, object]:
        raw = path.read_bytes()
        return {"path": str(path.resolve()), "sha256": attested._sha(raw), "size": len(raw)}

    def current_identity(
        *,
        job: stageb_inputs.InputJob,
        meta: dict[str, object],
        executable: Path,
        work_dir: Path | None = None,
        lock_authority: dict[str, object] | None = None,
    ) -> dict[str, object]:
        assert lock_authority is not None
        case_id = job.case_id
        job_payload = {
            "case_id": case_id,
            "rationale": job.rationale,
            "index_record": meta,
            "scenario": meta["scenario"],
            "native_image_height_mm": float(meta["image_height_mm"]),
        }
        return {
            "runner_kind": stageb_authority.BATCH_RUNNER_KIND,
            "lock_authority": dict(lock_authority),
            "job": job_payload,
            "job_sha256": attested._sha(attested._canonical_json(job_payload)),
            "source": descriptor(source_root / str(meta["source_zmx"])),
            "codev": {
                **descriptor(executable),
                "version": _PINNED_CODEV_VERSION,
            },
            "official_macro": descriptor(official_macro),
            "runner_sources": {
                "files": runner_files,
                "aggregate_sha256": attested._sha(attested._canonical_json(runner_files)),
            },
            "python_environment": {
                **python_payload,
                "aggregate_sha256": attested._sha(attested._canonical_json(python_payload)),
            },
            "parameters": stageb_inputs._parameters(job=job, meta=meta, work_dir=work_dir),
        }

    def mocked_ladder(**kwargs: object) -> dict[str, object]:
        work_dir = Path(str(kwargs["work_dir"]))
        emitted = work_dir.parent / "raw-emitted.zmx"
        emitted.write_bytes(Path(str(kwargs["source_zmx"])).read_bytes())
        accepted = {
            "rung_index": 3,
            "target_fnum": kwargs["fnum_target"],
            "status": "measured",
            "measured_fnum": kwargs["fnum_target"],
            "fnum_target_deviation_pct": 0.0,
            "fno_param_achieved": True,
            "ray_traceable": True,
            "ray_grid": {
                "category": "ok",
                "refl_count": 0,
                "miss_count": 0,
                "ray_aiming_warning": False,
                "aperture_conflict_matched": None,
                "excerpt": None,
                "note": "mocked positive measured listing evidence",
                "normal_completion": True,
                "abnormal_completion_matched": None,
            },
            "efl_target_deviation_pct": 0.0,
            "post_aut.max_rms_spot_diameter_um": 10.0,
            "post_aut.max_rms_wavefront_error_waves": 0.1,
            "err_f_ratio": 0.0,
            "aut_termination": "normal_completion",
            "aut_converged": True,
            "autovig.edge_used": "0.0",
            "autovig.converged": "1",
            "effective_edge_used": 0.3,
            "quality_note": "mocked accepted ladder pupil",
            "optimized_zmx_path": str(emitted.resolve()),
            "ray_retry": None,
            "error": None,
        }
        return {
            "schema": "atelier-p15-fno-ladder-v1",
            "source_zmx": Path(str(kwargs["source_zmx"])).name,
            "stage": "B",
            "target_efl_mm": kwargs["target_efl_mm"],
            "fnum_target": kwargs["fnum_target"],
            "rung_count": 3,
            "fnum_tolerance_pct": 8.0,
            "vig_ladder": list(stageb_inputs.VIG_LADDER),
            "ray_retry_vig_ladder": list(stageb_inputs.RAY_RETRY_VIG_LADDER),
            "num_fields": 3,
            "extra_dof": "both",
            "native_fnum_measured": 2.4,
            "rungs": [accepted],
            "last_measured_rung_index": 3,
            "last_measured_rung": accepted,
            "target_achieved": True,
            "accepted_final": accepted,
            "blocked": False,
        }

    monkeypatch.setattr(stageb_inputs, "_current_identity", current_identity)
    monkeypatch.setattr(stageb_inputs, "run_codev_target_fno_ladder", mocked_ladder)
    accepted_entries: list[dict[str, object]] = []
    for index in range(1, 9):
        case_id = f"seed-{index:04d}"
        source_name = f"{case_id}.zmx"
        source_path = source_root / source_name
        source_path.write_bytes(angular_source)
        meta = {
            "case_id": case_id,
            "scenario": "smartphone-wide",
            "source_zmx": source_name,
            "efl_mm": 3.6,
            "image_height_mm": 2.9,
        }
        job = stageb_inputs.InputJob(case_id, 2.4, "cross-module fresh attempt")
        cache = stageb_inputs._run_job(
            job=job,
            meta=meta,
            output_dir=output_dir,
            executable=executable,
            recovery_p18_root=p18_root,
            lock_authority=lock_authority,
            lock_owner_ids=lock_owner_ids,
            p18_terminal_authority=p18_terminal_authority,
        )
        result = cache["result"]
        assert isinstance(result, dict) and isinstance(result["accepted_final"], dict)
        result_path = Path(str(cache["path"])).resolve(strict=True)
        record_path = Path(str(cache["record"])).resolve(strict=True)
        raw_result_path = Path(str(cache["raw"])).resolve(strict=True)
        intent = stageb_inputs._strict_json(record_path)
        assert intent["attempt_id"] == record_path.parent.name
        accepted_path = Path(str(result["accepted_final"]["optimized_zmx_path"])).resolve(
            strict=True
        )
        entry = {
            "case_id": case_id,
            "scenario": "smartphone-wide",
            "source_zmx": str(source_path.resolve()),
            "source_zmx_sha256": attested._sha(source_path.read_bytes()),
            "accepted_zmx": str(accepted_path),
            "accepted_zmx_sha256": attested._sha(accepted_path.read_bytes()),
            "target_efl_mm": 3.6,
            "native_image_height_mm": 2.9,
            "fnum_target": 2.4,
            "accepted_final": result["accepted_final"],
            "ladder_result": str(result_path),
            "ladder_result_sha256": attested._sha(result_path.read_bytes()),
            "raw_ladder_result_path": str(raw_result_path),
            "raw_ladder_result_sha256": attested._sha(raw_result_path.read_bytes()),
            "cache_scope": cache["scope"],
            "cache_record_path": str(record_path),
            "cache_record_sha256": attested._sha(record_path.read_bytes()),
            "pre_run_bound": True,
        }
        accepted_entries.append(entry)

    manifest = {
        "schema_id": stageb_authority.STAGEB_MANIFEST_SCHEMA,
        "created_at": "2026-07-12T00:00:00+00:00",
        "required_count": 8,
        "accepted_count": 8,
        "complete": True,
        "accepted": accepted_entries,
        "outcomes": [
            {
                "case_id": entry["case_id"],
                "fnum_target": entry["fnum_target"],
                "accepted": True,
                "reason": None,
                "cache_scope": entry["cache_scope"],
                "cache_record_path": entry["cache_record_path"],
                "cache_record_sha256": entry["cache_record_sha256"],
                "pre_run_bound": entry["pre_run_bound"],
                "result_sha256": entry["ladder_result_sha256"],
            }
            for entry in accepted_entries
        ],
        "cache_scope_counts": {"pre-run-bound": 8},
        "all_inputs_pre_run_bound": True,
        "incomplete_attempts": [],
        "expert_verdict": None,
        "truth_notice": stageb_authority.STAGEB_TRUTH_NOTICE,
    }
    manifest_path = output_dir / "manifest-v2.json"
    manifest_path.write_bytes(attested._canonical_json(manifest))
    cells = matrix._canonical_cells(
        stageb_manifest=manifest_path,
        reconstruction_root=tmp_path / "reconstruction",
        published_root=tmp_path / "published",
    )

    assert len(cells) == 24
    assert {cell["cache_scope"] for cell in cells} == {"pre-run-bound"}
    assert all(cell["pre_run_bound"] is True for cell in cells)


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("unknown-scope", "batch outcome binding"),
        ("contradictory-bool", "batch outcome binding"),
    ],
)
def test_cache_scope_claims_fail_closed_under_coherent_hash_dag(
    tmp_path: Path, defect: str, message: str
) -> None:
    receipt = _seal(tmp_path / f"run_scope_{defect}")
    manifest_path = receipt.parent / "stageb-manifest.json"
    manifest = attested._strict_json(manifest_path.read_bytes(), "test manifest")
    entries = manifest["accepted"]
    assert isinstance(entries, list) and isinstance(entries[0], dict)
    if defect == "unknown-scope":
        entries[0]["cache_scope"] = "invented-scope"
    else:
        entries[0]["pre_run_bound"] = False
    manifest_path.write_bytes(attested._canonical_json(manifest))
    _rebind_cache_dag(receipt)

    with pytest.raises(ValueError, match=message):
        attested.restore_stagec_attested_evidence(receipt)


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("schema", "pre-run intent"),
        ("case", "identity claims"),
        ("scenario", "identity claims"),
        ("native-image-height", "effective parameters"),
        ("codev-sha", "hard-pinned toolchain"),
        ("p18-global-lock", "closed global window"),
        ("attempt-format", "pre-run intent"),
        ("attempt-path", "pre-run intent"),
    ],
)
def test_coherently_resigned_cache_record_semantic_tamper_is_rejected(
    tmp_path: Path, defect: str, message: str
) -> None:
    receipt = _seal(tmp_path / f"run_record_{defect}")
    record_path = receipt.parent / "stageb-cache-record.json"
    record = attested._strict_json(record_path.read_bytes(), "test cache record")
    if defect == "schema":
        record["schema_id"] = "invented-cache-record-v1"
    elif defect == "case":
        identity = record["identity"]
        assert isinstance(identity, dict) and isinstance(identity["job"], dict)
        identity["job"]["case_id"] = "other-seed"
        identity["job_sha256"] = attested._sha(attested._canonical_json(identity["job"]))
    elif defect in {"scenario", "native-image-height"}:
        identity = record["identity"]
        assert isinstance(identity, dict) and isinstance(identity["job"], dict)
        if defect == "scenario":
            identity["job"]["scenario"] = "smartphone-telephoto"
        else:
            identity["job"]["native_image_height_mm"] = 3.0
        identity["job_sha256"] = attested._sha(attested._canonical_json(identity["job"]))
    elif defect == "codev-sha":
        identity = record["identity"]
        assert isinstance(identity, dict) and isinstance(identity["codev"], dict)
        identity["codev"]["sha256"] = "0" * 64
    elif defect == "p18-global-lock":
        identity = record["identity"]
        assert isinstance(identity, dict)
        lock_authority = identity["lock_authority"]
        assert isinstance(lock_authority, dict)
        roots = lock_authority["roots"]
        assert isinstance(roots, dict)
        roots["p18_global"] = str((tmp_path / "foreign-p18-window").resolve())
    elif defect == "attempt-format":
        record["attempt_id"] = "not-lowercase-hex"
    else:
        record["attempt_id"] = "b" * 32
    record_path.write_bytes(attested._canonical_json(record))
    _rebind_cache_dag(receipt)

    with pytest.raises(ValueError, match=message):
        attested.restore_stagec_attested_evidence(receipt)


def test_coherently_resigned_ladder_provenance_tamper_is_rejected(
    tmp_path: Path,
) -> None:
    receipt = _seal(tmp_path / "run_provenance_tamper")
    ladder_path = receipt.parent / "stageb-ladder-result.json"
    ladder = attested._strict_json(ladder_path.read_bytes(), "test ladder")
    provenance = ladder["cache_provenance"]
    assert isinstance(provenance, dict)
    provenance["intent_sha256"] = "0" * 64
    ladder_path.write_bytes(attested._canonical_json(ladder))
    _rebind_cache_dag(receipt)

    with pytest.raises(ValueError, match="unique raw-derived"):
        attested.restore_stagec_attested_evidence(receipt)


def test_retrospective_embedded_legacy_manifest_descriptor_is_revalidated(
    tmp_path: Path,
) -> None:
    receipt = _seal(
        tmp_path / "run_retro_manifest_tamper",
        cache_scope="retrospective-current-state-adoption",
    )
    record_path = receipt.parent / "stageb-cache-record.json"
    record = attested._strict_json(record_path.read_bytes(), "test adoption")
    embedded = attested._strict_json(
        base64.b64decode(str(record["legacy_manifest_base64"]), validate=True),
        "test embedded legacy manifest",
    )
    embedded["created_at"] = "2026-07-12T00:00:01+00:00"
    changed = attested._canonical_json(embedded)
    record["legacy_manifest_base64"] = base64.b64encode(changed).decode("ascii")
    record_path.write_bytes(attested._canonical_json(record))
    _rebind_cache_dag(receipt)

    with pytest.raises(ValueError, match="legacy manifest digest"):
        attested.restore_stagec_attested_evidence(receipt)


def test_signed_receipt_cache_claim_cannot_override_retained_authority(tmp_path: Path) -> None:
    receipt_path = _seal(tmp_path / "run_signed_scope_tamper")
    receipt = attested._strict_json(receipt_path.read_bytes(), "test receipt")
    payload = {key: value for key, value in receipt.items() if key != "attestation"}
    payload["stageb_cache"] = {
        "scope": "retrospective-current-state-adoption",
        "pre_run_bound": False,
        "record_sha256": payload["stageb_cache"]["record_sha256"],
    }
    receipt_path.write_bytes(attested._canonical_json(attested._attach_local_attestation(payload)))

    with pytest.raises(ValueError, match="retained Stage B authority"):
        attested.restore_stagec_attested_evidence(receipt_path)


def test_missing_retained_cache_record_never_attests(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_missing_cache_record")
    (receipt.parent / "stageb-cache-record.json").unlink()

    with pytest.raises(ValueError, match="missing, extra, or non-canonical"):
        attested.restore_stagec_attested_evidence(receipt)


def test_public_initializer_rejects_unrestored_evidence() -> None:
    with pytest.raises(TypeError, match="post-run receipt"):
        attested.StageCAttestedEvidence(
            run_id="forged",
            matrix_id="matrix-001",
            cell_id="seed-0001--target-low",
            seed_id="seed-0001",
            arm="target-low",
            repeat_index=1,
            receipt_sha256="0" * 64,
            execution_plan_sha256="0" * 64,
            package_path="D:/forged",
            source_zmx_sha256="0" * 64,
            reconstructed_zmx_sha256="0" * 64,
            target_efl_mm=3.6,
            target_image_height_mm=2.9,
            normalized_fractions=(0.0, 1.0),
            expected_vignetting_profile=((0.0, 0.0, 0.0, 0.0),) * 2,
            measured_efl_mm=3.6,
            fields=(),
            process_returncode_observed=0,
            process_duration_seconds=1.0,
        )


def test_model_construct_is_not_an_attestation_boundary() -> None:
    # Pydantic's internal constructor intentionally bypasses validation.  The
    # receipt restore function, not this factory, is the attestation boundary.
    forged = attested.StageCAttestedEvidence.model_construct(
        process_returncode_observed=7,
        process_duration_seconds=-1.0,
    )

    assert forged.process_returncode_observed == 7
    assert forged.process_duration_seconds == -1.0


@pytest.mark.parametrize(
    "name",
    [
        "source.zmx",
        "reconstructed.zmx",
        "execution-plan.json",
        "stageb-cache-record.json",
        "stagec.seq",
        "metrics.tsv",
        "listing.lis",
    ],
)
def test_any_retained_artifact_tamper_breaks_receipt(tmp_path: Path, name: str) -> None:
    receipt = _seal(tmp_path / "run_002")
    path = receipt.parent / name
    path.write_bytes(path.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="digest mismatch"):
        attested.restore_stagec_attested_evidence(receipt)


def test_inflight_and_noncanonical_receipts_never_attest(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_003")
    inflight = receipt.parent.with_name("run_003.inflight")
    receipt.parent.rename(inflight)
    with pytest.raises(ValueError, match="inflight"):
        attested.restore_stagec_attested_evidence(inflight / receipt.name)

    with pytest.raises(ValueError, match="post-run-receipt"):
        attested.restore_stagec_attested_evidence(inflight / "missing.json")


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"field_type": "ANG"}, "exact RIH"),
        ({"rms_wfe_waves": "NaN"}, "finite"),
        ({"rsi_actual_y_mm": "Inf"}, "finite"),
        ({"field_index": "1"}, "unique contiguous"),
    ],
)
def test_semantic_forgery_fails_before_receipt_can_be_sealed(
    tmp_path: Path, override: dict[str, str], message: str
) -> None:
    run_id = "run_004"
    with pytest.raises(ValueError, match=message):
        _seal(tmp_path / run_id, metrics=_metrics(run_id, override=override))


def test_ray_and_vignetting_failures_are_parser_derived_not_caller_supplied(
    tmp_path: Path,
) -> None:
    run_id = "run_005"
    receipt = _seal(
        tmp_path / run_id,
        metrics=_metrics(run_id, override={"rer": "7", "vuy": "0.125"}),
    )

    evidence = attested.restore_stagec_attested_evidence(receipt)

    assert evidence.fields[1].ray_classification == "ray-error"
    assert evidence.all_rays_valid is False
    assert evidence.zero_vignetting is False
    assert evidence.image_height_achieved is False


def test_normalized_sidecar_cannot_override_raw_metrics(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_006")
    sidecar = receipt.parent / "normalized-metrics.json"
    forged = sidecar.read_bytes().replace(b'"zero_vignetting":false', b'"zero_vignetting":true')
    sidecar.write_bytes(forged + b" ")

    with pytest.raises(ValueError, match="digest mismatch"):
        attested.restore_stagec_attested_evidence(receipt)


def test_production_plan_accepts_one_cell_and_repeat_at_least_one(tmp_path: Path) -> None:
    receipt = _seal(
        tmp_path / "run_007",
        plan_kind="production",
        repeat_index=3,
    )

    evidence = attested.restore_stagec_attested_evidence(receipt)

    assert evidence.arm == "production-target"
    assert evidence.repeat_index == 3
    assert evidence.image_height_achieved is True


def test_extra_directory_is_rejected_even_when_receipt_artifacts_are_closed(
    tmp_path: Path,
) -> None:
    receipt = _seal(tmp_path / "run_008")
    (receipt.parent / "unexpected").mkdir()

    with pytest.raises(ValueError, match="missing, extra, or non-canonical"):
        attested.restore_stagec_attested_evidence(receipt)


def test_extra_symlink_is_rejected(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_009")
    link = receipt.parent / "unexpected-link"
    try:
        link.symlink_to(receipt.parent / "source.zmx")
    except (NotImplementedError, OSError):
        pytest.skip("filesystem does not permit symlink creation")

    with pytest.raises(ValueError, match="missing, extra, or non-canonical"):
        attested.restore_stagec_attested_evidence(receipt)


def test_canonical_artifact_name_must_be_a_regular_file(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_010")
    stdout = receipt.parent / "stdout.bin"
    stdout.unlink()
    stdout.mkdir()

    with pytest.raises(ValueError, match="not a regular file"):
        attested.restore_stagec_attested_evidence(receipt)


def test_canonical_artifact_symlink_is_rejected(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_011")
    stdout = receipt.parent / "stdout.bin"
    stdout.unlink()
    try:
        stdout.symlink_to(receipt.parent / "source.zmx")
    except (NotImplementedError, OSError):
        pytest.skip("filesystem does not permit symlink creation")

    with pytest.raises(ValueError, match="link or junction"):
        attested.restore_stagec_attested_evidence(receipt)


def test_package_directory_symlink_is_rejected(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_012")
    linked_run = tmp_path / "run_012_link"
    try:
        linked_run.symlink_to(receipt.parent, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("filesystem does not permit directory symlink creation")

    with pytest.raises(ValueError, match="canonical regular post-run-receipt"):
        attested.restore_stagec_attested_evidence(linked_run / receipt.name)


@pytest.mark.parametrize(
    ("attribute", "mismatch"),
    [
        ("_TRUSTED_CODEV_EXECUTABLE", Path("D:/untrusted/codev.exe")),
        ("_TRUSTED_CODEV_SHA256", "d" * 64),
        ("_TRUSTED_CODEV_SIZE_BYTES", 124),
        ("_TRUSTED_ZEMAX_MACRO_SHA256", "e" * 64),
        ("TRUSTED_CODEV_FILE_VERSION", "12.0"),
    ],
)
def test_restore_requires_every_machine_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attribute: str,
    mismatch: object,
) -> None:
    receipt = _seal(tmp_path / "run_013")
    monkeypatch.setattr(attested, attribute, mismatch)

    with pytest.raises(ValueError, match="shared CODE V lock launch"):
        attested.restore_stagec_attested_evidence(receipt)


@pytest.mark.parametrize("location", ["launch", "process"])
def test_restore_rejects_truncated_retained_codev_version(
    tmp_path: Path,
    location: str,
) -> None:
    receipt = _seal(tmp_path / f"run_truncated_version_{location}")
    if location == "launch":
        launch_path = receipt.parent / "launch.json"
        launch = attested._strict_json(launch_path.read_bytes(), "test launch")
        launch["codev_version"] = "11.5"
        launch_path.write_bytes(attested._canonical_json(launch))
        _rebind_package(receipt)
    else:
        receipt_payload = attested._strict_json(receipt.read_bytes(), "test receipt")
        process = receipt_payload.get("process")
        assert isinstance(process, dict)
        process["codev_version"] = "11.5"
        receipt.write_bytes(attested._canonical_json(receipt_payload))
        _resign_receipt(receipt)

    with pytest.raises(ValueError, match="shared CODE V lock launch"):
        attested.restore_stagec_attested_evidence(receipt)


def test_restore_does_not_probe_live_codev_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _seal(tmp_path / "run_restore_offline_version")
    original_resolve = Path.resolve
    protected_keys = {
        attested._absolute_path_syntax_key(
            str(attested._TRUSTED_CODEV_EXECUTABLE), "test executable"
        ),
        attested._absolute_path_syntax_key(
            str(receipt.parent.with_name(f"{receipt.parent.name}.inflight")),
            "test owner work directory",
        ),
    }

    def refuse_live_probe(_path: Path) -> str:
        raise AssertionError("restore must use retained pre/post version observations")

    def refuse_target_resolve(path: Path, strict: bool = False) -> Path:
        try:
            key = attested._absolute_path_syntax_key(str(path), "test observed path")
        except ValueError:
            key = None
        caller_file = Path(sys._getframe(1).f_code.co_filename).name
        if key in protected_keys and caller_file == "stagec_attested.py":
            raise AssertionError("restore must not resolve retained or live executable paths")
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(attested, "_read_windows_file_version", refuse_live_probe)
    monkeypatch.setattr(Path, "resolve", refuse_target_resolve)
    evidence = attested.restore_stagec_attested_evidence(receipt)

    assert evidence.receipt_attested is True


def test_absolute_path_syntax_keys_are_offline_and_platform_explicit() -> None:
    assert attested._absolute_path_syntax_key(
        r"D:\CODEV115\codev.exe", "Windows path"
    ) == attested._absolute_path_syntax_key("d:/codev115/CODEV.EXE", "Windows path")
    assert attested._absolute_path_syntax_key(
        "/opt/codev/codev.exe", "POSIX path"
    ) != attested._absolute_path_syntax_key("/opt/CODEV/codev.exe", "POSIX path")
    for invalid in ("codev.exe", r"D:\CODEV115\..\foreign.exe", "/opt/codev/../foreign"):
        with pytest.raises(ValueError, match="canonical absolute path"):
            attested._absolute_path_syntax_key(invalid, "invalid path")


@pytest.mark.parametrize("bad_executable", ["codev.exe", r"D:\CODEV115\codev.ex"])
def test_restore_rejects_relative_or_wrong_retained_executable_path(
    tmp_path: Path,
    bad_executable: str,
) -> None:
    receipt_path = _seal(tmp_path / "run_restore_bad_executable")
    launch_path = receipt_path.parent / "launch.json"
    launch = attested._strict_json(launch_path.read_bytes(), "test launch")
    command = launch.get("command")
    assert isinstance(command, list)
    command[0] = bad_executable
    launch_path.write_bytes(attested._canonical_json(launch))

    receipt = attested._strict_json(receipt_path.read_bytes(), "test receipt")
    process = receipt.get("process")
    assert isinstance(process, dict)
    owner = process.get("lock_owner")
    assert isinstance(owner, dict)
    details = owner.get("details")
    assert isinstance(details, dict)
    details["command"] = list(command)
    receipt_path.write_bytes(attested._canonical_json(receipt))
    _resign_receipt(receipt_path)

    with pytest.raises(ValueError, match="shared CODE V lock launch"):
        attested.restore_stagec_attested_evidence(receipt_path)


@pytest.mark.parametrize(
    "bad_work_dir",
    ["run.inflight", r"D:\stagec-runs\run.infligh"],
)
def test_restore_rejects_relative_or_wrong_retained_owner_work_directory(
    tmp_path: Path,
    bad_work_dir: str,
) -> None:
    receipt_path = _seal(tmp_path / "run_restore_bad_owner")
    receipt = attested._strict_json(receipt_path.read_bytes(), "test receipt")
    process = receipt.get("process")
    assert isinstance(process, dict)
    owner = process.get("lock_owner")
    assert isinstance(owner, dict)
    details = owner.get("details")
    assert isinstance(details, dict)
    details["work_dir"] = bad_work_dir
    receipt_path.write_bytes(attested._canonical_json(receipt))
    _resign_receipt(receipt_path)

    with pytest.raises(ValueError, match="canonical inflight package"):
        attested.restore_stagec_attested_evidence(receipt_path)


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("schema", "unsupported Stage C execution-plan schema"),
        ("duplicate", "cell identities must be unique"),
        ("extra-cell-key", "keys differ from the closed schema"),
        ("count", "counts/metadata are invalid"),
        ("float-count", "counts/metadata are invalid"),
        ("stageb-path", "matrix or Stage B manifest binding"),
        ("stageb-hash", "matrix or Stage B manifest binding"),
        ("accepted-hash", "accepted hash differs from retained Stage B source"),
        ("noncurrent-accepted-hash", "hashes do not match retained Stage B manifest"),
        ("reconstruction-extra-key", "reconstruction differs from the closed schema"),
        ("reconstruction-shape", "fresh runner reconstruction semantics"),
        ("reconstruction-field-before", "fresh runner reconstruction semantics"),
        ("reconstruction-vignetting", "fresh runner reconstruction semantics"),
        ("reconstruction-reason", "fresh runner reconstruction semantics"),
    ],
)
def test_real_matrix_plan_is_a_closed_8_seed_24_cell_contract(
    tmp_path: Path,
    defect: str,
    message: str,
) -> None:
    receipt = _seal(tmp_path / "run_014")
    plan_path = receipt.parent / "execution-plan.json"
    plan = attested._strict_json(plan_path.read_bytes(), "test execution plan")
    cells = plan.get("cells")
    assert isinstance(cells, list)
    assert cells and isinstance(cells[0], dict)
    if defect == "schema":
        plan["schema_id"] = "caller-authored-plan-v99"
    elif defect == "duplicate":
        cells[1] = dict(cells[0])
    elif defect == "extra-cell-key":
        cells[0]["caller_verdict"] = True
    elif defect == "count":
        plan["expected_run_count"] = 47
    elif defect == "float-count":
        plan["seed_count"] = 8.0
    elif defect == "stageb-path":
        plan["stageb_manifest"] = str((tmp_path / "other-manifest.json").resolve())
    elif defect == "stageb-hash":
        plan["stageb_manifest_sha256"] = "0" * 64
    elif defect == "accepted-hash":
        cells[0]["accepted_zmx_sha256"] = "d" * 64
        reconstruction = cells[0].get("reconstruction")
        assert isinstance(reconstruction, dict)
        reconstruction["source_sha256_before"] = "d" * 64
        reconstruction["source_sha256_after"] = "d" * 64
    elif defect == "noncurrent-accepted-hash":
        cells[3]["accepted_zmx_sha256"] = "d" * 64
        reconstruction = cells[3].get("reconstruction")
        assert isinstance(reconstruction, dict)
        reconstruction["source_sha256_before"] = "d" * 64
        reconstruction["source_sha256_after"] = "d" * 64
    elif defect == "reconstruction-extra-key":
        reconstruction = cells[0].get("reconstruction")
        assert isinstance(reconstruction, dict)
        reconstruction["caller_claim"] = True
    elif defect == "reconstruction-shape":
        reconstruction = cells[0].get("reconstruction")
        assert isinstance(reconstruction, dict)
        reconstruction["num_fields"] = 1
        reconstruction["normalized_fractions"] = [1.0]
    elif defect == "reconstruction-field-before":
        reconstruction = cells[0].get("reconstruction")
        assert isinstance(reconstruction, dict)
        reconstruction["field_type_before"] = 1
    elif defect == "reconstruction-vignetting":
        reconstruction = cells[0].get("reconstruction")
        assert isinstance(reconstruction, dict)
        reconstruction["vignetting_status"] = "nonzero-retained"
    elif defect == "reconstruction-reason":
        reconstruction = cells[0].get("reconstruction")
        assert isinstance(reconstruction, dict)
        reconstruction["reason"] = "caller-authored but structurally valid reason"
    else:
        raise AssertionError(f"unhandled defect fixture: {defect}")
    plan_path.write_bytes(attested._canonical_json(plan))
    _rebind_package(receipt)

    with pytest.raises(ValueError, match=message):
        attested.restore_stagec_attested_evidence(receipt)


def test_real_plan_requires_exact_eight_stageb_manifest_bindings(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_019")
    manifest_path = receipt.parent / "stageb-manifest.json"
    manifest = attested._strict_json(manifest_path.read_bytes(), "test Stage B manifest")
    entries = manifest.get("accepted")
    assert isinstance(entries, list)
    manifest["required_count"] = 1
    manifest["accepted_count"] = 1
    manifest["accepted"] = entries[:1]
    manifest.pop("outcomes")
    manifest.pop("incomplete_attempts")
    manifest["cache_scope_counts"] = {"pre-run-bound": 1}
    manifest["all_inputs_pre_run_bound"] = True
    manifest_raw = attested._canonical_json(manifest)
    manifest_path.write_bytes(manifest_raw)

    plan_path = receipt.parent / "execution-plan.json"
    plan = attested._strict_json(plan_path.read_bytes(), "test execution plan")
    plan["stageb_manifest_sha256"] = attested._sha(manifest_raw)
    plan_path.write_bytes(attested._canonical_json(plan))
    _rebind_package(receipt)

    with pytest.raises(ValueError, match="exactly 8 accepted entries"):
        attested.restore_stagec_attested_evidence(receipt)


def test_spec_rebinds_the_actual_stageb_manifest_path(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_020")
    spec_path = receipt.parent / "spec.json"
    spec = attested._strict_json(spec_path.read_bytes(), "test spec")
    spec["stageb_manifest_path"] = str((tmp_path / "other-manifest.json").resolve())
    spec_path.write_bytes(attested._canonical_json(spec))
    _rebind_package(receipt)

    with pytest.raises(ValueError, match="matrix or Stage B manifest binding"):
        attested.restore_stagec_attested_evidence(receipt)


def test_out_of_contract_process_exit_is_not_attested(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_015")
    receipt_payload = attested._strict_json(receipt.read_bytes(), "test receipt")
    process = receipt_payload.get("process")
    assert isinstance(process, dict)
    process["returncode"] = 2
    receipt.write_bytes(attested._canonical_json(receipt_payload))
    _resign_receipt(receipt)

    with pytest.raises(ValueError, match="successful finite CODE V process"):
        attested.restore_stagec_attested_evidence(receipt)


@pytest.mark.parametrize("duration", [-0.5, "1.0"])
def test_process_duration_must_be_numeric_finite_and_nonnegative(
    tmp_path: Path, duration: object
) -> None:
    receipt = _seal(tmp_path / "run_016")
    receipt_payload = attested._strict_json(receipt.read_bytes(), "test receipt")
    process = receipt_payload.get("process")
    assert isinstance(process, dict)
    process["duration_seconds"] = duration
    receipt.write_bytes(attested._canonical_json(receipt_payload))
    _resign_receipt(receipt)

    with pytest.raises(ValueError, match="successful finite CODE V process"):
        attested.restore_stagec_attested_evidence(receipt)


def test_foreign_reconstruction_bytes_fail_deterministic_replay(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_017")
    reconstructed_path = receipt.parent / "reconstructed.zmx"
    original = reconstructed_path.read_bytes()
    foreign = original.replace(
        b"YFLN 0 2.8999999999999999",
        b"YFLN 0 2.9",
    )
    assert foreign != original
    reconstructed_path.write_bytes(foreign)

    plan_path = receipt.parent / "execution-plan.json"
    plan = attested._strict_json(plan_path.read_bytes(), "test execution plan")
    cells = plan.get("cells")
    assert isinstance(cells, list)
    matching = [
        cell
        for cell in cells
        if isinstance(cell, dict)
        and cell.get("cell_id") == "seed-0001--native-imh-reconstructed-control"
    ]
    assert len(matching) == 1
    reconstruction = matching[0].get("reconstruction")
    assert isinstance(reconstruction, dict)
    reconstruction["output_sha256"] = attested._sha(foreign)
    plan_path.write_bytes(attested._canonical_json(plan))
    _rebind_package(receipt)

    with pytest.raises(ValueError, match="not the deterministic Stage B transform"):
        attested.restore_stagec_attested_evidence(receipt)


def test_stageb_shallow_four_flag_forgery_fails_full_validator(tmp_path: Path) -> None:
    receipt = _seal(tmp_path / "run_018")
    ladder_path = receipt.parent / "stageb-ladder-result.json"
    ladder = attested._strict_json(ladder_path.read_bytes(), "test Stage B ladder")
    accepted_final = ladder.get("accepted_final")
    assert isinstance(accepted_final, dict)
    rungs = ladder.get("rungs")
    last_measured = ladder.get("last_measured_rung")
    assert isinstance(rungs, list) and isinstance(last_measured, dict)
    for retained in (accepted_final, rungs[0], last_measured):
        assert isinstance(retained, dict)
        retained["measured_fnum"] = 99.0
    ladder_raw = attested._canonical_json(ladder)
    ladder_path.write_bytes(ladder_raw)

    manifest_path = receipt.parent / "stageb-manifest.json"
    manifest = attested._strict_json(manifest_path.read_bytes(), "test Stage B manifest")
    entries = manifest.get("accepted")
    assert isinstance(entries, list)
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("case_id") == "seed-0001"
    ]
    assert len(matches) == 1
    matches[0]["accepted_final"] = accepted_final
    matches[0]["ladder_result_sha256"] = attested._sha(ladder_raw)
    outcomes = manifest.get("outcomes")
    assert isinstance(outcomes, list)
    matching_outcomes = [
        outcome
        for outcome in outcomes
        if isinstance(outcome, dict) and outcome.get("case_id") == "seed-0001"
    ]
    assert len(matching_outcomes) == 1
    matching_outcomes[0]["result_sha256"] = attested._sha(ladder_raw)
    manifest_raw = attested._canonical_json(manifest)
    manifest_path.write_bytes(manifest_raw)

    plan_path = receipt.parent / "execution-plan.json"
    plan = attested._strict_json(plan_path.read_bytes(), "test execution plan")
    plan["stageb_manifest_sha256"] = attested._sha(manifest_raw)
    plan_path.write_bytes(attested._canonical_json(plan))
    _rebind_package(receipt)

    with pytest.raises(ValueError, match="unique raw-derived"):
        attested.restore_stagec_attested_evidence(receipt)


@pytest.mark.parametrize(
    "statement",
    [
        ("import app.core.engines.stagec_attested; import app.core.orchestration.candidate"),
        ("import app.core.orchestration.candidate; import app.core.engines.stagec_attested"),
    ],
)
def test_stagec_and_candidate_import_in_either_order(statement: str) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-c", statement],
        cwd=repository_root,
        env={**os.environ, "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
