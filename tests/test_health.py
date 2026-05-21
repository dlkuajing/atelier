"""Health endpoint smoke tests + deterministic optical calc unit tests."""

import math

import pytest
from fastapi.testclient import TestClient

from app.core.optical_calc import (
    airy_disk_diameter_um,
    angular_field_of_view_deg,
    depth_of_field_mm,
    image_height_mm,
    thin_lens_image_distance,
)
from app.main import app


client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0.1.0"}


def test_root_responds():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["service"] == "lumira-atelier-backend"


def test_thin_lens_image_distance_at_2f_returns_2f():
    """Object at 2f → image at 2f (1:1 magnification)."""
    f = 50.0
    s_prime = thin_lens_image_distance(2 * f, f)
    assert math.isclose(s_prime, 2 * f, rel_tol=1e-6)


def test_thin_lens_image_distance_at_focal_point_raises():
    with pytest.raises(ValueError, match="image at infinity"):
        thin_lens_image_distance(50.0, 50.0)


def test_thin_lens_negative_inputs_raise():
    with pytest.raises(ValueError):
        thin_lens_image_distance(-1.0, 50.0)
    with pytest.raises(ValueError):
        thin_lens_image_distance(50.0, -1.0)


def test_angular_fov_50mm_fullframe():
    """50mm lens on full-frame (43.27mm diagonal) → ~46.79° diagonal FOV."""
    fov = angular_field_of_view_deg(50.0, 43.266615)
    assert math.isclose(fov, 46.79, abs_tol=0.05)


def test_image_height_zero_at_optical_axis():
    assert math.isclose(image_height_mm(50.0, 0.0), 0.0, abs_tol=1e-9)


def test_image_height_increases_with_angle():
    h1 = image_height_mm(50.0, 10.0)
    h2 = image_height_mm(50.0, 20.0)
    assert h2 > h1


def test_airy_disk_550nm_f4():
    """Airy disk at 550nm, f/4 → ~5.37 μm."""
    d = airy_disk_diameter_um(550.0, 4.0)
    assert math.isclose(d, 5.368, abs_tol=0.01)


def test_dof_at_hyperfocal_extends_to_infinity():
    """At hyperfocal distance, far limit is infinity."""
    f = 50.0
    N = 4.0
    c = 0.030  # mm
    H = f**2 / (N * c) + f
    near, far = depth_of_field_mm(f, N, H, c)
    assert far == float("inf")
    assert near < H


def test_dof_returns_positive_near_limit():
    near, far = depth_of_field_mm(50.0, 4.0, 3000.0, 0.030)
    assert near > 0
    assert far > near
