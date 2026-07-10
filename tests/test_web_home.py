"""Homepage rendering contract tests."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_homepage_renders_html_shell():
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<title>Atelier Optical Design Agent</title>" in response.text
    assert "site.css" in response.text
    assert 'aria-label="Primary navigation"' in response.text
    assert '<form class="requirement-form"' in response.text
    assert 'name="requirement"' in response.text
    assert "Natural language requirement" in response.text


def test_static_stylesheet_is_served():
    response = client.get("/static/site.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert ".requirement-form" in response.text
