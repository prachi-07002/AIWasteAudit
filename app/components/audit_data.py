"""Persistence and dashboard preparation, independent of Streamlit."""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path
import tempfile

from waste_audit.classification.sort_categories import MIXED_STREAM, load_sort_scheme

ROOT = Path(__file__).resolve().parents[2]
AUDITS_PATH = ROOT / "data/exports/audits.jsonl"
SITES_PATH = ROOT / "configs/sites.yaml"
STREAMS = ("recycling", "compost", "landfill")
CONTAMINANTS = {"recycling": ("trash", "other"), "compost": ("plastic", "metal", "glass", "trash"), "landfill": ()}


def finite_number(value, minimum=0, maximum=float("inf")):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and minimum <= number <= maximum else None
    except (ValueError, TypeError):
        return None


def save_audit(record, path=None):
    """Only report success after the append has been flushed to disk."""
    path = Path(path) if path is not None else AUDITS_PATH
    payload = json.dumps(record, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def read_audits(path=None):
    """Skip invalid records and report how many were skipped; retain unknown fields."""
    path = Path(path) if path is not None else AUDITS_PATH
    records, skipped = [], 0
    if not path.exists():
        return records, skipped
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or not isinstance(row.get("site_id"), str) or not row["site_id"].strip():
                    raise ValueError("Missing site")
                date = dt.datetime.fromisoformat(str(row.get("scanned_at", "")).replace("Z", "+00:00"))
                date = date.replace(tzinfo=dt.timezone.utc) if date.tzinfo is None else date
                pct = finite_number(row.get("contamination_pct"), maximum=100)
                undefined_score = ("contamination_pct" in row and row["contamination_pct"] is None
                                   and row.get("category_set") in ("fine", "coarse")
                                   and row.get("stream_type") not in load_sort_scheme().streams)
                if (pct is None and not undefined_score) or row.get("stream_type") not in STREAMS:
                    raise ValueError("Invalid measurement")
                row = dict(row, date=date.astimezone(dt.timezone.utc).date(), contamination_pct=pct)
                row["weight_lb"] = finite_number(row.get("weight_lb"))
                row["source"] = row.get("inference_source") if row.get("inference_source") in ("model", "mock") else "unknown"
                records.append(row)
            except (ValueError, TypeError, OverflowError):
                skipped += 1
    return records, skipped


def filter_audits(records, start, end, sites=(), streams=(), include_mock=False, include_legacy=False):
    return [row for row in records if start <= row["date"] <= end
            and (not sites or row["site_id"] in sites)
            and (not streams or row["stream_type"] in streams)
            and (row["source"] == "model" or (include_mock and row["source"] == "mock")
                 or (include_legacy and row["source"] == "unknown"))]


def category_profile(records):
    """Aggregate corrected category shares; no per-item or mass claims."""
    totals = {}
    count = 0
    for row in records:
        categories = row.get("categories")
        if not isinstance(categories, list):
            continue
        values = {}
        for item in categories:
            if not isinstance(item, dict) or not isinstance(item.get("category"), str):
                continue
            value = finite_number(item.get("corrected_pct"), maximum=100)
            if value is not None:
                values[item["category"]] = value
        if not values or abs(sum(values.values()) - 100) > .2:
            continue
        count += 1
        for key, value in values.items():
            totals[key] = totals.get(key, 0) + value
    return {key: value / count for key, value in totals.items()}


def top_contaminant(records):
    totals = {}
    scheme = load_sort_scheme()
    for row in records:
        profile = category_profile([row])
        category_set = row.get("category_set")
        if category_set in ("fine", "coarse"):
            if row["stream_type"] not in scheme.streams or row["stream_type"] == "landfill":
                continue
            keys = [key for key in scheme.keys(category_set)
                    if scheme.stream_of(key, category_set) not in (row["stream_type"], MIXED_STREAM)]
        else:
            # Historical records used the original six generic categories.
            keys = CONTAMINANTS.get(row["stream_type"], ())
        for key in keys:
            if key in profile:
                label = scheme.labels(category_set)[key] if category_set in ("fine", "coarse") else key.title()
                totals[label] = totals.get(label, 0) + profile[key]
    if not totals:
        return None
    if max(totals.values()) == 0:
        return "None (0%)"
    return max(totals, key=totals.get)


def save_site(site, path=None, *, creating=False):
    """Update the existing YAML registry atomically, preserving identifiers and metadata."""
    import re
    import yaml
    path = Path(path) if path is not None else SITES_PATH
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.setdefault("sites", [])
    site = dict(site)
    sid = site.get("site_id", "").strip()
    name = site.get("site_name", "").strip()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", sid):
        raise ValueError("Site ID must contain lowercase letters, numbers, and single hyphens.")
    if not name:
        raise ValueError("Site name is required.")
    if site.get("site_type") not in raw.get("site_types", []):
        raise ValueError("Choose a configured location archetype.")
    if site.get("bin_type") not in STREAMS:
        raise ValueError("Choose a supported waste stream.")
    gps = site.get("gps")
    existing = next((entry for entry in entries if entry["site_id"] == sid), None)
    if gps is not None and not (existing is not None and gps == existing.get("gps")):
        if not isinstance(gps, dict) or finite_number(gps.get("latitude"), -90, 90) is None or finite_number(gps.get("longitude"), -180, 180) is None:
            raise ValueError("Enter valid latitude (−90 to 90) and longitude (−180 to 180).")
    if creating and existing is not None:
        raise ValueError("This site ID already exists. Choose a unique ID.")
    if not creating and existing is None:
        raise ValueError("The selected site no longer exists. Reload and try again.")
    site.update(site_id=sid, site_name=name)
    if existing is not None:
        existing.update(site)
    else:
        entries.append(site)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as handle:
            temp_path = Path(handle.name)
            yaml.safe_dump(raw, handle, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
