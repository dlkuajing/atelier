from pathlib import Path

import pytest

from app.core.batch_run_lock import BatchRunnerLockHeldError, batch_runner_lock
from scripts import stagec_verified_probe as probe_module
from scripts.stagec_verified_probe import (
    PROBE_HEADERS,
    PROBE_SCHEMA,
    build_probe_sequence,
    validate_probe_outputs,
)


def test_probe_uses_cross_worktree_p18_window_before_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    window = tmp_path / "p18-global-window"

    def fake_probe(**_kwargs: object) -> Path:
        nonlocal calls
        with pytest.raises(BatchRunnerLockHeldError), batch_runner_lock(window):
            raise AssertionError("probe runner executed outside the P18 window")
        calls += 1
        return tmp_path / "receipt.json"

    monkeypatch.setattr(probe_module, "_run_probe_under_window", fake_probe)
    with batch_runner_lock(window), pytest.raises(BatchRunnerLockHeldError):
        probe_module.run_probe(
            source_zmx=tmp_path / "source.zmx",
            run_root=tmp_path / "runs",
            arm="native",
            executable=tmp_path / "codev.exe",
            timeout_seconds=1.0,
            p18_window_root=window,
        )
    assert calls == 0
    assert (
        probe_module.run_probe(
            source_zmx=tmp_path / "source.zmx",
            run_root=tmp_path / "runs",
            arm="native",
            executable=tmp_path / "codev.exe",
            timeout_seconds=1.0,
            p18_window_root=window,
        )
        == tmp_path / "receipt.json"
    )
    assert calls == 1
    with batch_runner_lock(window):
        pass


def test_probe_sequence_uses_official_rih_and_ray_semantics(tmp_path: Path) -> None:
    sequence = build_probe_sequence(
        source_zmx=tmp_path / "source.zmx",
        metrics_path=tmp_path / "metrics.tsv",
        run_id="stagec_probe_test_001",
        arm="native",
    )

    assert "IN CV_MACRO:ZEMAXOS_TO_CV" in sequence
    assert sequence.index("LCL NUM") < sequence.index("OUT NO")
    assert "^field_type == (TYP FLD)" in sequence
    assert "(XRI F^f Z1)" in sequence
    assert "(YRI F^f Z1)" in sequence
    assert "RAYRSI(1,^refw,^f,0,^input)" in sequence
    assert "^input(1) == 0" in sequence
    assert "^input(4) == 0" in sequence
    assert "^rer == (RER)" in sequence
    assert "^bls == (BLS)" in sequence
    for value in ("(X S^image)", "(Y S^image)", "(L S^image)", "(M S^image)", "(N S^image)"):
        assert value in sequence
    for value in ("VUY", "VLY", "VUX", "VLX"):
        assert f"({value} F^f Z1)" in sequence
    assert "rms_spot_diameter_um" in sequence
    assert "rms_spot_radius" not in sequence
    assert "BUF FMT B1 I^row J6..7 '5e.17e'" in sequence
    assert f"STAGEC_PROBE_BEGIN {PROBE_SCHEMA}" in sequence
    assert f"STAGEC_PROBE_END {PROBE_SCHEMA}" in sequence


@pytest.mark.parametrize(
    ("arm", "expected"),
    (("native", None), ("to-img", "IMG"), ("to-rih", "RIH")),
)
def test_probe_sequence_conversion_arms(tmp_path: Path, arm: str, expected: str | None) -> None:
    sequence = build_probe_sequence(
        source_zmx=tmp_path / "source.zmx",
        metrics_path=tmp_path / "metrics.tsv",
        run_id="stagec_probe_test_002",
        arm=arm,  # type: ignore[arg-type]
    )

    conversion_rows = [line for line in sequence.splitlines() if "CVTFIELD" in line]
    assert conversion_rows == ([] if expected is None else [f"IN CV_MACRO:CVTFIELD {expected}"])


def test_probe_sequence_rejects_unsafe_run_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run_id"):
        build_probe_sequence(
            source_zmx=tmp_path / "source.zmx",
            metrics_path=tmp_path / "metrics.tsv",
            run_id="unsafe id",
            arm="native",
        )


def test_probe_completeness_comes_from_raw_artifacts_not_returncode() -> None:
    run_id = "stagec_probe_test_003"
    arm = "native"
    metrics = (
        "\t".join(PROBE_HEADERS)
        + "\r\n"
        + "\t".join(
            [
                "FIELD",
                run_id,
                arm,
                "1",
                "RIH",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "1",
                "0",
                "0",
                "0",
                "0",
                "0",
                "12.3",
                "0.5",
                "0.4",
                "3.6",
            ]
        )
        + "\r\n"
    ).encode()
    listing = (
        f"STAGEC_PROBE_BEGIN {PROBE_SCHEMA} {run_id} {arm}\r\n"
        f"STAGEC_PROBE_END {PROBE_SCHEMA} {run_id} {arm}\r\n"
    ).encode()

    result = validate_probe_outputs(
        metrics_bytes=metrics,
        listing_bytes=listing,
        run_id=run_id,
        arm=arm,
    )

    assert result["complete"] is True
    assert result["field_count"] == 1
    assert result["process_returncode_is_not_a_completeness_gate"] is True
