"""Mask/area helpers used to turn segmentation output into percentages.

Contamination % is computed by pixel area, not item count, so a single
large contaminant (e.g. a greasy pizza box) is weighted appropriately
against several small correct-stream items. See pipeline/contamination.py
for how these are combined into an audit-level score.
"""
from __future__ import annotations

import numpy as np


def mask_area(mask: np.ndarray) -> int:
    """Pixel count of a binary segmentation mask."""
    return int(np.count_nonzero(mask))


def tarp_region_area(tarp_mask: np.ndarray) -> int:
    """Total pixel area of the isolated tarp region.

    Used as the normalization denominator so contamination % is
    comparable across photos taken at different distances/angles,
    rather than using raw full-image area.
    """
    return mask_area(tarp_mask)
