"""Tests for app.core.lens_system pydantic models."""

import pytest
from pydantic import ValidationError

from app.core.lens_system import (
    LensAssembly,
    LensElement,
    LensSurface,
    Scenario,
    SurfaceType,
)


def _make_surface(idx: int, radius: float, thickness: float, is_stop: bool = False) -> LensSurface:
    return LensSurface(
        surface_index=idx,
        surface_type=SurfaceType.SPHERICAL,
        radius_mm=radius,
        thickness_mm=thickness,
        semi_diameter_mm=2.0,
        is_stop=is_stop,
    )


def _make_element(elem_idx: int, surf_start: int, glass: str = "N-BK7") -> LensElement:
    return LensElement(
        element_index=elem_idx,
        front_surface=_make_surface(surf_start, radius=10.0, thickness=1.5),
        back_surface=_make_surface(surf_start + 1, radius=-20.0, thickness=0.5),
        glass_name=glass,
    )


def _minimal_assembly(scenario: Scenario = Scenario.SMARTPHONE_TELEPHOTO) -> LensAssembly:
    return LensAssembly(
        scenario=scenario,
        name="test 7mm f/2.4",
        effective_focal_length_mm=7.0,
        f_number=2.4,
        field_of_view_deg=30.0,
        image_height_mm=3.7,
        wavelength_nm=550.0,
        elements=[
            _make_element(0, 0),
            _make_element(1, 2),
            _make_element(2, 4),
        ],
        aperture_stop_surface_index=2,
    )


def test_minimal_assembly_validates():
    a = _minimal_assembly()
    assert a.n_elements == 3
    assert a.n_surfaces == 6


def test_aperture_diameter_derived_from_efl_and_fnumber():
    a = _minimal_assembly()
    expected = 7.0 / 2.4
    assert abs(a.aperture_diameter_mm - expected) < 1e-9


def test_f_number_below_1_rejected():
    with pytest.raises(ValidationError):
        LensAssembly(
            scenario=Scenario.SMARTPHONE_TELEPHOTO,
            name="impossible",
            effective_focal_length_mm=7.0,
            f_number=0.5,  # below 1.0 physically impossible
            field_of_view_deg=30.0,
            image_height_mm=3.7,
            elements=[_make_element(0, 0)],
            aperture_stop_surface_index=0,
        )


def test_non_contiguous_element_indices_rejected():
    with pytest.raises(ValidationError):
        LensAssembly(
            scenario=Scenario.SMARTPHONE_TELEPHOTO,
            name="gappy",
            effective_focal_length_mm=7.0,
            f_number=2.4,
            field_of_view_deg=30.0,
            image_height_mm=3.7,
            elements=[
                _make_element(0, 0),
                _make_element(2, 2),  # skipped index 1
            ],
            aperture_stop_surface_index=0,
        )


def test_non_contiguous_surface_indices_rejected():
    with pytest.raises(ValidationError):
        LensAssembly(
            scenario=Scenario.SMARTPHONE_TELEPHOTO,
            name="gappy surfaces",
            effective_focal_length_mm=7.0,
            f_number=2.4,
            field_of_view_deg=30.0,
            image_height_mm=3.7,
            elements=[
                _make_element(0, 0),
                _make_element(1, 5),  # surfaces should start at 2, not 5
            ],
            aperture_stop_surface_index=0,
        )


def test_aperture_stop_out_of_range_rejected():
    with pytest.raises(ValidationError):
        LensAssembly(
            scenario=Scenario.SMARTPHONE_TELEPHOTO,
            name="bad stop",
            effective_focal_length_mm=7.0,
            f_number=2.4,
            field_of_view_deg=30.0,
            image_height_mm=3.7,
            elements=[_make_element(0, 0)],
            aperture_stop_surface_index=100,  # only surfaces 0 and 1 exist
        )


def test_element_back_surface_must_follow_front():
    with pytest.raises(ValidationError):
        LensElement(
            element_index=0,
            front_surface=_make_surface(0, 10.0, 1.5),
            back_surface=_make_surface(5, -20.0, 0.5),  # 5 != 0+1
            glass_name="N-BK7",
        )


def test_json_roundtrip():
    a = _minimal_assembly()
    json_str = a.model_dump_json()
    a2 = LensAssembly.model_validate_json(json_str)
    assert a == a2
