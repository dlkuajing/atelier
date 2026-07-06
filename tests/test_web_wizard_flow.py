"""Web wizard flow contract tests."""

from html.parser import HTMLParser
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _mock_chat_response(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


class _HiddenInputParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_summary_form = False
        self.action: str | None = None
        self.method: str | None = None
        self.button_types: list[str] = []
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: value or "" for name, value in attrs}
        if tag == "form" and attr.get("data-confirmation-form") == "result-summary":
            self.in_summary_form = True
            self.action = attr.get("action")
            self.method = attr.get("method")
            return

        if not self.in_summary_form:
            return

        if tag == "input" and attr.get("type") == "hidden":
            self.fields[attr["name"]] = attr.get("value", "")
        if tag == "button":
            self.button_types.append(attr.get("type", "submit"))

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self.in_summary_form:
            self.in_summary_form = False


def _hidden_summary_fields(html: str) -> _HiddenInputParser:
    parser = _HiddenInputParser()
    parser.feed(html)
    assert parser.action == "/jobs"
    assert parser.method == "post"
    assert "submit" in parser.button_types
    return parser


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

    form = _hidden_summary_fields(html)
    assert {
        "scenario",
        "scenario_label_en",
        "focal_length_mm",
        "f_number",
        "field_of_view_deg",
        "image_height_mm",
        "n_elements",
        "wavelength_nm",
        "total_track_mm",
        "airy_disc_diameter_um",
        "cutoff_freq_lp_per_mm",
        "requirement",
        "job_id",
    }.issubset(form.fields)
    assert form.fields["scenario"] == "smartphone-telephoto"
    assert form.fields["scenario_label_en"] == "Smartphone Telephoto"
    assert float(form.fields["focal_length_mm"]) == 18.0
    assert float(form.fields["f_number"]) == 1.8
    assert float(form.fields["field_of_view_deg"]) == 45.0
    assert float(form.fields["image_height_mm"]) == 2.5
    assert int(form.fields["n_elements"]) == 9
    assert float(form.fields["wavelength_nm"]) > 0.0
    assert float(form.fields["total_track_mm"]) > 0.0
    assert float(form.fields["airy_disc_diameter_um"]) > 0.0
    assert float(form.fields["cutoff_freq_lp_per_mm"]) > 0.0
    assert form.fields["requirement"] == requirement

    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == requirement
