"""Load and validate YAML configs (taxonomy, sites, model)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None

CONFIG_DIR = Path(__file__).resolve().parents[3] / "configs"


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is not None:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}

    # Basic fallback parser if PyYAML is not yet installed in environment
    import re
    result: dict[str, Any] = {}
    with open(path, "r") as f:
        content = f.read()

    # If parsing sites.yaml
    if "sites:" in content:
        sites_list = []
        site_blocks = re.findall(r"- site_id:\s*([^\n]+)\s+site_name:\s*\"?([^\n\"]+)\"?\s+site_type:\s*([^\n]+)\s+bin_type:\s*([^\n]+)", content)
        for sid, sname, stype, btype in site_blocks:
            sites_list.append({
                "site_id": sid.strip(),
                "site_name": sname.strip(),
                "site_type": stype.strip(),
                "bin_type": btype.strip(),
            })
        result["sites"] = sites_list

    # If parsing taxonomy.yaml
    if "classes:" in content:
        classes_list = []
        class_blocks = re.findall(r"- name:\s*([^\n]+)\s+material_category:\s*([^\n]+)\s+correct_stream:\s*([^\n]+)\s+hazard_flag:\s*([^\n]+)", content)
        for name, mat, stream, haz in class_blocks:
            classes_list.append({
                "name": name.strip(),
                "material_category": mat.strip(),
                "correct_stream": stream.strip(),
                "hazard_flag": haz.strip().lower() == "true",
            })
        result["classes"] = classes_list

    return result


@dataclass
class TaxonomyClass:
    name: str
    material_category: str
    correct_stream: str
    hazard_flag: bool
    notes: str | None = None


def load_taxonomy(path: Path = CONFIG_DIR / "taxonomy.yaml") -> dict[str, TaxonomyClass]:
    """Load configs/taxonomy.yaml into a name -> TaxonomyClass lookup.

    TODO: add schema validation (pydantic) once the taxonomy stabilizes,
    so a malformed config fails fast at load time rather than at inference.
    """
    raw = load_yaml(path)
    classes = {}
    for entry in raw.get("classes", []):
        classes[entry["name"]] = TaxonomyClass(
            name=entry["name"],
            material_category=entry.get("material_category", "unknown"),
            correct_stream=entry.get("correct_stream", "unknown"),
            hazard_flag=bool(entry.get("hazard_flag", False)),
            notes=entry.get("notes"),
        )
    return classes


def load_sites(path: Path = CONFIG_DIR / "sites.yaml") -> dict[str, dict[str, Any]]:
    """Load configs/sites.yaml into a site_id -> site record lookup."""
    raw = load_yaml(path)
    return {s["site_id"]: s for s in raw.get("sites", [])}


def load_model_config(path: Path = CONFIG_DIR / "model.yaml") -> dict[str, Any]:
    return load_yaml(path)
