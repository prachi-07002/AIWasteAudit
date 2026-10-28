# Waste Audit Classifier

Computer-vision system for auditing recycling/compost contamination from tarp
photos. Detects and segments individual items, classifies material +
contaminant status against a self-defined taxonomy, computes area-based
contamination percentages, and links results back to bin/site context
(e.g., "pipettes near the lab", "food waste near the cafe") for
source-attribution reporting.

## How it works

1. **Preprocess** — correct perspective, isolate the tarp region, normalize
   lighting (`src/waste_audit/preprocessing`).
2. **Detect + segment** — YOLO-seg model finds individual items and their
   pixel masks (`src/waste_audit/detection`).
3. **Classify** — each detected item is mapped to a taxonomy class
   (material, contaminant flag, hazard flag) (`src/waste_audit/classification`).
4. **Score** — contamination % is computed from mask area, not item count
   (`src/waste_audit/pipeline`).
5. **Persist** — audit results + site metadata are saved to Postgres
   (`src/waste_audit/db`).
6. **Review + report** — Streamlit app for human-in-the-loop correction and
   a dashboard for trends by site/contaminant/time (`app/`).

## Repo layout

```
waste-audit-classifier/
├── app/                  Streamlit app (capture/audit mode + dashboard mode)
├── configs/              Taxonomy, site list, model/training configs (YAML)
├── data/
│   ├── raw/              Original, untouched audit photos
│   ├── processed/        Perspective-corrected / normalized images
│   ├── annotations/      Label files (COCO/YOLO format, from Roboflow/CVAT)
│   └── exports/          Generated reports / CSV exports
├── models/
│   ├── detection/        YOLO-seg training configs + run outputs
│   ├── classification/   (optional) second-stage classifier training
│   └── weights/          Saved model weights (gitignored, use Git LFS or DVC)
├── src/waste_audit/      Installable package: all core logic lives here
├── scripts/              One-off / CLI scripts (train, batch-infer, seed DB)
├── notebooks/            Exploratory analysis, dataset audits
├── tests/                Unit tests
└── docs/                 Taxonomy definitions, site schema, design notes
```

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .              # makes `waste_audit` importable
cp .env.example .env          # add ANTHROPIC_API_KEY, DB connection string, etc.
python scripts/init_db.py     # create tables
streamlit run app/main.py
```

To run the app without training a detector, you only need `ANTHROPIC_API_KEY`
— the interim classifier (below) covers steps 2-3. The DB step is optional
until you want audits persisted. `ultralytics`, `opencv`, and `tensorflow`
are only needed for the YOLO-seg path and can be skipped for now.

### Interim classifier

Step 2-3 (detect + classify) has no trained checkpoint yet, so
`src/waste_audit/classification/vlm_classifier.py` stands in: it sends the bag
photo to Claude and gets back a percentage breakdown across the hand-sort
sheet's categories, defined with their coarse groups and recycling/landfill
streams in `configs/sort_categories.yaml`. Configured under `vlm:` in
`configs/model.yaml`; `vlm.category_set` picks `fine` (the 13 sort-sheet
categories) or `coarse` (their groups). A fine result or hand sort rolls up to
groups with `SortScheme.to_groups()`, so both sets score against the same
hand sort.

A provisional weight estimate (`src/waste_audit/pipeline/weight.py`) turns area
% into weight % and pounds using per-material weighting factors, also in
`configs/sort_categories.yaml`. The results screen shows it next to the area %.
`scripts/compare_hand_sort.py` compares it to a bag's hand-sort weights
(per-category signed error and the recycling vs. landfill split).

It is a stopgap, not the destination. It estimates visible surface area by
eye — no per-item detection, no masks, and **no hazard flagging**, so it will
not catch pipettes, batteries, or sharps. Those remain the job of the trained
detector. Without an API key the app falls back to placeholder values and
labels them as such on the results screen.

## Status

Skeleton stage — see `docs/taxonomy.md` and `docs/site_schema.md` for the
data model this is built around, and `docs/roadmap.md` for what's stubbed
vs. implemented.
