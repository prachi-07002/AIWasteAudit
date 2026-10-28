# origin/main integration into figma-ui2

Baseline: `02b9d26` (Figma implementation). Refreshed upstream: `10d3828`.
The branch was clean, one commit ahead and five commits behind upstream.
No applicable AGENTS.md was found in the repository or parent directories.

## Resolution decisions

- `c6f8a85` (older UI rework): preserve the current Figma palette, typography,
  layout, controls and responsive rules instead of restoring the older styling.
- `acf93da` (Material Symbols): retain the escaped `material_icon` helper and
  its narrowly scoped CSS. Use Streamlit's bundled Material Symbols font rather
  than introducing a Google Fonts request. Keep current page icons, category
  configuration and stepper markers unchanged.
- `9dc4399` (camera preview): keep the current camera widget unchanged. The
  incoming cropping, sizing, button styling and 1.5-second startup overlay
  would change the existing appearance and behavior.
- `ea3f5d3` (CSS consolidation): keep all shared CSS centralized in
  `inject_mockup_css`; preserve the Figma variables and selectors.
- `10d3828` is the upstream merge of those changes; integrate its full history
  with a normal two-parent merge into figma-ui2.

All four overlapping files were reviewed, including automatically merged
category icons, the Material helper and stepper changes. The helper's required
`escape` import was retained. Current page code, classifier integration,
correction retention, persistence, dashboard filters, site management,
configuration and audit records remain unchanged from the baseline.

## Validation

- Existing suite: **32 passed** before and after integration. Includes classifier
  mocks, correction retention, save errors, invalid photos, discard/reset,
  date/site/stream/source filtering, historical records and site persistence.
- Pre-merge screenshots of Audit Capture, Dashboard and Site Registry at
  **1440 × 1000** and **390 × 844**. All six post-merge screenshots are
  pixel-identical to the corresponding baseline screenshots.
- Browser workflow: upload → mocked classification → invalid total blocks save
  → corrections → rerun preserves corrections → save → next audit resets state.
- Browser Dashboard: saved mock records appear when their explicit source
  filter is enabled.
- Browser Site Registry: create, search and edit a site; stable ID remains
  disabled during editing; updated name persists.
- Browser camera: synthetic video preview and snapshot work. Physical camera
  hardware, real permission prompts, device switching, and hardware startup
  timing remain unverified.
- Existing site YAML and audit JSONL checksums remain unchanged. Browser writes
  used temporary copies; classification was patched to a mock result. No paid
  model calls were made.
- Material helper rendering/escaping and Git whitespace checks pass.

No deployment or merge into main is part of this integration.
