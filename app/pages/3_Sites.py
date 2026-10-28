"""Browse and maintain the existing YAML site registry."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
for path in (ROOT_DIR, ROOT_DIR / "src", ROOT_DIR / "app"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import pandas as pd
import streamlit as st
from app.components.audit_data import read_audits, save_site, SITES_PATH
from app.components.mockup_ui import panel, page_shell
from waste_audit.utils.config import load_sites, load_yaml

st.set_page_config(page_title="Site Registry · WasteAudit", page_icon="♲", layout="wide")
page_shell("Site Registry", "Operational locations and bin deployment")
try:
    sites = load_sites()
    raw = load_yaml(SITES_PATH)
except (OSError, ValueError, TypeError, KeyError) as exc:
    st.error(f"Cannot load site registry: {exc}")
    st.stop()
try:
    audits, _ = read_audits()
except OSError:
    audits = []
    st.warning("Audit history is unavailable; site configuration remains accessible.")

if st.session_state.pop('site_saved', False):
    st.success("Location saved. Existing audit references are preserved.")
st.session_state.setdefault('editing_site', None)


def create_site():
    st.session_state.editing_site = None
    st.session_state['site_form_version'] = st.session_state.get('site_form_version', 0) + 1


registry, editor = st.columns([1.8, 1], gap="large")
with registry:
    with panel("registry"):
        title, add = st.columns([2,1])
        with title:
            st.subheader("Deployed Audit Sites")
            st.caption(f"{len(sites)} configured locations")
        with add:
            st.button("＋ Add New Site", on_click=create_site, use_container_width=True)
        query = st.text_input("Search sites", placeholder="Name, site ID, archetype, or bin configuration")
        rows = []
        for sid, site in sites.items():
            if query.casefold() not in ' '.join(str(v) for v in site.values()).casefold():
                continue
            recent = [row for row in audits if row['site_id'] == sid]
            gps = site.get('gps')
            coordinate = f"{gps.get('latitude')}, {gps.get('longitude')}" if isinstance(gps,dict) else (str(gps) if gps else 'Not set')
            rows.append({'Site ID':sid,'Site name':site.get('site_name',sid),
                         'Archetype':site.get('site_type','other').replace('_',' ').upper(),
                         'Bin type':site.get('bin_configuration') or site.get('bin_type','Unavailable'),
                         'GPS coordinates':coordinate,
                         'Last audit':max((row['date'] for row in recent),default=None)})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            detail_id = st.selectbox("Site details", [row['Site ID'] for row in rows],
                                     format_func=lambda sid: sites[sid].get('site_name',sid))
            site = sites[detail_id]
            st.caption(f"Stable identifier: {detail_id} · Default stream: {site.get('bin_type','Unavailable')}")
            recent = [row for row in audits if row['site_id'] == detail_id]
            st.caption(f"Last audit: {max((row['date'].isoformat() for row in recent), default='Not recorded')} · Coordinates: {site.get('gps') or 'Not set'}")
            if st.button("Edit selected site"):
                st.session_state.editing_site = detail_id
                st.session_state['site_form_version'] = st.session_state.get('site_form_version',0) + 1
                st.rerun()
        else:
            st.info("No sites match your search.")

with editor:
    with panel("editor"):
        editing = st.session_state.editing_site
        site = sites.get(editing, {})
        st.subheader("Edit Audit Site" if editing else "Create Audit Site")
        st.caption("Configure a physical collection location. Site identifiers stay stable after creation.")
        version = st.session_state.get('site_form_version', 0)
        with st.form(f"site_editor_{version}"):
            sid = st.text_input("Site ID", value=site.get('site_id',''), placeholder="chem-lab-140", disabled=bool(editing))
            name = st.text_input("Site name", value=site.get('site_name',''), placeholder="Agricultural Science Rm 140")
            types = raw.get('site_types', ['other'])
            archetype = st.selectbox("Location archetype", types, index=types.index(site.get('site_type')) if site.get('site_type') in types else 0,
                                    format_func=lambda value: value.replace('_',' ').title())
            streams = ['recycling','compost','landfill']
            stream = st.selectbox("Default waste stream", streams, index=streams.index(site.get('bin_type')) if site.get('bin_type') in streams else 0, format_func=str.title)
            configuration = st.text_input("Bin model / configuration", value=site.get('bin_configuration',''), placeholder="Slim Jim Double Blue/Black")
            gps = site.get('gps')
            gps = gps if isinstance(gps,dict) else {}
            lat_col, lon_col = st.columns(2)
            with lat_col:
                latitude = st.text_input("Latitude (optional)", value=str(gps.get('latitude','')), placeholder="40.46512")
            with lon_col:
                longitude = st.text_input("Longitude (optional)", value=str(gps.get('longitude','')), placeholder="-86.92618")
            cancel, save = st.columns(2)
            with cancel:
                cancelled = st.form_submit_button("Cancel", use_container_width=True)
            with save:
                submitted = st.form_submit_button("Save Location", type="primary", use_container_width=True)
        if cancelled:
            create_site()
            st.rerun()
        if submitted:
            try:
                if bool(latitude.strip()) != bool(longitude.strip()):
                    raise ValueError("Enter both coordinates, or leave both blank.")
                coords = dict(latitude=float(latitude),longitude=float(longitude)) if latitude.strip() else None
                # Preserve legacy coordinate formats and extra fields unless explicitly replaced.
                updated = dict(site, site_id=sid.strip(),site_name=name.strip(),site_type=archetype,
                               bin_type=stream,bin_configuration=configuration.strip(),
                               gps=site['gps'] if site.get('gps') and not isinstance(site['gps'], dict) and coords is None else coords)
                save_site(updated, creating=not bool(editing))
            except (OSError, ValueError, TypeError, ImportError) as exc:
                st.error(f"Location was not saved: {exc}")
            else:
                st.session_state.site_saved = True
                create_site()
                st.rerun()
