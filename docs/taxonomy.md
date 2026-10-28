# Taxonomy design notes

The taxonomy is self-defined (`configs/taxonomy.yaml`) rather than pulled
from a standard dataset, since contamination rules vary by hauler/
municipality/institution. Key design decisions:

## Stream-relative contamination

An item's contaminant status is **not** a fixed property of the class —
it depends on which stream (`recycling` / `compost` / `landfill`) the bin
being audited is for. `correct_stream` on each taxonomy class is compared
against the audit's `stream_type` at classification time
(`src/waste_audit/classification/taxonomy.py`).

## Area-based percentages, not item counts

Contamination % is computed from segmentation mask pixel area, not number
of items. A single greasy pizza box contaminates more volume than five
bottle caps — counting items would misrepresent that.
(`src/waste_audit/pipeline/contamination.py`)

## Hazard flag is separate from contaminant status

Some contaminants (pipettes, syringes, batteries) need different handling
than a routine sorting correction — they're a safety issue for whoever
processes the bin. `hazard_flag` is tracked independently so the dashboard
can surface "hazard-flagged incidents" as its own metric, not buried in a
general contamination percentage.

## Adding a new class

1. Add an entry to `configs/taxonomy.yaml` (name, material_category,
   correct_stream, hazard_flag).
2. Add/relabel training examples for it (Roboflow/CVAT) using the exact
   same class name.
3. Regenerate `data/annotations/dataset.yaml` before retraining, so the
   YOLO class list and taxonomy never drift apart.
