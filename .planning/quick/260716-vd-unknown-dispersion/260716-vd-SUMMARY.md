# Summary: unknown dispersion must not be fabricated as vd=50

`resolve_material` used to turn "unknown glass, usable placeholder index, dispersion
unspecified (vd 0/None)" into `AbbeMaterial(nd, 50.0)` — a fabricated Abbe number with no
provenance marker. The branch was effectively dead in production: the only caller of
`resolve_material` anywhere in the repo is a test, and real ZMX ingest resolves glass
through `optiland_patches._patched_read_glass` -> `lookup_nd_vd` (returns None for
unknowns, never fabricates). This change hardens the dead branch fail-closed so any
future caller cannot inherit the fabrication: unknown dispersion now raises a clear
ValueError, matching the honest vd->None provenance convention in
`engines/codev_readout.py`. Fully usable placeholders (real nd AND vd) and datasheet-table
materials resolve exactly as before; the warned conservative default for unusable
placeholder indices is unchanged.

Offline gates pass: tests/test_zmx_ingest.py 11/11, ruff clean, blast-radius sweep
(`-k "zmx or material or ingest" -m "not real_machine"`) 587 passed. No new evidence is
created and no north-star gate changes; this is provenance hardening only.
