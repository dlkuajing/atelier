# Family 63585563 source audit

## Identity and relationship

- `US-11435552-B2` and `US-20200041761-A1` share Family ID `63585563`, application
  `16/485921`, title `OPTICAL LENS ASSEMBLY AND ELECTRONIC DEVICE COMPRISING SAME`, and
  Samsung Electronics ownership. The B2 record's Prior Publication Data explicitly names
  `US 20200041761 A1` dated February 6, 2020.
- Retained official HTML SHA-256 values are
  `fc7ffce9d6d1ba6245b1cee259c8e63a022c92314840324273e1022f96b73089` (B2) and
  `41a8a3a3a2183a9129cdde921874fc090aa2471a6af657a2f29195e47ceb2d38` (A1).
  Parser-normalized text hashes are
  `be2f3764ff09939c08c1f23718d4b4aa1855ea70384b6c71ac742dc98121edd0` and
  `182146469a92e0140562a94e9d85025d8036ca44d40a0918affc4d1a69c10e05`.
  All 11 ordered table blocks are independently digest-bound per publication in the exact profile.

## Source denominator and item mapping

Each publication declares three numerical embodiments, 18 figures, and 11 tables. Every
numerical embodiment has two independent operating states: visible-light imaging with the moving
group deviated from the optical axis, and infrared imaging with that group inserted. Therefore the
ledger denominator is six state items, not three undifferentiated embodiments:

| Ledger item | Numerical embodiment | State | Source tables |
|---:|---:|---|---|
| 1 | 1 | visible | 1 / 3 / 11 |
| 2 | 1 | IR | 2 / 3 / 11 |
| 3 | 2 | visible | 4 / 6 / 11 |
| 4 | 2 | IR | 5 / 6 / 7 / 11 |
| 5 | 3 | visible | 8 / 10 / 11 |
| 6 | 3 | IR | 9 / 10 / 11 |

TABLE 11 publishes `F, f1, f2, f3, f4, f5, HALF FIELD OF VIEW, OAL, Fnumber,
T34, V3-V2, f2/f, T34/OAL, fIR`. Its three exact rows are:

| Embodiment | F | f1 | f2 | f3 | f4 | f5 | HFOV | OAL | Fnumber | T34 | V3-V2 | f2/f | T34/OAL | fIR |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3.75 | 2.6 | -5.5 | 29.5 | -11.1 | 457.3 | 37 | 4.51 | 2.08 | 0.696 | 35.7 | -1.47 | 0.154 | 49.6 |
| 2 | 3.69 | 2.8 | -5.3 | 12.8 | -10.4 | 1013.6 | 37 | 4.46 | 2.05 | 0.69 | 35.7 | -1.44 | 0.154 | 48.9 |
| 3 | 3.82 | 2.6 | -4.9 | 48.5 | -13.0 | 767.7 | 36 | 4.46 | 2.06 | 0.635 | 35.7 | -1.28 | 0.142 | 39 |

The first narrative directly publishes `f=3.75`, `Fnumber=2.08`, and half field `36.7`; rounding
the narrative field to the integer TABLE 11 field is source-compatible. The second narrative
publishes `f=3.7`, `Fnumber=2.05`, and half field `37`, compatible with the table's displayed
precision. The third narrative instead publishes `f=3.79`, `Fnumber=2.05`, and half field `36.5`,
which conflicts with TABLE 11's `3.82`, `2.06`, and `36`.

## Official-raster reconciliation

Both official PDFs have 34 image-only pages and no text layer. B2 drawing pages are 3-20 and table
pages are 25-28; A1 drawing pages are 2-19 and table pages are 24-27. The 18 drawing sheets map
one-to-one to declared FIGS.1-18. All-page contact sheets were visually inspected.

| Publication | Retained PDF SHA-256 | Second live-wrapper SHA-256 | Stable raster-set SHA-256 | Contact SHA-256 |
|---|---|---|---|---|
| B2 | `8e6b6b7e578d64ceb7aefcf996f26aff175d648be43f7556e1c00374fbbb06cc` | `9a373cae577669866cba3152786ad6022c2ddc2c1be17f6b02865bfc3f0824cc` | `7233dd1327c6a0e481040b89b9186cec3c18338d8670e5516b228e1c9eb6e869` | `f46515ec46d8fff2f30065e4b45a30f9b969ce25a730292d6dad77a25e8ad3ec` |
| A1 | `1ce579191890e9f3728cc2a0856d643c77814b26ec548892e2c64c579cc20c37` | `4a503fdb5267b83cff132f7c0d81066687962053dcf076e7f6b2473f81fc0aa6` | `17addc97711b083f9866ebec90f5890033e139bc7e876bbd8f7eeaea6c6a46c2` | `50c5868bf5e3859323bfa2aed527cba678daf994d74472e4261ab283a813e9e2` |

Live wrapper bytes differ, while all 34 decoded page rasters are identical within each
publication. Wrapper equality is not claimed. The raster evidence confirms that the following are
source defects, not HTML extraction errors:

- TABLES 6 and 10 label asphere columns `1..10`, despite surface TABLES 4 and 9 placing `ST`
  between source surfaces 4 and 6. The labels therefore include a nonexistent/stop surface 5 and
  omit source surface 11; shifting them would be an unauthorized repair.
- TABLE 7 prints coefficient-row labels `K,A,B,C,D,E,F,G,H,K`, including the duplicate final `K`.
- TABLE 8 prints the radius token `1.530f377`; it is nonnumeric in the official raster itself.

## Fail-closed outcome

The first visible state is an unambiguous 14-surface prescription with direct `f=3.75`,
`Fnumber=2.08`, `HFOV=36.7`, reference wavelength 0.5876 um, ten asphere surfaces, and fingerprint
`2f0f22ea16129b08`. The first IR state is an unambiguous 17-surface prescription using the same
direct system values, explicit 0.82 um reference wavelength, ten asphere surfaces, and fingerprint
`60e6e642c0aa3840`. No wavelength substitution is made.

The remaining four states stay `parser_review_required` with a separate exact source-conflict
message for each state. No surface renumbering, token correction, table-column shift, metadata
choice, interpolation, or numeric derivation is performed. Correcting any pinned defect changes
the exact conflict signature and reopens parsing rather than silently preserving the rejection.

The conversion worker classifies the first visible state as `trace_timeout` after its 60-second
hard boundary. It classifies the 0.82 um IR state as `trace_failed` because the model reports the
reference wavelength outside its range. Both outcomes retain process receipts and stable request
identities; no candidate ZMX is published.
