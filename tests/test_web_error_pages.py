"""Web error page contract tests."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _assert_web_error_page(response, status_code: int) -> None:
    assert response.status_code == status_code
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert 'data-error-page' in html
    assert f'data-status-code="{status_code}"' in html
    assert "Atelier" in html
    assert 'href="/"' in html
    assert "Return home" in html
    assert "返回首页" in html


def test_invalid_result_job_renders_branded_404_page():
    response = client.get("/results/not-a-job")

    _assert_web_error_page(response, 404)
    assert "design result" in response.text
    assert "没有找到" in response.text
    assert "not-a-job" in response.text


def test_wizard_form_validation_renders_branded_422_page():
    response = client.post("/wizard/confirm", data={"requirement": "x"})

    _assert_web_error_page(response, 422)
    assert "Check the form" in response.text
    assert "表单" in response.text
    assert "requirement" in response.text


def test_web_500_renders_branded_error_page():
    async def broken_page() -> None:
        raise RuntimeError("forced test error")

    original_route_count = len(app.router.routes)
    app.add_api_route("/__test_web_error_page", broken_page, include_in_schema=False)
    try:
        with TestClient(app, raise_server_exceptions=False) as local_client:
            response = local_client.get("/__test_web_error_page")
    finally:
        del app.router.routes[original_route_count:]

    _assert_web_error_page(response, 500)
    assert "Something went wrong" in response.text
    assert "内部错误" in response.text


def test_api_job_404_keeps_structured_json():
    response = client.get("/api/optical/jobs/missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == {"error": "job_not_found", "job_id": "missing"}
    assert 'data-error-page' not in response.text


def test_api_validation_422_keeps_structured_json():
    response = client.post("/api/wizard/executive-summary", json={})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    assert isinstance(response.json()["detail"], list)
    assert 'data-error-page' not in response.text
