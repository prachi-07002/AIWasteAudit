"""Tests for the sort-category config and its group/stream roll-ups."""
from __future__ import annotations

import pytest

from waste_audit.classification.sort_categories import (
    MIXED_STREAM,
    SortCategoryError,
    load_sort_scheme,
    resolve_category_set,
)

SORT_SHEET_LABELS = [
    "Paper",
    "Cardboard and paperboard",
    "Plastic #1",
    "Plastic #2 jugs",
    "Plastic #5",
    "Metal cans",
    "Glass bottles",
    "Plastic cups #1/#5",
    "Paper cups",
    "Styrofoam",
    "Soft plastics",
    "Organics",
    "Landfill/office waste",
]


@pytest.fixture
def scheme():
    return load_sort_scheme()


def test_fine_set_is_the_sort_sheet(scheme):
    assert list(scheme.labels("fine").values()) == SORT_SHEET_LABELS


def test_coarse_set_is_the_groups(scheme):
    assert scheme.keys("coarse") == [
        "paper", "cardboard", "plastic_containers", "metal", "glass", "cups", "other_landfill",
    ]


def test_every_stream_is_recycling_or_landfill(scheme):
    assert {c.stream for c in scheme.categories} <= {"recycling", "landfill"}


def test_unconfirmed_streams_are_flagged(scheme):
    unconfirmed = {c.key for c in scheme.unconfirmed_streams()}
    assert {"paper_cups", "glass_bottles", "plastic_5"} <= unconfirmed


def test_to_groups_sums_members_and_preserves_total(scheme):
    hand_sort = {"plastic_1": 2.0, "plastic_2_jugs": 1.5, "plastic_5": 0.5, "paper_cups": 1.0,
                 "plastic_cups": 0.25, "organics": 3.0}
    groups = scheme.to_groups(hand_sort)
    assert groups["plastic_containers"] == pytest.approx(4.0)
    assert groups["cups"] == pytest.approx(1.25)
    assert groups["other_landfill"] == pytest.approx(3.0)
    assert groups["glass"] == 0.0
    assert sum(groups.values()) == pytest.approx(sum(hand_sort.values()))


def test_to_groups_rejects_unknown_keys(scheme):
    with pytest.raises(SortCategoryError):
        scheme.to_groups({"plastic": 10.0})


def test_fine_and_coarse_agree_at_the_stream_level(scheme):
    """Streams roll up the same way from either set, except mixed groups."""
    shares = {key: 1.0 for key in scheme.keys("fine")}
    fine = scheme.to_streams(shares, "fine")
    coarse = scheme.to_streams(scheme.to_groups(shares), "coarse")
    mixed = coarse.pop(MIXED_STREAM, 0.0)
    assert sum(coarse.values()) + mixed == pytest.approx(sum(fine.values()))


def test_cups_group_is_mixed_stream(scheme):
    assert scheme.stream_of("cups", "coarse") == MIXED_STREAM
    assert scheme.stream_of("other_landfill", "coarse") == "landfill"


def test_fallback_is_landfill_office(scheme):
    assert scheme.fallback_key("fine") == "landfill_office"
    assert scheme.fallback_key("coarse") == "other_landfill"


def test_resolve_category_set():
    assert resolve_category_set(None) == "fine"
    assert resolve_category_set("coarse") == "coarse"
    with pytest.raises(SortCategoryError):
        resolve_category_set("13")


# ----------------------------------------------------------------------
# Validation: a broken config should fail at load, not mid-scoring
# ----------------------------------------------------------------------
_VALID = """
streams: [recycling, landfill]
material_classes: {paper: 1.0, other: 1.5}
default_material: other
groups:
  - {key: g1, label: G1}
  - {key: g2, label: G2}
categories:
  - {key: a, label: A, group: g1, stream: recycling, stream_confirmed: true, description: a}
  - {key: b, label: B, group: g2, stream: landfill, stream_confirmed: false, description: b, fallback: true}
"""


def _write(tmp_path, text):
    path = tmp_path / "sort_categories.yaml"
    path.write_text(text)
    return path


def test_valid_minimal_config_loads(tmp_path):
    scheme = load_sort_scheme(_write(tmp_path, _VALID))
    assert scheme.keys("fine") == ["a", "b"]


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("group: g2, stream: landfill", "group: g9, stream: landfill", "unknown group"),
        ("stream: landfill, stream_confirmed", "stream: compost, stream_confirmed", "unknown stream"),
        ("{key: b, label: B", "{key: a, label: B", "duplicate category"),
        (", fallback: true", "", "fallback"),
        ("stream_confirmed: false, ", "", "stream_confirmed"),
        ("group: g1, stream", "group: g1, material: wood, stream", "unknown material"),
        ("paper: 1.0,", "paper: -1.0,", "non-negative"),
        ("default_material: other", "default_material: rock", "default_material"),
        ("  - {key: g2, label: G2}\n", "  - {key: g2, label: G2}\n  - {key: g3, label: G3}\n", "no categories"),
    ],
)
def test_malformed_config_fails_loudly(tmp_path, old, new, message):
    assert old in _VALID
    with pytest.raises(SortCategoryError, match=message):
        load_sort_scheme(_write(tmp_path, _VALID.replace(old, new)))
