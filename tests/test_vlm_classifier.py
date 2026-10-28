"""Tests for the interim VLM classifier.

No network calls — the Anthropic client is injected as a stub, so these run
offline and without an API key.
"""
from __future__ import annotations

import io
import json
import os
import sys

import pytest

from waste_audit.classification.sort_categories import load_sort_scheme
from waste_audit.classification.vlm_classifier import (
    MAX_IMAGE_DIM,
    VLMClassifierError,
    _build_schema,
    build_system_prompt,
    classify_bag,
    normalize_percentages,
    prepare_image,
)

SCHEME = load_sort_scheme()
FINE = SCHEME.keys("fine")
COARSE = SCHEME.keys("coarse")


def _even(keys: list[str]) -> dict[str, float]:
    return {key: 100 / len(keys) for key in keys}


# ----------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------
def test_schema_omits_unsupported_numeric_keywords():
    """Structured outputs reject `minimum`/`maximum` on number types with a
    400. Caught live, not by the stubs below — so guard it here."""
    for spec in _build_schema()["properties"].values():
        assert "minimum" not in spec
        assert "maximum" not in spec


@pytest.mark.parametrize("category_set, keys", [("fine", FINE), ("coarse", COARSE)])
def test_schema_pins_the_exact_category_keys(category_set, keys):
    schema = _build_schema(category_set)
    assert set(schema["properties"]) == set(keys)
    assert schema["required"] == keys
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize("category_set, keys", [("fine", FINE), ("coarse", COARSE)])
def test_system_prompt_lists_every_category_and_the_fallback(category_set, keys):
    prompt = build_system_prompt(category_set)
    for key in keys:
        assert f"- {key} (" in prompt
    assert f'"{SCHEME.fallback_key(category_set)}"' in prompt
    assert "{" not in prompt  # no unfilled template fields


# ----------------------------------------------------------------------
# Stub client
# ----------------------------------------------------------------------
class _Block:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _Usage:
    input_tokens = 1500
    output_tokens = 120


class _Response:
    stop_reason = "end_turn"

    def __init__(self, payload: dict):
        self.content = [_Block(json.dumps(payload))]
        self.usage = _Usage()


class _StubMessages:
    def __init__(self, payload: dict):
        self._payload = payload
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _Response(self._payload)


class _StubClient:
    def __init__(self, payload: dict):
        self.messages = _StubMessages(payload)


def _photo_bytes(size: tuple[int, int] = (800, 600)) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (120, 140, 110)).save(buffer, format="JPEG")
    return buffer.getvalue()


# ----------------------------------------------------------------------
# normalize_percentages
# ----------------------------------------------------------------------
def test_normalize_rescales_to_exactly_100():
    # Model returned something summing to 97 — common, the schema can't enforce a sum.
    raw = {key: 7 for key in FINE}  # 13 x 7 = 91
    result = normalize_percentages(raw)
    assert sum(result.values()) == pytest.approx(100.0, abs=0.05)


def test_normalize_preserves_relative_proportions():
    result = normalize_percentages({"paper": 50, "plastic_1": 25})
    assert result["paper"] == pytest.approx(66.7, abs=0.2)
    assert result["plastic_1"] == pytest.approx(33.3, abs=0.2)
    assert result["metal_cans"] == 0.0


def test_normalize_fills_missing_and_invalid_keys_with_zero():
    result = normalize_percentages({"paper": 100, "plastic_1": "not a number"})
    assert set(result) == set(FINE)
    assert result["paper"] == 100.0
    assert result["plastic_1"] == 0.0


def test_normalize_uses_the_requested_category_set():
    result = normalize_percentages({"cups": 40, "other_landfill": 60}, "coarse")
    assert set(result) == set(COARSE)
    assert result["cups"] == 40.0


def test_normalize_clamps_negative_values():
    result = normalize_percentages({"paper": 80, "plastic_1": -10, "metal_cans": 20})
    assert result["plastic_1"] == 0.0
    assert sum(result.values()) == pytest.approx(100.0, abs=0.05)


def test_normalize_rejects_all_zero():
    with pytest.raises(VLMClassifierError):
        normalize_percentages({key: 0 for key in FINE})


# ----------------------------------------------------------------------
# prepare_image
# ----------------------------------------------------------------------
def test_prepare_image_downscales_large_photos():
    from PIL import Image

    data, media_type = prepare_image(_photo_bytes((4000, 3000)))
    assert media_type == "image/jpeg"

    import base64

    decoded = Image.open(io.BytesIO(base64.standard_b64decode(data)))
    assert max(decoded.size) == MAX_IMAGE_DIM


def test_prepare_image_rejects_non_image_bytes():
    with pytest.raises(VLMClassifierError):
        prepare_image(b"this is not a photo")


# ----------------------------------------------------------------------
# classify_bag
# ----------------------------------------------------------------------
def test_classify_bag_returns_normalized_categories():
    client = _StubClient({"paper": 40, "cardboard": 30, "plastic_1": 10, "metal_cans": 10,
                          "organics": 5, "landfill_office": 5})
    result = classify_bag(_photo_bytes(), stream_type="recycling", client=client, category_set="fine")

    assert result.category_set == "fine"
    assert set(result.categories) == set(FINE)
    assert sum(result.categories.values()) == pytest.approx(100.0, abs=0.05)
    assert result.input_tokens == 1500
    assert result.estimated_cost_usd > 0


def test_classify_bag_sends_image_and_stream_context():
    client = _StubClient(_even(FINE))
    classify_bag(_photo_bytes(), stream_type="compost", client=client, category_set="fine")

    content = client.messages.last_kwargs["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert "compost" in content[1]["text"]


def test_classify_bag_coarse_asks_for_and_returns_groups():
    client = _StubClient(_even(COARSE))
    result = classify_bag(_photo_bytes(), client=client, category_set="coarse")

    schema = client.messages.last_kwargs["output_config"]["format"]["schema"]
    assert schema["required"] == COARSE
    assert result.category_set == "coarse"
    assert set(result.categories) == set(COARSE)


def test_classify_bag_rejects_unknown_category_set():
    with pytest.raises(VLMClassifierError, match="category set"):
        classify_bag(_photo_bytes(), client=_StubClient({}), category_set="medium")


def test_classify_bag_raises_on_invalid_json():
    client = _StubClient({})
    client.messages.create = lambda **kwargs: type(  # noqa: ARG005
        "R", (), {"stop_reason": "end_turn", "content": [_Block("not json")], "usage": _Usage()}
    )()

    with pytest.raises(VLMClassifierError, match="invalid JSON"):
        classify_bag(_photo_bytes(), client=client)


# ----------------------------------------------------------------------
# Drift guard
# ----------------------------------------------------------------------
def test_categories_match_the_apps_category_list():
    """The UI renders labels/icons per category key; a mismatch silently drops
    a category from the results screen."""
    from app.components.mockup_ui import CATEGORY_SET, MOCKUP_CATEGORIES

    assert [c["key"] for c in MOCKUP_CATEGORIES] == SCHEME.keys(CATEGORY_SET)


@pytest.mark.parametrize("environment_key", [None, "test-shell-key"])
def test_client_loads_project_dotenv_independently_of_launch_directory(monkeypatch, tmp_path, environment_key):
    import anthropic
    from waste_audit.classification import vlm_classifier

    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text("ANTHROPIC_API_KEY=test-project-key\n")
    launcher = tmp_path / "launcher"
    launcher.mkdir()
    (launcher / ".env").write_text("ANTHROPIC_API_KEY=test-unrelated-key\n")
    monkeypatch.chdir(launcher)
    monkeypatch.setattr(vlm_classifier, "__file__", str(project / "src/waste_audit/classification/vlm_classifier.py"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    if environment_key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", environment_key)
    # Return the selected dummy credential instead of constructing a real client.
    monkeypatch.setattr(anthropic, "Anthropic", lambda: os.environ["ANTHROPIC_API_KEY"])

    assert vlm_classifier.build_client() == (environment_key or "test-project-key")


def test_ui_reports_missing_sdk_instead_of_missing_key(monkeypatch):
    from app.components.inference import run_classifier

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-configured-key")
    monkeypatch.setitem(sys.modules, "anthropic", None)
    result = run_classifier(b"not sent to any API")

    assert result.is_mock
    assert "anthropic" in result.error and "not installed" in result.error
    assert "API_KEY is not set" not in result.error


def test_ui_reports_missing_key_when_sdk_is_installed(monkeypatch):
    import dotenv
    from app.components.inference import run_classifier

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    result = run_classifier(b"not sent to any API")

    assert result.is_mock
    assert "ANTHROPIC_API_KEY is not set" in result.error
