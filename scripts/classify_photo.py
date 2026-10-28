"""Run the interim VLM classifier on one photo or a folder of photos and print
what came back — the quickest way to eyeball whether the model's estimates
are any good on real audit images, without clicking through the app.

Usage:
    python scripts/classify_photo.py path/to/bag.jpg
    python scripts/classify_photo.py data/raw --stream recycling
    python scripts/classify_photo.py data/raw --json > results.json
    python scripts/classify_photo.py data/raw --categories coarse
    python scripts/classify_photo.py bag.jpg --bag-weight 12.4

Requires ANTHROPIC_API_KEY in .env (see .env.example). ~$0.005 per photo.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Runs without `pip install -e .` — same trick as app/main.py.
ROOT_DIR = Path(__file__).resolve().parents[1]
for p in (ROOT_DIR, ROOT_DIR / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from waste_audit.classification.sort_categories import CATEGORY_SETS  # noqa: E402
from waste_audit.classification.vlm_classifier import (  # noqa: E402
    VLMClassifierError,
    classify_bag,
)
from waste_audit.pipeline.weight import estimate_weights  # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _collect_images(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


def _print_breakdown(name: str, categories: dict[str, float], weights) -> None:
    """Text bar chart of area %, sorted by share, with the provisional weight
    estimate beside it — reads faster than a dict on 20 photos."""
    print(f"\n{name}")
    for key, pct in sorted(categories.items(), key=lambda kv: kv[1], reverse=True):
        bar = "#" * int(round(pct / 2))
        weight = f"wt {weights.weight_pct[key]:5.1f}%"
        if weights.weight_lb is not None:
            weight += f" {weights.weight_lb[key]:6.2f} lb"
        print(f"  {key:<18} {pct:5.1f}%  {weight}  {bar}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path, help="A photo, or a folder of photos")
    parser.add_argument("--stream", choices=["recycling", "compost", "landfill"], default=None,
                        help="Which stream the bag came from (context for the model)")
    parser.add_argument("--effort", choices=["low", "medium", "high"], default=None,
                        help="Override configs/model.yaml -> vlm.effort for this run")
    parser.add_argument("--categories", choices=CATEGORY_SETS, default=None,
                        help="Sort-sheet categories (fine) or their groups (coarse); "
                             "overrides configs/model.yaml -> vlm.category_set")
    parser.add_argument("--bag-weight", type=float, default=None,
                        help="Measured bag weight in lb; adds estimated lb per category")
    parser.add_argument("--json", action="store_true", help="Emit one JSON object per photo instead of text")
    args = parser.parse_args()

    images = _collect_images(args.path)
    if not images:
        print(f"No images found at {args.path}", file=sys.stderr)
        return 1

    total_cost = 0.0
    failures = 0
    for path in images:
        try:
            result = classify_bag(path.read_bytes(), stream_type=args.stream, effort=args.effort,
                                  category_set=args.categories)
        except VLMClassifierError as exc:
            failures += 1
            print(f"\n{path.name}: FAILED — {exc}", file=sys.stderr)
            continue

        total_cost += result.estimated_cost_usd
        weights = estimate_weights(result.categories, result.category_set, bag_weight_lb=args.bag_weight)
        if args.json:
            print(json.dumps({
                "file": path.name,
                "stream": args.stream,
                "model": result.model,
                "category_set": result.category_set,
                "categories": result.categories,
                "weight_pct": weights.weight_pct,
                "weight_lb": weights.weight_lb,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": round(result.estimated_cost_usd, 5),
            }))
        else:
            _print_breakdown(path.name, result.categories, weights)
            print(f"  ({result.model}, {result.input_tokens} in / {result.output_tokens} out, "
                  f"${result.estimated_cost_usd:.4f})")

    if not args.json:
        print(f"\n{len(images) - failures}/{len(images)} photos classified, ~${total_cost:.4f} total")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
