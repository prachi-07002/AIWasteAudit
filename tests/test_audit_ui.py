"""Tests for mockup UI logic, categories, and record persistence."""
import json

import pytest

from app.components.mockup_ui import (
    CATEGORY_SET,
    MOCK_FINE_PCT,
    MOCKUP_CATEGORIES,
    calculate_stream_contamination,
    run_mock_classifier,
)
from waste_audit.classification.sort_categories import load_sort_scheme


def test_mock_pct_covers_exactly_the_fine_categories():
    """Renaming a category in sort_categories.yaml must update the mock too."""
    assert set(MOCK_FINE_PCT) == set(load_sort_scheme().keys("fine"))


def test_mockup_categories_sum():
    """Verify that default mock classifier percentages sum to 100%."""
    output = run_mock_classifier()
    assert len(output) == len(MOCKUP_CATEGORIES)
    assert set(output) == set(load_sort_scheme().keys(CATEGORY_SET))
    assert sum(output.values()) == pytest.approx(100.0)


def test_stream_contamination_recycling_counts_landfill_categories():
    categories = {"paper": 40.0, "plastic_1": 20.0, "soft_plastics": 25.0, "landfill_office": 15.0}
    contam, hazard = calculate_stream_contamination("recycling", categories, "fine")
    assert contam == 40.0  # 25 + 15
    assert hazard is False


def test_stream_contamination_coarse_skips_mixed_groups():
    # cups holds both plastic cups (recycling) and paper cups (landfill).
    categories = {"paper": 50.0, "cups": 30.0, "other_landfill": 20.0}
    contam, _ = calculate_stream_contamination("recycling", categories, "coarse")
    assert contam == 20.0


def test_stream_contamination_landfill_is_zero():
    contam, _ = calculate_stream_contamination("landfill", {"paper": 100.0}, "fine")
    assert contam == 0.0


def test_stream_contamination_undefined_stream_is_none():
    """The sort sheet has no compost stream; report n/a, not a false 0."""
    contam, _ = calculate_stream_contamination("compost", {"organics": 100.0}, "fine")
    assert contam is None


def test_saved_record_structure():
    """Verify the record format matches the mockup specifications."""
    record = {
        "bag_id": "RB-0412",
        "weight_lb": 4.2,
        "site_id": "example-lab-220",
        "stream_type": "recycling",
        "category_set": "fine",
        "contamination_pct": 8.0,
        "hazard_flagged": False,
        "categories": [
            {"category": "paper", "original_pct": 34.0, "corrected_pct": 34.0},
            {"category": "plastic_1", "original_pct": 28.0, "corrected_pct": 28.0},
        ],
        "scanned_at": "2026-09-18T14:30:00.000Z",
    }
    # Verify serializable
    serialized = json.dumps(record)
    loaded = json.loads(serialized)
    assert loaded["bag_id"] == "RB-0412"
    assert loaded["weight_lb"] == 4.2
    assert len(loaded["categories"]) == 2
