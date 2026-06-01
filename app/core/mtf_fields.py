"""Shared MTF field-fraction constants and display helpers."""

from __future__ import annotations

import math

# Canonical MTF field fractions (axis, mid, 0.7-zone, full) that lens datasheets
# cite. 4 points keep GeometricMTF fast while covering the field; 0.7 is the
# de-facto "image quality" zone for phone lenses.
MTF_CANONICAL_FIELD_FRACS: tuple[float, ...] = (0.0, 0.5, 0.7, 1.0)

# Fallback field sets are tried widest-first. Wide phone-camera seeds can have
# unstable 1.0-field edge rays while still producing finite evidence between
# the 0.7 zone and full field.
MTF_FIELD_FALLBACK_SETS: tuple[tuple[float, ...], ...] = (
    (0.0, 0.5, 0.7, 1.0),
    (0.0, 0.5, 0.7, 0.9),
    (0.0, 0.5, 0.7, 0.85),
    (0.0, 0.5, 0.7, 0.8),
    (0.0, 0.5, 0.7, 0.75),
    (0.0, 0.5, 0.7),
    (0.0, 0.5),
)


def format_mtf_field_fraction(value: float | None) -> str:
    """Stable display for MTF field fractions, preserving values like 0.75."""
    if value is None:
        return "unknown"
    if math.isclose(value, round(value, 1), abs_tol=1e-9):
        return f"{value:.1f}"
    return f"{value:.2f}".rstrip("0").rstrip(".")
