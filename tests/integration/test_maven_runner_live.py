"""Integration test: real ``mvn`` invocation against the sample project.

Skipped automatically by the conftest gate unless ``EA_INTEGRATION=1``. Also
self-skips if no JDK can be resolved (CI runners without Java pre-installed).
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from execution_accelerator.execution.maven_runner import MavenRunner
from execution_accelerator.schemas import DependencyCoordinate

COMMONS_TEXT_GROUP = "org.apache.commons"
COMMONS_TEXT_ARTIFACT = "commons-text"


def _mvn_available() -> bool:
    return shutil.which("mvn") is not None


def test_mvn_version_runs(sample_maven_project: Path, java_home: str | None, tmp_path: Path) -> None:
    """``mvn -version`` succeeds with a resolvable JDK."""

    if not _mvn_available():
        pytest.skip("mvn not on PATH")
    if java_home is None:
        pytest.skip("No JDK detected for mvn invocation")

    runner = MavenRunner(
        log_dir=tmp_path / "logs",
        java_home=Path(java_home),
    )
    # ``mvn --version`` is the cheapest probe; it doesn't touch the project.
    result = runner.run(
        sample_maven_project,
        ["--version"],
        jdk_home=Path(java_home),
        action="version",
    )
    assert result.returncode == 0
    assert "Apache Maven" in result.stdout


def test_dependency_tree_contains_known_vulnerable_dep(
    sample_maven_project: Path,
    java_home: str | None,
    tmp_path: Path,
) -> None:
    """``mvn dependency:tree`` lists ``commons-text:1.9`` as a direct dependency."""

    if not _mvn_available():
        pytest.skip("mvn not on PATH")
    if java_home is None:
        pytest.skip("No JDK detected for mvn invocation")

    runner = MavenRunner(log_dir=tmp_path / "logs")

    try:
        entries = runner.dependency_tree(sample_maven_project, jdk_home=Path(java_home))
    except subprocess.SubprocessError as exc:  # pragma: no cover - defensive
        pytest.xfail(f"mvn dependency:tree failed (likely network/Artifactory): {exc}")

    matches = [
        entry
        for entry in entries
        if entry.coordinate.group_id == COMMONS_TEXT_GROUP
        and entry.coordinate.artifact_id == COMMONS_TEXT_ARTIFACT
    ]
    assert matches, "Expected commons-text in the resolved dependency tree"
    direct_match = next((entry for entry in matches if entry.direct), None)
    assert direct_match is not None, "commons-text should be classified as direct"
    assert direct_match.coordinate.version == "1.9"


def test_fetch_metadata_returns_versions_for_commons_text(tmp_path: Path) -> None:
    """Maven Central exposes ``maven-metadata.xml`` for ``commons-text``."""

    runner = MavenRunner(log_dir=tmp_path / "logs")
    coordinate = DependencyCoordinate(
        group_id=COMMONS_TEXT_GROUP,
        artifact_id=COMMONS_TEXT_ARTIFACT,
        version="1.9",
    )

    try:
        metadata = runner.fetch_metadata(coordinate)
    except Exception as exc:  # pragma: no cover - defensive against transient outages
        pytest.xfail(f"Maven Central unreachable: {exc}")

    assert metadata.coordinate.artifact_id == COMMONS_TEXT_ARTIFACT
    assert metadata.versions, "Metadata should list at least one published version"
    # 1.10.0 is the documented fix for CVE-2022-42889 and should appear.
    assert "1.10.0" in metadata.versions
