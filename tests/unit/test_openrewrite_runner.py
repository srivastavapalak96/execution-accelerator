from __future__ import annotations

from pathlib import Path

from execution_accelerator.execution import MavenRunner, OpenRewriteRunner
from execution_accelerator.schemas import MavenExecutionPlan


def test_openrewrite_runner_plans_upgrade_with_detected_maven_settings(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    args_file = repo_dir / "rewrite-args.txt"
    wrapper = repo_dir / "mvnw"
    wrapper.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                f"printf '%s\\n' \"$@\" > {args_file}",
                "echo '[INFO] rewrite dry run complete'",
            ]
        )
        + "\n"
    )
    wrapper.chmod(0o755)
    settings_path = tmp_path / "settings.xml"
    settings_path.write_text("<settings />\n")
    java_home = tmp_path / "jdk-17"
    java_home.mkdir()
    runner = OpenRewriteRunner(MavenRunner(log_dir=tmp_path / "logs"))

    result = runner.plan_upgrade(
        repo_dir,
        group_id="org.example",
        artifact_id="legacy-json",
        target_version="1.2.4",
        execution_plan=MavenExecutionPlan(
            repository="payments-service",
            command=["./mvnw"],
            root_pom_path=str(repo_dir / "pom.xml"),
            uses_wrapper=True,
            settings_xml=str(settings_path),
            java_home=str(java_home),
        ),
    )

    invoked_args = args_file.read_text().splitlines()
    assert result.stdout.strip() == "[INFO] rewrite dry run complete"
    assert invoked_args[0] == "-s"
    assert invoked_args[1] == str(settings_path)
    assert invoked_args[2] == "org.openrewrite.maven:rewrite-maven-plugin:dryRun"
    assert "-Drewrite.activeRecipes=org.openrewrite.java.dependencies.UpgradeDependencyVersion" in invoked_args
    assert "-Drewrite.groupId=org.example" in invoked_args
    assert "-Drewrite.artifactId=legacy-json" in invoked_args
    assert "-Drewrite.newVersion=1.2.4" in invoked_args


def test_openrewrite_runner_applies_named_recipe_with_recipe_artifact_coordinates(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    args_file = repo_dir / "rewrite-apply-args.txt"
    wrapper = repo_dir / "mvnw"
    wrapper.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                f"printf '%s\\n' \"$@\" > {args_file}",
                "echo '[INFO] rewrite apply complete'",
            ]
        )
        + "\n"
    )
    wrapper.chmod(0o755)
    runner = OpenRewriteRunner(
        MavenRunner(log_dir=tmp_path / "logs"),
        recipe_artifact_coordinates="org.openrewrite.recipe:rewrite-migrate-java:1.0.0",
    )

    result = runner.apply_recipe(
        repo_dir,
        recipe_name="org.openrewrite.java.migrate.UpgradeToJava17",
        recipe_options={"style": "google"},
    )

    invoked_args = args_file.read_text().splitlines()
    assert result.stdout.strip() == "[INFO] rewrite apply complete"
    assert invoked_args[0] == "org.openrewrite.maven:rewrite-maven-plugin:run"
    assert "-Drewrite.activeRecipes=org.openrewrite.java.migrate.UpgradeToJava17" in invoked_args
    assert "-Drewrite.recipeArtifactCoordinates=org.openrewrite.recipe:rewrite-migrate-java:1.0.0" in invoked_args
    assert "-Drewrite.style=google" in invoked_args
