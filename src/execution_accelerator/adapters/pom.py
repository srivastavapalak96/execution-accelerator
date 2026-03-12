"""Pom mutation and preflight helpers for the Day 5 simple remediation flow."""

from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

from execution_accelerator.adapters._mode import require_fixture_mode
from execution_accelerator.config import RuntimeConfig
from execution_accelerator.schemas import (
    ExecutionMode,
    PomMutationChange,
    PomMutationPlan,
    PreflightResolutionResult,
)


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
        mode: ExecutionMode = ExecutionMode.FIXTURE,
    ) -> None:
        self.fixture_before_path = fixture_before_path
        self.fixture_after_path = fixture_after_path
        self.mode = mode

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "PomMutationAdapter":
        """Create the pom mutation adapter from runtime configuration."""

        return cls(
            fixture_before_path=config.pom_fixture_before_path,
            fixture_after_path=config.pom_fixture_after_path,
            mode=config.execution_mode,
        )

    def load_fixture_before(self, *, fixture_path: Path | None = None) -> str:
        """Load the baseline pom fixture."""

        require_fixture_mode(self.mode, capability="Pom live mutation seeding")
        resolved_fixture_path = fixture_path or self.fixture_before_path
        if resolved_fixture_path is None:
            raise PomMutationConfigurationError(
                "Pom fixture path is not configured. Set EA_POM_FIXTURE_BEFORE_PATH for local Day 5 remediation."
            )
        return resolved_fixture_path.read_text()

    def apply_plan(self, xml_text: str, plan: PomMutationPlan) -> str:
        """Apply the simple remediation plan to the provided pom.xml text."""

        require_fixture_mode(self.mode, capability="Pom live mutation")
        root = ET.fromstring(
            xml_text,
            parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)),
        )

        for change in plan.changes:
            if change.target_section == "dependency_management":
                self._apply_dependency_management_override(root, change)
            else:
                self._apply_direct_dependency_update(root, change)

        return ET.tostring(root, encoding="unicode")

    def _apply_direct_dependency_update(self, root: ET.Element, change: PomMutationChange) -> None:
        dependencies = root.findall(".//m:dependencies/m:dependency", MAVEN_NAMESPACE)
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
                return
        raise PomMutationTargetError(
            f"Dependency {change.dependency.group_id}:{change.dependency.artifact_id} was not found in pom.xml."
        )

    def _apply_dependency_management_override(self, root: ET.Element, change: PomMutationChange) -> None:
        dependency_management = root.find("m:dependencyManagement", MAVEN_NAMESPACE)
        if dependency_management is None:
            dependency_management = ET.SubElement(root, _namespaced("dependencyManagement"))

        dependencies = dependency_management.find("m:dependencies", MAVEN_NAMESPACE)
        if dependencies is None:
            dependencies = ET.SubElement(dependency_management, _namespaced("dependencies"))

        for dependency in dependencies.findall("m:dependency", MAVEN_NAMESPACE):
            group_id = dependency.find("m:groupId", MAVEN_NAMESPACE)
            artifact_id = dependency.find("m:artifactId", MAVEN_NAMESPACE)
            version = dependency.find("m:version", MAVEN_NAMESPACE)
            if (
                group_id is not None
                and artifact_id is not None
                and group_id.text == change.dependency.group_id
                and artifact_id.text == change.dependency.artifact_id
            ):
                if version is None:
                    version = ET.SubElement(dependency, _namespaced("version"))
                version.text = change.target_version
                return

        dependency = ET.SubElement(dependencies, _namespaced("dependency"))
        ET.SubElement(dependency, _namespaced("groupId")).text = change.dependency.group_id
        ET.SubElement(dependency, _namespaced("artifactId")).text = change.dependency.artifact_id
        ET.SubElement(dependency, _namespaced("version")).text = change.target_version

    def expected_fixture_after(self, *, fixture_path: Path | None = None) -> str:
        """Load the expected mutated pom fixture for local verification."""

        require_fixture_mode(self.mode, capability="Pom live mutation verification")
        resolved_fixture_path = fixture_path or self.fixture_after_path
        if resolved_fixture_path is None:
            raise PomMutationConfigurationError(
                "Expected pom fixture path is not configured. Set EA_POM_FIXTURE_AFTER_PATH for local Day 5 remediation."
            )
        return resolved_fixture_path.read_text()


class PreflightResolutionAdapter:
    """Load fixture-backed preflight resolution results."""

    def __init__(
        self,
        *,
        fixture_path: Path | None = None,
        mode: ExecutionMode = ExecutionMode.FIXTURE,
    ) -> None:
        self.fixture_path = fixture_path
        self.mode = mode

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "PreflightResolutionAdapter":
        """Create the preflight adapter from runtime configuration."""

        return cls(fixture_path=config.preflight_resolution_fixture_path, mode=config.execution_mode)

    def load_result(
        self,
        *,
        repository: str,
        fixture_path: Path | None = None,
    ) -> PreflightResolutionResult:
        """Load the fixture-backed preflight resolution result."""

        require_fixture_mode(self.mode, capability="Preflight live validation")
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


def _namespaced(tag: str) -> str:
    return f"{{{MAVEN_NAMESPACE['m']}}}{tag}"
