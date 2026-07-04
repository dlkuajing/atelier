"""Web wizard flow contract tests."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _mock_chat_response(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


def test_homepage_form_posts_to_wizard_confirmation():
    response = client.get("/")

    assert response.status_code == 200
    assert 'class="requirement-form"' in response.text
    assert 'action="/wizard/confirm"' in response.text
    assert 'method="post"' in response.text


@patch("app.api.wizard.get_async_client")
def test_wizard_form_submission_renders_scenario_parameters_and_clamped_bounds(
    mock_get_client,
):
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "scenario": "smartphone-telephoto",
              "focal_length_mm": 99,
              "f_number": 1.2,
              "field_of_view_deg": 90,
              "image_height_mm": 1,
              "n_elements": 20,
              "reasoning": "Phone telephoto request with aggressive targets."
            }
            """
        )
    )
    mock_get_client.return_value = mock_client

    requirement = "Design a phone telephoto module, around 99mm, very fast aperture."
    response = client.post("/wizard/confirm", data={"requirement": requirement})

    assert response.status_code == 200, response.text
    html = response.text
    assert "Wizard Scenario Confirmation" in html
    assert 'data-scenario="smartphone-telephoto"' in html
    assert "Smartphone Telephoto" in html
    assert requirement in html
    assert "Phone telephoto request with aggressive targets." in html

    assert 'data-field="focal_length_mm"' in html
    assert "18.0 mm" in html
    assert "5.0-18.0 mm" in html
    assert "f/1.8" in html
    assert "f/1.8-f/4.0" in html
    assert "45.0 deg" in html
    assert "15.0-45.0 deg" in html
    assert "2.5 mm" in html
    assert "2.5-8.0 mm" in html
    assert ">9<" in html
    assert ">5-9<" in html

    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == requirement
