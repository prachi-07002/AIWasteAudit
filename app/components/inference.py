"""Bridge between the Streamlit audit page and the classifier.

Keeps one decision in one place: use the real model when it's configured and
working, fall back to the mock breakdown when it isn't, and always tell the
page which one it got so the UI can label the numbers honestly. An auditor
should never see mock percentages presented as a model estimate.
"""
from __future__ import annotations

from dataclasses import dataclass

from waste_audit.classification.vlm_classifier import (
    VLMClassifierError,
    classify_bag,
)

try:
    from app.components.mockup_ui import run_mock_classifier
except ImportError:
    from components.mockup_ui import run_mock_classifier


@dataclass
class InferenceResult:
    """What the audit page needs to render and label a breakdown."""

    categories: dict[str, float]
    source: str                      # "model" | "mock"
    model: str | None = None
    cost_usd: float = 0.0
    error: str | None = None         # set when a real attempt failed and we fell back

    @property
    def is_mock(self) -> bool:
        return self.source == "mock"

    @property
    def label(self) -> str:
        """Short provenance string for the results header."""
        if self.is_mock:
            return "Mock data — no model configured"
        return f"AI estimate · {self.model}"


def run_classifier(image_bytes: bytes | None, stream_type: str | None = None) -> InferenceResult:
    """Classify a photo, degrading to the mock breakdown rather than erroring out.

    Field auditors shouldn't lose a bag's worth of work to a dropped connection
    or an expired key — they can still correct the numbers by hand and save the
    record. The returned `source`/`error` fields make the degradation visible.
    """
    if image_bytes is None:
        return InferenceResult(categories=run_mock_classifier(), source="mock")

    try:
        result = classify_bag(image_bytes, stream_type=stream_type)
    except VLMClassifierError as exc:
        return InferenceResult(
            categories=run_mock_classifier(),
            source="mock",
            error=str(exc),
        )

    return InferenceResult(
        categories=result.categories,
        source="model",
        model=result.model,
        cost_usd=result.estimated_cost_usd,
    )
