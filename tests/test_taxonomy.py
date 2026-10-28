import pytest

from waste_audit.classification.taxonomy import TaxonomyResolver
from waste_audit.utils.config import load_taxonomy


def test_taxonomy_loads_from_config():
    taxonomy = load_taxonomy()
    assert "pipette" in taxonomy
    assert taxonomy["pipette"].hazard_flag is True
    assert "aluminum_can" in taxonomy
    assert taxonomy["aluminum_can"].hazard_flag is False


def test_item_is_contaminant_when_stream_mismatches():
    resolver = TaxonomyResolver()
    result = resolver.classify("plastic_bag_film", stream_type="recycling")
    assert result.is_contaminant is True


def test_item_is_not_contaminant_when_stream_matches():
    resolver = TaxonomyResolver()
    result = resolver.classify("aluminum_can", stream_type="recycling")
    assert result.is_contaminant is False


def test_unknown_class_raises_instead_of_guessing():
    resolver = TaxonomyResolver()
    with pytest.raises(KeyError):
        resolver.classify("some_unlabeled_thing", stream_type="recycling")
