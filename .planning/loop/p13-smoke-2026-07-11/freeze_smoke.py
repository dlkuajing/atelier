"""P13 freeze-sequence grammar smoke (real machine, single candidate).

Pipeline: real readout -> identity -> snap proposals -> freeze/reopt sequence
-> codev.exe /B -> inspect listing for grammar errors. Scratch probe; the
matrix execution driver proper is shovel 3.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path("D:/atelier")
sys.path.insert(0, str(REPO))

from app.core.engines.codev_batch import resolve_default_codev_executable  # noqa: E402
from app.core.engines.codev_readout import run_codev_readout  # noqa: E402
from app.core.engines.glass_snap import build_plastic_catalog  # noqa: E402
from app.core.engines.glass_snap_chain import (  # noqa: E402
    build_glass_freeze_reopt_sequence,
    build_material_region_identities,
    configuration_fingerprint,
    material_claims_from_readout,
    propose_material_snaps,
)

OUT = Path(__file__).resolve().parent / "smoke_out"
OUT.mkdir(exist_ok=True)
CAND = REPO / ".planning/loop/candidates-2026-07-09/US20170003482A1/both/US20170003482A1_target3.797_optimized.zmx"

print("step 1: real readout of candidate ...")
readout_result = run_codev_readout(source_zmx=CAND, work_dir=OUT / "readout")
readout = readout_result.readout
print("  readout ok:", type(readout).__name__)

claims = material_claims_from_readout(readout)
print("step 2: material claims:", len(claims))
identity = build_material_region_identities(claims)
print("  regions:", len(identity.regions), "withheld:", identity.withheld_reasons)
if not identity.writable:
    print("IDENTITY-WITHHELD — cannot proceed")
    sys.exit(2)

catalog = build_plastic_catalog()
proposals = propose_material_snaps(identity, catalog, tolerance=0.05, disp_factor=1.0)
for p in proposals:
    e = p.result.entry
    print(f"  region {p.region.region_id} S{p.region.start_surface}: {p.disposition}"
          f" -> {(e.glass_name + f' d={p.result.distance:.5f}') if e else 'fictitious-kept'}")
if any(p.disposition != "proposed" for p in proposals):
    print("NOTE: some regions kept fictitious; freeze sequence needs all proposed — smoke uses tolerance=0.05 (uncalibrated, smoke only)")
    proposals = tuple(p for p in proposals if p.disposition == "proposed")

fingerprint = configuration_fingerprint({"probe": "p13-freeze-grammar-smoke", "cand": CAND.name})
seq = build_glass_freeze_reopt_sequence(
    source_zmx=CAND,
    result_path=OUT / "freeze_result.txt",
    proposals=tuple(proposals),
    session_run_id="p13smoke001",
    configuration_fingerprint=fingerprint,
)
seq_path = OUT / "freeze_smoke_run.seq"
seq_path.write_text(seq, encoding="ascii", newline="\r\n")
print("step 3: sequence written:", seq_path, f"({len(seq.splitlines())} lines)")

exe = resolve_default_codev_executable()
start = time.monotonic()
proc = subprocess.Popen([str(exe), "/B", str(seq_path)], cwd=str(OUT),
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
try:
    raw, _ = proc.communicate(timeout=900)
except subprocess.TimeoutExpired:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
    raw, _ = proc.communicate()
    print("TIMEOUT after 900s")
print(f"step 4: rc={proc.returncode} elapsed={time.monotonic()-start:.1f}s")

lis = sorted(OUT.glob("*.lis"), key=lambda p: p.stat().st_mtime, reverse=True)
if lis:
    text = lis[0].read_bytes().decode("ascii", errors="replace")
    import re
    errs = [line for line in text.splitlines() if re.search(r"ERROR|WARNING - Sequence aborted|not allowed|Syntax", line)]
    print("step 5: listing errors/aborts:", len(errs))
    for line in errs[:12]:
        print("   ", line.strip())
res = OUT / "freeze_result.txt"
print("result file:", f"EXISTS {res.stat().st_size} bytes" if res.exists() else "MISSING")
