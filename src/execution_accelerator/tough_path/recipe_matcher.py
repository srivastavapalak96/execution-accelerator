"""Map ``(group, artifact, fromMajor, toMajor)`` tuples to OpenRewrite recipe FQNs.

The matcher is intentionally simple: exact group + artifact match, with major-
version range comparison. Patch versions and qualifiers (``-RC1``, ``-SNAPSHOT``,
etc.) are discarded — the question this layer answers is "is there a known
community recipe for this kind of jump?", not "is this exact version diff safe?"
that's the job of the policy engine and validation gates.

Registry loads from ``config/openrewrite_recipes.yaml`` by default; tests inject
their own path. Unknown matches return ``None`` — that's the signal the ladder
should fall through to deterministic structural edits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

RECIPE_REGISTRY_PATH: Final[Path] = (
    Path(__file__).resolve().parents[3] / "config" / "openrewrite_recipes.yaml"
)

_VERSION_PREFIX_PATTERN = re.compile(r"^\d+")


class RecipeRegistryError(RuntimeError):
    """Raised when the YAML registry is malformed."""


@dataclass(frozen=True)
class RecipeMatchInput:
    """Coordinates of a remediation jump being considered for the recipe lane."""

    group: str
    artifact: str
    from_version: str
    to_version: str


@dataclass(frozen=True)
class RecipeMatch:
    """Result of a successful registry lookup."""

    recipe: str
    rationale: str
    matched_group: str
    matched_artifact: str
    matched_from_major: int
    matched_to_major: int


@dataclass(frozen=True)
class RecipeRegistry:
    """In-memory representation of ``config/openrewrite_recipes.yaml``."""

    entries: tuple[dict[str, object], ...]

    def lookup(self, candidate: RecipeMatchInput) -> RecipeMatch | None:
        from_major = _major_version(candidate.from_version)
        to_major = _major_version(candidate.to_version)
        if from_major is None or to_major is None:
            return None
        for entry in self.entries:
            match_block = entry.get("match")
            if not isinstance(match_block, dict):
                continue
            if str(match_block.get("group", "")) != candidate.group:
                continue
            if str(match_block.get("artifact", "")) != candidate.artifact:
                continue
            entry_from = _coerce_major(match_block.get("from_major"))
            entry_to = _coerce_major(match_block.get("to_major"))
            if entry_from is None or entry_to is None:
                continue
            if from_major != entry_from or to_major != entry_to:
                continue
            recipe = str(entry.get("recipe", "")).strip()
            if not recipe:
                raise RecipeRegistryError(
                    f"Registry entry for {candidate.group}:{candidate.artifact} has no 'recipe' field."
                )
            return RecipeMatch(
                recipe=recipe,
                rationale=str(entry.get("rationale", "")) or recipe,
                matched_group=str(match_block.get("group", "")),
                matched_artifact=str(match_block.get("artifact", "")),
                matched_from_major=entry_from,
                matched_to_major=entry_to,
            )
        return None


def load_recipe_registry(path: Path | None = None) -> RecipeRegistry:
    """Parse the YAML registry into a :class:`RecipeRegistry`."""

    resolved_path = path or RECIPE_REGISTRY_PATH
    if not resolved_path.exists():
        raise RecipeRegistryError(f"Recipe registry not found at {resolved_path}")
    payload = yaml.safe_load(resolved_path.read_text())
    if not isinstance(payload, dict):
        raise RecipeRegistryError(f"Recipe registry root must be a mapping, got {type(payload).__name__}")
    raw_entries = payload.get("recipes")
    if not isinstance(raw_entries, list):
        raise RecipeRegistryError("Recipe registry 'recipes' key must be a list.")
    entries: list[dict[str, object]] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise RecipeRegistryError(f"Recipe registry entry must be a mapping, got {type(raw_entry).__name__}")
        entries.append(raw_entry)
    return RecipeRegistry(entries=tuple(entries))


def match_recipe(
    candidate: RecipeMatchInput,
    *,
    registry: RecipeRegistry | None = None,
) -> RecipeMatch | None:
    """Look up a recipe for the given jump. Returns ``None`` on no match."""

    resolved_registry = registry if registry is not None else load_recipe_registry()
    return resolved_registry.lookup(candidate)


def _major_version(version: str) -> int | None:
    match = _VERSION_PREFIX_PATTERN.match(version.strip())
    if match is None:
        return None
    try:
        return int(match.group(0))
    except ValueError:  # pragma: no cover - regex guarantees digits
        return None


def _coerce_major(raw: object) -> int | None:
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw.strip())
        except ValueError:
            return None
    return None
