"""Draw detection masks/boxes over an audit image for review in the UI.

Kept separate from the pages so both the Audit page and any future
export/report generation can reuse the same rendering logic.
"""
from __future__ import annotations

import cv2
import numpy as np

# Contaminant items in red, correct-stream items in green, hazard-flagged
# items get a thicker border regardless of contaminant status.
CONTAMINANT_COLOR = (0, 0, 255)   # BGR
CLEAN_COLOR = (0, 200, 0)
HAZARD_BORDER_THICKNESS = 4
DEFAULT_THICKNESS = 2


def draw_overlays(image: np.ndarray, detections: list, classified: list) -> np.ndarray:
    """Return a copy of `image` with mask contours + labels drawn on.

    Args:
        detections: list of detection.Detection
        classified: parallel list of classification.taxonomy.ClassifiedItem
    """
    overlay = image.copy()
    for det, cls in zip(detections, classified):
        color = CONTAMINANT_COLOR if cls.is_contaminant else CLEAN_COLOR
        thickness = HAZARD_BORDER_THICKNESS if cls.hazard_flag else DEFAULT_THICKNESS

        contours, _ = cv2.findContours(det.mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, color, thickness)

        x1, y1, _, _ = det.bbox
        label = f"{cls.class_name} ({det.confidence:.2f})"
        cv2.putText(overlay, label, (x1, max(y1 - 8, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    return overlay
