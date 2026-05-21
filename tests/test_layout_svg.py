"""Tests for app.core.layout_svg — Optiland draw() → SVG string."""

import pytest

from app.core.layout_svg import render_layout_svg
from app.core.lens_system import LayoutSVG, Scenario
from app.core.optical_engine import build_optic_for_scenario


@pytest.fixture
def smartphone_tele_optic():
    return build_optic_for_scenario(
        Scenario.SMARTPHONE_TELEPHOTO, target_efl_mm=7.0, target_f_number=2.4
    )


def test_render_returns_layout_svg(smartphone_tele_optic):
    svg = render_layout_svg(smartphone_tele_optic)
    assert isinstance(svg, LayoutSVG)


def test_svg_content_starts_with_xml_or_svg_tag(smartphone_tele_optic):
    svg = render_layout_svg(smartphone_tele_optic)
    # matplotlib emits a `<?xml ... ?>` prologue then an `<svg>` root.
    head = svg.svg_content.lstrip()[:200]
    assert head.startswith("<?xml") or head.startswith("<svg")


def test_svg_contains_svg_root_element(smartphone_tele_optic):
    svg = render_layout_svg(smartphone_tele_optic)
    assert "<svg" in svg.svg_content
    assert "</svg>" in svg.svg_content


def test_svg_dimensions_default(smartphone_tele_optic):
    svg = render_layout_svg(smartphone_tele_optic)
    assert svg.width_px == 1200
    assert svg.height_px == 600


def test_svg_custom_dimensions(smartphone_tele_optic):
    svg = render_layout_svg(smartphone_tele_optic, width_px=800, height_px=400)
    assert svg.width_px == 800
    assert svg.height_px == 400


def test_svg_zero_or_negative_dimension_raises(smartphone_tele_optic):
    with pytest.raises(ValueError):
        render_layout_svg(smartphone_tele_optic, width_px=0)
    with pytest.raises(ValueError):
        render_layout_svg(smartphone_tele_optic, height_px=-1)


def test_svg_has_non_trivial_content(smartphone_tele_optic):
    """A real optical layout should produce more than just an empty SVG shell."""
    svg = render_layout_svg(smartphone_tele_optic)
    # Empty SVGs are ~200 bytes; a real lens layout produces 10KB+.
    assert len(svg.svg_content) > 5000
