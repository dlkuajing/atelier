# Family 87936009 source audit

## Identity and family boundary

- Frozen root `US-12591118` resolves to grant `US-12591118-B2`, application `18/845222`,
  Family ID `87936009`, owned by Huawei Technologies Co., Ltd. It claims priority to
  `CN202210240794.3` dated 2022-03-10, identifies `PCT/CN2023/080164` /
  `WO-2023169441-A1`, and names prior publication `US-20250199270-A1`.
- The same-application A1 plus CN, WO, EP, and later CN family publications are outside the
  frozen 619-root cohort and are retained in `family-87936009-external-family-members.json`.
  Current replay completeness is not extended to any queued publication.
- Family `85407590` shares the generic layout signature but is a distinct source family. No
  value, table, state, parser outcome, or raster is borrowed between them.

## State, prescription, and metadata denominator

- Exact official B2 HTML SHA-256
  `8f7df2cc433e510cb39cd9a5a9b28912c38683908d0f7b55ec5197715b93fa44` and normalized SHA-256
  `d30d8e3c5633b1de6d37375aa64852f63628cec45f293c5c93db1cc518098fb2` bind the source profile.
- The disclosure has five formal embodiments, FIGS.1-23, and exactly 16 PPUBS tables. TABLES
  2-4, 5-7, 8-10, 11-13, and 14-16 are respectively five surface/asphere/system triples. The
  first three embodiments have seven lenses; the last two have eight.
- Every surface table publishes a first retracted non-working state and a second extended working
  state. Only `CG S2` and the last-lens `S2` thickness differ between the two states. The five
  non-working states have no state-specific system metadata, so they remain five explicit
  `metadata_unpublished.non_working_retracted_state_has_no_system_metadata` terminals.
- Each system table directly publishes total focal length, equivalent focal length, F-number,
  total image height, full field of view, and retraction ratio. The source explicitly defines FOV
  as the included angle between the two maximum-range edges; the parser therefore uses FOV/2 as
  half field and does not reinterpret it.
- The source lists `CG S2, Stop, L1 S1` with `Stop -> L1 S1 = -0.1500 mm`. The exact physical
  order is `CG S2 -> L1 S1 -> Stop -> L1 S2`; the parser splits the published L1 center thickness
  at that coordinate, keeps L1 glass on the zero-power stop plane, rejects non-positive segments,
  and proves the transformed axial sum equals the source sum.

## Malformed source cells and official raster denominator

- TABLE 3 publishes embodiment-1 `L4 S2 A26` as `2.2728-07`, lacking an exponent marker. TABLE
  12 publishes embodiment-4 `L2 S1 A24` as `-5.39SE-06`, with an alphabetic character inside
  the mantissa. Neither token is repaired, interpolated, or borrowed.
- Two independently fetched B2 wrappers each contain 43 image-only pages. Their PDF container
  hashes differ, while all 43 decoded page rasters agree at page-hash-set SHA-256
  `a4ce6342a782adbba8e95f7452dc5f65e964d0cd39cb95ce31062177b0c05ddd`. Pages 3-20 are the 18
  drawing sheets and pages 28-41 contain the prescription tables; the malformed cells are on
  pages 31 and 38.
- Two independently fetched A1 wrappers likewise contain 43 image-only pages and differ at the
  container layer, while every decoded page raster agrees at page-hash-set SHA-256
  `a919cd83454743fb687af5d8f5b5e9c7d43ce17fa9f6b4a4f38372e42bda9248`. Pages 2-19 are the 18
  drawing sheets and pages 27-41 contain the tables; the same malformed cells are on pages 30 and
  38. Both retained all-page contacts and all wrapper/page hashes are covered by
  `family-87936009-raster-audit.json`.

## Replay outcome

- Embodiments 1 and 4 working states remain precise malformed-source metadata terminals.
  Embodiments 2, 3, and 5 parse to exact prescriptions; isolated optical tracing classifies
  embodiments 3 and 5 as `trace_failed` and produces no candidate ZMX for them.
- Embodiment 2 produces staging-only `US-12591118-B2-e4.zmx`, SHA-256
  `8a24f5c8ed0da05ed42457b4caf67e39f94fe7b3b01e220fb8c94fd0b22a9760`. Its receipt records
  only 3/5 finite final rays and real image height `1.0516645549268637 mm`; it remains
  `converted_pending_intake` and carries no production-validity claim.
- Attempts 3/4 are semantic-equal after excluding only permitted retry/result identity, at
  `fbdc95ccdfddadb296c5d4c2eb21fc72d4387d9590da2dfc8d71fd92c5f6fafd`. The frozen root is one
  mixed nonterminal containing one staging conversion and nine terminals; the strict ledger
  remains 619/619 with corrupt=0.
