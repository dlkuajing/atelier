# Family 67207110 source audit

## Identity and denominator

The exact retained official source is `US-12013514-B2`, application `17/553988`,
Family ID `67207110`, titled *Imaging lens assembly, camera module and electronic
device*. It is a continuation of application `16/505926` (grant `US-11237361`) and
claims Taiwan priority `107214451` dated 2018-10-24. The source contains one numbered
Related Applications paragraph, six numbered Background/Summary paragraphs, 80 numbered
Description paragraphs, 13 claims, 16 declared figure entries, four flattened tables,
no MathML objects, and seven source-disclosed items. Claim 1 is the sole independent
claim; claims 12 and 13 add a camera module and an electronic device.

## Prescription boundary

Description paragraphs 35-72 disclose four five-lens imaging lens assemblies. Each
names five ordered lens elements, a lens barrel, an image surface, blocking sheets, and
first and second spacing rings, but it publishes no lens-surface radii, optical axial
thicknesses or air spaces, optical materials, refractive indices, Abbe numbers, asphere
coefficients, stop position, EFL, F-number, optical field, or image height. Tables 1-4
contain only mechanical spacing-ring values `t1`, `t2`, `d`, `t1/d`, and `t2/d`; those
values are not reclassified as an optical prescription. The first four items are exact
`confirmed_no_prescription` terminals.

Paragraphs 73-79 disclose smartphone, tablet, and wearable-device wrappers that reuse a
camera module based on one of the first four assemblies. They add sensor, circuit,
autofocus, anti-shake, user-interface, and packaging details, but no independent ordered
optical prescription. These three wrappers are also exact `confirmed_no_prescription`
terminals. No conversion request, receipt, fingerprint, candidate ZMX, staging ZMX, or
formal intake is warranted.

## Figure-label discrepancy and original-raster review

The source text calls the third first-embodiment drawing `FIG. 10` in Brief Description
paragraph 4 and again in paragraph 35. Official PDF page 5 is visibly labeled `Fig. 1C`,
and detailed paragraph 42 also refers to `FIG. 1C`. This is recorded as a one-token
source discrepancy; the raw source is not silently repaired and the drawing is not used
to infer any numeric value.

The retained official PDF has 26 image-only pages: one cover, one references-cited page,
16 drawing sheets, and eight specification/claim pages. Pages 21-24 confirm the printed
layouts of Tables 1-4 and pages 25-26 contain the claims. Original lossless page rasters
were reviewed without enhancement, measurement, or numeric transcription. Two
consecutive USPTO endpoint fetches produced byte-distinct PDF containers of identical
length but the same decoded page-raster content. HTML remains the content authority and
the PDF is used for layout and printed-label confirmation only.

## Replay and residual census

Append-only attempts 2 and 3 are each 6,597 bytes and produce seven terminal
`confirmed_no_prescription` items. Their canonical business payloads are identical at
`7c20127e84e51e83afa22cb7693bdd1367e607c409c018e3c8551f51fabd86bc` after
removing only `result_attempt`; no outcome, request, path, receipt, or runtime field is
normalized. Neither attempt invokes a worker or creates a request, receipt, fingerprint,
candidate, staging ZMX, formal intake item, or CODE V call.

The strict replay audit is 619/619 roots with zero missing and zero corrupt results. The
generic residual falls from 71 to 70 roots/items. Both independently rebuilt after
censuses are byte-identical at
`ded193a9907de2d87d70b20f708728ade64708e302e6df1972ef1616aa0bfe4d`,
with result set
`2366d288e7a831f4d700e9d60a7236dc3da2f0aaaaa656e4e98ec5191d547af3`.
The live summary and report are pinned at
`f7183347a784ab78932efbd7155f2894fdfbb0e9f1d56dc811d2ae16eb57fbcd`
and `b1c69518b58e666aa478f0e2015e076f55b5ad626cb850dd04d0c6edb53b4bbd`.
Focused family tests pass 7/7, including the current evidence-manifest rehash; the
complete non-`real_machine` repository sweep passes
3,523 tests with one existing skip and ten real-machine tests deselected, the offline
CODE V guard passes 5/5, and the 22 prior evidence rehash tests pass. Ruff, compile,
JSON, strict-ledger, formal-output, contamination, protected-path, diff, primary-repository,
and process-inventory audits pass. CODE V inventory remains zero. Stable ordering selects
Family `66534470` / `US-20190154987-A1` next; global saturation remains incomplete.
