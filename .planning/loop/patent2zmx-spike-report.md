# DATA-06a patent-to-ZMX spike report

- target_successes: 6
- attempts: 41
- successes: 6
- source: local data/patents/uspto-smartphone-batch*.jsonl + USPTO PPUBS HTML
- parser: deterministic first-embodiment table parse; no numeric LLM fill
- clear_aperture: derived from parsed f/Fno/HFOV only for ZMX DIAM/MEMA metadata

## Per-patent attempts

| patent | status | zmx | efl_mm | field coverage | reason |
|---|---|---|---:|---|---|
| US-20260160977-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12650578-B2 | success | data\zmx-staging\US-12650578-B2.zmx | 1.91231 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=1.91; f_number=2.15; hfov_deg=59.0 | parsed and ingested |
| US-20260133409-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12591115-B2 | failed |  |  |  | PatentParseError: unsupported nonzero high-order asphere terms: S2:A18=-81.7, S3:A18=840, S6:A18=8.49, S3:A20=-1.04e+03, S8:A18=61.3, S9:A18=-33, S10:A18=-14.9, S11:A18=8.27 |
| US-20260036790-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12493167-B2 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250370230-A1 | failed |  |  |  | PatentParseError: surface table index break: expected 9, found 6 |
| US-20250370222-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12468127-B2 | success | data\zmx-staging\US-12468127-B2.zmx | 1.28996 | surfaces=18; r=18/18; d=18/18; nd_vd=9/18; asphere_surfaces=12; f_mm=1.29; f_number=1.82; hfov_deg=83.4 | parsed and ingested |
| US-20250341704-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250334774-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12416791-B2 | failed |  |  |  | PatentParseError: surface table index break: expected 9, found 6 |
| US-12638660-B2 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20260140289-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20260126622-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12607827-B2 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12578554-B2 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20260063872-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12546974-B2 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12535657-B2 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12523851-B2 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250377520-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12481124-B2 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12474546-B2 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12461337-B2 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12461279-B2 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12461346-B2 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250334721-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250314863-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250291157-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20260009981-A1 | failed |  |  |  | PatentParseError: surface 13 radius is not numeric: Prism |
| US-20260003159-A1 | failed |  |  |  | PatentParseError: surface table did not start with surface 0 Object |
| US-20250383531-A1 | success | data\zmx-staging\US-20250383531-A1.zmx | 1.32097 | surfaces=20; r=20/20; d=20/20; nd_vd=9/20; asphere_surfaces=16; f_mm=1.32; f_number=1.8; hfov_deg=60.0 | parsed and ingested |
| US-12449639-B2 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-12443014-B2 | failed |  |  |  | PatentParseError: surface 13 radius is not numeric: Prism |
| US-12429675-B2 | success | data\zmx-staging\US-12429675-B2.zmx | 1.32097 | surfaces=20; r=20/20; d=20/20; nd_vd=9/20; asphere_surfaces=16; f_mm=1.32; f_number=1.8; hfov_deg=60.0 | parsed and ingested |
| US-12429670-B2 | failed |  |  |  | PatentParseError: surface table did not start with surface 0 Object |
| US-12422650-B2 | failed |  |  |  | PatentParseError: surface 4 radius is not numeric: Prism |
| US-20250231379-A1 | failed |  |  |  | PatentParseError: first embodiment f/Fno/HFOV line not found |
| US-20250216655-A1 | success | data\zmx-staging\US-20250216655-A1.zmx | 4.0153 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=4.01; f_number=2.0; hfov_deg=44.3 | parsed and ingested |
| US-20250189767-A1 | success | data\zmx-staging\US-20250189767-A1.zmx | 3.88992 | surfaces=18; r=18/18; d=18/18; nd_vd=8/18; asphere_surfaces=14; f_mm=3.89; f_number=1.6; hfov_deg=35.8 | parsed and ingested |
