"""Unit tests for execution_accelerator.tough_path.recipe_matcher."""

from __future__ import annotations

from pathlib import Path

import pytest

from execution_accelerator.tough_path.recipe_matcher import (
    RecipeMatchInput,
    RecipeRegistry,
    RecipeRegistryError,
    load_recipe_registry,
    match_recipe,
)


def _write_registry(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "recipes.yaml"
    path.write_text(content)
    return path


@pytest.fixture
def junit_registry(tmp_path: Path) -> RecipeRegistry:
    path = _write_registry(
        tmp_path,
        """
recipes:
  - match: { group: junit, artifact: junit, from_major: 4, to_major: 5 }
    recipe: org.openrewrite.java.testing.junit5.JUnit4to5Migration
    rationale: Community recipe.
""".strip(),
    )
    return load_recipe_registry(path)


def test_match_recipe_exact_major_version_jump(junit_registry: RecipeRegistry) -> None:
    candidate = RecipeMatchInput(
        group="junit",
        artifact="junit",
        from_version="4.13.2",
        to_version="5.10.0",
    )
    result = match_recipe(candidate, registry=junit_registry)
    assert result is not None
    assert result.recipe == "org.openrewrite.java.testing.junit5.JUnit4to5Migration"
    assert result.matched_from_major == 4
    assert result.matched_to_major == 5


def test_match_recipe_returns_none_on_unknown_artifact(junit_registry: RecipeRegistry) -> None:
    candidate = RecipeMatchInput(
        group="junk",
        artifact="not-real",
        from_version="1.0",
        to_version="2.0",
    )
    assert match_recipe(candidate, registry=junit_registry) is None


def test_match_recipe_returns_none_on_wrong_major_jump(junit_registry: RecipeRegistry) -> None:
    candidate = RecipeMatchInput(
        group="junit",
        artifact="junit",
        from_version="3.8.1",
        to_version="4.13.2",
    )
    # 3 -> 4 doesn't match the 4 -> 5 recipe in our fixture.
    assert match_recipe(candidate, registry=junit_registry) is None


def test_match_recipe_handles_qualifiers(junit_registry: RecipeRegistry) -> None:
    """Trailing -SNAPSHOT/-RC1/etc. should not break the major-version match."""

    candidate = RecipeMatchInput(
        group="junit",
        artifact="junit",
        from_version="4.13.2-SNAPSHOT",
        to_version="5.10.0-RC1",
    )
    assert match_recipe(candidate, registry=junit_registry) is not None


def test_match_recipe_returns_none_on_unparseable_version(junit_registry: RecipeRegistry) -> None:
    candidate = RecipeMatchInput(
        group="junit",
        artifact="junit",
        from_version="not-a-version",
        to_version="5.10.0",
    )
    assert match_recipe(candidate, registry=junit_registry) is None


def test_load_registry_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"
    with pytest.raises(RecipeRegistryError, match="not found"):
        load_recipe_registry(missing)


def test_load_registry_rejects_non_mapping_root(tmp_path: Path) -> None:
    path = _write_registry(tmp_path, "- one\n- two\n")
    with pytest.raises(RecipeRegistryError, match="must be a mapping"):
        load_recipe_registry(path)


def test_load_registry_rejects_non_list_recipes(tmp_path: Path) -> None:
    path = _write_registry(tmp_path, "recipes: 'not-a-list'\n")
    with pytest.raises(RecipeRegistryError, match="must be a list"):
        load_recipe_registry(path)


def test_load_registry_rejects_entry_without_recipe(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path,
        """
recipes:
  - match: { group: x, artifact: y, from_major: 1, to_major: 2 }
    rationale: missing recipe key
""".strip(),
    )
    registry = load_recipe_registry(path)
    candidate = RecipeMatchInput(group="x", artifact="y", from_version="1.0", to_version="2.0")
    with pytest.raises(RecipeRegistryError, match="no 'recipe' field"):
        match_recipe(candidate, registry=registry)


def test_default_registry_loads_from_repo_config() -> None:
    """The repo-level config file should parse into a non-empty registry."""

    registry = load_recipe_registry()
    assert len(registry.entries) >= 1
    # Sanity check: the JUnit and commons-lang entries should be present.
    candidate = RecipeMatchInput(
        group="junit",
        artifact="junit",
        from_version="4.13.2",
        to_version="5.10.0",
    )
    result = match_recipe(candidate, registry=registry)
    assert result is not None
    assert "JUnit4to5Migration" in result.recipe
