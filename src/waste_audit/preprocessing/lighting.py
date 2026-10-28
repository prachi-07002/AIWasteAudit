"""Normalize lighting/exposure so material color isn't a confound across
audits taken outdoors, indoors, at different times of day, etc.
"""
from __future__ import annotations

import cv2
import numpy as np


def normalize_lighting(image: np.ndarray, clip_limit: float = 2.0, tile_grid_size: tuple[int, int] = (8, 8)) -> np.ndarray:
    """Apply CLAHE (contrast-limited adaptive histogram equalization) on
    the luminance channel only, to avoid distorting color used for
    material classification.
    """
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    l_eq = clahe.apply(l_channel)
    merged = cv2.merge((l_eq, a_channel, b_channel))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
