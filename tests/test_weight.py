"""Tests for the provisional area -> weight estimate and hand-sort comparison.

Property tests run over many seeded random breakdowns rather than one
hand-picked example, so they cover zeros, tiny shares, and dominant ones.
"""
from __future__ import annotations

import dataclasses
import random

import pytest

from waste_audit.classification.sort_categories import SortCategoryError, load_sort_scheme
from waste_audit.pipeline.weight import compare_to_hand_sort, estimate_weights

SCHEME = load_sort_scheme()
SETS = ["fine", "coarse"]


def _random_areas(rng: random.Random, keys: list[str]) -> dict[str, float]:
    """Random area % summing to 100, with some categories absent."""
    raw = {k: (rng.random() if rng.random() > 0.3 else 0.0) for k in keys}
    if not any(raw.values()):
        raw[keys[0]] = 1.0
    total = sum(raw.values())
    return {k: v / total * 100 for k, v in raw.items()}


def _cases(category_set: str, n: int = 200):
    rng = random.Random(f"weights-{category_set}")
    keys = SCHEME.keys(category_set)
    return [_random_areas(rng, keys) for _ in range(n)]


def _with_factor(category_set: str, key: str, factor: float):
    """Scheme where only `key` gets `factor`: it is moved to a material class of
    its own, so categories sharing its original class are unaffected."""
    factors = {**SCHEME.material_factors, "_solo": factor}
    if category_set == "fine":
        cats = tuple(dataclasses.replace(c, material="_solo") if c.key == key else c for c in SCHEME.categories)
        return dataclasses.replace(SCHEME, categories=cats, material_factors=factors)
    groups = tuple(dataclasses.replace(g, material="_solo") if g.key == key else g for g in SCHEME.groups)
    return dataclasses.replace(SCHEME, groups=groups, material_factors=factors)


# ----------------------------------------------------------------------
# Required properties
# ----------------------------------------------------------------------
@pytest.mark.parametrize("category_set", SETS)
def test_weight_pct_always_sums_to_100(category_set):
    for areas in _cases(category_set):
        est = estimate_weights(areas, category_set)
        assert sum(est.weight_pct.values()) == pytest.approx(100.0)


@pytest.mark.parametrize("category_set", SETS)
def test_weight_pct_sums_to_100_even_when_area_does_not(category_set):
    # Auditor edits can leave area at e.g. 93%; P renormalizes regardless.
    for areas in _cases(category_set, 50):
        est = estimate_weights({k: v * 0.93 for k, v in areas.items()}, category_set)
        assert sum(est.weight_pct.values()) == pytest.approx(100.0)


@pytest.mark.parametrize("category_set", SETS)
def test_equal_factors_leave_area_unchanged(category_set):
    equal = dataclasses.replace(SCHEME, material_factors={m: 2.5 for m in SCHEME.material_factors})
    for areas in _cases(category_set):
        est = estimate_weights(areas, category_set, scheme=equal)
        for key, area in areas.items():
            assert est.weight_pct[key] == pytest.approx(area)


@pytest.mark.parametrize("category_set", SETS)
def test_raising_one_factor_raises_it_and_lowers_all_others(category_set):
    rng = random.Random(f"raise-{category_set}")
    for areas in _cases(category_set, 100):
        key = rng.choice([k for k, v in areas.items() if 0 < v < 100] or [None])
        if key is None:
            continue
        base_factor = SCHEME.factors(category_set)[key]
        before = estimate_weights(areas, category_set, scheme=_with_factor(category_set, key, base_factor))
        after = estimate_weights(areas, category_set, scheme=_with_factor(category_set, key, base_factor * 1.5))

        assert after.weight_pct[key] > before.weight_pct[key]
        for other, area in areas.items():
            if other == key:
                continue
            if area > 0:
                assert after.weight_pct[other] < before.weight_pct[other]
            else:
                assert after.weight_pct[other] == 0.0


@pytest.mark.parametrize("category_set", SETS)
def test_weight_lb_sums_to_bag_weight(category_set):
    rng = random.Random(f"lb-{category_set}")
    for areas in _cases(category_set):
        bag = rng.uniform(0.5, 60.0)
        est = estimate_weights(areas, category_set, bag_weight_lb=bag)
        assert sum(est.weight_lb.values()) == pytest.approx(bag)


# ----------------------------------------------------------------------
# Edge cases
# ----------------------------------------------------------------------
def test_zero_total_score_does_not_crash():
    est = estimate_weights({}, "fine", bag_weight_lb=10.0)
    assert not est.is_defined
    assert set(est.weight_pct.values()) == {0.0}
    assert set(est.weight_lb.values()) == {0.0}


def test_zero_factor_area_only_gives_undefined_estimate():
    zero = dataclasses.replace(SCHEME, material_factors={m: 0.0 for m in SCHEME.material_factors})
    est = estimate_weights({"paper": 100.0}, "fine", scheme=zero)
    assert not est.is_defined


def test_no_bag_weight_means_no_pounds():
    est = estimate_weights({"paper": 100.0}, "fine")
    assert est.weight_lb is None
    assert est.is_defined


def test_worked_example_matches_hand_calculation():
    # S = 50*1.0, 30*1.3, 20*4.0 = 50, 39, 80; sum 169
    est = estimate_weights({"paper": 50, "plastic_1": 30, "metal_cans": 20}, "fine", bag_weight_lb=16.9)
    assert est.weight_pct["metal_cans"] == pytest.approx(80 / 169 * 100)
    assert est.weight_lb["paper"] == pytest.approx(5.0)
    assert est.weight_lb["plastic_1"] == pytest.approx(3.9)
    assert est.weight_lb["metal_cans"] == pytest.approx(8.0)


def test_rejects_unknown_keys_and_negative_inputs():
    with pytest.raises(SortCategoryError):
        estimate_weights({"plastic": 100.0}, "fine")
    with pytest.raises(SortCategoryError):
        estimate_weights({"plastic_1": 100.0}, "coarse")  # fine key, coarse set
    with pytest.raises(ValueError):
        estimate_weights({"paper": -5.0}, "fine")
    with pytest.raises(ValueError):
        estimate_weights({"paper": 100.0}, "fine", bag_weight_lb=-1.0)


# ----------------------------------------------------------------------
# Config mappings
# ----------------------------------------------------------------------
def test_fine_material_mapping():
    materials = SCHEME.materials("fine")
    assert {k for k, m in materials.items() if m == "paper"} == {"paper", "cardboard", "paper_cups"}
    assert {k for k, m in materials.items() if m == "plastic"} == {
        "plastic_1", "plastic_2_jugs", "plastic_5", "plastic_cups", "soft_plastics", "styrofoam",
    }
    assert {k for k, m in materials.items() if m == "trash"} == {"organics", "landfill_office"}
    assert materials["metal_cans"] == "metal"
    assert materials["glass_bottles"] == "glass"


def test_coarse_material_mapping():
    assert SCHEME.materials("coarse") == {
        "paper": "paper", "cardboard": "paper", "plastic_containers": "plastic", "metal": "metal",
        "glass": "glass", "cups": "plastic", "other_landfill": "trash",
    }


def test_factor_values():
    assert dict(SCHEME.material_factors) == {
        "paper": 1.0, "plastic": 1.3, "metal": 4.0, "glass": 3.0, "trash": 1.5, "other": 1.5,
    }


# ----------------------------------------------------------------------
# Hand-sort comparison
# ----------------------------------------------------------------------
HAND_SORT = {"paper": 4.0, "plastic_1": 2.0, "metal_cans": 1.0, "paper_cups": 1.0, "plastic_cups": 1.0,
             "organics": 1.0}  # 10 lb: recycling 8, landfill 2


def test_comparison_signed_error_fine():
    est = estimate_weights({"paper": 50, "plastic_1": 30, "metal_cans": 20}, "fine", bag_weight_lb=16.9)
    cmp = compare_to_hand_sort(est, HAND_SORT)
    by_key = {c.key: c for c in cmp.categories}

    assert by_key["paper"].error_lb == pytest.approx(5.0 - 4.0)
    assert by_key["metal_cans"].error_lb == pytest.approx(8.0 - 1.0)
    assert by_key["organics"].error_lb == pytest.approx(-1.0)   # missed entirely: reads low
    assert by_key["glass_bottles"].error_lb == 0.0
    assert by_key["paper"].actual_pct == pytest.approx(40.0)
    assert sum(c.error_pct for c in cmp.categories) == pytest.approx(0.0)


def test_comparison_stream_split():
    est = estimate_weights({"paper": 50, "plastic_1": 30, "metal_cans": 20}, "fine", bag_weight_lb=16.9)
    cmp = compare_to_hand_sort(est, HAND_SORT)
    assert cmp.actual_streams_lb == pytest.approx({"recycling": 8.0, "landfill": 2.0})
    assert cmp.estimated_streams_lb == pytest.approx({"recycling": 16.9, "landfill": 0.0})
    assert cmp.actual_streams_pct["recycling"] == pytest.approx(80.0)


def test_comparison_coarse_rolls_hand_sort_up_to_groups():
    est = estimate_weights({"paper": 40, "cups": 30, "other_landfill": 30}, "coarse", bag_weight_lb=10.0)
    cmp = compare_to_hand_sort(est, HAND_SORT)
    by_key = {c.key: c for c in cmp.categories}

    assert [c.key for c in cmp.categories] == SCHEME.keys("coarse")
    assert by_key["cups"].actual_lb == pytest.approx(2.0)          # paper cups + plastic cups
    assert by_key["plastic_containers"].actual_lb == pytest.approx(2.0)
    # Actual split is exact from the fine sort; the estimate can't split cups.
    assert cmp.actual_streams_lb == pytest.approx({"recycling": 8.0, "landfill": 2.0})
    assert "mixed" in cmp.estimated_streams_lb


def test_comparison_needs_bag_weight_and_valid_hand_sort():
    with pytest.raises(ValueError, match="bag weight"):
        compare_to_hand_sort(estimate_weights({"paper": 100}, "fine"), HAND_SORT)
    est = estimate_weights({"paper": 100}, "fine", bag_weight_lb=5.0)
    with pytest.raises(SortCategoryError):
        compare_to_hand_sort(est, {"cups": 1.0})   # group key, not a sort-sheet category
    with pytest.raises(ValueError):
        compare_to_hand_sort(est, {"paper": -1.0})
