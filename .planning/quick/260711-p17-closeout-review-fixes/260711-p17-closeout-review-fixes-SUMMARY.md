# Summary

Completed all P17 close-out findings. Repeat samples now read the primary config from every
run, record flips/drops, and expose all successful run artifact paths. Repeatability labels the
CODE V cropped-pupil aperture. The offline CLI persists artifacts beside its output by default,
and its repeat contract is current. Added preferred-flip, first-run-failure, and web POST
penetration regressions.

Verification: 110 targeted tests passed; `uv run ruff check .` passed.
