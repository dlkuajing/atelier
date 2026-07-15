from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core import patent_conversion_process as process_runner
from app.core.patent_conversion_process import (
    PatentConversionRequest,
    PatentPrescriptionInput,
    PatentSurfaceInput,
    ProcessExecution,
    SourceDocumentEvidence,
    canonical_json_bytes,
    conversion_request_sha256,
    run_patent_conversion_attempt,
    run_process_with_hard_timeout,
    sha256_bytes,
)


def _minimal_request(tmp_path: Path) -> PatentConversionRequest:
    raw_path = tmp_path / "US-TEST-A1.html"
    raw_path.write_bytes(b"fixture")
    return PatentConversionRequest(
        prescription=PatentPrescriptionInput(
            patent_id="US-TEST-A1",
            embodiment="Embodiment 1",
            focal_length_mm=4.0,
            f_number=2.0,
            hfov_deg=35.0,
            surfaces=(
                PatentSurfaceInput(
                    index=0,
                    label="Object",
                    radius_mm=0.0,
                    thickness_mm=0.0,
                    material=None,
                    nd=None,
                    vd=None,
                    surface_type="SPH",
                    asphere_coefficients={},
                ),
            ),
        ),
        source_document=SourceDocumentEvidence(
            source_bucket="fixture",
            retained_path=raw_path.as_posix(),
            sha256=sha256_bytes(b"fixture"),
        ),
    )


def test_conversion_request_schema_version_is_closed(tmp_path: Path) -> None:
    payload = _minimal_request(tmp_path).model_dump(mode="json")
    payload["schema_version"] = 2

    with pytest.raises(ValidationError, match="schema_version"):
        PatentConversionRequest.model_validate(payload)


def test_default_reference_wavelength_preserves_historical_request_bytes(
    tmp_path: Path,
) -> None:
    request = _minimal_request(tmp_path)
    payload = request.model_dump(mode="json")

    assert "reference_wavelength_um" not in payload["prescription"]
    restored = PatentConversionRequest.model_validate_json(canonical_json_bytes(request))
    assert restored.prescription.reference_wavelength_um == pytest.approx(0.5876)
    assert conversion_request_sha256(restored) == conversion_request_sha256(request)


def test_nondefault_reference_wavelength_is_hashed_conversion_input(
    tmp_path: Path,
) -> None:
    default_request = _minimal_request(tmp_path)
    source_reference = default_request.model_copy(
        update={
            "prescription": default_request.prescription.model_copy(
                update={"reference_wavelength_um": 0.555}
            )
        }
    )
    payload = source_reference.model_dump(mode="json")

    assert payload["prescription"]["reference_wavelength_um"] == pytest.approx(0.555)
    assert conversion_request_sha256(source_reference) != conversion_request_sha256(
        default_request
    )


def test_real_sleeping_process_is_hard_timed_out_and_reaped(tmp_path: Path) -> None:
    started = time.monotonic()
    result = run_process_with_hard_timeout(
        [
            sys.executable,
            "-c",
            "import time; print('worker-started', flush=True); time.sleep(30)",
        ],
        work_dir=tmp_path,
        timeout_seconds=0.2,
    )

    assert result.timed_out is True
    assert time.monotonic() - started < 8.0
    assert b"worker-started" in result.stdout
    assert result.process_kill is not None
    assert result.process_kill["method"] == ("taskkill" if os.name == "nt" else "killpg")
    assert result.process_reap is not None
    assert result.process_reap["reaped"] is True


def test_timeout_receipt_retains_request_logs_and_does_not_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute(*_args: object, **_kwargs: object) -> ProcessExecution:
        return ProcessExecution(
            timed_out=True,
            returncode=1,
            stdout=b"partial stdout",
            stderr=b"partial stderr",
            elapsed_seconds=0.25,
            process_kill={"method": "taskkill", "pid": 123},
            process_reap={"method": "communicate", "pid": 123, "reaped": True},
        )

    monkeypatch.setattr(process_runner, "run_process_with_hard_timeout", fake_execute)
    published = tmp_path / "staging" / "candidate.zmx"
    receipt = run_patent_conversion_attempt(
        _minimal_request(tmp_path),
        published_zmx_path=published,
        attempts_root=tmp_path / "attempts",
        repo_root=tmp_path,
        timeout_seconds=0.2,
    )

    assert receipt.status == "trace_timeout"
    assert receipt.reason_code == "trace_timeout.worker_hard_timeout"
    assert receipt.attempt_id.endswith("attempt-0001")
    assert Path(receipt.request_path).is_file()
    assert Path(receipt.stdout_path).read_bytes() == b"partial stdout"
    assert Path(receipt.stderr_path).read_bytes() == b"partial stderr"
    assert Path(receipt.receipt_path).is_file()
    assert not published.exists()


def test_missing_worker_response_fails_closed_and_retry_is_append_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute(*_args: object, **_kwargs: object) -> ProcessExecution:
        return ProcessExecution(
            timed_out=False,
            returncode=0,
            stdout=b"",
            stderr=b"",
            elapsed_seconds=0.01,
        )

    monkeypatch.setattr(process_runner, "run_process_with_hard_timeout", fake_execute)
    request = _minimal_request(tmp_path)
    kwargs = {
        "published_zmx_path": tmp_path / "staging" / "candidate.zmx",
        "attempts_root": tmp_path / "attempts",
        "repo_root": tmp_path,
        "timeout_seconds": 1.0,
    }

    first = run_patent_conversion_attempt(request, **kwargs)
    second = run_patent_conversion_attempt(request, **kwargs)

    assert first.status == second.status == "trace_failed"
    assert first.reason_code == second.reason_code == "trace_failed.worker_response_invalid"
    assert first.request_sha256 == second.request_sha256
    assert first.retry_number == 1
    assert second.retry_number == 2
    assert first.attempt_id != second.attempt_id
    assert Path(first.request_path).parent != Path(second.request_path).parent


def test_windows_taskkill_gbk_output_is_diagnostic_not_decode_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeProcess:
        pid = 456
        returncode: int | None = None
        calls = 0

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(["fake"], timeout or 0, output=b"partial")
            self.returncode = 1
            return b"partial", b""

        def kill(self) -> None:
            self.returncode = 1

        def wait(self, timeout: float | None = None) -> int:
            self.returncode = 1
            return 1

    fake_process = FakeProcess()
    monkeypatch.setattr(process_runner.subprocess, "Popen", lambda *_a, **_kw: fake_process)
    monkeypatch.setattr(
        process_runner.subprocess,
        "run",
        lambda *_a, **_kw: subprocess.CompletedProcess(
            args=["taskkill"],
            returncode=0,
            stdout="成功".encode("gbk"),
            stderr=b"",
        ),
    )

    result = run_process_with_hard_timeout(
        ["fake"],
        work_dir=tmp_path,
        timeout_seconds=0.01,
        platform_name="nt",
    )

    assert result.timed_out is True
    assert result.process_kill is not None
    assert result.process_kill["method"] == "taskkill"
    assert "stdout_tail" in result.process_kill
