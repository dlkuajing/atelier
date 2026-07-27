# Family 91069629 source audit

## Scope and identity

The frozen 619-root cohort contains one Family ID `91069629` root,
`US-20240168282` (`US-20240168282-A1`, application `18/499185`). The application was
filed on 2023-10-31, claims priority to `JP2022-185927` filed on 2022-11-21, and
identifies Kantatsu Co., Ltd. and Sharp Display Technology Corporation. The same US
application issued as `US-12517327-B2` on 2026-01-06. The grant is outside the frozen
cohort and remains queue-only, but its exact official HTML is retained as an
independent same-application source-drift witness.

## Exact source denominator

The A1 contains paragraphs 1-120: background/summary paragraphs 1-75, brief drawing
description paragraphs 76-84 and detailed-description paragraphs 85-120. The B2 has
grant-style paragraph-number resets: background/summary paragraphs 1-74, brief
drawing-description paragraphs 1-9 and detailed-description paragraphs 10-50. Each
publication has claims 1-7, FIGS. 1-7 plus FIGS. 8A-8B (nine actual panels), four tagged
HTML table blocks and one MathML object.

The official A1 and B2 PDFs each have 18 image-only pages: cover page 1, eight drawing
sheets on pages 2-9 and specification pages 10-18. Every PDF page has zero extractable
text and one embedded page image. The independently decoded canonical raster sets hash
to `2890af7fcd3a43a0849a87232b8d9add92be06050901cc53e0016242d59e3266`
and `349aa06335706fd41e5534b02b59ec79fdae8446a209632503ff8cdf889020f1`.
All-page contact sheets and table pages 15-17 were inspected. The rasters corroborate
the text only; no coordinate or missing system value was transcribed or derived from a
drawing or page image.

## Prescription and source boundary

Tables 1-3 are three complete reflective pancake prescriptions. Each publishes direct
`f`, `Fno`, 45-degree half field, image height and TTL values; an ordered 29-row path
plus Display; reflective rows 8 and 14; negative-thickness return rows 9, 10, 11 and
13; asphere path rows 6, 11, 18 and 23; and `A4` through `A20` coefficients for the
two unique asphere lens surfaces 6 and 23. Table 4 publishes conditional expressions.
The three system-value tuples are `(16.29, 2.04, 45, 13.36, 32.0)`,
`(15.18, 1.90, 45, 12.62, 30.60)` and `(15.52, 1.94, 45, 12.94, 30.60)` for
`(f, Fno, half-field, image height, TTL)`. The single-lens focal lengths are
68.119, 60.623 and 65.331 mm. All four table numeric payload hashes are identical
between the A1 and B2. No numeric value is borrowed across publications.

## Converter capability boundary

The disclosed light path uses a half mirror, reflective polarizers, quarter-wave
plates, polarization-dependent branching, two reflective surfaces and return segments.
The current `PatentSurface`, `PatentSurfaceInput` and `CodeVSurfaceReadout` contracts
have no reflect/half-mirror/polarization/branch field. The current prescription-to-
readout builder also drops `PatentSurface.material`; a probe carrying `MIRROR` in both
material and surface type produces neither a mirror glass directive nor mirror surface
semantics. Negative thickness alone cannot encode the missing optical interactions.

Flattening these tables into an ordinary sequential refractive lens would therefore
silently change the disclosed system. The three complete prescriptions are classified
as `parser_review_required` for the explicit converter capability gap. They are not
source-exhausted terminals, and no conversion request, receipt, prescription
fingerprint, candidate or ZMX is created.

## Replay result

Append-only attempts 2 and 3 are semantic-equal after removing only `result_attempt`.
Each attempt contains the same three parser-review items and no worker identity or
conversion fields. Strict replay remains 619/619 with zero missing and zero corrupt
results. The result-set hash is
`813663383d10880ca64f1566b24c1e31e1bcae3f67a3154872334f3c4d9138b6`;
root counts remain 316 parser review, 146 mixed, 132 terminal and 25 converted. Item
counts become 1409 parser review, 1122 terminal, 551 staging and 28 conversion retry.

The generic bucket falls from 127 to 126 roots/items, and two independently rebuilt
after-census files are byte-identical. Family `82656625`, root `US-20260110882`, is the
next stable exact group. The generic bucket, other parser buckets, formal intake,
external-family queue and global patent/source saturation all remain incomplete.
