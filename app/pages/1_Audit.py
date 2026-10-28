"""Capture, review and persist one bag without losing work across reruns."""
from __future__ import annotations

import datetime as dt
from html import escape
import io
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
for path in (ROOT_DIR, ROOT_DIR / "src", ROOT_DIR / "app"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import streamlit as st
from PIL import Image, UnidentifiedImageError
from app.components.mockup_ui import CATEGORY_SET, MOCKUP_CATEGORIES, calculate_stream_contamination, panel, page_shell, render_html
from app.components.inference import run_classifier
from app.components.audit_data import save_audit
from waste_audit.utils.config import load_sites
from waste_audit.classification.sort_categories import load_sort_scheme
from waste_audit.pipeline.weight import estimate_weights

st.set_page_config(page_title="Audit Capture · WasteAudit", page_icon="♲", layout="wide")
page_shell("Audit Tarp Scan", "Field analysis and stream classification portal")

DEFAULTS = dict(step="capture", bag_id="", weight=0.0, site_id=None, stream_type="recycling", photo_bytes=None,
                model_output=None, corrected=None, saved_record=None, inference_label=None,
                inference_source=None, inference_error=None, inference_cost=0.0, photo_name="Bag photo")
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)
s = st.session_state


def reset_scan():
    # Remove widget state before controls are recreated, including previously uploaded photos.
    for key in list(st.session_state):
        if key.startswith(("capture_", "cat_input_", "rerun_")):
            del st.session_state[key]
    for key, value in DEFAULTS.items():
        if key not in ("site_id", "stream_type"):
            st.session_state[key] = value


def preview():
    try:
        image = Image.open(io.BytesIO(s.photo_bytes))
        st.image(image, use_container_width=True)
        st.caption(escape(s.photo_name))
        return True
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        st.error("This photo cannot be opened. Upload a valid JPG or PNG image.")
        return False


if s.step == "saved":
    with panel("saved"):
        st.success("Audit saved and locked")
        st.write(f"{s.bag_id} · {s.weight:.1f} lb")
        st.caption("Saved locally to data/exports/audits.jsonl. This record is available on the Dashboard.")
        with st.expander("View saved record"):
            st.json(s.saved_record)
        st.button("Start another audit", type="primary", on_click=reset_scan, use_container_width=True)

elif s.step == "capture":
    try:
        sites = load_sites()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f"Cannot load site registry: {exc}")
        st.stop()
    if not sites:
        st.info("Add a location in Site Registry before capturing an audit.")
        st.stop()
    choices = list(sites)
    if s.site_id not in sites:
        s.site_id = choices[0]
    with panel("context"):
        location, stream = st.columns([1, 1.2])
        with location:
            s.site_id = st.selectbox("Target location", choices, index=choices.index(s.site_id),
                                    format_func=lambda sid: f"{sites[sid].get('site_name', sid)} · {sites[sid].get('site_type', 'other').replace('_', ' ').upper()}", key="capture_site")
        with stream:
            streams = ["recycling", "compost", "landfill"]
            s.stream_type = st.radio("Target waste stream", streams, index=streams.index(s.stream_type),
                                     format_func=str.title, horizontal=True, key="capture_stream")
        bag, weight = st.columns(2)
        with bag:
            s.bag_id = st.text_input("Bag identification", value=s.bag_id, placeholder="RB-0412", key="capture_bag")
        with weight:
            s.weight = st.number_input("Measured bag weight (lb)", min_value=0.0, value=float(s.weight), step=.1, key="capture_weight")
    with panel("capture"):
        st.subheader("Capture bag contents")
        method = st.radio("Photo source", ["Upload photo", "Camera capture"], horizontal=True, key="capture_method")
        if method == "Upload photo":
            photo = st.file_uploader("Upload alternative or choose a photo", type=["png", "jpg", "jpeg"], key="capture_upload")
        else:
            photo = st.camera_input("Take a wide, top-down photo", key="capture_camera")
        if photo is not None:
            if photo.getvalue() != s.photo_bytes:
                s.model_output, s.corrected = None, None
            s.photo_bytes, s.photo_name = photo.getvalue(), photo.name
        valid_photo = preview() if s.photo_bytes else False
        if not s.photo_bytes:
            render_html('<div class="scan-frame"><div><span class="photo-placeholder-icon">♧</span>Upload or capture a top-down photo of the bag contents</div></div>')
        ready = bool(s.bag_id.strip() and s.weight > 0 and valid_photo)
        st.caption("Required: bag identification, a weight greater than zero, and a valid photo.")
        if st.button("Run classification", type="primary", disabled=not ready, use_container_width=True):
            s.step = "scanning"
            st.rerun()

elif s.step == "scanning":
    with panel("scanning"):
        preview()
        with st.spinner("Analyzing bag contents…"):
            try:
                result = run_classifier(s.photo_bytes, s.stream_type)
            except Exception as exc:
                st.error(f"Classification could not finish: {exc}")
                if st.button("Return to audit"):
                    s.step = "results" if s.model_output else "capture"
                    st.rerun()
                st.stop()
        # Keep manual overrides on rerun; untouched categories take the new estimate.
        previous, corrections = s.model_output or {}, s.corrected or {}
        edited = {k: v for k, v in corrections.items() if abs(v - previous.get(k, v)) > .001}
        s.model_output = dict(result.categories)
        s.corrected = {**result.categories, **edited}
        for key in list(s):
            if key.startswith("cat_input_"):
                del s[key]
        s.inference_label, s.inference_source = result.label, result.source
        s.inference_error, s.inference_cost = result.error, result.cost_usd
        s.step = "results"
        st.rerun()

elif s.step == "results":
    st.caption(f"{s.bag_id} · {s.weight:.1f} lb · {s.site_id} · {s.stream_type.title()}")
    with panel("preview"):
        preview()
        st.caption("Category percentages only. Item detections, item confidence, and hazard findings are unavailable.")
        rerun, replace = st.columns(2)
        with rerun:
            if st.button("Re-run classifier", use_container_width=True):
                s.step = "scanning"
                st.rerun()
        with replace:
            if st.button("Retake / upload alternative", use_container_width=True):
                s.step = "capture"
                st.rerun()
        st.caption("Re-running keeps manual corrections. A replacement photo starts a fresh classification.")
    with panel("review"):
        st.subheader("Verification & Correction Queue")
        st.caption("Review category estimates and adjust their percentages before saving.")
        if s.inference_source == "mock":
            st.warning(f"Mock demonstration values — {s.inference_error or 'no model result available'}. Correct before using for reporting.")
        else:
            st.caption(f"{s.inference_label} · Estimated classification cost: ${s.inference_cost:.4f}")
        for cfg in MOCKUP_CATEGORIES:
            key, label = cfg["key"], cfg["label"]
            original = float(s.model_output.get(key, 0))
            left, middle, right = st.columns([4, 2, 2])
            with right:
                s.corrected[key] = st.number_input(f"{label} %", min_value=0.0, max_value=100.0,
                                                  value=float(s.corrected.get(key, original)), step=.5, key=f"cat_input_{key}")
            edited = abs(s.corrected[key] - original) > .001
            with left:
                render_html(f'<div class="cat-content"><span class="cat-name-text">{label}</span><div class="cat-orig-text">Original: {original:.1f}%</div><div class="cat-bar-bg"><div class="cat-bar-fill" style="width:{s.corrected[key]}%"></div></div></div>')
            with middle:
                badge = "Corrected" if edited else ("Mock value" if s.inference_source == "mock" else "AI estimate")
                render_html(f'<div class="cat-badge-container"><span class="badge-{"corrected" if edited else "estimate"}">{badge}</span></div>')
        total = sum(s.corrected.values())
        total_ok = abs(total - 100) < .2
        st.caption(f"Total category share: {total:.1f}%")
        if not total_ok:
            st.warning("Category percentages must total 100% before saving.")
        weight_est = estimate_weights(s.corrected, CATEGORY_SET, bag_weight_lb=float(s.weight))
        with st.expander("Estimated material weights", expanded=True):
            if weight_est.is_defined:
                weight_rows = [dict(Category=c["label"], **{
                    "Area %": round(weight_est.area_pct[c["key"]], 1),
                    "Factor": weight_est.factors[c["key"]],
                    "Weight %": round(weight_est.weight_pct[c["key"]], 1),
                    "Est. lb": round(weight_est.weight_lb[c["key"]], 2),
                }) for c in MOCKUP_CATEGORIES]
                weight_rows.append({"Category": "Total", "Area %": round(sum(weight_est.area_pct.values()), 1),
                                    "Factor": None, "Weight %": round(sum(weight_est.weight_pct.values()), 1),
                                    "Est. lb": round(sum(weight_est.weight_lb.values()), 2)})
                st.dataframe(weight_rows, hide_index=True, use_container_width=True)
                st.caption(f"Provisional estimate: area share × material factor, normalized to the {s.weight:.1f} lb bag weight. Factors are not yet fitted.")
            else:
                st.caption("No weight estimate: every category is at 0%.")
        unconfirmed = ", ".join(c.label for c in load_sort_scheme().unconfirmed_streams())
        if unconfirmed:
            st.caption(f"Recycling vs. landfill not yet confirmed for: {unconfirmed}.")
        contamination, _ = calculate_stream_contamination(s.stream_type, s.corrected)
        contamination_label = f"{contamination:.1f}%" if contamination is not None else "n/a"
        render_html(f'<div class="live-summary"><div><small>LIVE ESTIMATES</small><strong>{contamination_label}</strong>Contamination share</div><div><small>Hazard assessment</small><br>Unavailable</div><div><small>Basis</small><br>Reviewed category percentages</div></div>')
        st.caption("Contamination uses the existing provisional stream rules. Photo estimates are not measured mass fractions.")
        discard, save = st.columns(2)
        with discard:
            st.button("Discard scan", on_click=reset_scan, use_container_width=True)
        with save:
            if st.button("Save & Lock Audit", type="primary", disabled=not total_ok, use_container_width=True):
                record = dict(bag_id=s.bag_id.strip(), weight_lb=float(s.weight), site_id=s.site_id,
                              stream_type=s.stream_type, category_set=CATEGORY_SET, contamination_pct=contamination, hazard_flagged=None,
                              hazard_assessed=False, reviewed=True, inference_source=s.inference_source,
                              inference_label=s.inference_label, scanned_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                              categories=[dict(category=c["key"], label=c["label"], original_pct=s.model_output[c["key"]],
                                               corrected_pct=s.corrected[c["key"]], edited=abs(s.corrected[c["key"]]-s.model_output[c["key"]])>.001,
                                               weight_factor=weight_est.factors[c["key"]],
                                               est_weight_pct=round(weight_est.weight_pct[c["key"]], 2),
                                               est_weight_lb=round(weight_est.weight_lb[c["key"]], 3)) for c in MOCKUP_CATEGORIES])
                try:
                    save_audit(record)
                except (OSError, ValueError, TypeError) as exc:
                    st.error(f"Audit was not saved: {exc}. Your review is preserved. Retry after resolving the storage problem.")
                else:
                    s.saved_record, s.step = record, "saved"
                    st.rerun()
