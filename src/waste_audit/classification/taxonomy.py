"""Resolve a detected class name into contaminant/hazard status, relative
to the stream the audit was taken for.

A detected class is a contaminant if its `correct_stream` (from
configs/taxonomy.yaml) does not match the audit's actual `stream_type`
(e.g. a recycling-bin audit finding a `plastic_bag_film`, whose
correct_stream is `landfill`, is a contaminant; the same item in a
landfill-bin audit is not).
"""
from __future__ import annotations

from dataclasses import dataclass

from waste_audit.utils.config import TaxonomyClass, load_taxonomy


@dataclass
class ClassifiedItem:
    class_name: str
    material_category: str
    is_contaminant: bool
    hazard_flag: bool


class TaxonomyResolver:
    def __init__(self, taxonomy: dict[str, TaxonomyClass] | None = None):
        self.taxonomy = taxonomy or load_taxonomy()

    def classify(self, class_name: str, stream_type: str) -> ClassifiedItem:
        tax_class = self.taxonomy.get(class_name)
        if tax_class is None:
            # Unknown class from the model — surface loudly rather than
            # silently guessing, so it gets added to the taxonomy/labels.
            raise KeyError(f"'{class_name}' not found in taxonomy.yaml — add it before use.")

        is_contaminant = tax_class.correct_stream != stream_type
        return ClassifiedItem(
            class_name=class_name,
            material_category=tax_class.material_category,
            is_contaminant=is_contaminant,
            hazard_flag=tax_class.hazard_flag,
        )
