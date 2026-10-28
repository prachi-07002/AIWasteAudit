"""Thin wrapper around an Ultralytics YOLO-seg model.

Detection and material/contaminant classification are combined in one
model pass (class list = configs/taxonomy.yaml). If class confusion
between visually similar materials becomes a problem later (e.g. paper vs.
cardboard), split into a second classification stage — see
src/waste_audit/classification/ for where that would plug in.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Detection:
    class_name: str
    confidence: float
    mask: np.ndarray          # binary mask, same H x W as source image
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2


class WasteDetector:
    """Loads a trained YOLO-seg checkpoint and runs inference on an image."""

    def __init__(self, weights_path: str | Path, confidence_threshold: float = 0.35, iou_threshold: float = 0.5):
        self.weights_path = Path(weights_path)
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self._model = None  # lazy-loaded, see load()

    def load(self) -> None:
        """Load the model into memory.

        Deferred from __init__ so the class can be imported/instantiated
        (e.g. in tests) without requiring weights to exist on disk yet.
        """
        from ultralytics import YOLO  # local import: heavy dependency

        self._model = YOLO(str(self.weights_path))

    def predict(self, image: np.ndarray) -> list[Detection]:
        """Run inference on a single BGR image and return per-item detections.

        TODO: implement once a trained checkpoint exists.
          - self._model(image, conf=self.confidence_threshold, iou=self.iou_threshold)
          - map result.masks / result.boxes / result.names into Detection objects
        """
        if self._model is None:
            self.load()
        raise NotImplementedError("Wire up once a trained YOLO-seg checkpoint is available.")
