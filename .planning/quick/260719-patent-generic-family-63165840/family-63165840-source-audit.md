# Family 63165840 source audit

`US-10197774-B1` is the sole retained US publication for application `15/864483` in
this replay root. The exact official USPTO HTML is the numeric authority. Its raw
SHA-256 is
`1887b838473fcde0aa10edc6b1d88235c8fa194523749ff63dbe3e68deb1a696`;
the runtime-normalized text has 41,072 characters and SHA-256
`ac350ae7365778dbb2e1299283667b9f999d9a66160133863e47b7c00c287cff`.

## Closed denominator

The publication contains four numbered background/summary paragraphs, 121 numbered
description paragraphs (13 brief-drawing and 108 detailed), 11 claims (claim 1 is the
only independent claim), 12 declared figures, 13 flattened tables and 22 inline
formula pairs. Tables 1/5/9 are three ordered prescriptions, Tables 2/6/10 are their
even-asphere coefficients, Tables 3/7/11 and 4/8/12 are inflexion/arrest auxiliaries,
and Table 13 is shared condition/summary evidence. There are exactly three disclosed
prescription items and no camera-module wrapper with another prescription.

Each item publishes Stop plus R1-R14 (15 rows), twelve even-asphere surfaces, and a
complete set of direct `f`, `Fno`, diagonal `FOV`, entrance-pupil diameter, image
height and `TTL` values. The modeled representation appends one image surface, so the
closed denominator is 45 published rows, 48 modeled surfaces, 36 aspheres and 288
even-asphere coefficient cells. All paragraphs, claims, figures, tables, formulas and
source items are mapped; no drawing-derived value or related-family value was used.

## Explicit source conflicts

Three narrow conflicts are retained rather than repaired:

1. Paragraphs 52-69 call R13/R14 and d12-d14 a seventh lens L7, while claim 2,
   Figures 1/5/9, the `ndg`/`vg` definitions and each detailed table identify six
   lenses followed by filter GF. The parser preserves every numeric cell and binds
   R13/R14 to GF.
2. Embodiment 3 Table 9 and summary Table 13 disagree on all six center thicknesses
   and on the L3/L6 material pairs. Table 9 is the direct ordered prescription and is
   authoritative; Table 13 remains recorded conflict evidence and performs no repair.
3. Detailed spacing sums are 5.201/5.199/5.202 mm versus rounded Table 13 TTL values
   5.200/5.201/5.201 mm. Detailed ordered spacings are preserved.

## Official raster review boundary

The official 893,622-byte B1 PDF has container SHA-256
`caa2faf6a6f9b7109d9838667b0da40142f4c51d5e7e2280094e78db7403ffcb`.
It has 16 pages, no text layer, and one 2560 x 3300 bilevel raster per page. Sixteen
lossless original page PNGs were extracted; their canonical raster-set SHA-256 is
`1d4172fe2cb85efd4166a362b90f4dbb39fd88dbdf5d3c20d8ed72e1aef76c61`.
The contact sheet is navigation-only. Original pages 1, 2, 9 and 11-16 were visually
reviewed to confirm page roles and that the Table 9/Table 13 conflict is printed in
the official document. No enhancement, measurement or raster numeric transcription
was performed.

## Replay outcome

The family-keyed parser emits exactly three prescriptions and fails closed on any raw,
normalized, section or table drift. Two append-only replays have equal canonical
business semantics (`2ce5a426544fc44d3e767e0162e6f5a950fc9fd6c4b2f56025552bfea4c61ca8`)
and byte-identical request, response, candidate and log payloads. Embodiment 2 produced
one process-isolated staging ZMX at SHA-256
`66851dd7e5d61f639dfd0337ec0d82674503ddff885e14098aae79693a4bca12`.
Embodiments 1 and 3 deterministically terminated `trace_failed` because full-field
real rays did not reach the image surface. No CODE V call or formal intake occurred.

The strict ledger remains complete at 619/619 roots with zero missing or corrupt
results. Repeated censuses are byte-identical and reduce the generic residual from 74
to 73 roots/items. Patent saturation is not complete; the next exact group is Family
90360259 / `US-12554108-B2` under the minimum-layout-signature ordering rule.
