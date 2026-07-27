# Source audit: Family 85177416 / root US-20230048740

## Scope and collision boundary

This audit closes only root `US-20230048740` and publication
`US-20230048740-A1`. The historical same-family root `US-12498545` was not used
as classification evidence and supplied no numeric value, denominator, or
terminal conclusion.

## Exact source denominator

The retained official A1 HTML contains 19 continuously numbered
background/summary paragraphs and 104 continuously numbered description
paragraphs, for 123 numbered paragraphs total. It declares 12 figure panels,
contains 10 flattened `TABLE-US` objects, nine MathML objects, and seven claims.
The detailed description binds exactly five six-lens prescriptions to paragraph
ranges 54-67, 68-80, 81-93, 94-106, and 107-119, respectively. No additional
prescription or device-wrapper item was found.

Each odd table publishes 17 ordered rows (`Object`, surfaces, `Stop`, and
`Image`); each even table publishes Qcon data for 12 surfaces. The exact source
does not publish effective focal length, F-number, or a
prescription-specific angular field for any of the five items. Items 1, 2, 3,
and 5 also contain directly printed radius conflicts or malformed tokens between
their paired surface and Qcon tables. Item 4 has an internally consistent paired
surface/Qcon set but remains unrepresentable because the required system
metadata is absent.

All five items therefore close as `metadata_unpublished`. No source token was
repaired, no value was inferred from image height or TOPL/Himg, and no drawing
geometry was measured.

## Official PDF/raster review

Two independent downloads of the official A1 PDF produced distinct container
hashes but the same 25 decoded page records and the same raster-set SHA-256.
Both PDFs are image-only and contain exactly one raster per page. All 25 original
page rasters were retained; pages 17-24 were inspected individually for table
layout and printed-token preservation. Four contact sheets were used only for
navigation. No enhancement, OCR-based numeric substitution, raster measurement,
or numeric transcription from raster evidence was used.

## Replay and output boundary

Append-only replay attempts 2 and 3 each produced five terminal items and no
conversion request, receipt, prescription fingerprint, staging ZMX, candidate
ZMX, formal intake, or CODE V call. After removing only `result_attempt`, both
results have semantic SHA-256
`a0a411c1ffaed02b1cb77b94762658782d1458b0bfa4aa8395643b75559f85bf`.
The strict ledger audit reports 619/619 roots with results and zero corrupt
results. The generic residual census is stable across two independent after
runs at 61 roots/items.
