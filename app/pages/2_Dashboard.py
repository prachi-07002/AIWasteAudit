"""Filtered analytics from saved audits; no fabricated metrics."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
for path in (ROOT_DIR, ROOT_DIR / "src", ROOT_DIR / "app"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import pandas as pd
import plotly.express as px
import streamlit as st
from app.components.audit_data import read_audits, filter_audits, category_profile, top_contaminant
from app.components.mockup_ui import panel, page_shell
from waste_audit.utils.config import load_sites

st.set_page_config(page_title="Dashboard · WasteAudit", page_icon="♲", layout="wide")
page_shell("Ops Intelligence Hub", "Real-time stream purity analytics")
try:
    records, skipped = read_audits()
    sites = load_sites()
except (OSError, ValueError, TypeError, KeyError) as exc:
    st.error(f"Cannot load audit data or site registry: {exc}")
    st.stop()
if skipped:
    st.warning(f"Skipped {skipped} malformed audit record(s). Other records remain available.")

with panel("filters"):
    dates, locations, streams = st.columns([1.2, 1, 1])
    today = dt.datetime.now(dt.timezone.utc).date()
    first = min((row['date'] for row in records), default=today - dt.timedelta(days=30))
    last = max((row['date'] for row in records), default=today)
    with dates:
        date_range = st.date_input("Date range", value=(first, max(today, last)), key="dashboard_dates")
    with locations:
        selected_sites = st.multiselect("Sites", sorted(set(sites) | {r['site_id'] for r in records}),
                                        format_func=lambda sid: sites.get(sid, {}).get('site_name', sid), placeholder="All sites")
    with streams:
        selected_streams = st.multiselect("Waste streams", ['recycling', 'compost', 'landfill'], format_func=str.title, placeholder="All streams")
    sources = st.columns(2)
    with sources[0]:
        include_mock = st.checkbox("Include labeled mock audits", value=False)
    with sources[1]:
        include_legacy = st.checkbox("Include historical audits with unknown provenance", value=False)
    st.caption("All charts use these filters. Confidence filtering is unavailable because category estimates have no per-item confidence.")

if len(date_range) != 2:
    st.info("Choose both a start date and an end date.")
    st.stop()
filtered = filter_audits(records, *date_range, sites=selected_sites, streams=selected_streams,
                         include_mock=include_mock, include_legacy=include_legacy)
if include_mock or include_legacy:
    st.warning("This view may include mock data or historical records whose classifier source was not recorded. These are not verified model measurements.")
if not filtered:
    st.info("No audits match these filters. Save an audit in Audit Capture, adjust the filters, or include mock/historical records explicitly.")

metrics = st.columns(4)
scored = [row for row in filtered if row['contamination_pct'] is not None]
average = sum(row['contamination_pct'] for row in scored) / len(scored) if scored else None
if len(scored) < len(filtered):
    st.caption("Audits without a defined stream mapping remain in audit counts and exports; contamination averages exclude them.")
# Old hazard_flagged=False values were placeholders; only explicitly assessed results count.
assessed = [row for row in filtered if row.get('hazard_assessed') is True and isinstance(row.get('hazard_flagged'), bool)]
for col, label, value in zip(metrics,
    ["Avg. contamination share", "Total audits executed", "Hazard incidents (critical)", "Top contaminant category"],
    [f"{average:.1f}%" if average is not None else "—", str(len(filtered)),
     str(sum(row['hazard_flagged'] for row in assessed)) if assessed else "Unavailable",
     top_contaminant(filtered) or "Unavailable"]):
    with col:
        st.metric(label, value)
st.caption("Contamination is an unweighted mean of reviewed category estimates, using provisional stream rules. No mass fraction or trend change is inferred.")


def chart(figure):
    figure.update_layout(paper_bgcolor='white', plot_bgcolor='white', font=dict(color='#58645b', family='Arial'),
                         margin=dict(l=12,r=12,t=20,b=12), legend_title_text='', height=300)
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor='#edf0eb')
    st.plotly_chart(figure, use_container_width=True, config={'displayModeBar':False})


with panel("trend"):
    st.subheader("Contamination Rate Trajectory (%)")
    st.caption("Daily average category share by waste stream")
    if scored:
        df = pd.DataFrame(scored)
        trend = df.groupby(['date','stream_type'], as_index=False)['contamination_pct'].mean()
        figure = px.line(trend, x='date', y='contamination_pct', color='stream_type', markers=True,
                         color_discrete_map={'recycling':'#2e8b57','compost':'#d99a27','landfill':'#839384'},
                         labels={'date':'Date','contamination_pct':'Contamination (%)','stream_type':'Stream'})
        figure.update_yaxes(range=[0,100])
        figure.update_xaxes(tickformat='%b %d')
        if trend['date'].nunique() == 1:
            day = trend['date'].iloc[0]
            figure.update_xaxes(range=[day-dt.timedelta(days=1), day+dt.timedelta(days=1)], dtick=86400000)
        chart(figure)
    else:
        st.caption("No trend available for this selection.")

with panel("profile"):
    st.subheader("Contaminant Profile by Location Archetype")
    st.caption("Reviewed category composition; all materials shown, including materials accepted in the selected streams.")
    profiles = []
    archetypes = sorted({sites.get(row['site_id'], {}).get('site_type','unregistered') for row in filtered})
    for archetype in archetypes:
        group = [row for row in filtered if sites.get(row['site_id'], {}).get('site_type','unregistered') == archetype]
        for category, share in category_profile(group).items():
            profiles.append(dict(archetype=archetype.replace('_',' ').title(), category=category.title(), share=share))
    if profiles:
        chart(px.bar(pd.DataFrame(profiles), x='share', y='archetype', color='category', orientation='h',
                     color_discrete_sequence=['#5688e0','#e4b849','#67b78e','#a89ac5','#df6672','#a7b2aa'],
                     labels={'share':'Average category share (%)','archetype':'','category':'Category'}))
    else:
        st.caption("No valid historical category breakdown is available.")

hazards, comparison = st.columns(2)
with hazards:
    with panel("hazards"):
        st.subheader("Hazard Critical Incidents")
        if assessed:
            incident_df = pd.DataFrame(assessed).groupby('date',as_index=False)['hazard_flagged'].sum()
            chart(px.line(incident_df, x='date', y='hazard_flagged', markers=True,
                          labels={'date':'Date','hazard_flagged':'Incidents'}))
            st.caption(f"Based on {len(assessed)} explicitly assessed audits; other audits have unknown hazard status.")
        else:
            st.info("Unavailable — the classifier does not assess hazards. Historical placeholder safety flags are excluded.")
with comparison:
    with panel("comparison"):
        st.subheader("Major Contamination Vectors by Site")
        comparison_rows = []
        for sid in sorted({row['site_id'] for row in filtered}):
            group = [row for row in filtered if row['site_id']==sid]
            site_scores = [r['contamination_pct'] for r in group if r['contamination_pct'] is not None]
            comparison_rows.append({'Site':sites.get(sid,{}).get('site_name',sid), 'Audits':len(group),
                                    'Contamination (%)':round(sum(site_scores)/len(site_scores),1) if site_scores else None,
                                    'Top contaminant':top_contaminant(group) or 'Unavailable'})
        if comparison_rows:
            st.dataframe(pd.DataFrame(comparison_rows).sort_values('Contamination (%)',ascending=False), hide_index=True, use_container_width=True)
        else:
            st.caption("No site comparisons available.")

if filtered:
    with st.expander("Filtered audit records"):
        columns = ['bag_id','date','site_id','stream_type','weight_lb','contamination_pct','source']
        display = pd.DataFrame(filtered).reindex(columns=columns)
        st.dataframe(display, hide_index=True, use_container_width=True)
        st.download_button("Export filtered audits (CSV)", display.to_csv(index=False), 'waste-audits.csv', 'text/csv')
