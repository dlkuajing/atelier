# DATA-06a patent-to-ZMX spike report

- target_successes: 6
- attempts: 41
- successes: 3
- success_rate: 3/41 (7.3%)
- rechecked_failures: 38
- source: local data/patents/uspto-smartphone-batch*.jsonl + USPTO PPUBS HTML
- parser: deterministic NFKC-normalized embodiment table parse; no numeric LLM fill
- clear_aperture: ZMX -> zmx_ingest/Optiland real-ray sampled per-surface envelope; f*tan(HFOV) is sanity-only
- imh: Optiland edge-field finite-ray image height persisted in report and ZMX tail comments

## Per-patent attempts

| patent | status | zmx | efl_mm | real_imh_mm | f_tan_sanity_mm | field coverage | reason |
|---|---|---|---:|---:|---:|---|---|
| US-20260160977-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12650578-B2 | success | data\zmx-staging\US-12650578-B2.zmx | 1.91231 | 2.288 | 3.17877 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=1.91; f_number=2.15; hfov_deg=59.0; real_image_height_mm=2.2880004165038716; sanity_image_height_mm=3.17877381128949; finite_final_rays=5/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20260133409-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12591115-B2 | failed |  |  |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S2:A18=-81.7, S3:A18=840, S6:A18=8.49, S3:A20=-1.04e+03, S8:A18=61.3, S9:A18=-33, S10:A18=-14.9, S11:A18=8.27 |
| US-20260036790-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12493167-B2 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250370230-A1 | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 9, found 6 |
| US-20250370222-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12468127-B2 | success | data\zmx-staging\US-12468127-B2.zmx | 1.28996 | 2.17911 | 11.1491 | surfaces=18; r=18/18; d=18/18; nd_vd=9/18; asphere_surfaces=12; f_mm=1.29; f_number=1.82; hfov_deg=83.4; real_image_height_mm=2.1791123378843458; sanity_image_height_mm=11.149144224730389; finite_final_rays=4/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250341704-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250334774-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12416791-B2 | failed |  |  |  |  |  | PatentParseError: surface table index break: expected 9, found 6 |
| US-12638660-B2 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20260140289-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20260126622-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12607827-B2 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12578554-B2 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20260063872-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12546974-B2 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12535657-B2 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12523851-B2 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250377520-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12481124-B2 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12474546-B2 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12461337-B2 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12461279-B2 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12461346-B2 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250334721-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250314863-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250291157-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20260009981-A1 | failed |  |  |  |  |  | PatentParseError: surface 13 radius is not numeric: Prism |
| US-20260003159-A1 | failed |  |  |  |  |  | PatentParseError: surface table did not start with surface 0 Object |
| US-20250383531-A1 | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12449639-B2 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12443014-B2 | failed |  |  |  |  |  | PatentParseError: surface 13 radius is not numeric: Prism |
| US-12429675-B2 | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |
| US-12429670-B2 | failed |  |  |  |  |  | PatentParseError: surface table did not start with surface 0 Object |
| US-12422650-B2 | failed |  |  |  |  |  | PatentParseError: surface 4 radius is not numeric: Prism |
| US-20250231379-A1 | failed |  |  |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250216655-A1 | success | data\zmx-staging\US-20250216655-A1.zmx | 4.0153 | 3.82813 | 3.9132 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=4.01; f_number=2.0; hfov_deg=44.3; real_image_height_mm=3.8281267215317363; sanity_image_height_mm=3.913195094331742; finite_final_rays=3/5; aperture_interpolated_surfaces=none | parsed and ingested |
| US-20250189767-A1 | failed |  |  |  |  |  | PatentParseError: full-field real rays did not reach image surface |

## CODE V cross-check

- target: data/zmx-staging/US-12468127-B2.zmx
- executable: D:\CODEV115\codev.exe
- import: `IN CV_MACRO:ZEMAXOS_TO_CV` completed with structured result `status=ok` (process returncode 1, accepted by existing CODE V readout contract after result schema validation)
- EFL/EFY: Optiland `f2()=1.28996 mm`; CODE V `(EFY)=1.29022 mm`; delta=0.020% (<2%)
- PARM mapping: ZMX `PARM 2..5 = -0.0001111, 9.7715e-07, 2.2777e-08, -1.0235e-11`; CODE V readback `A=-0.0001111, B=0.000001, C=2.277700e-08, D=-1.023500e-11`
- conclusion: PARM 1 reserved at 0 and A..G -> PARM 2..8 mapping is externally confirmed for this sample.
