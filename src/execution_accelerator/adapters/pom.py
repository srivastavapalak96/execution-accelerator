"""Pom mutation and preflight helpers for the Day 5 simple remediation flow."""

from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

from execution_accelerator.adapters._mode import FixtureOnlyError
from execution_accelerator.config import RuntimeConfig, load_credentials
from execution_accelerator.execution import DependencyTreeEntry, MavenRunner, OpenRewriteRunner
from execution_accelerator.schemas import (
    DependencyCoordinate,
    ExecutionMode,
    MavenExecutionPlan,
    MavenVerification,
    PomMutationChange,
    PomMutationPlan,
    PreflightResolutionResult,
    ValidationStatus,
    VulnerabilityDetails,
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
        openrewrite_runner: OpenRewriteRunner | None = None,
    ) -> None:
        self.fixture_before_path = fixture_before_path
        self.fixture_after_path = fixture_after_path
        self.mode = mode
        self.openrewrite_runner = openrewrite_runner

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "PomMutationAdapter":
        """Create the pom mutation adapter from runtime configuration."""

        credentials = load_credentials(repo_root=config.repo_root)
        return cls(
            fixture_before_path=config.pom_fixture_before_path,
            fixture_after_path=config.pom_fixture_after_path,
            mode=config.execution_mode,
            openrewrite_runner=OpenRewriteRunner(
                MavenRunner(
                    log_dir=config.logs_dir / "maven",
                    settings_xml=credentials.maven_settings,
                    java_home=config.java_home,
                )
            ),
        )

    def load_fixture_before(self, *, fixture_path: Path | None = None) -> str:
        """Load the baseline pom fixture."""

        if self.mode == ExecutionMode.LIVE:
            raise FixtureOnlyError("Pom fixture seeding is only available in EA_MODE=fixture.")
        resolved_fixture_path = fixture_path or self.fixture_before_path
        if resolved_fixture_path is None:
            raise PomMutationConfigurationError(
                "Pom fixture path is not configured. Set EA_POM_FIXTURE_BEFORE_PATH for local Day 5 remediation."
            )
        return resolved_fixture_path.read_text()

    def apply_plan(
        self,
        xml_text: str,
        plan: PomMutationPlan,
        *,
        workspace_path: Path | None = None,
        execution_plan: MavenExecutionPlan | None = None,
    ) -> str:
        """Apply the simple remediation plan to the provided pom.xml text."""

        if self.mode == ExecutionMode.LIVE:
            return self._apply_live_plan(plan, workspace_path=workspace_path, execution_plan=execution_plan)

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

    def _apply_live_plan(
        self,
        plan: PomMutationPlan,
        *,
        workspace_path: Path | None,
        execution_plan: MavenExecutionPlan | None,
    ) -> str:
        if self.openrewrite_runner is None:
            raise PomMutationConfigurationError("Live pom mutation requires an OpenRewrite runner.")
        if workspace_path is None:
            raise PomMutationConfigurationError("Live pom mutation requires a workspace path.")

        for change in plan.changes:
            if change.target_section == "dependency_management":
                self.openrewrite_runner.apply_recipe(
                    workspace_path,
                    recipe_name="org.openrewrite.maven.AddManagedDependency",
                    execution_plan=execution_plan,
                    recipe_options={
                        "groupId": change.dependency.group_id,
                        "artifactId": change.dependency.artifact_id,
                        "version": change.target_version,
                    },
                )
                continue
            self.openrewrite_runner.apply_recipe(
                workspace_path,
                recipe_name="org.openrewrite.java.dependencies.UpgradeDependencyVersion",
                execution_plan=execution_plan,
                recipe_options={
                    "groupId": change.dependency.group_id,
                    "artifactId": change.dependency.artifact_id,
                    "newVersion": change.target_version,
                },
            )

        target_path = Path(workspace_path) / plan.changes[0].file_path
        if not target_path.exists():
            raise PomMutationTargetError(f"OpenRewrite did not produce the expected pom file: {target_path}")
        return target_path.read_text()

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

        if self.mode == ExecutionMode.LIVE:
            raise FixtureOnlyError("Pom fixture verification is only available in EA_MODE=fixture.")
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
        maven_runner: MavenRunner | None = None,
    ) -> None:
        self.fixture_path = fixture_path
        self.mode = mode
        self.maven_runner = maven_runner

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "PreflightResolutionAdapter":
        """Create the preflight adapter from runtime configuration."""

        credentials = load_credentials(repo_root=config.repo_root)
        return cls(
            fixture_path=config.preflight_resolution_fixture_path,
            mode=config.execution_mode,
            maven_runner=MavenRunner(
                log_dir=config.logs_dir / "maven",
                settings_xml=credentials.maven_settings,
                java_home=config.java_home,
            ),
        )

    def load_result(
        self,
        *,
        repository: str,
        workspace_path: Path | None = None,
        vulnerability_details: VulnerabilityDetails | None = None,
        maven_verification: MavenVerification | None = None,
        execution_plan: MavenExecutionPlan | None = None,
        fixture_path: Path | None = None,
    ) -> PreflightResolutionResult:
        """Load the fixture-backed preflight resolution result."""

        if self.mode == ExecutionMode.LIVE:
            return self._load_live_result(
                repository=repository,
                workspace_path=workspace_path,
                vulnerability_details=vulnerability_details,
                maven_verification=maven_verification,
                execution_plan=execution_plan,
            )

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

    def _load_live_result(
        self,
        *,
        repository: str,
        workspace_path: Path | None,
        vulnerability_details: VulnerabilityDetails | None,
        maven_verification: MavenVerification | None,
        execution_plan: MavenExecutionPlan | None,
    ) -> PreflightResolutionResult:
        if self.maven_runner is None:
            raise PomMutationConfigurationError("Live preflight validation requires a Maven runner.")
        if workspace_path is None:
            raise PomMutationConfigurationError("Live preflight validation requires a workspace path.")
        if vulnerability_details is None or maven_verification is None:
            raise PomMutationConfigurationError("Live preflight validation requires verified vulnerability details.")

        coordinate = _dependency_coordinate(vulnerability_details, target_version=maven_verification.target_version)
        dependency_tree = self.maven_runner.dependency_tree(
            workspace_path,
            settings_xml=Path(execution_plan.settings_xml) if execution_plan and execution_plan.settings_xml else None,
            jdk_home=Path(execution_plan.java_home) if execution_plan and execution_plan.java_home else None,
        )
        matching_entries = _matching_dependency_entries(dependency_tree, coordinate=coordinate)
        if not matching_entries:
            return PreflightResolutionResult(
                repository=repository,
                status=ValidationStatus.FAILED,
                resolved_version=vulnerability_details.installed_version,
                dependency_kind=maven_verification.dependency_kind,
                message="Dependency did not resolve after the requested pom mutation.",
            )

        resolved_entry = next(
            (entry for entry in matching_entries if entry.coordinate.version == maven_verification.target_version),
            matching_entries[0],
        )
        status = (
            ValidationStatus.PASSED
            if resolved_entry.coordinate.version == maven_verification.target_version
            else ValidationStatus.FAILED
        )
        message = (
            f"Dependency resolves cleanly after the {'direct version bump' if resolved_entry.direct else 'managed override'}."
            if status == ValidationStatus.PASSED
            else "Dependency resolved, but not to the requested target version."
        )
        return PreflightResolutionResult(
            repository=repository,
            status=status,
            resolved_version=resolved_entry.coordinate.version,
            dependency_kind=maven_verification.dependency_kind,
            message=message,
        )


def _namespaced(tag: str) -> str:
    return f"{{{MAVEN_NAMESPACE['m']}}}{tag}"


def _dependency_coordinate(
    vulnerability_details: VulnerabilityDetails,
    *,
    target_version: str,
) -> DependencyCoordinate:
    group_id, artifact_id = vulnerability_details.package_name.split(":", maxsplit=1)
    return DependencyCoordinate(group_id=group_id, artifact_id=artifact_id, version=target_version)


def _matching_dependency_entries(
    entries: list[DependencyTreeEntry],
    *,
    coordinate: DependencyCoordinate,
) -> list[DependencyTreeEntry]:
    return [
        entry
        for entry in entries
        if entry.coordinate.group_id == coordinate.group_id and entry.coordinate.artifact_id == coordinate.artifact_id
    ]
