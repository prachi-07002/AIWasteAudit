"""Compute audit-level contamination metrics from per-item detections.

Percentages are area-based (mask pixels), not count-based — a single
large contaminant should outweigh several small correct-stream items.
See docs/taxonomy.md for the reasoning.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from waste_audit.classification.taxonomy import ClassifiedItem
from waste_audit.detection.detector import Detection
from waste_audit.utils.geometry import mask_area


@dataclass
class ContaminationResult:
    total_area: int
    contaminant_area: int
    contamination_pct: float
    hazard_flagged: bool
    breakdown_by_class: dict[str, float]  # class_name -> % of total area


def compute_contamination(
    detections: list[Detection],
    classified: list[ClassifiedItem],
    tarp_area: int | None = None,
) -> ContaminationResult:
    """Combine detection masks + classification into a contamination score.

    Args:
        detections: raw detector output (for mask areas).
        classified: parallel list of ClassifiedItem, same order/length as
            `detections`.
        tarp_area: total tarp-region pixel area (from
            preprocessing.tarp_segmentation) to use as the denominator.
            Falls back to sum of detected item areas if not provided —
            less accurate, since it ignores empty tarp space, but usable
            before tarp segmentation is wired in.
    """
    if len(detections) != len(classified):
        raise ValueError("detections and classified must be the same length and order")

    areas = [mask_area(d.mask) for d in detections]
    total_area = tarp_area if tarp_area is not None else sum(areas)

    contaminant_area = sum(a for a, c in zip(areas, classified) if c.is_contaminant)
    hazard_flagged = any(c.hazard_flag for c in classified)

    breakdown: dict[str, float] = {}
    for area, item in zip(areas, classified):
        pct = (area / total_area * 100) if total_area else 0.0
        breakdown[item.class_name] = breakdown.get(item.class_name, 0.0) + pct

    contamination_pct = (contaminant_area / total_area * 100) if total_area else 0.0

    return ContaminationResult(
        total_area=total_area,
        contaminant_area=contaminant_area,
        contamination_pct=round(contamination_pct, 2),
        hazard_flagged=hazard_flagged,
        breakdown_by_class={k: round(v, 2) for k, v in breakdown.items()},
    )
