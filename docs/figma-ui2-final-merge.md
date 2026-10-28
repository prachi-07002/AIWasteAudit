# Figma UI merge into main — October 25, 2026

Merged `figma-ui2` at `75bd0ba` into main at `c422037`, retaining the October 21
category refinement and weight calculation work (`0b94f37`).

## Resolutions

- Retained Figma shared CSS, page shell, navigation, responsive cards, capture,
  review, dashboard, and site registry. The shared styling/layout helpers are
  unchanged from figma-ui2.
- Retained main's configured fine/coarse category lists, mock breakdowns,
  classifier schema and prompts, stream mapping, weighting calculations,
  classifier CLI and hand-sort comparison. Configurations and core category and
  weight modules are unchanged from main.
- Added estimated material weights to the Figma review card. Manual corrections
  drive the estimates. Saved audits include category_set, weight_factor,
  est_weight_pct and est_weight_lb, alongside original and corrected area shares.
- Retained the Figma classifier environment-loading fix and its error reporting.
- Updated the Figma dashboard's top contaminant calculation to use each new
  record's fine/coarse stream mappings. Historical generic-category records
  retain their original interpretation.
- Compost has no sort-sheet mapping: review shows n/a; saved records retain a
  null contamination score. Dashboard audit counts, exports and category charts
  retain these records, while contamination averages exclude undefined scores.
  Missing or otherwise invalid contamination scores are still rejected.
- Kept Figma's interactive dashboard charts instead of displaying main's older
  mock chart images. The original image files remain in the repository.

## Validation

- `python -m pytest -q`: **92 passed**.
- Workflow tests cover correction retention on rerun, invalid totals, storage
  failures, save/reset, site editing, provenance and dashboard filters.
- Added end-to-end Streamlit tests for review → save → reload → dashboard and
  CSV export availability, for fine/coarse categories and recycling/compost.
- Saved category factors and weights are checked against the weight estimator;
  category weights total the measured bag weight within storage rounding.
- Verified Figma styling/layout helpers and main category/contamination helpers
  by comparing their parsed function bodies with the source branches.
- Git whitespace checks pass. No paid classifier calls were made; automated UI
  workflows used synthetic images and isolated temporary audit files.
- Physical camera operation and a live model call were not tested in this merge.
