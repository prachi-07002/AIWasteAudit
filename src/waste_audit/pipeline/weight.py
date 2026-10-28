"""Provisional weight estimate from area %, and comparison to a hand sort.

The model reports each category's share of visible area. Weight differs from
area by material (a can weighs more than a paper sheet of the same footprint),
so each category's area is scaled by a weighting factor D for its material
class, then renormalized:

    S_i = A_i * D_i                 A_i = area %, D_i = weighting factor
    P_i = S_i / sum(S) * 100        estimated weight %
    W_i = P_i / 100 * bag_weight    estimated lb, when a bag weight is given

Factors and the category -> material mappings come from
configs/sort_categories.yaml. They are provisional (Aaron's), not fitted.

Values are kept unrounded. Round for display only, so scoring isn't biased
by rounding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from waste_audit.classification.sort_categories import (
    DEFAULT_CATEGORY_SET,
    SortCategoryError,
    SortScheme,
    load_sort_scheme,
    resolve_category_set,
)


@dataclass(frozen=True)
class WeightEstimate:
    category_set: str
    area_pct: dict[str, float]           # A_i, as given
    factors: dict[str, float]            # D_i used
    weight_pct: dict[str, float]         # P_i; all 0.0 when not is_defined
    weight_lb: dict[str, float] | None   # W_i; None without a bag weight
    bag_weight_lb: float | None

    @property
    def is_defined(self) -> bool:
        """False when sum(S) was 0 (no area, or only zero-factor area), so
        there is no weight share to report. P_i and W_i are then all 0."""
        return any(self.weight_pct.values())


def estimate_weights(
    area_pct: Mapping[str, float],
    category_set: str = DEFAULT_CATEGORY_SET,
    bag_weight_lb: float | None = None,
    scheme: SortScheme | None = None,
) -> WeightEstimate:
    """Area % per category -> estimated weight % (and lb, given a bag weight).

    Missing categories count as 0 area. Unknown keys and negative inputs raise,
    since either means the caller has the wrong category set or bad data.
    """
    scheme = scheme or load_sort_scheme()
    category_set = resolve_category_set(category_set)
    keys = scheme.keys(category_set)

    unknown = sorted(set(area_pct) - set(keys))
    if unknown:
        raise SortCategoryError(f"Unknown {category_set} category keys: {', '.join(unknown)}")
    if any(float(v) < 0 for v in area_pct.values()):
        raise ValueError("Area percentages must be non-negative.")
    if bag_weight_lb is not None and bag_weight_lb < 0:
        raise ValueError("Bag weight must be non-negative.")

    factors = scheme.factors(category_set)
    area = {key: float(area_pct.get(key, 0.0)) for key in keys}
    scores = {key: area[key] * factors[key] for key in keys}
    total = sum(scores.values())

    if total > 0:
        weight_pct = {key: s / total * 100 for key, s in scores.items()}
    else:
        weight_pct = {key: 0.0 for key in keys}

    weight_lb = None
    if bag_weight_lb is not None:
        weight_lb = {key: p / 100 * bag_weight_lb for key, p in weight_pct.items()}

    return WeightEstimate(
        category_set=category_set,
        area_pct=area,
        factors=factors,
        weight_pct=weight_pct,
        weight_lb=weight_lb,
        bag_weight_lb=bag_weight_lb,
    )


# ----------------------------------------------------------------------
# Comparison against a hand sort
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class CategoryError:
    key: str
    estimated_lb: float
    actual_lb: float
    estimated_pct: float   # P_i
    actual_pct: float      # share of the hand-sort total

    @property
    def error_lb(self) -> float:
        """Signed: positive means the estimate reads high."""
        return self.estimated_lb - self.actual_lb

    @property
    def error_pct(self) -> float:
        """Signed error in weight-% points. Unlike error_lb, this doesn't
        depend on the bag weight matching the hand-sort total."""
        return self.estimated_pct - self.actual_pct


@dataclass(frozen=True)
class HandSortComparison:
    category_set: str
    categories: list[CategoryError]
    estimated_streams_lb: dict[str, float]   # may include "mixed" for coarse groups
    actual_streams_lb: dict[str, float]
    bag_weight_lb: float
    hand_sort_total_lb: float

    @staticmethod
    def _as_pct(streams_lb: Mapping[str, float]) -> dict[str, float]:
        total = sum(streams_lb.values())
        return {s: (lb / total * 100 if total > 0 else 0.0) for s, lb in streams_lb.items()}

    @property
    def estimated_streams_pct(self) -> dict[str, float]:
        return self._as_pct(self.estimated_streams_lb)

    @property
    def actual_streams_pct(self) -> dict[str, float]:
        return self._as_pct(self.actual_streams_lb)


def compare_to_hand_sort(
    estimate: WeightEstimate,
    hand_sort_lb: Mapping[str, float],
    scheme: SortScheme | None = None,
) -> HandSortComparison:
    """Per-category signed error and stream split, estimate vs. hand sort.

    `hand_sort_lb` is pounds per fine category, as on the sort sheet. Missing
    categories count as 0. For a coarse estimate it is rolled up to groups,
    so both sides are compared on the same keys.

    The actual stream split is always computed from the fine hand sort, so it
    is exact. A coarse estimate can't split a mixed group (cups) between
    streams, so its split may carry a "mixed" bucket.
    """
    scheme = scheme or load_sort_scheme()
    if estimate.weight_lb is None or estimate.bag_weight_lb is None:
        raise ValueError("Comparison needs an estimate made with a bag weight (bag_weight_lb).")
    if any(float(v) < 0 for v in hand_sort_lb.values()):
        raise ValueError("Hand-sort weights must be non-negative.")

    fine_actual = {key: 0.0 for key in scheme.keys("fine")}
    for key, lb in hand_sort_lb.items():
        if key not in fine_actual:
            raise SortCategoryError(f"Unknown fine category in hand sort: '{key}'")
        fine_actual[key] = float(lb)

    actual = fine_actual if estimate.category_set == "fine" else scheme.to_groups(fine_actual)
    actual_total = sum(actual.values())

    categories = [
        CategoryError(
            key=key,
            estimated_lb=estimate.weight_lb[key],
            actual_lb=actual[key],
            estimated_pct=estimate.weight_pct[key],
            actual_pct=actual[key] / actual_total * 100 if actual_total > 0 else 0.0,
        )
        for key in scheme.keys(estimate.category_set)
    ]

    return HandSortComparison(
        category_set=estimate.category_set,
        categories=categories,
        estimated_streams_lb=scheme.to_streams(estimate.weight_lb, estimate.category_set),
        actual_streams_lb=scheme.to_streams(fine_actual, "fine"),
        bag_weight_lb=estimate.bag_weight_lb,
        hand_sort_total_lb=actual_total,
    )
