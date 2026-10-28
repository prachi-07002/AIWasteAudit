"""Train the YOLO-seg detector on data/annotations/dataset.yaml.

Usage:
    python scripts/train_detector.py --config configs/model.yaml

TODO:
    - generate data/annotations/dataset.yaml from configs/taxonomy.yaml
      (see scripts/build_yolo_dataset_yaml.py, not yet written) so class
      lists never drift between taxonomy and training data.
    - wire up ultralytics YOLO(...).train(...) using configs/model.yaml
    - log runs (e.g. to models/detection/runs/) for comparison across
      dataset versions
"""
import argparse

from waste_audit.utils.config import load_model_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/model.yaml")
    args = parser.parse_args()

    config = load_model_config(args.config)
    raise NotImplementedError(
        "Wire up ultralytics YOLO training once data/annotations/dataset.yaml exists. "
        f"Loaded config: {config}"
    )


if __name__ == "__main__":
    main()
