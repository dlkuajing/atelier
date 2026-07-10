# Phase 12 铲 2 — SEKONIX parser implementation notes

## Delivered

- Added the isolated `_parse_sekonix_table_attempts()` fallback after Sunny.
- Added deterministic surface parsing for RDY/THI, Sphere/Asphere + Y Radius,
  and Qcon Asphere + numeric Glass Code tables.
- Numeric Glass Code decoding is deterministic (`535000.5600` -> nd 1.535,
  vd 56.00); named codes without printed nd/vd fail closed.
- Added explicit `A3 -> Code V A4`, `A4 -> Code V A6`, etc. mapping and
  `4th/6th/... Qcon -> Code V A/B/...` mapping, with a nonzero unsupported
  high-order rejection gate.
- Metadata accepts only exact instance f/Fno/FOV. Range/inequality-only text
  is rejected per embodiment.

## Tests and fixtures

- New tests: 8 passed.
- Patent parser regression: 29 existing + 8 new = 37 passed.
- Real Google Patents text fixtures cover:
  - RDY/THI: `US-11099361-B2`
  - Sphere/Asphere + Y Radius/Thickness/Glass Code: `US-12619054-B2`
  - Qcon Asphere + Glass Code: `US-12498545-B2`
- The powered-lens rows of all three fixtures parse with radius, thickness,
  nd/vd, and coefficient spot checks tied directly to fixture tokens.

## Honest fail-loud ledger

- `US-11099361-B2`: only range/conditional metadata is present in the copied
  passage (`TTL/f<0.85`, angle 26–32 degrees); no exact instance f/Fno/FOV,
  so the embodiment is rejected rather than midpoint-filled.
- `US-12619054-B2`: powered lens numeric Glass Codes parse, but the complete
  table ends with named substrate `'D263T'` and no printed nd/vd; complete
  embodiment therefore fails closed. Its prose also gives exact FOV/Fno but
  no exact instance focal length in the inspected publication text.
- `US-12498545-B2`: powered lens numeric Glass Codes parse, but the complete
  table ends with named `BK7_SCHOTT` and no printed nd/vd; complete embodiment
  therefore fails closed.

These are source-data limitations discovered while enforcing the requested
red lines. No midpoint, catalog guess, or invented fixture value was added.

## Verification

- `PYTHONUTF8=1 uv run pytest tests/test_patent_to_zmx.py tests/test_patent_to_zmx_sekonix.py -q`
  -> `37 passed`.
- `uv run ruff check scripts/patent_to_zmx.py tests/test_patent_to_zmx_sekonix.py`
  -> passed.
- Required whole-tree `uv run ruff check .` remains blocked by 40 pre-existing
  lint findings in files untouched by this shovel (origin/main baseline).
