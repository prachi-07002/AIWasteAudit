import numpy as np

from waste_audit.classification.taxonomy import ClassifiedItem
from waste_audit.detection.detector import Detection
from waste_audit.pipeline.contamination import compute_contamination


def _fake_detection(mask_shape, area_px, class_name):
    mask = np.zeros(mask_shape, dtype=np.uint8)
    mask.flat[:area_px] = 1
    return Detection(class_name=class_name, confidence=0.9, mask=mask, bbox=(0, 0, 10, 10))


def test_contamination_pct_is_area_weighted_not_count_weighted():
    # One large contaminant (pizza box) should outweigh several small
    # correct items (bottle caps), even though it's outnumbered 1-to-3.
    detections = [
        _fake_detection((100, 100), area_px=4000, class_name="cardboard_greasy"),   # large contaminant
        _fake_detection((100, 100), area_px=100, class_name="aluminum_can"),
        _fake_detection((100, 100), area_px=100, class_name="aluminum_can"),
        _fake_detection((100, 100), area_px=100, class_name="aluminum_can"),
    ]
    classified = [
        ClassifiedItem("cardboard_greasy", "paper", is_contaminant=True, hazard_flag=False),
        ClassifiedItem("aluminum_can", "metal", is_contaminant=False, hazard_flag=False),
        ClassifiedItem("aluminum_can", "metal", is_contaminant=False, hazard_flag=False),
        ClassifiedItem("aluminum_can", "metal", is_contaminant=False, hazard_flag=False),
    ]

    result = compute_contamination(detections, classified)

    # 4000 / (4000 + 300) total area
    assert result.contamination_pct > 90.0
    assert result.hazard_flagged is False


def test_hazard_flag_propagates_even_at_small_area():
    detections = [
        _fake_detection((100, 100), area_px=9000, class_name="aluminum_can"),
        _fake_detection((100, 100), area_px=10, class_name="pipette"),
    ]
    classified = [
        ClassifiedItem("aluminum_can", "metal", is_contaminant=False, hazard_flag=False),
        ClassifiedItem("pipette", "plastic", is_contaminant=True, hazard_flag=True),
    ]

    result = compute_contamination(detections, classified)

    assert result.hazard_flagged is True
    # contamination_pct should still be small in area terms, but the
    # hazard flag must not depend on area proportion.
    assert result.contamination_pct < 1.0


def test_mismatched_list_lengths_raise():
    import pytest

    detections = [_fake_detection((10, 10), 5, "aluminum_can")]
    classified = []

    with pytest.raises(ValueError):
        compute_contamination(detections, classified)
