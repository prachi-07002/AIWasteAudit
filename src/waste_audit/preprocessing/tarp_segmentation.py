"""Isolate the tarp region from the background so downstream area
calculations use the tarp as the denominator, not the full raw image.

Approach: color thresholding tuned to the known tarp color, refined with
GrabCut if needed. Swap in a trained segmentation model later if a fixed
color threshold proves unreliable across lighting conditions.
"""
from __future__ import annotations

import cv2
import numpy as np


def isolate_tarp(image: np.ndarray, tarp_hsv_range: tuple[tuple[int, int, int], tuple[int, int, int]]) -> np.ndarray:
    """Return a binary mask of the tarp region.

    Args:
        image: BGR image as loaded by cv2.imread.
        tarp_hsv_range: ((h_low, s_low, v_low), (h_high, s_high, v_high))
            HSV bounds for the tarp color. Calibrate against your actual
            tarp material/color — this is the single biggest source of
            error if lighting varies a lot between audit sites.

    Returns:
        uint8 mask, same H x W as image, 255 = tarp, 0 = background.

    TODO: fall back to GrabCut (cv2.grabCut) when color thresholding
    produces a mask with implausible area (e.g. < 10% or > 95% of frame),
    as a sanity check against bad HSV calibration.
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lower, upper = np.array(tarp_hsv_range[0]), np.array(tarp_hsv_range[1])
    mask = cv2.inRange(hsv, lower, upper)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    return mask


def largest_contour_mask(mask: np.ndarray) -> np.ndarray:
    """Keep only the largest connected region in a binary mask.

    Useful after isolate_tarp() to drop small stray regions that also
    happen to match the tarp color (e.g. a blue plastic item).
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return mask
    largest = max(contours, key=cv2.contourArea)
    clean = np.zeros_like(mask)
    cv2.drawContours(clean, [largest], -1, 255, thickness=cv2.FILLED)
    return clean
