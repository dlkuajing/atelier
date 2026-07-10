"""Serializable prescription table for loaded optical systems."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from app.core.zmx_ingest import load_normalized_zmx
from app.core.zmx_materials import _CODEV_MODEL_GLASS_MARKER_RE


class PrescriptionSurface(BaseModel):
    """One row in a lens prescription table."""

    index: int = Field(..., ge=0)
    surface_type: str
    z_mm: float | None = Field(None, description="Axial surface position; None for infinity")
    radius_mm: float | None = Field(None, description="Radius of curvature; None for plane")
    thickness_mm: float | None = Field(None, description="Distance to next surface; None for infinity")
    glass: str | None = Field(None, description="Material after this surface")
    refractive_index_d: float | None = Field(
        None,
        description="Material refractive index at the d-line after zmx_ingest normalization",
    )
    abbe_number: float | None = Field(
        None,
        description="Material Abbe number after zmx_ingest normalization",
    )
    conic: float = 0.0
    asphere_coefficients: list[float] = Field(default_factory=list)
    is_stop: bool = False
    is_object: bool = False
    is_image: bool = False


class PrescriptionTable(BaseModel):
    """Complete serializable lens prescription table."""

    source_zmx: str | None = None
    surface_count: int = Field(..., ge=0)
    stop_surface_index: int = Field(..., ge=0)
    surfaces: list[PrescriptionSurface]


def _safe_float(value) -> float:
    arr = np.asarray(value, dtype=float).flatten()
    if arr.size == 0:
        raise ValueError("empty numeric value")
    return float(arr[0])


def _finite_or_none(value) -> float | None:
    try:
        out = _safe_float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _read_zmx_text(path: Path) -> str:
    for encoding in ("utf-16", "utf-16-le", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except (OSError, UnicodeError):
            continue
    return path.read_text(errors="ignore")


def _zmx_glass_names_by_surface(path: Path) -> dict[int, str]:
    """Read raw GLAS names because Optiland material objects keep only nd/vd."""
    names: dict[int, str] = {}
    current_surface: int | None = None
    for raw_line in _read_zmx_text(path).splitlines():
        line = raw_line.strip()
        if line.startswith("SURF "):
            parts = line.split()
            try:
                current_surface = int(parts[1])
            except (IndexError, ValueError):
                current_surface = None
            continue
        if current_surface is None or not line.startswith("GLAS "):
            continue
        parts = line.split()
        if len(parts) >= 2:
            # Strip the CODE V model-glass marker appended by
            # scripts/repair_legacy_zmx_glass.py (keeps the display name equal
            # to the real trade name, e.g. APL5014CL_14_BLANK -> APL5014CL_14).
            # One authoritative marker rule: the shared regex's lookbehind
            # already preserves the plain Zemax "___BLANK" placeholder.
            names[current_surface] = _CODEV_MODEL_GLASS_MARKER_RE.sub(
                "", parts[1].strip('"')
            )
    return names


def _material_scalar(material: dict, key: str) -> float | None:
    if key not in material:
        return None
    return _finite_or_none(material[key])


def _glass_label(material: dict, explicit_name: str | None) -> str | None:
    if explicit_name:
        return explicit_name

    material_type = str(material.get("type", "")).strip()
    index = _material_scalar(material, "index")
    abbe = _material_scalar(material, "abbe")
    if material_type == "IdealMaterial" or (index is not None and math.isclose(index, 1.0)):
        return "air"
    if index is not None and abbe is not None:
        return f"{material_type}(nd={index:g},vd={abbe:g})"
    if index is not None:
        return f"{material_type}(n={index:g})"
    return material_type or None


def _surface_type(surface, surface_dict: dict, geometry: dict) -> str:
    surface_type = getattr(surface, "surface_type", None)
    if surface_type:
        return str(surface_type)
    geometry_type = geometry.get("type")
    if geometry_type:
        return str(geometry_type)
    return str(surface_dict.get("type", "surface"))


def extract_prescription_table(
    optic,
    *,
    source_zmx: str | Path | None = None,
) -> PrescriptionTable:
    """Serialize the full prescription from a zmx_ingest-loaded Optic.

    Numeric fields come from the normalized Optiland object produced by
    ``load_normalized_zmx``. When ``source_zmx`` is supplied, raw GLAS labels are
    added because Optiland's material objects preserve nd/vd but not the source
    material name.
    """
    source_path = Path(source_zmx) if source_zmx is not None else None
    glass_names = _zmx_glass_names_by_surface(source_path) if source_path is not None else {}

    positions = np.asarray(optic.surfaces.positions).flatten()
    raw_surfaces = list(optic.surfaces.surfaces)
    surface_count = len(raw_surfaces)
    stop_surface_index = int(optic.surfaces.stop_index)

    rows: list[PrescriptionSurface] = []
    for index, surface in enumerate(raw_surfaces):
        surface_dict = surface.to_dict()
        geometry = surface_dict.get("geometry") or {}
        material = surface_dict.get("material_post") or {}
        coefficients = geometry.get("coefficients") or []

        rows.append(
            PrescriptionSurface(
                index=index,
                surface_type=_surface_type(surface, surface_dict, geometry),
                z_mm=_finite_or_none(positions[index]) if index < positions.size else None,
                radius_mm=_finite_or_none(geometry.get("radius")),
                thickness_mm=_finite_or_none(surface_dict.get("thickness")),
                glass=_glass_label(material, glass_names.get(index)),
                refractive_index_d=_material_scalar(material, "index"),
                abbe_number=_material_scalar(material, "abbe"),
                conic=_finite_or_none(geometry.get("conic")) or 0.0,
                asphere_coefficients=[_safe_float(value) for value in coefficients],
                is_stop=bool(surface_dict.get("is_stop", index == stop_surface_index)),
                is_object=index == 0,
                is_image=index == surface_count - 1,
            )
        )

    return PrescriptionTable(
        source_zmx=source_path.name if source_path is not None else None,
        surface_count=surface_count,
        stop_surface_index=stop_surface_index,
        surfaces=rows,
    )


def load_prescription_table(path: str | Path) -> PrescriptionTable:
    """Load a ZMX file via zmx_ingest and return its prescription table."""
    zmx_path = Path(path)
    optic = load_normalized_zmx(zmx_path)
    return extract_prescription_table(optic, source_zmx=zmx_path)
