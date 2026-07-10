# Phase 12 铲 2 — SEKONIX parser implementation notes

## Review-finding repair ledger (F1–F4)

- **F1 fixed:** numeric Glass Code now accepts the publication's general six-digit
  refractive-index field: `nd = 1 + code/1_000_000`, `vd = code/100`.
  `535000.5600`, `544100.5600`, and `634000.2390` decode to `(1.535, 56.0)`,
  `(1.5441, 56.0)`, and `(1.634, 23.9)`.  In a `Glass Code` table, a numeric
  tail token matching `\d{5,7}\.\d{3,5}` but not the exact encoding now raises
  `PatentParseError`; it can no longer silently become air.
- **F2 fixed fail-closed:** removed the Qcon-to-Code-V monomial mapping.  Any
  coefficient table containing `Qcon Coefficient` now raises
  `PatentParseError("Qcon basis conversion not implemented")` before any
  coefficient is attached to a surface.
- **F3 verified and retained:** the RDY/THI A-number is an even-power sequence
  index, so `A3 -> r^4`, `A4 -> r^6`, ..., is correct for this publication.
- **F4 fixed:** each metadata span now begins at the nearest embodiment marker
  in the prose between the preceding coefficient table and the current surface
  table, then ends at the next surface table.  This includes both prose before
  the current table and prose after its coefficient table, while excluding
  prior-art values and the preceding embodiment's trailing metadata.

## Verbatim equation evidence (Google Patents English publication)

Sources inspected from the full Google Patents pages on 2026-07-10:

- `US-12619054-B2`, Mathematical Expression 1:
  `z = cr²/(1 + sqrt(1-(1+k)c²r²)) + u⁴ · Σ[m=0..13] a_m · Q_m^con(u²)`.
  The immediately following prose states verbatim: “r_n indicates a
  normalization radius, u indicates r/r_n, a_m indicates an m-th Qcon
  coefficient, and Q_m^con indicates a m-th Qcon polynomial.”  Therefore its
  Table 2 `Qcon Coefficient` names are Forbes-basis coefficients even though
  that table does not print a `Normalization Radius` row.
- `US-12498545-B2`, Mathematical Expression 1:
  `z = cr²/(1 + sqrt(1-(1+k)c²r²)) + u⁴ · Σ[m=0..12] a_m · Q_m^con(u²)`.
  Its following prose has the same verbatim definitions of `r_n`, `u`, `a_m`,
  and `Q_m^con`; Table 2 also prints `Normalization Radius`.  Direct monomial
  mapping would therefore produce the wrong sag.
- `US-11099361-B2`, Equation 1, verbatim term sequence:
  `A3 · Y⁴ + A4 · Y⁶ + A5 · Y⁸ + A6 · Y¹⁰ + … + A14 · Y²⁶`.
  The publication says: “R is a radius of curvature, K is a conic constant,
  and A3, A4, A5, A6, . . . , A14 are aspherical coefficients.”  This directly
  supports the retained `codev_order = 2 * (n - 1)` mapping.

## Metadata position evidence and positive-case status

- `US-12619054-B2`: Table 1 starts before Table 2; exact `FOV=21.8°` and
  `Fno=2.79` occur in prose after Table 2 and before Table 3.  No exact
  embodiment focal length is printed (only ratios such as `f/f2=2.65`).  Its
  full surface table also ends in named substrate `'D263T'` without printed
  nd/vd.  Thus no complete `PatentPrescription` can be formed honestly.
- `US-12498545-B2`: the inspected full publication defines the Qcon equation
  before its coefficient table, but supplies no exact instance f/Fno/FOV trio;
  its full surface table also ends in named `BK7_SCHOTT` without printed nd/vd.
- `US-11099361-B2`: embodiment prose after Table 2 prints only derived/range
  facts such as `TTL/f=0.84` and angle-of-view ranges, not exact f/Fno/FOV.

Accordingly none of these three publications combines complete exact instance
metadata with a fully decodable glass prescription.  **Positive end-to-end
embodiment gap remains: validate against the remaining 14 SEKONIX publications
in the intake shovel.**  No midpoint, catalog lookup, or invented value was
introduced.  The span correction is still required because the publications
demonstrate metadata on both sides of table pairs, and it prevents systematic
loss of table-leading prose in the remaining family corpus.

## Tests and verification

- Google Patents fixture table text remains copied verbatim; equation evidence
  is quoted in code/test comments with publication and equation identifiers.
- Added surface 4/10 checks for `544100.5600`, three-code unit coverage, and a
  malformed numeric-code fail-loud regression.
- Qcon tests now assert basis-level fail-closed; RDY/THI retains an equation-
  backed coefficient mapping test.
- `PYTHONUTF8=1 uv run pytest tests/test_patent_to_zmx_sekonix.py tests/test_patent_to_zmx.py -q`
  -> `39 passed`.
- `uv run ruff check scripts/patent_to_zmx.py tests/test_patent_to_zmx_sekonix.py`
  -> passed.
