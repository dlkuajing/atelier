# Family 75614661 source audit

## Identity and source boundary

The frozen-cohort root is `US-20260063874`, represented by publication
`US-20260063874-A1` (application 19/384402), titled *IMAGING LENS SYSTEM*. The exact
USPTO HTML input is 66,714 bytes with raw SHA-256
`efa6c9872a90688f543d804e5145f113167cdd900db49108f70e5def0180094a`; normalized text
is 53,583 characters with SHA-256
`df0fce200fc3fb932895ba5e7dfeaf0f48dde5bfde82e4223c752548f8508dd9`.
The source states priority to KR 10-2020-0046525 (April 17, 2020) and a continuation
chain through applications 16/998,063 and 17/858,195. No coordinates were imported
from those relatives.

## Complete denominator

The publication contains numbered paragraphs 1-91, ten declared figures, twelve
tagged HTML tables, ten MathML objects and claims 1-12. The twelve tables are five
surface-prescription tables, five matching asphere tables, TABLE 11 system metadata
and TABLE 12 conditional expressions. The source declares five optical examples.
Examples 1-3 contain 18 surface rows apiece; examples 4-5 contain 17. Every asphere
table contains the fourteen lens-surface rows. The published asphere equation uses
conic `K` and coefficients A-J at even powers r^4 through r^20, all representable by
the existing patent XASPHERE writer.

TABLE 11 publishes focal length, f-number and full field of view for all five
examples. The parser converts only that explicitly published full FOV to the
pipeline's half-field contract by division by two. It does not infer fields from
drawings. Examples 1-3 carry a separate stop at S5. In examples 4-5 the source marks
the powered/aspheric third-lens back surface S6 itself as `(Stop)`; the writer retains
that surface and emits `STOP` on it rather than inserting an extra zero-thickness
surface.

## Source conflict and fail-closed decision

Examples 1, 2, 4 and 5 reconcile their surface and asphere tables and produce complete
source prescriptions. Example 3 does not: all fourteen lens-surface radii in TABLE 5
disagree with the `R` column printed in TABLE 6, including S14 changing from +17.092
to -39.5782. The official page-18 raster visibly confirms both conflicting columns.
Because the publication offers no source-grounded rule for choosing one radius set,
example 3 remains `parser_review_required` with an exact `PatentParseError`; no value
is selected, averaged, interpolated or borrowed.

## Official raster audit

The official USPTO PDF is 1,015,681 bytes with SHA-256
`1b9ea49592409781f767062c27fdb9eb4412e90d6f3eff6d11f4d91d49517c31`.
It has 22 image-only pages, one decoded raster per page and zero extractable text:
page 1 cover, pages 2-11 ten drawing sheets, and pages 12-22 description/claims.
Numeric tables occupy pages 15-21. Retained critical rasters cover FIG. 7 on page 8,
the TABLE 5/6 conflict on page 18, the coincident stop in TABLES 7/8 on page 19, and
TABLES 11/12 on page 21. Raster review was used only to verify source layout and
conflict facts, never to derive numeric coordinates.

## Replay outcome

With a 600-second patent budget, independent result attempts 3 and 4 have identical
normalized request, coverage and outcome semantics. Examples 1, 2, 4 and 5 each have
an exact request hash, prescription fingerprint and receipt-backed terminal
`trace_timeout` after the 120-second worker hard limit. Example 3 remains the
source-conflict parser-review item. The root is therefore `mixed_nonterminal`: four
terminal items plus one unresolved source conflict. No staging ZMX was emitted, CODE V
was not used, and no formal intake occurred.

Receipt bytes intentionally remain distinct audit evidence. Their runtime attempt
identities, process IDs, elapsed timing and the number of identical Optiland fallback
warnings captured before a hard timeout are excluded from semantic equality. The raw
receipt and log hashes, warning counts, status, reason, timeout, request hashes and
return codes remain recorded in `family-75614661-replay-determinism.json`.

## Saturation boundary

This shovel removes one root from the generic-summary residual bucket (121 to 120),
but it does not establish family, bucket or global saturation. The next deterministic
generic group is Family82951912 / `US-12591109-B2`; AAC and Sunny residual buckets
also remain open.
