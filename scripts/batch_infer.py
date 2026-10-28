"""Run the audit pipeline over a folder of existing photos and write
results to the DB — for backfilling historical audit photos once a
trained model + site attribution exist.

Usage:
    python scripts/batch_infer.py --images data/raw --site-id example-lab-220 --stream recycling
"""
import argparse
from pathlib import Path

import cv2

from waste_audit.classification.taxonomy import TaxonomyResolver
from waste_audit.detection.detector import WasteDetector
from waste_audit.pipeline.run_audit import run_audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", required=True, help="Folder of audit photos")
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--stream", required=True, choices=["recycling", "compost", "landfill"])
    parser.add_argument("--weights", default="models/weights/yolo_seg_contamination.pt")
    args = parser.parse_args()

    detector = WasteDetector(weights_path=args.weights)
    resolver = TaxonomyResolver()

    image_paths = sorted(Path(args.images).glob("*.jpg")) + sorted(Path(args.images).glob("*.png"))
    print(f"Found {len(image_paths)} images.")

    for path in image_paths:
        image = cv2.imread(str(path))
        result = run_audit(image, stream_type=args.stream, detector=detector, resolver=resolver)
        print(f"{path.name}: {result.contamination.contamination_pct}% contamination, "
              f"{result.n_items_detected} items, hazard={result.contamination.hazard_flagged}")
        # TODO: persist Audit + DetectionRecord rows via waste_audit.db.session


if __name__ == "__main__":
    main()
