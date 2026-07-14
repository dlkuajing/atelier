---
quick_id: 260714-stageb-pin-line-ending
status: verified_fixed_commit_pending
mode: debug
validation: required
owner: Codex
base_commit: 7f53436d3e470fde589bf62177b88d5ad11cebd5
base_tree: 6a75caf13826c595be4f1a698af6ddf72bee5131
must_haves:
  truths:
    - "The reviewed LF-byte SHA-256 and size pins remain unchanged."
    - "A Git checkout containing uniformly converted CRLF source bytes verifies against the same reviewed LF pins."
    - "Mixed LF/CRLF content, bare CR, or any non-line-ending source mutation remains fail-closed."
    - "The fix is offline only and does not launch CODE V or any real runner."
  artifacts:
    - path: "scripts/p16_stagec_stageb_inputs_supplement2.py"
      provides: "Strict canonical reviewed-source descriptor for LF and uniform Git CRLF checkouts."
    - path: "tests/test_p16_stagec_stageb_inputs_supplement2.py"
      provides: "Cross-platform positive vectors and mixed/bare-CR negative vectors."
---

# Debug 260714: Stage B reviewed-source pins on Windows

## Root cause

`core.autocrlf=true` converts every LF in the two pinned Python sources to CRLF in a Windows
worktree. The base file gains exactly 1,767 bytes for 1,767 lines and the first supplement gains
exactly 245 bytes for 245 lines. Replacing uniform CRLF with LF reproduces both existing reviewed
size/SHA-256 pins exactly. `origin/main` contains the same source and therefore the failure predates
O-01; Ubuntu CI reads LF bytes and does not expose it.

## Fix

Hash a strict canonical source representation: accept either all-LF or uniformly CRLF-converted
checkout bytes, canonicalize only the latter to LF, and reject mixed line endings or any bare CR.
Do not change the reviewed pin constants and do not normalize arbitrary source content.

## Validation

```powershell
$env:PYTHONUTF8='1'; uv run pytest tests/test_p16_stagec_stageb_inputs_supplement2.py -q -k "not real" -m "not real_machine"
$env:PYTHONUTF8='1'; uv run ruff check scripts/p16_stagec_stageb_inputs_supplement2.py tests/test_p16_stagec_stageb_inputs_supplement2.py
$env:PYTHONUTF8='1'; uv run pytest -q -k "not real" -m "not real_machine"
```

The branch must pass read-only review and the normal PR/CI/merge/main-CI path before O-01 rebases
onto it.
