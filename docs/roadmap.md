# Roadmap

## Skeleton stage (current)

- [x] Repo structure
- [x] Taxonomy + site config schema
- [x] DB models (Site / Audit / DetectionRecord)
- [x] Pipeline scaffolding (preprocessing -> detection -> classification ->
      contamination scoring), with contamination math implemented and
      tested against synthetic inputs
- [x] Streamlit skeleton (Audit + Dashboard pages, stubbed inference)

## Next: data foundation

- [ ] Audit existing photo set: consistent angle/tarp/lighting? EXIF/GPS
      present? Can photos be mapped to real sites?
- [ ] Finalize `configs/sites.yaml` with real site list
- [ ] Finalize `configs/taxonomy.yaml` class list against a sample of real
      photos (don't lock it in from theory alone)
- [ ] Set up Roboflow (or CVAT) project, label an initial batch
      (segmentation/polygon, not just boxes)
- [ ] Write `scripts/build_yolo_dataset_yaml.py` to generate
      `data/annotations/dataset.yaml` from `configs/taxonomy.yaml`, so the
      two never drift apart

## Interim: hosted VLM classifier (done)

- [x] `vlm_classifier.py` — Claude vision call returning generic-category
      percentages, wired into the Audit page with mock fallback
- [ ] Run it over a sample of real audit photos and eyeball whether the
      breakdowns are usable — this is the check that tells you how much the
      trained detector actually has to beat
- [x] Replace the six placeholder categories with the hand-sort sheet's
      categories (`configs/sort_categories.yaml`), with coarse groups and
      streams; `vlm.category_set` switches between fine and coarse
- [x] Provisional weight estimate (area % x material factor, scaled to bag
      weight) and hand-sort comparison (`pipeline/weight.py`,
      `scripts/compare_hand_sort.py`)
- [ ] Replace the provisional weighting factors with ones fit on staged scenes
- [ ] Confirm recycling vs. landfill for paper cups, glass, and #5 plastics
      (`stream_confirmed: false` in `configs/sort_categories.yaml`)

## Next: modeling

- [ ] Train initial YOLOv8s-seg checkpoint on labeled batch
- [ ] Evaluate recall specifically on rare/small/hazard classes (pipettes,
      batteries) — these matter most and are likely to be the hardest
- [ ] Calibrate `tarp_hsv_range` per real tarp material/color;
      confirm `isolate_tarp` mask quality across a range of lighting
      conditions in the actual photo set
- [ ] Wire up `WasteDetector.predict()` and remove the NotImplementedError

## Next: app

- [ ] Wire "Run detection" button in Audit page to `run_audit()`
- [ ] Build the review/correction table (`st.data_editor`) and persist
      corrections to `DetectionRecord.corrected_class_name`
- [ ] Build dashboard queries once real audit data exists
- [ ] Decide whether corrected labels feed back into retraining data
      automatically or via a manual export step

## Open questions (flagged during design, not yet decided)

- Do contamination percentages need to reflect a specific hauler/MRF's
  published rules, or is the taxonomy purely internal?
- Is item weight/volume estimation needed eventually, or is area-based %
  sufficient for the project's goals?
