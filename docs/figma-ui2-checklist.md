# Figma implementation checklist

Reference: Untitled / audit-screen (0-1), dashboard-screen (3-173), sites-screen (3-408).
Inspected all three complete frames via read-only browser canvas, including below the initial viewport.
All three screens use sidebar and Frame auto layouts. Expanded nested Frame containers in Audit and Sites; the design uses generic Frame names. No separate loading/error/saved frames were shown; those follow the existing workflow.

## Starting point
- Existing figma-ui2 at 94d5d3c, clean working tree; no uncommitted changes were present.
- ui_changes diverges; preserve current shared CSS centralization and classifier integration.
- No AGENTS.md files found in the repository or applicable parent directories.

## Shared design
- Forest sidebar (#15291e), green active actions (#2e8b57), near-white canvas, white bordered rounded cards.
- Neutral sans typography, muted small labels, 1px gray borders, 24–32px spacing.
- Shared sidebar: Audit Capture, Dashboard, Site Registry, local-storage footer.
- Header: title/subtitle and contextual badges; responsive cards and controls.

## Audit Capture — first milestone
- [x] Target location/stream, bag ID/scale weight, upload/camera, image preview.
- [x] Classifier loading, labeled mock fallback, correction queue, live contamination estimate.
- [x] Re-run preserves overrides; retake/upload; discard; validated save; next audit.
- [x] Surface persistence errors; never claim unavailable hazard safety or detections.
- [x] Run complete workflow with mocked classifier before implementing other screens.

## Dashboard
- [x] Date, site, stream filters; consistent metrics and charts.
- [x] Four metrics; contamination trend; category profile by archetype; site comparison.
- [x] Hazard unavailable, historical provenance and malformed/empty records handled.

## Site Registry
- [x] Deployed Audit Sites table with search/details; Create Audit Site form alongside.
- [x] Name, archetype, bin configuration, optional coordinates, cancel/save.
- [x] Persistent YAML edits, stable identifiers, validation.

## Verification
- [x] Relevant existing and targeted tests with mocked model calls.
- [x] Browser inspection of all pages, narrow window, errors/empty states.
- [x] Document limits: no boxes/item confidence/hazards; no fabricated trend deltas or mass claims.


## Verification results and deliberate differences
- 32 offline tests (24 existing plus 8 targeted) cover JSONL persistence/failure, malformed history, source filters, date/site/stream filtering, category aggregation, site validation/updates, review totals, correction retention, discard, corrupt photos and next-audit reset.
- Real browser: synthetic upload → mock classification → corrections → rerun → save → new audit; saved record reload on Dashboard; site invalid submission/edit/cancel; all pages inspected at desktop and 390px widths without overall horizontal overflow.
- The one browser-test audit was removed by exact provenance/identifier matching. Existing audit exports and site configuration remain unchanged.
- Camera permission state is visible, but live camera capture could not be completed in this browser. Real Claude calls were intentionally not made. No YOLO implementation or training was added.
- Figma's item boxes/confidence/hazard toggles are replaced by honest category-percentage review; contamination is a provisional visible-area estimate, not a measured mass fraction. Hazard assessment remains unavailable.
- Dashboard confidence threshold and fabricated period deltas are omitted. Mock audits and older records of unknown provenance require explicit inclusion. Historical false hazard placeholders do not count as safety assessments.
- Site IDs/default streams and optional coordinates extend Figma's form to preserve compatibility with configuration and audit exports. Tables may scroll within their own bounds at small sizes; overall pages do not.
- CSS stays in inject_mockup_css; panel and page_shell provide scoped reusable layouts using functional Streamlit controls. System sans typography avoids a network font dependency.

## Run
From the repository root with Python 3.10+ and the project dependencies installed:

```sh
python -m streamlit run app/main.py
```

Streamlit 1.50+ is required. For UI-only setup without optional YOLO training dependencies:

```sh
python -m pip install 'streamlit>=1.50' pandas plotly Pillow PyYAML anthropic python-dotenv pytest
python -m pytest
```

The existing Claude integration reads ANTHROPIC_API_KEY from the environment/.env. Without a configured model it shows a labeled mock fallback. Do not set an API key when checking mock behavior. Changes remain on figma-ui2, unmerged and unpushed.
