"""Vision-language-model classifier: photo in, generic category breakdown out.

This is the *interim* classifier. The project's end state is the YOLO-seg
pipeline in `waste_audit.detection` (per-item masks -> taxonomy.yaml classes
-> area-based contamination). That needs labeled data which doesn't exist
yet, so this module gets a real model analyzing real photos today by asking
Claude for a whole-bag estimate against the audit sort categories instead
of per-item detection.

Deliberate scope limits, so this doesn't get mistaken for the real thing:
  - It estimates *visible surface area* proportions by eye. It does not
    detect, count, or localize individual items.
  - It uses the sort-sheet categories in configs/sort_categories.yaml,
    either the fine list or its coarse groups (vlm.category_set in
    configs/model.yaml). Not the detector classes in configs/taxonomy.yaml.
    Hazard flags (pipettes, batteries, sharps) are NOT detected here — that's
    exactly what the trained detector is for.
  - Output shape matches the app's existing mock classifier
    (`dict[str, float]` summing to 100) so it's a drop-in swap.
"""
from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from waste_audit.classification.sort_categories import (
    DEFAULT_CATEGORY_SET,
    SortCategoryError,
    load_sort_scheme,
    resolve_category_set,
)
from waste_audit.utils.config import load_model_config

# Claude vision downsamples anything larger than this internally, so sending a
# bigger image costs upload bandwidth and input tokens without adding detail.
MAX_IMAGE_DIM = 1568
JPEG_QUALITY = 85

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_EFFORT = "low"
DEFAULT_MAX_TOKENS = 4096

_SYSTEM_PROMPT_TEMPLATE = """You are assisting a physical waste audit. An auditor has emptied a single \
collection bag onto a tarp or into a sorting bin and photographed it.

Estimate what fraction of the visible waste belongs to each material category, by \
VISIBLE SURFACE AREA — not by item count, and not by weight. One large flattened \
cardboard box covering a third of the frame is roughly 33% cardboard, regardless of \
how many small items sit beside it.

Categories:
{category_list}

Method:
1. Look at the whole frame and identify the distinct materials present.
2. Judge how much of the visible waste each material covers.
3. Assign percentages that sum to exactly 100.

Rules:
- Estimate only what you can actually see. Do not infer the contents of opaque bags or \
guess at what is underneath the top layer — count an opaque bag as the material the \
bag itself is made of.
- When an item is ambiguous between two categories, pick the more likely one rather \
than defaulting to "{fallback}".
- Use "{fallback}" for genuinely unidentifiable, obscured, or out-of-category material. \
If the photo is dark, blurred, or mostly empty, a high "{fallback}" value is the correct \
and honest answer — do not invent a plausible-looking breakdown.
- Every category must be present in your response. Use 0 for categories that are absent.
"""


class VLMClassifierError(RuntimeError):
    """Raised when the model call fails or returns something unusable."""


@dataclass
class VLMClassification:
    """Result of one classification call."""

    categories: dict[str, float]          # category key -> % of visible area, sums to 100
    model: str
    category_set: str = DEFAULT_CATEGORY_SET  # "fine" | "coarse": which keys `categories` uses
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def estimated_cost_usd(self) -> float:
        """Rough per-call cost at claude-sonnet-5 list pricing ($2/$10 per MTok)."""
        return (self.input_tokens / 1_000_000 * 2.00) + (self.output_tokens / 1_000_000 * 10.00)


def build_system_prompt(category_set: str = DEFAULT_CATEGORY_SET) -> str:
    scheme = load_sort_scheme()
    labels = scheme.labels(category_set)
    category_list = "\n".join(
        f"- {key} ({labels[key]}): {description}"
        for key, description in scheme.descriptions(category_set).items()
    )
    return _SYSTEM_PROMPT_TEMPLATE.format(
        category_list=category_list, fallback=scheme.fallback_key(category_set)
    )


def _build_schema(category_set: str = DEFAULT_CATEGORY_SET) -> dict[str, Any]:
    """JSON schema constraining the response to exactly the set's category keys.

    No `minimum`/`maximum` here — structured outputs reject numeric range
    keywords ("For 'number' type, properties maximum, minimum are not
    supported"). Range is enforced in normalize_percentages() instead, which
    has to clamp and rescale anyway since no schema can require a sum of 100.
    """
    scheme = load_sort_scheme()
    labels = scheme.labels(category_set)
    keys = scheme.keys(category_set)
    return {
        "type": "object",
        "properties": {key: {"type": "number", "description": labels[key]} for key in keys},
        "required": keys,
        "additionalProperties": False,
    }


def prepare_image(image_bytes: bytes, max_dim: int = MAX_IMAGE_DIM) -> tuple[str, str]:
    """Downscale/re-encode a photo for the API. Returns (base64_data, media_type).

    Phone photos are routinely 4000px and several MB; the model downsamples
    above MAX_IMAGE_DIM anyway, so shrinking here is free accuracy-wise and
    cuts upload time and input tokens substantially.
    """
    from PIL import Image  # local import: keeps module importable without Pillow

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGB")  # drops alpha/palette modes JPEG can't encode
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    except Exception as exc:  # noqa: BLE001 — surface any decode failure uniformly
        raise VLMClassifierError(f"Could not read the photo: {exc}") from exc

    return base64.standard_b64encode(buffer.getvalue()).decode("utf-8"), "image/jpeg"


def normalize_percentages(
    raw: dict[str, Any], category_set: str = DEFAULT_CATEGORY_SET
) -> dict[str, float]:
    """Coerce a model response into non-negative floats summing to 100.

    The schema constrains types and keys but cannot enforce a sum, so the
    model's numbers routinely land at 99 or 101. Rescaling here keeps the
    app's total-% validation from tripping on rounding.
    """
    values: dict[str, float] = {}
    for key in load_sort_scheme().keys(category_set):
        try:
            values[key] = max(0.0, float(raw.get(key, 0.0)))
        except (TypeError, ValueError):
            values[key] = 0.0

    total = sum(values.values())
    if total <= 0:
        raise VLMClassifierError("Model returned all-zero percentages — nothing to report.")

    scaled = {key: value / total * 100 for key, value in values.items()}

    # Round to 1dp, then push any residual onto the largest category so the
    # displayed values add up to exactly 100.
    rounded = {key: round(value, 1) for key, value in scaled.items()}
    residual = round(100.0 - sum(rounded.values()), 1)
    if residual:
        largest = max(rounded, key=lambda k: rounded[k])
        rounded[largest] = round(rounded[largest] + residual, 1)

    return rounded


def classify_bag(
    image_bytes: bytes,
    stream_type: str | None = None,
    *,
    client: Any | None = None,
    model: str | None = None,
    effort: str | None = None,
    max_tokens: int | None = None,
    category_set: str | None = None,
) -> VLMClassification:
    """Send one audit photo to Claude and get back a category breakdown.

    Args:
        image_bytes: raw photo bytes (JPEG/PNG, any size).
        stream_type: 'recycling' | 'compost' | 'landfill'. Passed to the model
            as context only — contaminant status is still decided downstream by
            calculate_stream_contamination(), so the model isn't asked to judge
            what counts as contamination.
        client: an anthropic.Anthropic instance. Constructed from the
            environment if omitted (injectable for tests).
        model / effort / max_tokens / category_set: override configs/model.yaml
            -> vlm. category_set is "fine" (sort-sheet categories) or "coarse"
            (their groups); see configs/sort_categories.yaml.

    Raises:
        VLMClassifierError: missing API key, missing SDK, API failure, or an
            unparseable response.
    """
    settings = _vlm_settings()
    model = model or settings["model"]
    effort = effort or settings["effort"]
    max_tokens = max_tokens or settings["max_tokens"]
    try:
        category_set = resolve_category_set(category_set or settings["category_set"])
    except SortCategoryError as exc:
        raise VLMClassifierError(str(exc)) from exc

    if client is None:
        client = build_client()

    image_data, media_type = prepare_image(image_bytes)

    context = (
        f"This bag was collected from the {stream_type} stream."
        if stream_type
        else "The collection stream for this bag is unspecified."
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=build_system_prompt(category_set),
            thinking={"type": "adaptive"},
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": _build_schema(category_set)},
            },
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": f"{context}\n\nEstimate the material breakdown of this bag.",
                        },
                    ],
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001 — caller only needs one failure mode
        raise VLMClassifierError(f"Model request failed: {exc}") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise VLMClassifierError("The model declined to analyze this image.")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise VLMClassifierError("Model returned no text block — nothing to parse.")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VLMClassifierError(f"Model returned invalid JSON: {text[:200]}") from exc

    usage = getattr(response, "usage", None)
    return VLMClassification(
        categories=normalize_percentages(parsed, category_set),
        model=model,
        category_set=category_set,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        raw=parsed,
    )


def build_client() -> Any:
    """Construct an Anthropic client, with actionable errors when unconfigured."""
    try:
        import anthropic
    except ImportError as exc:
        raise VLMClassifierError(
            "The `anthropic` package is not installed. Run: pip install anthropic"
        ) from exc

    try:
        from dotenv import load_dotenv

        # Streamlit and VS Code may start outside the repository directory.
        load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    except ImportError:
        pass  # dotenv is a convenience; a real env var works fine without it

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise VLMClassifierError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file (see .env.example)."
        )

    return anthropic.Anthropic()


def is_configured() -> bool:
    """True if a classification call has a chance of succeeding.

    Lets the UI show 'AI estimate' vs. 'mock data' without making a request.
    """
    try:
        build_client()
    except VLMClassifierError:
        return False
    return True


def _vlm_settings() -> dict[str, Any]:
    """Read the `vlm:` block from configs/model.yaml, falling back to defaults."""
    try:
        vlm = load_model_config().get("vlm") or {}
    except Exception:  # noqa: BLE001 — a bad config shouldn't block inference
        vlm = {}

    return {
        "model": vlm.get("model", DEFAULT_MODEL),
        "effort": vlm.get("effort", DEFAULT_EFFORT),
        "max_tokens": int(vlm.get("max_tokens", DEFAULT_MAX_TOKENS)),
        "category_set": vlm.get("category_set", DEFAULT_CATEGORY_SET),
    }


def active_category_set() -> str:
    """The category set configured in configs/model.yaml -> vlm.category_set.

    Raises SortCategoryError on an unknown value rather than quietly falling
    back to the default, which would mislabel a scoring run.
    """
    return resolve_category_set(_vlm_settings()["category_set"])
