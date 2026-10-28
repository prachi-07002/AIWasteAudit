# Site / location schema

"Where" in this project means the physical bin/location an audit photo was
taken at (e.g. a specific lab room, a cafe), not GPS precision or position
within the pile. `site_type` (lab, food_service, office, dorm, ...) is the
primary grouping field for source-attribution reporting — it's what lets
the dashboard answer "labs have a pipette problem, cafes have a food-waste
problem" without needing exact coordinates.

## Workflow

1. Define your real sites in `configs/sites.yaml` before processing bulk
   historical photos. Retrofitting site attribution onto already-captured,
   unlabeled photos is much more work than tagging at capture time.
2. `python scripts/seed_sites.py` loads them into the `sites` table.
3. Every audit (`Audit` row) is attributed to exactly one `site_id`. If a
   historical photo's location is genuinely unknown, consider an explicit
   `unknown` site rather than a null/guessed value, so downstream
   contamination-by-site queries don't silently misattribute it.

## GPS

Optional (`gps_lat`/`gps_lon` on `Site`). Only worth populating if
map-based reporting is a priority — `site_type` alone drives most of the
source-attribution use cases described in the project brief (pipettes near
labs, food waste near cafes).
