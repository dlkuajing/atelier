# Family 85199256 source audit

## Identity and relationship

- `US-12517281-B2` application `18/097820` and continuation
  `US-20260093056-A1` application `19/413947` share Family ID `85199256`, title
  `Meta-optical device and electronic device including the same`, and Samsung Electronics
  ownership. The A1 record explicitly names application `18/097820` as its parent.
- The B2 Prior Publication Data names `US-20230236339-A1` dated July 27, 2023. That publication
  is not one of the frozen 619 roots, so it is retained in the external-family queue for later
  processing and is not claimed complete here.
- Retained official HTML SHA-256 values are
  `8d33014a60dc3d2cc9d9a02e39831bf45852c1984f46bda6c4f70ce218345068` (B2) and
  `925f82e175ec31eb5d9b20eef019db1715d7b01030701edce7453f1cdbc20854` (A1).
  Parser-normalized hashes are
  `ab059245b4672308e713c2df51b45d37485236c8b35e869aa9bc4fcf6ab7a9c1` and
  `af16fee0a73427814535b21023812fc614949042a09f5504122e69b037853f14`.

## Source denominator

Neither source contains a `TABLE-US` block, a PPUBS text table, or a numbered `EXAMPLE n` or
`NUMERICAL EMBODIMENT n` heading. The brief drawing section declares FIGS.1-19 with 24 panels:
FIGS.1-11, FIGS.12A/B through 16A/B, and FIGS.17-19. These declarations reconcile exactly to
24 official drawing sheets in each PDF.

FIGS.1-11 disclose cross-sections of meta-structure, functional, protective, and antireflective
layers. FIGS.12A/B through 15A/B disclose layer-stack dimensions and simulated transmittance;
FIGS.16A/B disclose a meta-lens region structure and phase profile. FIGS.17-19 are electronic
device, camera-module, and 3D-sensor block diagrams. Thus the document denominator is one
architecture disclosure per publication, not 24 independent optical prescriptions.

The exact normalized sources contain three generic `focal length` occurrences and one generic
`F number` occurrence each. None is a numeric assignment to a disclosed optical prescription.
Both sources contain zero radius-of-curvature/curvature-radius, Abbe, asphere, surface-number,
optical-data, lens-data, prescription, or numeric focal-length-assignment markers. The layer
dimensions and transmittance simulations are not refractive-surface prescriptions.

## Official-raster reconciliation

Both official PDFs are image-only, contain exactly one decoded grayscale image per page, and have
no text layer. Every page was decoded and hashed in order; all-page contact sheets were inspected.
No hidden surface table or numerical lens prescription appears in the drawings or text-page
rasters.

| Publication | Pages | Drawing pages | Retained PDF SHA-256 | Second live-wrapper SHA-256 | Stable raster-set SHA-256 | Contact SHA-256 |
|---|---:|---|---|---|---|---|
| B2 | 40 | 3-26 | `8e02e932f400e6454844ff94c56e029681355d0aa27f9952250e09d8cd89043e` | `646894ad94953d1a32f64da6771bb5b4e4584d81abc048c75c3a056e7ac1bbe9` | `7cd529ab5b3c8c6a3cd383d77996579c58afa69f4612ab985c0c451395f034a3` | `cca892d58e0402d9426410d4d181a2df449bff24074e2755a1a97abba8e7946c` |
| A1 | 39 | 2-25 | `bcf30001d2ecb0a078bb264bacf895dd1007a36ce437fc41fca9ee86433b7a1f` | `2136be51feca117287359fd5e3b8c4b51aa7a86338a3e471a81cfb6076adfec5` | `11aa2c8afae815e2e809350ca3a964517834017f3cabe4717a75013870fb9172` | `c26539ac094c8e1c98d6a035b30bf8e932557564e2765b16399bd119cd20ba26` |

The two live wrapper byte streams differ per publication, while every decoded page raster is
identical within that publication. Wrapper equality is not claimed. The retained audit JSON and
tests independently rehash both wrappers, every page raster, and both contact sheets.

## Fail-closed outcome

Each exact source produces one
`confirmed_no_prescription.meta_optical_layer_and_device_architecture_only` terminal item. The
result has no conversion worker, request, receipt, prescription fingerprint, candidate, or ZMX.
Raw/normalized source identity, title, owner, family, application/continuation markers, zero-table
and zero-numbered-example denominators, all 24 drawing declarations, architecture phrase counts,
and zero strong prescription markers are fail-closed. Any source, drawing, table, or prescription
marker drift returns the root to parser review instead of preserving the terminal classification.

Attempts 2 and 3 are append-only and byte-distinct only because of `result_attempt`; their
canonical semantic SHA-256 values are
`572d28888de884d810a2e1eae405a72599b74f0c954349efe6f4a843ea51b8ee` (B2) and
`8bfb3798aad5f9919b7de0c88f7093127b7da8a14c245f94c74842cbeb886673` (A1).
