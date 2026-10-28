"""End-to-end: raw photo -> preprocessed image -> detections -> classified
items -> contamination result -> (optionally) persisted audit record.

This is the function the Streamlit capture page and any batch/CLI script
should call, so preprocessing/inference logic lives in exactly one place.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from waste_audit.classification.taxonomy import TaxonomyResolver
from waste_audit.detection.detector import WasteDetector
from waste_audit.pipeline.contamination import ContaminationResult, compute_contamination
from waste_audit.preprocessing.lighting import normalize_lighting
from waste_audit.preprocessing.tarp_segmentation import isolate_tarp, largest_contour_mask
from waste_audit.utils.geometry import tarp_region_area


@dataclass
class AuditRunResult:
    contamination: ContaminationResult
    n_items_detected: int


def run_audit(
    image: np.ndarray,
    stream_type: str,
    detector: WasteDetector,
    resolver: TaxonomyResolver,
    tarp_hsv_range: tuple[tuple[int, int, int], tuple[int, int, int]] | None = None,
) -> AuditRunResult:
    """Run the full pipeline on a single audit photo.

    Args:
        image: BGR image (already perspective-corrected, if applicable —
            perspective correction requires knowing tarp corners and is
            expected to happen at capture time / a prior step).
        stream_type: which stream this audit is for ('recycling', 'compost',
            'landfill') — determines contaminant status per item.
        detector: loaded WasteDetector instance.
        resolver: TaxonomyResolver instance.
        tarp_hsv_range: HSV bounds for tarp color, if tarp-area
            normalization should be used. If None, contamination % is
            normalized against total detected item area instead.
    """
    normalized = normalize_lighting(image)

    tarp_area = None
    if tarp_hsv_range is not None:
        tarp_mask = largest_contour_mask(isolate_tarp(normalized, tarp_hsv_range))
        tarp_area = tarp_region_area(tarp_mask)

    detections = detector.predict(normalized)
    classified = [resolver.classify(d.class_name, stream_type) for d in detections]

    contamination = compute_contamination(detections, classified, tarp_area=tarp_area)

    return AuditRunResult(contamination=contamination, n_items_detected=len(detections))
