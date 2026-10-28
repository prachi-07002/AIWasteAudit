"""Compare the provisional weight estimate for one bag against its hand sort.

Reports per-category signed error (estimate minus actual, in lb and in
weight-% points) and the recycling vs. landfill split for both.

Usage:
    python scripts/compare_hand_sort.py bag.jpg --hand-sort bag_sort.json --bag-weight 12.4
    python scripts/compare_hand_sort.py --areas prediction.json --hand-sort bag_sort.json

--hand-sort is a JSON object of pounds per fine category key, e.g.
    {"paper": 2.1, "cardboard": 3.4, "plastic_1": 0.8, "organics": 1.2}
Missing categories count as 0; see configs/sort_categories.yaml for keys.

--areas skips the model call and reuses area % from a file: either a plain
{key: pct} object, or one line of `classify_photo.py --json` output.

Without --bag-weight, the hand-sort total is used as the bag weight, so the lb
error then reflects only the area and factor steps.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
for p in (ROOT_DIR, ROOT_DIR / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from waste_audit.classification.sort_categories import CATEGORY_SETS, load_sort_scheme  # noqa: E402
from waste_audit.classification.vlm_classifier import VLMClassifierError, classify_bag  # noqa: E402
from waste_audit.pipeline.weight import compare_to_hand_sort, estimate_weights  # noqa: E402


def _load_areas(path: Path, category_set: str | None) -> tuple[dict[str, float], str]:
    data = json.loads(path.read_text())
    if "categories" in data:  # a classify_photo.py --json line
        return data["categories"], category_set or data.get("category_set", "fine")
    return data, category_set or "fine"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("photo", type=Path, nargs="?", help="Bag photo (omit when using --areas)")
    parser.add_argument("--areas", type=Path, help="Area %% JSON to use instead of calling the model")
    parser.add_argument("--hand-sort", type=Path, required=True, help="Hand-sort lb per fine category (JSON)")
    parser.add_argument("--bag-weight", type=float, default=None, help="Measured bag weight, lb")
    parser.add_argument("--categories", choices=CATEGORY_SETS, default=None,
                        help="Category set for the model call (default: configs/model.yaml)")
    parser.add_argument("--json", action="store_true", help="Emit the comparison as JSON")
    args = parser.parse_args()

    if (args.photo is None) == (args.areas is None):
        parser.error("give exactly one of: a photo, or --areas")

    if args.areas:
        areas, category_set = _load_areas(args.areas, args.categories)
    else:
        try:
            result = classify_bag(args.photo.read_bytes(), category_set=args.categories)
        except VLMClassifierError as exc:
            print(f"Classification failed: {exc}", file=sys.stderr)
            return 1
        areas, category_set = result.categories, result.category_set

    hand_sort = json.loads(args.hand_sort.read_text())
    bag_weight = args.bag_weight if args.bag_weight is not None else sum(hand_sort.values())

    estimate = estimate_weights(areas, category_set, bag_weight_lb=bag_weight)
    if not estimate.is_defined:
        print("No weight estimate: every category has 0 area (or a 0 factor).", file=sys.stderr)
        return 1
    comparison = compare_to_hand_sort(estimate, hand_sort)

    if args.json:
        print(json.dumps({
            "category_set": category_set,
            "bag_weight_lb": comparison.bag_weight_lb,
            "hand_sort_total_lb": comparison.hand_sort_total_lb,
            "categories": [
                {"key": c.key, "area_pct": estimate.area_pct[c.key], "factor": estimate.factors[c.key],
                 "estimated_lb": c.estimated_lb, "actual_lb": c.actual_lb, "error_lb": c.error_lb,
                 "estimated_pct": c.estimated_pct, "actual_pct": c.actual_pct, "error_pct": c.error_pct}
                for c in comparison.categories
            ],
            "streams": {
                "estimated_lb": comparison.estimated_streams_lb,
                "actual_lb": comparison.actual_streams_lb,
                "estimated_pct": comparison.estimated_streams_pct,
                "actual_pct": comparison.actual_streams_pct,
            },
        }, indent=2))
        return 0

    labels = load_sort_scheme().labels(category_set)
    source = "measured" if args.bag_weight is not None else "hand-sort total"
    print(f"{category_set} set · bag {comparison.bag_weight_lb:.2f} lb ({source}) · "
          f"hand sort {comparison.hand_sort_total_lb:.2f} lb\n")
    print(f"  {'Category':<26} {'Area%':>6} {'D':>4} {'Est lb':>7} {'Act lb':>7} {'Err lb':>7} "
          f"{'Est%':>6} {'Act%':>6} {'Err pts':>8}")
    for c in comparison.categories:
        print(f"  {labels[c.key]:<26} {estimate.area_pct[c.key]:6.1f} {estimate.factors[c.key]:4.1f} "
              f"{c.estimated_lb:7.2f} {c.actual_lb:7.2f} {c.error_lb:+7.2f} "
              f"{c.estimated_pct:6.1f} {c.actual_pct:6.1f} {c.error_pct:+8.1f}")

    print("\n  Stream split        Est lb   Act lb    Est%    Act%")
    est_pct, act_pct = comparison.estimated_streams_pct, comparison.actual_streams_pct
    for stream in dict.fromkeys([*comparison.actual_streams_lb, *comparison.estimated_streams_lb]):
        print(f"  {stream:<18} {comparison.estimated_streams_lb.get(stream, 0.0):7.2f} "
              f"{comparison.actual_streams_lb.get(stream, 0.0):8.2f} "
              f"{est_pct.get(stream, 0.0):7.1f} {act_pct.get(stream, 0.0):7.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
