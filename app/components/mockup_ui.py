"""Centralized Figma palette, responsive layout, navigation and category helpers."""
from __future__ import annotations

import textwrap
from typing import Any
from html import escape

try:
    import streamlit as st
except ImportError:
    st = None

from waste_audit.classification.sort_categories import MIXED_STREAM, load_sort_scheme
from waste_audit.classification.vlm_classifier import active_category_set

# Placeholder breakdown over the fine sort categories, shown when no model is
# configured. Rolled up to groups when the app runs the coarse set.
# tests/test_audit_ui.py checks these keys match configs/sort_categories.yaml.
MOCK_FINE_PCT: dict[str, float] = {
    "paper": 14.0,
    "cardboard": 12.0,
    "plastic_1": 10.0,
    "plastic_2_jugs": 4.0,
    "plastic_5": 5.0,
    "metal_cans": 6.0,
    "glass_bottles": 5.0,
    "plastic_cups": 6.0,
    "paper_cups": 7.0,
    "styrofoam": 3.0,
    "soft_plastics": 9.0,
    "organics": 8.0,
    "landfill_office": 11.0,
}

CATEGORY_SET = active_category_set()


def _mock_pct(category_set: str) -> dict[str, float]:
    if category_set == "fine":
        return dict(MOCK_FINE_PCT)
    return load_sort_scheme().to_groups(MOCK_FINE_PCT)


def _build_category_config(category_set: str) -> list[dict[str, Any]]:
    scheme = load_sort_scheme()
    labels = scheme.labels(category_set)
    icons = scheme.icons(category_set)
    defaults = _mock_pct(category_set)
    return [
        {"key": key, "label": labels[key], "default_pct": defaults.get(key, 0.0), "icon": icons[key]}
        for key in scheme.keys(category_set)
    ]


# Categories the results screen renders, for the configured category set.
MOCKUP_CATEGORIES = _build_category_config(CATEGORY_SET)


def material_icon(name: str, class_name: str = "") -> str:
    """Return a decorative Material Symbols icon for custom HTML content."""
    classes = "material-symbols-rounded"
    if class_name:
        classes += f" {escape(class_name, quote=True)}"
    return f'<span class="{classes}" aria-hidden="true">{escape(name)}</span>'


def render_html(content: str) -> None:
    """Render raw HTML/CSS without Markdown parsing converting indented lines into code blocks."""
    if st is None:
        return
    dedented = textwrap.dedent(content).strip()
    if hasattr(st, "html"):
        st.html(dedented)
    else:
        st.markdown(dedented, unsafe_allow_html=True)


def run_mock_classifier(image_bytes: bytes | None = None) -> dict[str, float]:
    """Stand-in for a real inference call: MOCK_FINE_PCT in the active category set."""
    return {c["key"]: c["default_pct"] for c in MOCKUP_CATEGORIES}


def inject_mockup_css() -> None:
    """Inject shared canvas, sidebar, controls and reusable panel styling."""
    css_content = """
<style>
/* Upstream icon helper uses Streamlit's bundled Material Symbols font.
   Current Figma controls keep their existing icons. */
  .material-symbols-rounded {
    font-family: 'Material Symbols Rounded';
    font-weight: normal;
    font-style: normal;
    font-size: 24px;
    line-height: 1;
    letter-spacing: normal;
    text-transform: none;
    display: inline-block;
    white-space: nowrap;
    word-wrap: normal;
    direction: ltr;
    font-feature-settings: 'liga';
    -webkit-font-smoothing: antialiased;
    vertical-align: middle;
    font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
  }
:root {
 --bg:#f7f8f6; --surface:#fff; --surface-raised:#fff; --ink:#242925;
 --ink-muted:#7c847e; --ink-faint:#939b95; --rule:#e0e5e0; --rule-strong:#d6ddd6;
 --accent:#2e8b57; --accent-ink:#fff; --accent-soft:#e8f4ec; --warn:#d99a27;
 --warn-soft:#fff4cf; --danger:#df515b; --sidebar:#15291e;
 --radius-sm:7px; --radius-md:14px;
 --font-ui:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
 --font-data:ui-monospace,SFMono-Regular,Consolas,monospace;
}
.stApp {background:var(--bg);color:var(--ink);font-family:var(--font-ui)}
.stApp [data-testid="stHeader"] {background:transparent}
.stApp [data-testid="stMainBlockContainer"] {max-width:1320px;padding:2.5rem 3rem 4rem}
.stApp h1,.stApp h2,.stApp h3,.stApp p,.stApp label {font-family:var(--font-ui)}
.stApp [data-testid="stSidebar"] {background:var(--sidebar);color:#fff;min-width:240px;max-width:260px}
.stApp [data-testid="stSidebarNav"] {display:none}
.stApp [data-testid="stSidebar"] [data-testid="stPageLink"] a {color:#e7eee9;padding:12px;border-radius:8px;margin-bottom:6px}
.stApp [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover,
.stApp [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {background:var(--accent)}
.stApp [data-testid="stSidebar"] [data-testid="stPageLink"] p,
.stApp [data-testid="stSidebar"] [data-testid="stIconMaterial"] {color:#fff}
.stApp [data-testid="stSidebarUserContent"] {padding-top:1.8rem}
.stApp .st-key-nav_active [data-testid="stPageLink"] a {background:var(--accent)!important}
.brand {font-size:23px;font-weight:750;padding:4px 0 42px;color:#fff}
.brand-icon {display:inline-flex;padding:6px 10px;background:var(--accent);border-radius:7px;margin-right:8px}
.nav-label {color:#9cad9f;font-size:11px;letter-spacing:.05em;margin-bottom:14px}
.sidebar-footer {margin-top:max(24px,calc(100vh - 550px));border-top:1px solid #34483a;padding-top:18px;color:#dbe6de;font-size:12px}
.sidebar-footer small {color:#9cad9f}
.page-header {display:flex;justify-content:space-between;align-items:center;gap:16px;border-bottom:1px solid var(--rule);padding:0 0 22px;margin-bottom:20px;flex-wrap:wrap}
.page-header h1 {font-size:26px;line-height:1.3;margin:0;font-weight:720}
.page-header p {font-size:13px;color:var(--ink-muted);margin:4px 0 0}
.header-tags {display:flex;gap:8px;flex-wrap:wrap}
.header-tags span {font-size:11px;background:#f2f4f1;border:1px solid var(--rule);border-radius:5px;padding:5px 9px;color:#58645b}
.stApp [class*="st-key-panel_"] {background:var(--surface);border-color:var(--rule)!important;border-radius:var(--radius-md)}
.stApp [data-testid="stMetric"] {border:1px solid var(--rule);border-top:3px solid var(--accent);border-radius:9px;padding:16px;background:#fff}
.stApp [data-testid="stMetricValue"] {font-size:28px;font-weight:700}
.stApp [data-testid="stMetricLabel"] {color:var(--ink-muted);font-size:12px}
.stApp [data-testid="stButton"] button {border-radius:7px;min-height:42px;font-weight:600;border-color:var(--rule-strong)}
.stApp [data-testid="stButton"] button[kind="primary"] {background:var(--accent);border-color:var(--accent);color:#fff}
.stApp [data-testid="stTextInput"] input,.stApp [data-testid="stNumberInput"] input {background:#f7f8f6;color:var(--ink)}
.stApp [data-baseweb="select"]>div {background:#f7f8f6}
.stApp [data-testid="stImage"] img {border-radius:10px;max-height:540px;object-fit:contain}
.stApp h2 {font-size:20px}.stApp h3 {font-size:17px}
.stApp [data-testid="stCaptionContainer"] {color:var(--ink-muted)}
.audit-card {background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius-md);padding:22px;margin-bottom:20px}
.scan-frame {border:1px dashed var(--rule-strong);border-radius:10px;min-height:220px;display:flex;align-items:center;justify-content:center;background:#f5f7f4;text-align:center;color:var(--ink-muted);padding:30px}
.photo-placeholder-icon {display:block;font-size:32px;margin-bottom:12px}
.cat-content {padding:7px 0}.cat-name-text {font-size:14px;font-weight:600}
.cat-orig-text {font-size:11px;color:var(--ink-muted)}
.cat-bar-bg {height:5px;background:var(--rule);border-radius:3px;max-width:240px;margin-top:8px;overflow:hidden}
.cat-bar-fill {height:100%;background:var(--accent);border-radius:3px}
.cat-badge-container {padding-top:12px}
.badge-estimate,.badge-corrected {font-size:11px;border-radius:20px;padding:4px 8px;white-space:nowrap;background:var(--warn-soft);color:#906b13}
.badge-corrected {background:var(--accent-soft);color:var(--accent)}
.live-summary {background:var(--sidebar);border-radius:10px;color:white;display:flex;justify-content:space-between;align-items:center;padding:20px;gap:20px;flex-wrap:wrap;margin:12px 0}
.live-summary small {color:#a8baad}.live-summary strong {color:#f28787;font-size:27px;display:block}
@media(max-width:850px) {
 .stApp [data-testid="stMainBlockContainer"] {padding:2rem 1rem}
 .page-header h1 {font-size:23px}.header-tags {display:none}
 .sidebar-footer {margin-top:50px}
}
@media(max-width:600px) {
 .stApp [data-testid="stHorizontalBlock"] {flex-wrap:wrap}
 .stApp [data-testid="stColumn"] {min-width:min(100%,260px);flex:1 1 100%}
 .cat-badge-container {padding:0}.page-header {padding-bottom:14px}
}
</style>
"""
    render_html(css_content)


def render_masthead(bag_id: str, weight: float) -> None:
    """Renders the top masthead with app title and dynamic bag tag."""
    weight_str = f"{weight:.1f} lb" if weight > 0 else "0.0 lb"
    tag_str = f"{bag_id} · {weight_str}" if bag_id.strip() else "New scan"
    render_html(
        f"""
<div class="masthead-container">
    <h1 class="masthead-title">Waste Audit</h1>
    <span class="masthead-tag">{tag_str}</span>
</div>
"""
    )


def render_stepper(current_step: str) -> None:
    """Renders the 3-step progress bar (Capture -> Scan -> Results)."""
    steps = [
        ("capture", "Capture"),
        ("scanning", "Scan"),
        ("results", "Results"),
    ]
    step_key = "results" if current_step == "saved" else current_step
    active_idx = next((i for i, s in enumerate(steps) if s[0] == step_key), 0)

    parts = ['<div class="stepper-container">']
    for i, (key, label) in enumerate(steps):
        if i == active_idx:
            status = "active"
            marker = str(i + 1)
        elif i < active_idx:
            status = "done"
            marker = "✓"
        else:
            status = ""
            marker = str(i + 1)

        parts.append(
            f'<div class="step-item {status}"><div class="step-dot">{marker}</div><div class="step-label">{label}</div></div>'
        )
        if i < len(steps) - 1:
            line_status = "done" if i < active_idx else ""
            parts.append(f'<div class="step-line {line_status}"></div>')

    parts.append("</div>")
    render_html("".join(parts))


def calculate_stream_contamination(
    stream_type: str,
    categories: dict[str, float],
    category_set: str = CATEGORY_SET,
) -> tuple[float | None, bool]:
    """Contamination % for the audited stream, using the stream mapping in
    configs/sort_categories.yaml.

    - recycling: share of categories whose stream is landfill. In the coarse
      set, a group spanning both streams (e.g. cups) is not counted.
    - landfill: 0, as before; recyclables in landfill aren't scored here.
    - any stream the sort sheet doesn't define (compost): None, since there is
      no mapping to judge it by. The page shows "n/a" rather than a false 0.
    """
    hazard_flagged = False
    if stream_type == "landfill":
        return 0.0, hazard_flagged

    scheme = load_sort_scheme()
    if stream_type not in scheme.streams:
        return None, hazard_flagged

    by_stream = scheme.to_streams(categories, category_set)
    contaminant_pct = sum(
        pct for stream, pct in by_stream.items() if stream not in (stream_type, MIXED_STREAM)
    )
    return min(round(contaminant_pct, 1), 100.0), hazard_flagged


def page_shell(title: str, subtitle: str) -> None:
    """Shared navigation and heading; all actions remain native Streamlit controls."""
    from html import escape
    inject_mockup_css()
    with st.sidebar:
        render_html('<div class="brand"><span class="brand-icon">♲</span>WasteAudit</div><div class="nav-label">CORE OPERATIONS</div>')
        navigation = [
            ("Audit Tarp Scan", "pages/1_Audit.py", "Audit Capture", ":material/fact_check:"),
            ("Ops Intelligence Hub", "pages/2_Dashboard.py", "Dashboard", ":material/monitoring:"),
            ("Site Registry", "pages/3_Sites.py", "Site Registry", ":material/location_on:"),
        ]
        for heading, path, label, icon in navigation:
            with st.container(key="nav_active" if heading == title else f"nav_{heading}"):
                st.page_link(path, label=label, icon=icon)
        render_html('<div class="sidebar-footer">Waste Audit · Field Portal<br><small>Local storage enabled</small></div>')
    render_html(f'<header class="page-header"><div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>'
                '<div class="header-tags"><span>Campus Operations</span><span>Category estimation</span></div></header>')


def panel(key: str):
    """A reusable, scoped white card containing real Streamlit widgets."""
    return st.container(border=True, key=f"panel_{key}")
