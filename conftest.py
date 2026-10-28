"""Pytest path setup.

Tests import both `waste_audit.*` (from src/) and `app.components.*` (from the
repo root). Putting this file at the root makes pytest add the root to
sys.path; the src/ insert means tests also run without `pip install -e .`.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
for path in (ROOT_DIR, ROOT_DIR / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
