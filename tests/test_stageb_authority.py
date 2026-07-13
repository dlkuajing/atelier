from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from app.core.engines import stageb_authority as authority


def _request(tmp_path: Path) -> authority.StageBAuthorityRequest:
    source = tmp_path / "source.zmx"
    source.write_bytes(b"FTYP 0 0 2 0 0 0 0 2\nXFLN 0 0\nYFLN 0 40\n")
    return authority.StageBAuthorityRequest(
        case_id="case-1",
        rationale="offline authority contract",
        index_record={
            "case_id": "case-1",
            "scenario": "smartphone-wide",
            "source_zmx": "source.zmx",
            "efl_mm": 3.6,
            "image_height_mm": 2.9,
        },
        source_zmx=source,
        accepted_output_path=tmp_path / "candidate" / "candidate.zmx",
        scenario="smartphone-wide",
        target_efl_mm=3.6,
        fnum_target=2.4,
        native_image_height_mm=2.9,
    )


def _config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> authority.StageBAuthorityConfig:
    executable = tmp_path / "codev.exe"
    macro = tmp_path / "official.seq"
    executable.write_bytes(b"offline-codev-fixture")
    macro.write_bytes(b"offline-macro-fixture")
    monkeypatch.setattr(authority, "OFFICIAL_EXECUTABLE", executable)
    monkeypatch.setattr(authority, "OFFICIAL_MACRO", macro)
    monkeypatch.setattr(authority, "P18_GLOBAL_WINDOW_ROOT", tmp_path / "p18-lock")
    monkeypatch.setattr(
        authority,
        "TRUSTED_CODEV_SHA256",
        hashlib.sha256(executable.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(authority, "TRUSTED_CODEV_SIZE_BYTES", executable.stat().st_size)
    monkeypatch.setattr(
        authority,
        "TRUSTED_MACRO_SHA256",
        hashlib.sha256(macro.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(authority, "TRUSTED_CODEV_FILE_VERSION", "11.5-test")
    return authority.StageBAuthorityConfig(
        authority_root=tmp_path / "authority",
        output_lock_root=tmp_path / "output-lock",
        p18_lock_root=tmp_path / "p18-lock",
        executable=executable,
        official_macro=macro,
        _codev_version_for_tests="11.5-test",
    )


def _accepted_runner(called: list[dict[str, object]], *, authority_root: Path):
    def run(**kwargs: object) -> dict[str, object]:
        intents = list((authority_root / "attempts").glob("*/intent.json"))
        assert len(intents) == 1
        intent = json.loads(intents[0].read_text(encoding="utf-8"))
        assert intent["scope"] == "pre-run-intent"
        called.append(dict(kwargs))
        work_dir = Path(str(kwargs["work_dir"]))
        emitted = work_dir / "emitted.zmx"
        emitted.write_bytes(b"accepted-zmx-bytes\n")
        accepted_final = {
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
            "autovig.edge_used": "0",
            "autovig.converged": "1",
            "effective_edge_used": 0.3,
            "quality_note": "measured on accepted pupil",
            "optimized_zmx_path": str(emitted.resolve()),
            "ray_retry": None,
            "error": None,
        }
        return {
            "schema": "atelier-p15-fno-ladder-v1",
            "source_zmx": "source.zmx",
            "stage": kwargs["stage"],
            "target_efl_mm": kwargs["target_efl_mm"],
            "fnum_target": kwargs["fnum_target"],
            "rung_count": kwargs["rung_count"],
            "fnum_tolerance_pct": kwargs["fnum_tolerance_pct"],
            "vig_ladder": list(kwargs["vig_ladder"]),
            "ray_retry_vig_ladder": list(kwargs["ray_retry_vig_ladder"]),
            "num_fields": kwargs["num_fields"],
            "extra_dof": kwargs["extra_dof"],
            "native_fnum_measured": 2.5,
            "rungs": [dict(accepted_final)],
            "last_measured_rung_index": 3,
            "last_measured_rung": dict(accepted_final),
            "target_achieved": True,
            "accepted_final": accepted_final,
            "blocked": False,
        }

    return run


def test_session_publishes_intent_before_runner_and_closes_raw_dag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path, monkeypatch)
    request = _request(tmp_path)
    called: list[dict[str, object]] = []
    with authority._open_stageb_authority_for_tests(  # noqa: SLF001
        config, _accepted_runner(called, authority_root=config.authority_root)
    ) as session:
        outcome = session.run(request)

    assert len(called) == 1
    assert outcome.status == "accepted"
    assert outcome.manifest_path is not None
    assert outcome.final_result_path is not None
    manifest_raw = outcome.manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    entry = manifest["accepted"][0]
    binding = authority.validate_retained_stageb_authority(
        manifest_raw=manifest_raw,
        ladder_raw=outcome.final_result_path.read_bytes(),
        raw_ladder_raw=outcome.raw_result_path.read_bytes(),
        cache_record_raw=outcome.intent_path.read_bytes(),
        case_id="case-1",
        accepted_zmx_raw=outcome.accepted_zmx.read_bytes(),  # type: ignore[union-attr]
        verify_external_paths=True,
    )
    assert binding.scope == authority.PRE_RUN_SCOPE
    assert binding.pre_run_bound is True
    assert binding.raw_result_sha256 == entry["raw_ladder_result_sha256"]
    assert Path(entry["accepted_zmx"]).read_bytes() == b"accepted-zmx-bytes\n"


def test_collision_refuses_before_intent_and_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path, monkeypatch)
    request = _request(tmp_path)
    request.accepted_output_path.parent.mkdir(parents=True)
    request.accepted_output_path.write_bytes(b"existing")
    called: list[dict[str, object]] = []
    with (
        authority._open_stageb_authority_for_tests(  # noqa: SLF001
            config, _accepted_runner(called, authority_root=config.authority_root)
        ) as session,
        pytest.raises(FileExistsError, match="collision"),
    ):
        session.run(request)
    assert called == []
    assert list(config.authority_root.rglob("intent.json")) == []


def test_nonaccepted_result_preserves_intent_and_raw_without_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path, monkeypatch)
    request = _request(tmp_path)

    def runner(**kwargs: object) -> dict[str, object]:
        assert list((config.authority_root / "attempts").glob("*/intent.json"))
        rung = {
            "rung_index": 0,
            "target_fnum": None,
            "status": "error",
            "measured_fnum": None,
            "fnum_target_deviation_pct": None,
            "fno_param_achieved": False,
            "ray_traceable": False,
            "ray_grid": None,
            "efl_target_deviation_pct": None,
            "post_aut.max_rms_spot_diameter_um": None,
            "post_aut.max_rms_wavefront_error_waves": None,
            "err_f_ratio": None,
            "aut_termination": None,
            "aut_converged": False,
            "autovig.edge_used": None,
            "autovig.converged": None,
            "effective_edge_used": None,
            "quality_note": "machine rung returned no accepted measurement",
            "optimized_zmx_path": None,
            "ray_retry": None,
            "error": {"kind": "failure", "detail": "offline fixture"},
        }
        return {
            "schema": "atelier-p15-fno-ladder-v1",
            "source_zmx": "source.zmx",
            "stage": kwargs["stage"],
            "target_efl_mm": kwargs["target_efl_mm"],
            "fnum_target": kwargs["fnum_target"],
            "rung_count": kwargs["rung_count"],
            "fnum_tolerance_pct": kwargs["fnum_tolerance_pct"],
            "vig_ladder": list(kwargs["vig_ladder"]),
            "ray_retry_vig_ladder": list(kwargs["ray_retry_vig_ladder"]),
            "num_fields": kwargs["num_fields"],
            "extra_dof": kwargs["extra_dof"],
            "native_fnum_measured": None,
            "rungs": [rung],
            "last_measured_rung_index": None,
            "last_measured_rung": None,
            "target_achieved": False,
            "accepted_final": None,
            "blocked": True,
        }

    with authority._open_stageb_authority_for_tests(config, runner) as session:  # noqa: SLF001
        outcome = session.run(request)
    assert outcome.status == "not-accepted"
    assert outcome.intent_path.is_file()
    assert outcome.raw_result_path.is_file()
    assert outcome.final_result_path is None
    assert outcome.manifest_path is None
    assert not request.accepted_output_path.exists()


def test_fresh_validator_rejects_semantically_tampered_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path, monkeypatch)
    request = _request(tmp_path)
    with authority._open_stageb_authority_for_tests(  # noqa: SLF001
        config, _accepted_runner([], authority_root=config.authority_root)
    ) as session:
        outcome = session.run(request)
    assert outcome.manifest_path is not None and outcome.final_result_path is not None
    final = json.loads(outcome.final_result_path.read_text(encoding="utf-8"))
    final["target_achieved"] = False
    forged_raw = authority._canonical_bytes(final)  # noqa: SLF001
    manifest = json.loads(outcome.manifest_path.read_text(encoding="utf-8"))
    manifest["accepted"][0]["ladder_result_sha256"] = authority._sha(forged_raw)  # noqa: SLF001
    with pytest.raises(ValueError, match="target gate and accepted_final"):
        authority.validate_retained_stageb_authority(
            manifest_raw=authority._canonical_bytes(manifest),  # noqa: SLF001
            ladder_raw=forged_raw,
            raw_ladder_raw=outcome.raw_result_path.read_bytes(),
            cache_record_raw=outcome.intent_path.read_bytes(),
            case_id="case-1",
            accepted_zmx_raw=outcome.accepted_zmx.read_bytes(),  # type: ignore[union-attr]
            verify_external_paths=False,
        )


def test_production_identity_allows_truthful_missing_native_image_height(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path, monkeypatch)
    request = _request(tmp_path)
    request = replace(
        request,
        native_image_height_mm=None,
        index_record={**request.index_record, "image_height_mm": None},
    )
    with authority._open_stageb_authority_for_tests(  # noqa: SLF001
        config, _accepted_runner([], authority_root=config.authority_root)
    ) as session:
        outcome = session.run(request)
    assert outcome.status == "accepted"
    assert outcome.manifest_path is not None
    entry = json.loads(outcome.manifest_path.read_text(encoding="utf-8"))["accepted"][0]
    assert entry["native_image_height_mm"] is None


def test_authority_refuses_output_lock_aliasing_codev_before_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = replace(_config(tmp_path, monkeypatch), output_lock_root=authority.CODEV_LOCK_ROOT)
    called: list[dict[str, object]] = []
    with (
        pytest.raises(ValueError, match="output, P18, and CODE V lock roots"),
        (
            authority._open_stageb_authority_for_tests(  # noqa: SLF001
                config, _accepted_runner(called, authority_root=config.authority_root)
            )
        ),
    ):
        pytest.fail("aliased authority unexpectedly opened")
    assert called == []
    assert not config.authority_root.exists()


def test_ladder_validator_rejects_nested_verdict_and_open_ray_grid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path, monkeypatch)
    with authority._open_stageb_authority_for_tests(  # noqa: SLF001
        config, _accepted_runner([], authority_root=config.authority_root)
    ) as session:
        outcome = session.run(_request(tmp_path))

    forbidden = deepcopy(outcome.result)
    forbidden["accepted_final"]["quality_note"] = "[EXPERT] PASS"
    with pytest.raises(ValueError, match="forbidden verdict"):
        authority._validate_ladder_shape(forbidden, label="fixture")  # noqa: SLF001

    open_grid = deepcopy(outcome.result)
    for retained in (
        open_grid["accepted_final"],
        open_grid["rungs"][0],
        open_grid["last_measured_rung"],
    ):
        retained["ray_grid"]["unbound_extra"] = True
    with pytest.raises(ValueError, match="ray grid is not closed"):
        authority._validate_ladder_shape(open_grid, label="fixture")  # noqa: SLF001


def test_trusted_codev_file_version_uses_windows_fixed_file_info_segments() -> None:
    assert authority.TRUSTED_CODEV_FILE_VERSION == "11.5.27302.701"
