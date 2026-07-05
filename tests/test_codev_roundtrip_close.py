from __future__ import annotations

from pathlib import Path

import pytest

from app.core.engines.codev_batch import DEFAULT_CODEV_EXECUTABLE
from app.core.engines.codev_roundtrip import (
    DEFAULT_PATENT_ROUNDTRIP_SEED,
    run_codev_roundtrip_close,
)


def test_real_codev_readout_rebuilds_zmx_and_passes_four_fidelity_gates(
    tmp_path: Path,
) -> None:
    assert DEFAULT_CODEV_EXECUTABLE.is_file(), "CODE V executable is required for ENGINE-04c"

    result = run_codev_roundtrip_close(work_dir=tmp_path, timeout_seconds=120.0)
    comparison = result.comparison

    assert result.source_zmx.name == DEFAULT_PATENT_ROUNDTRIP_SEED
    assert result.readout.readout.source_zmx == DEFAULT_PATENT_ROUNDTRIP_SEED
    assert result.readout.readout.image_height_y_mm == pytest.approx(3.62257, rel=0.03)
    assert result.exported_zmx.name == "exported.zmx"
    assert result.exported_zmx.is_file()

    assert comparison.passed, comparison.describe()
    assert comparison.efl_deviation_pct < 2.0
    assert not comparison.glass_mismatches
    assert comparison.source.asphere_term_counts == comparison.exported.asphere_term_counts
    assert comparison.source.vignetting["VDX"] == comparison.exported.vignetting["VDX"]
    assert comparison.source.vignetting["VDY"] == comparison.exported.vignetting["VDY"]
