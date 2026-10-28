"""Correct camera-angle perspective distortion so tarp area/proportions
are consistent across audits taken from different heights/angles.
"""
from __future__ import annotations

import cv2
import numpy as np


def correct_perspective(image: np.ndarray, src_corners: np.ndarray, output_size: tuple[int, int]) -> np.ndarray:
    """Warp `image` so the tarp corners map to a rectangle.

    Args:
        image: BGR input image.
        src_corners: 4x2 array of (x, y) tarp corner points in the source
            image, ordered [top-left, top-right, bottom-right, bottom-left].
            TODO: auto-detect these (e.g. largest quadrilateral contour)
            instead of requiring manual input, once tarp corners are
            reliably distinguishable from background.
        output_size: (width, height) of the corrected output image.

    Returns:
        Perspective-corrected BGR image.
    """
    w, h = output_size
    dst_corners = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src_corners.astype(np.float32), dst_corners)
    return cv2.warpPerspective(image, matrix, output_size)
