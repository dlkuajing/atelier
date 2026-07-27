# Family 79728600 source audit

## Bound source and identity

- Frozen root: `US-20230132659`; exact classification publication: `US-20230132659-A1`.
- Retained USPTO source: `data/patent-lake/uspto-ppubs-html/US-PGPUB/f0df7ad3fbe33052/US-20230132659-A1.html`, 57,732 bytes, SHA-256 `f0df7ad3fbe33052eeeb9c1fb09e758a2cb18bf32fa2ba124256bc423c8020eb`.
- Application `17/607400`, Family ID `79728600`, PCT `PCT/IB2021/056357`, provisional `63/054862`, priority 2020-07-22, filed 2021-07-14 and published 2023-05-04.
- Title: *Folded Camera Lens Designs*. Applicant: Corephotonics Ltd. Inventors: Gal Shabtay, Ephraim Goldenberg, Roy Rudnick and Nadav Goulinski.
- The same application's later grant is `US-12050308-B2`; continuation children are `US-12392999-B2` and `US-12571999-B2`.

The exact-source classifier binds the raw document hash, normalized-text hash, identity markers, section hashes, contiguous paragraph and claim denominators, figure declarations, three tagged table-block hashes, 20 surface rows, both 16-row coefficient blocks, high-order nonzero counts and the source's own missing-Table-3 language. Any drift fails closed as three parser-review items rather than preserving stale terminals.

## Complete source denominator

The official HTML contains contiguous paragraphs `[0001]` through `[0138]`: background/summary 1-31, drawing description 32-46, and detailed description 47-138. Claims 1-36 are present. Fourteen panels are declared: FIGS. 1A-1C, 2A-2E, 3A-3B and 4-7.

The official source has three tagged HTML blocks but only two logical tables. `TABLE-US-00001` is Table 1, the 20-row prescription. `TABLE-US-00002` and `TABLE-US-00003` are the two halves of Table 2, not separate logical Tables 2 and 3. Paragraph 76 says that Tables 1-3 describe the prescription, yet neither the A1 nor its same-application B2 contains a logical `TABLE 3` heading.

The 19-page publication PDF contains one cover, ten drawing sheets on pages 2-11 and eight specification pages on pages 12-19. Two official downloads and the exact Google PDF are raster-only, one decoded raster per page, and their rasters agree at every page position (19/19). The full contact sheet and specification pages 13-19 are retained. Visual review of page 15 confirms the Qcon formula and definitions only through Q5; page 16 contains Tables 1 and 2; page 17 contains the directional-aperture variants.

## One base prescription and three unique variants

Table 1 publishes one 20-row base prescription for lens 204: eight plastic elements, sixteen QT1 lens surfaces, stop row 1, filter row 18, air row 19 and image row 20. It reports EFL 4.14 mm, F/1.00, 80.4-degree diagonal FOV, TTL 8.34 mm, BFL 1.08 mm, 7 mm sensor diagonal and 555 nm reference wavelength. Table 2 provides Rnorm and A0-A8 for surfaces 2-17; A4-A6 are nonzero on all 16 lens surfaces, while A7-A8 are nonzero on four each.

1. Paragraphs 58-109 and 126-129 disclose the base lens 204 shared by FIGS. 2A, 2C and 2D. FIGS. 2C and 2D change only the folding prism, so they do not duplicate the lens coordinates.
2. Paragraphs 110-125 and FIG. 2B disclose cut lens 204-prime. It inherits the base prescription but replaces the y-direction aperture radius on every L6/L8 surface and S15 with 2.5 mm, producing a non-circular variant.
3. Paragraphs 130-135 and FIG. 2E disclose cut lens 204-double-prime. It inherits the base prescription but replaces the y-direction aperture radius on every L6/L8 surface plus S11/S15 with 2.45 mm, producing a second non-circular variant.

Paragraphs 47-57 and 136-138 provide known architecture or support text. FIGS. 1A-1C, 3A-3B and 4-7 likewise provide architecture, ray-footprint, cutting and barrel context rather than additional coordinate sets. Every detailed paragraph and figure panel is mapped, and no coordinates are inferred from drawings.

## Source gap and terminal boundary

The exact A1 Google wrapper retains nine MathML objects; the same-application B2 retains eleven. Both formula sequences define only Q0 through Q5. Neither wrapper publishes Q6, Q7 or Q8 definitions even though Table 2 contains nonzero coefficients through A8. Neither publication supplies any per-surface conic-parameter values, and neither supplies the referenced logical Table 3.

The missing values are prescription-critical. This repository does not infer an external Forbes/Qcon convention, assume conic values, reinterpret the tagged continuation as logical Table 3, or borrow coordinates from another publication. The same-application B2 therefore does not repair the A1. All three unique variants are exact-source `metadata_unpublished` terminals with reason `terminal.metadata_unpublished.qcon_q6_q8_surface_conic_and_table3_absent`.

## Replay proof and remaining queue

Replay attempts 2 and 3 are append-only and byte-distinct only because `result_attempt` differs. After excluding that field, both have semantic SHA-256 `353e5864f2329efe054f957dfbe33a9ecb1fae76b4096e13dfae46a7491b2214`. They create no conversion request, receipt, fingerprint or candidate ZMX.

The strict ledger audit reports 619/619 roots and zero missing or corrupt results, with result-set SHA-256 `dbbdf20c8ab4beb1c30abd1aeb8ea6b4752e32ce7f740404fad21f6aa16f834d`. The generic residual census moves from 131 to 130 roots/items and is byte-identical across two after snapshots. The deterministic next group is Family `94050343`, root `US-20260072245`, publication `US-20260072245-A1`.

This closes only the frozen Family 79728600 root. Related publications outside the frozen cohort, all remaining parser buckets, staging intake, macro replay support and global patent/source saturation remain open.
