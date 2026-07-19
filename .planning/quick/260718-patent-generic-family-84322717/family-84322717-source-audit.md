# Family 84322717 source audit

## Retained authority

- Primary parser input: official USPTO grant HTML `US-12656584-B2`, application
  `18/526988`, Family `84322717`.
- Same-application corroboration: official USPTO `US-20240134168-A1` HTML and PDF.
  All 45 table numeric sequences agree; no related-family numeric borrowing was used.
- Primary visual authority: the 45-page official B2 PDF. Every page contains one
  2560×3300 source raster and no text layer. Original page rasters only were reviewed;
  no enhancement, drawing measurement or numeric transcription was performed.

## Complete denominator

The B2 description has 170 consecutive numbered paragraphs, 13 claims (independent
claims 1, 10 and 13), 22 declared figure panels, 45 flattened tables and 31 inline
formula pairs. Five examples each disclose a short- and long-focal-length path, for ten
numeric prescription items. Camera-module and imaging-device wrappers add no distinct
surface prescription. The table denominator is ten surface tables, ten lens-focal
tables, ten system-metadata tables, ten asphere tables and five condition tables.

The ten surface tables contain 138 published rows. After omitting the blank virtual S1
and preserving the terminal published `Image Plane` distance as the filter-exit-to-
sensor air gap, the model appends one zero-thickness image per path and still contains
138 sequential surfaces. The ten coefficient tables bind 88 aspheric lens surfaces and
publish `R`, `K`, and every `A3` through `A20` row. All 792 odd-order cells are exactly
zero.

## Exact representation rules

- The source publishes full field `2ω`; the parser uses only the direct unit/coordinate
  transform `HFOV = 2ω / 2`.
- The source equation uses `sqrt(1-K_source*C²*h²)` while CODE V/Zemax uses
  `sqrt(1-(1+K_codev)*C²*h²)`. Therefore the exact convention transform is
  `K_codev = K_source - 1`. Every published `K_source` is zero and every written
  `K_codev` is `-1`.
- Published `Di` is the distance from surface `Si` to `Si+1`; every distance is retained
  along the unfolded scalar sequential path. First/Second Mirror remains a material-free
  plane. No mirror aperture, tilt or three-dimensional coordinate was synthesized.
- The optical-filter row is the filter entry and carries glass thickness/index. The
  published `Image Plane` row is the planar filter exit carrying the final air gap;
  a zero-thickness image surface follows it.
- The source's direct 2.35 mm image height is audited but is not substituted into the
  existing pipeline sanity property `EFL*tan(HFOV)`.

## Published internal inconsistencies

Two inconsistencies are retained and disclosed rather than silently repaired.

1. Table 32 `Di` sums to 38.457 mm while Table 34 publishes `ΣTd = 38.56 mm`; the
   0.103 mm difference equals the terminal published air gap. The conversion preserves
   every Table 32 distance and records the mismatch.
2. Tables 28/32 reverse all six shared-rear S8–S13 radius signs relative to exact Tables
   31/35. The exact coefficient-table signs also agree with the published L3/L4/L5
   focal-length signs (`−3000.00`, `+13.75`, `−9.70`). Only this six-surface Example 4
   group accepts sign-opposite rounded reconciliation; the exact Tables 31/35 `R` values
   are used. All other exact radii must reconcile to the surface tables within rounding.

Official original B2 pages 37–39 confirm both printed table versions. This selection is
same-document table precedence, not drawing inference or external numeric repair.

## Replay outcome and boundary

Append-only attempts 2 and 3 each produced ten process-isolated conversion receipts and
ten staging ZMX files. After normalizing only attempt-sequence paths and receipt runtime
fields, their business semantics are equal at
`b1ea4876a77ee4679565ae163eabd60a6da9411cb07a3d36dbe0f7869004acdc`;
request, response, candidate, staging, stdout and stderr hashes are pairwise identical.
The root closes the generic parser bucket as `converted_pending_intake`; none of these
items is formal intake, case-library data or expert-backed output. CODE V calls: zero.
