"""Audit sort categories: the hand-sort sheet's categories, their coarse
groups, their streams, and their weighting factors, loaded from
configs/sort_categories.yaml.

Two category sets come out of the one config:
  - "fine":   the sort-sheet categories themselves
  - "coarse": the groups those categories roll up into

A fine breakdown (from the model, or a hand sort) converts to coarse by
summing each category into its group, so a model run in either set can be
scored against the same hand sort at the group level.

The config is validated at load time and fails loudly. A typo in a group or
stream name would otherwise silently drop share out of a roll-up.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from waste_audit.utils.config import CONFIG_DIR

CATEGORY_SETS = ("fine", "coarse")
DEFAULT_CATEGORY_SET = "fine"

# Stream reported for a coarse group whose categories go to different streams
# (e.g. cups: plastic cups vs. paper cups).
MIXED_STREAM = "mixed"

SORT_CATEGORIES_PATH = CONFIG_DIR / "sort_categories.yaml"


class SortCategoryError(ValueError):
    """Raised for a malformed sort-category config or an unknown category key."""


@dataclass(frozen=True)
class SortCategory:
    key: str
    label: str
    group: str
    stream: str
    stream_confirmed: bool
    description: str
    material: str
    icon: str = "category"
    fallback: bool = False


@dataclass(frozen=True)
class SortGroup:
    key: str
    label: str
    material: str
    icon: str = "category"


@dataclass(frozen=True)
class SortScheme:
    categories: tuple[SortCategory, ...]
    groups: tuple[SortGroup, ...]
    streams: tuple[str, ...]
    material_factors: Mapping[str, float]   # material class -> weighting factor

    # -- lookups --------------------------------------------------------
    def keys(self, category_set: str = DEFAULT_CATEGORY_SET) -> list[str]:
        category_set = resolve_category_set(category_set)
        if category_set == "fine":
            return [c.key for c in self.categories]
        return [g.key for g in self.groups]

    def labels(self, category_set: str = DEFAULT_CATEGORY_SET) -> dict[str, str]:
        if resolve_category_set(category_set) == "fine":
            return {c.key: c.label for c in self.categories}
        return {g.key: g.label for g in self.groups}

    def icons(self, category_set: str = DEFAULT_CATEGORY_SET) -> dict[str, str]:
        if resolve_category_set(category_set) == "fine":
            return {c.key: c.icon for c in self.categories}
        return {g.key: g.icon for g in self.groups}

    def descriptions(self, category_set: str = DEFAULT_CATEGORY_SET) -> dict[str, str]:
        """Per-key text the model sees. Coarse descriptions are built from the
        member categories so there is no second copy to keep in sync."""
        if resolve_category_set(category_set) == "fine":
            return {c.key: c.description for c in self.categories}
        return {
            g.key: f"{g.label}. Includes: "
            + " ".join(c.description for c in self.members(g.key))
            for g in self.groups
        }

    def members(self, group_key: str) -> list[SortCategory]:
        return [c for c in self.categories if c.group == group_key]

    def fallback_key(self, category_set: str = DEFAULT_CATEGORY_SET) -> str:
        fallback = next(c for c in self.categories if c.fallback)
        return fallback.key if resolve_category_set(category_set) == "fine" else fallback.group

    def stream_of(self, key: str, category_set: str = DEFAULT_CATEGORY_SET) -> str:
        """Stream for a key; MIXED_STREAM for a group spanning several streams."""
        if resolve_category_set(category_set) == "fine":
            return self._category(key).stream
        streams = {c.stream for c in self.members(self._group(key).key)}
        return streams.pop() if len(streams) == 1 else MIXED_STREAM

    def materials(self, category_set: str = DEFAULT_CATEGORY_SET) -> dict[str, str]:
        """Key -> material class. Coarse uses the group's own material, not
        its members', so a mixed group (cups) gets one placeholder class."""
        if resolve_category_set(category_set) == "fine":
            return {c.key: c.material for c in self.categories}
        return {g.key: g.material for g in self.groups}

    def factors(self, category_set: str = DEFAULT_CATEGORY_SET) -> dict[str, float]:
        """Key -> weighting factor D, via its material class."""
        return {
            key: self.material_factors[material]
            for key, material in self.materials(category_set).items()
        }

    def unconfirmed_streams(self) -> list[SortCategory]:
        return [c for c in self.categories if not c.stream_confirmed]

    # -- roll-ups -------------------------------------------------------
    def to_groups(self, shares: Mapping[str, float]) -> dict[str, float]:
        """Sum fine-category shares (or weights) into coarse groups.

        Missing categories count as 0; unknown keys raise, so a mislabeled
        hand sort can't quietly lose share.
        """
        totals = {g.key: 0.0 for g in self.groups}
        for key, value in shares.items():
            totals[self._category(key).group] += float(value)
        return totals

    def to_streams(
        self, shares: Mapping[str, float], category_set: str = DEFAULT_CATEGORY_SET
    ) -> dict[str, float]:
        """Sum shares by stream. A coarse set can produce a MIXED_STREAM bucket."""
        valid = set(self.keys(category_set))
        totals = {s: 0.0 for s in self.streams}
        for key, value in shares.items():
            if key not in valid:
                raise SortCategoryError(f"Unknown {category_set} category key: '{key}'")
            stream = self.stream_of(key, category_set)
            totals[stream] = totals.get(stream, 0.0) + float(value)
        return totals

    # -- internals ------------------------------------------------------
    def _category(self, key: str) -> SortCategory:
        for c in self.categories:
            if c.key == key:
                return c
        raise SortCategoryError(f"Unknown sort category: '{key}' (see configs/sort_categories.yaml)")

    def _group(self, key: str) -> SortGroup:
        for g in self.groups:
            if g.key == key:
                return g
        raise SortCategoryError(f"Unknown sort group: '{key}' (see configs/sort_categories.yaml)")


def resolve_category_set(category_set: str | None) -> str:
    """Validate a category-set name; None means the default."""
    if category_set is None:
        return DEFAULT_CATEGORY_SET
    if category_set not in CATEGORY_SETS:
        raise SortCategoryError(
            f"Unknown category set '{category_set}' — expected one of {', '.join(CATEGORY_SETS)}."
        )
    return category_set


def load_sort_scheme(path: Path = SORT_CATEGORIES_PATH) -> SortScheme:
    """Load and validate configs/sort_categories.yaml. Cached per path."""
    return _load_cached(Path(path).resolve())


@lru_cache(maxsize=None)
def _load_cached(path: Path) -> SortScheme:
    try:
        import yaml
    except ImportError as exc:
        raise SortCategoryError("PyYAML is required to read sort_categories.yaml") from exc

    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}
    return _parse(raw, path)


def _parse(raw: dict, path: Path) -> SortScheme:
    def fail(message: str) -> SortCategoryError:
        return SortCategoryError(f"{path.name}: {message}")

    streams = tuple(raw.get("streams") or ())
    if not streams:
        raise fail("no streams defined")

    material_factors: dict[str, float] = {}
    for material, factor in (raw.get("material_classes") or {}).items():
        if isinstance(factor, bool) or not isinstance(factor, (int, float)) or factor < 0:
            raise fail(f"material class {material} needs a non-negative number, got {factor!r}")
        material_factors[material] = float(factor)
    if not material_factors:
        raise fail("no material_classes defined")
    default_material = raw.get("default_material")
    if default_material not in material_factors:
        raise fail(f"default_material '{default_material}' is not in material_classes")

    groups = []
    for entry in raw.get("groups") or ():
        if "key" not in entry or "label" not in entry:
            raise fail(f"group needs key and label: {entry}")
        groups.append(
            SortGroup(
                key=entry["key"],
                label=entry["label"],
                material=entry.get("material", default_material),
                icon=entry.get("icon", "category"),
            )
        )

    categories = []
    for entry in raw.get("categories") or ():
        missing = [f for f in ("key", "label", "group", "stream", "description") if not entry.get(f)]
        if missing:
            raise fail(f"category {entry.get('key', '?')} is missing {', '.join(missing)}")
        if "stream_confirmed" not in entry:
            raise fail(f"category {entry['key']} must say stream_confirmed: true/false")
        categories.append(
            SortCategory(
                key=entry["key"],
                label=str(entry["label"]),
                group=entry["group"],
                stream=entry["stream"],
                stream_confirmed=bool(entry["stream_confirmed"]),
                description=" ".join(str(entry["description"]).split()),
                material=entry.get("material", default_material),
                icon=entry.get("icon", "category"),
                fallback=bool(entry.get("fallback", False)),
            )
        )

    if not categories:
        raise fail("no categories defined")
    for kind, keys in (("category", [c.key for c in categories]), ("group", [g.key for g in groups])):
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        if dupes:
            raise fail(f"duplicate {kind} keys: {', '.join(dupes)}")

    group_keys = {g.key for g in groups}
    for c in categories:
        if c.group not in group_keys:
            raise fail(f"category {c.key} has unknown group '{c.group}'")
        if c.stream not in streams:
            raise fail(f"category {c.key} has unknown stream '{c.stream}'")
    for item in (*categories, *groups):
        if item.material not in material_factors:
            raise fail(f"{item.key} has unknown material '{item.material}'")
    empty = [g.key for g in groups if not any(c.group == g.key for c in categories)]
    if empty:
        raise fail(f"groups with no categories: {', '.join(empty)}")

    fallbacks = [c.key for c in categories if c.fallback]
    if len(fallbacks) != 1:
        raise fail(f"exactly one category must be the fallback, found {fallbacks or 'none'}")

    return SortScheme(
        categories=tuple(categories),
        groups=tuple(groups),
        streams=streams,
        material_factors=material_factors,
    )
