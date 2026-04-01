from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from execution_accelerator.schemas import MavenExecutionPlan

from .maven_runner import MavenRunner
from .sandbox import CommandResult


_REWRITE_RUN_GOAL = "org.openrewrite.maven:rewrite-maven-plugin:run"
_REWRITE_DRY_RUN_GOAL = "org.openrewrite.maven:rewrite-maven-plugin:dryRun"
_UPGRADE_DEPENDENCY_RECIPE = "org.openrewrite.maven.UpgradeDependencyVersion"


@dataclass
class OpenRewriteRunner:
    """Thin helper for invoking OpenRewrite Maven goals with detected repo settings."""

    maven_runner: MavenRunner
    recipe_artifact_coordinates: str | None = None

    def plan_upgrade(
        self,
        cwd: Path,
        *,
        group_id: str,
        artifact_id: str,
        target_version: str,
        execution_plan: MavenExecutionPlan | None = None,
    ) -> CommandResult:
        return self.run_named_recipe(
            cwd,
            recipe_name=_UPGRADE_DEPENDENCY_RECIPE,
            recipe_options={
                "groupId": group_id,
                "artifactId": artifact_id,
                "newVersion": target_version,
            },
            execution_plan=execution_plan,
            dry_run=True,
        )

    def apply_recipe(
        self,
        cwd: Path,
        *,
        recipe_name: str,
        execution_plan: MavenExecutionPlan | None = None,
        recipe_options: dict[str, str] | None = None,
    ) -> CommandResult:
        return self.run_named_recipe(
            cwd,
            recipe_name=recipe_name,
            execution_plan=execution_plan,
            recipe_options=recipe_options,
            dry_run=False,
        )

    def run_named_recipe(
        self,
        cwd: Path,
        *,
        recipe_name: str,
        execution_plan: MavenExecutionPlan | None = None,
        recipe_options: dict[str, str] | None = None,
        dry_run: bool = False,
    ) -> CommandResult:
        goal = _REWRITE_DRY_RUN_GOAL if dry_run else _REWRITE_RUN_GOAL
        args = [goal, f"-Drewrite.activeRecipes={recipe_name}"]
        if self.recipe_artifact_coordinates:
            args.append(f"-Drewrite.recipeArtifactCoordinates={self.recipe_artifact_coordinates}")
        if recipe_options:
            serialized_options = ",".join(f"{key}={value}" for key, value in sorted(recipe_options.items()))
            args.append(f"-Drewrite.options={serialized_options}")
        return self.maven_runner.run(
            cwd,
            args,
            settings_xml=_plan_settings_path(execution_plan),
            jdk_home=_plan_java_home(execution_plan),
            action=f"openrewrite-{'dry-run' if dry_run else 'run'}",
        )


def _plan_settings_path(execution_plan: MavenExecutionPlan | None) -> Path | None:
    if execution_plan is None or execution_plan.settings_xml is None:
        return None
    return Path(execution_plan.settings_xml)


def _plan_java_home(execution_plan: MavenExecutionPlan | None) -> Path | None:
    if execution_plan is None or execution_plan.java_home is None:
        return None
    return Path(execution_plan.java_home)
