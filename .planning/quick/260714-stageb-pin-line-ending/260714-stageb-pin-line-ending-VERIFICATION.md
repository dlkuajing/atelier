# Verification: Stage B reviewed-source pins on Windows

## Root-cause evidence

- `core.autocrlf=true`; no `.gitattributes` override applies to the two pinned files.
- `scripts/p16_stagec_stageb_inputs.py` checkout bytes were 75,009 bytes with 1,767 CRLF
  sequences. Strict CRLF→LF conversion produced 73,242 bytes and SHA-256
  `4f94a0cbc01405a7b3025f6c2ebadf9403282d83d566fe46bad0390b2f79d080`, exactly the existing
  reviewed base pin.
- `scripts/p16_stagec_stageb_inputs_supplement.py` checkout bytes were 10,109 bytes with 245 CRLF
  sequences. Strict CRLF→LF conversion produced 9,864 bytes and SHA-256
  `9ffcbd381ccb62d8caefd01bd28e3dc7fed57a856d3b8c7a26d92cb7d40cae30`, exactly the existing
  reviewed first-supplement pin.
- The four affected source/test files were introduced together by `ca108a567fd380f15c33129d892d4a80411ef7c9`.
  They are unchanged relative to `origin/main@7f53436d`; the failure predates O-01.

## Assertions

- Existing reviewed pin constants are unchanged.
- All-LF and uniformly CRLF-converted bytes produce the same canonical descriptor.
- Mixed LF/CRLF and bare CR each raise before a descriptor is returned.
- A non-line-ending source mutation still changes canonical size/SHA-256 and fails the existing pin
  comparison.

## Commands and results

```text
PYTHONUTF8=1 uv run pytest tests/test_p16_stagec_stageb_inputs_supplement2.py -q -k "not real" -m "not real_machine"
25 passed in 1.76s

PYTHONUTF8=1 uv run ruff check scripts/p16_stagec_stageb_inputs_supplement2.py tests/test_p16_stagec_stageb_inputs_supplement2.py
All checks passed!

git diff --check
exit 0

PYTHONUTF8=1 uv run pytest -q -k "not real" -m "not real_machine"
2176 passed, 1 skipped, 545 deselected, 6154 warnings in 1192.25s
```

No real-machine test, runner, or CODE V process was selected or launched.
