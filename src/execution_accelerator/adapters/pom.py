"""Pom mutation and preflight helpers for the Day 5 simple remediation flow."""

from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

from execution_accelerator.config import RuntimeConfig
from execution_accelerator.schemas import PomMutationPlan, PreflightResolutionResult


MAVEN_NAMESPACE = {"m": "http://maven.apache.org/POM/4.0.0"}


class PomMutationAdapterError(RuntimeError):
    """Base error for pom mutation and preflight helpers."""


class PomMutationConfigurationError(PomMutationAdapterError):
    """Raised when local pom/preflight fixtures are not configured."""


class PomMutationTargetError(PomMutationAdapterError):
    """Raised when the target dependency cannot be found in the provided pom document."""


class PomMutationAdapter:
    """Apply simple fixture-backed pom.xml mutations for local Day 5 development."""

    def __init__(
        self,
        *,
        fixture_before_path: Path | None = None,
        fixture_after_path: Path | None = None,
    ) -> None:
        self.fixture_before_path = fixture_before_path
        self.fixture_after_path = fixture_after_path

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "PomMutationAdapter":
        """Create the pom mutation adapter from runtime configuration."""

        return cls(
            fixture_before_path=config.pom_fixture_before_path,
            fixture_after_path=config.pom_fixture_after_path,
        )

    def load_fixture_before(self, *, fixture_path: Path | None = None) -> str:
        """Load the baseline pom fixture."""

        resolved_fixture_path = fixture_path or self.fixture_before_path
        if resolved_fixture_path is None:
            raise PomMutationConfigurationError(
                "Pom fixture path is not configured. Set EA_POM_FIXTURE_BEFORE_PATH for local Day 5 remediation."
            )
        return resolved_fixture_path.read_text()

    def apply_plan(self, xml_text: str, plan: PomMutationPlan) -> str:
        """Apply the simple remediation plan to the provided pom.xml text."""

        root = ET.fromstring(xml_text)

        for change in plan.changes:
            dependencies = root.findall(".//m:dependency", MAVEN_NAMESPACE)
            matched = False
            for dependency in dependencies:
                group_id = dependency.find("m:groupId", MAVEN_NAMESPACE)
                artifact_id = dependency.find("m:artifactId", MAVEN_NAMESPACE)
                version = dependency.find("m:version", MAVEN_NAMESPACE)
                if (
                    group_id is not None
                    and artifact_id is not None
                    and version is not None
                    and group_id.text == change.dependency.group_id
                    and artifact_id.text == change.dependency.artifact_id
                ):
                    version.text = change.target_version
                    matched = True
                    break
            if not matched:
                raise PomMutationTargetError(
                    f"Dependency {change.dependency.group_id}:{change.dependency.artifact_id} was not found in pom.xml."
                )

        return ET.tostring(root, encoding="unicode")

    def expected_fixture_after(self, *, fixture_path: Path | None = None) -> str:
        """Load the expected mutated pom fixture for local verification."""

        resolved_fixture_path = fixture_path or self.fixture_after_path
        if resolved_fixture_path is None:
            raise PomMutationConfigurationError(
                "Expected pom fixture path is not configured. Set EA_POM_FIXTURE_AFTER_PATH for local Day 5 remediation."
            )
        return resolved_fixture_path.read_text()


class PreflightResolutionAdapter:
    """Load fixture-backed preflight resolution results."""

    def __init__(self, *, fixture_path: Path | None = None) -> None:
        self.fixture_path = fixture_path

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "PreflightResolutionAdapter":
        """Create the preflight adapter from runtime configuration."""

        return cls(fixture_path=config.preflight_resolution_fixture_path)

    def load_result(
        self,
        *,
        repository: str,
        fixture_path: Path | None = None,
    ) -> PreflightResolutionResult:
        """Load the fixture-backed preflight resolution result."""

        resolved_fixture_path = fixture_path or self.fixture_path
        if resolved_fixture_path is None:
            raise PomMutationConfigurationError(
                "Preflight resolution fixture path is not configured. "
                "Set EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH for local Day 5 remediation."
            )

        result = PreflightResolutionResult.model_validate(json.loads(resolved_fixture_path.read_text()))
        if result.repository != repository:
            raise PomMutationTargetError(
                "Preflight resolution fixture repository does not match the requested repository."
            )
        return result
