"""Advisory and Maven verification adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from execution_accelerator.config import RuntimeConfig
from execution_accelerator.execution import MavenRunner
from execution_accelerator.services.advisory import OsvAdvisoryService
from execution_accelerator.schemas import (
    AdvisoryVerification,
    CompatibilityRisk,
    DependencyCoordinate,
    ExecutionMode,
    MavenDependencyKind,
    MavenExecutionPlan,
    MavenVerification,
    VerificationStatus,
    VulnerabilityDetails,
)
from execution_accelerator.state import RepositoryWorkspace


class VerificationAdapterError(RuntimeError):
    """Base error for advisory and Maven verification failures."""


class VerificationConfigurationError(VerificationAdapterError):
    """Raised when local verification fixtures are not configured."""


class AdvisoryVerificationMismatchError(VerificationAdapterError):
    """Raised when advisory verification fixture data does not match the requested package."""


class MavenVerificationMismatchError(VerificationAdapterError):
    """Raised when Maven verification fixture data does not match the requested package."""


class AdvisoryVerificationAdapter:
    """Load normalized advisory verification data from a local fixture."""

    def __init__(
        self,
        *,
        fixture_path: Path | None = None,
        mode: ExecutionMode = ExecutionMode.FIXTURE,
        advisory_service: OsvAdvisoryService | None = None,
    ) -> None:
        self.fixture_path = fixture_path
        self.mode = mode
        self.advisory_service = advisory_service

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "AdvisoryVerificationAdapter":
        """Create the advisory adapter from runtime configuration."""

        return cls(
            fixture_path=config.advisory_fixture_path,
            mode=config.execution_mode,
            advisory_service=OsvAdvisoryService(
                api_base_url=config.advisory_api_base_url,
                cache_dir=config.cache_dir / "osv",
            ),
        )

    def load_verification(
        self,
        vulnerability_details: VulnerabilityDetails,
        *,
        fixture_path: Path | None = None,
    ) -> AdvisoryVerification:
        """Load advisory verification data for the requested vulnerability."""

        if self.mode == ExecutionMode.LIVE:
            if self.advisory_service is None:
                raise VerificationConfigurationError("Live advisory verification requires an OSV advisory service.")
            try:
                return self.advisory_service.query(
                    package_name=vulnerability_details.package_name,
                    version=vulnerability_details.installed_version,
                    severity=vulnerability_details.severity,
                    fixed_version_hint=vulnerability_details.fixed_version,
                )
            except (httpx.HTTPError, ValueError) as exc:
                raise VerificationAdapterError(
                    f"Failed to verify advisory data for {vulnerability_details.package_name}: {exc}"
                ) from exc

        resolved_fixture_path = fixture_path or self.fixture_path
        if resolved_fixture_path is None:
            raise VerificationConfigurationError(
                "Advisory fixture path is not configured. Set EA_ADVISORY_FIXTURE_PATH for local Day 4 verification."
            )

        verification = AdvisoryVerification.model_validate(json.loads(resolved_fixture_path.read_text()))
        if verification.package_name != vulnerability_details.package_name:
            raise AdvisoryVerificationMismatchError(
                "Advisory verification fixture package does not match the requested vulnerability package."
            )

        return verification


class MavenVerificationAdapter:
    """Load Maven verification data from a local fixture."""

    def __init__(
        self,
        *,
        fixture_path: Path | None = None,
        mode: ExecutionMode = ExecutionMode.FIXTURE,
        maven_runner: MavenRunner | None = None,
        eol_packages_path: Path | None = None,
    ) -> None:
        self.fixture_path = fixture_path
        self.mode = mode
        self.maven_runner = maven_runner
        self.eol_packages_path = eol_packages_path

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "MavenVerificationAdapter":
        """Create the Maven verification adapter from runtime configuration."""

        return cls(
            fixture_path=config.maven_verification_fixture_path,
            mode=config.execution_mode,
            maven_runner=MavenRunner(
                log_dir=config.logs_dir / "maven",
                metadata_base_url=config.maven_metadata_base_url,
                java_home=config.java_home,
            ),
            eol_packages_path=config.repo_root / "config" / "eol_packages.yaml",
        )

    def load_verification(
        self,
        vulnerability_details: VulnerabilityDetails,
        *,
        target_version: str,
        repository_workspace: RepositoryWorkspace | None = None,
        maven_plan: MavenExecutionPlan | None = None,
        fixture_path: Path | None = None,
    ) -> MavenVerification:
        """Load Maven verification data for the selected remediation target."""

        if self.mode == ExecutionMode.LIVE:
            return self._load_live_verification(
                vulnerability_details,
                target_version=target_version,
                repository_workspace=repository_workspace,
                maven_plan=maven_plan,
            )

        resolved_fixture_path = fixture_path or self.fixture_path
        if resolved_fixture_path is None:
            raise VerificationConfigurationError(
                "Maven verification fixture path is not configured. "
                "Set EA_MAVEN_VERIFICATION_FIXTURE_PATH for local Day 4 verification."
            )

        verification = MavenVerification.model_validate(json.loads(resolved_fixture_path.read_text()))
        if verification.package_name != vulnerability_details.package_name:
            raise MavenVerificationMismatchError(
                "Maven verification fixture package does not match the requested vulnerability package."
            )
        if verification.target_version != target_version:
            raise MavenVerificationMismatchError(
                "Maven verification fixture target version does not match the requested remediation target."
            )

        return verification

    def _load_live_verification(
        self,
        vulnerability_details: VulnerabilityDetails,
        *,
        target_version: str,
        repository_workspace: RepositoryWorkspace | None,
        maven_plan: MavenExecutionPlan | None,
    ) -> MavenVerification:
        if self.maven_runner is None:
            raise VerificationConfigurationError("Live Maven verification requires a configured Maven runner.")
        if repository_workspace is None:
            raise VerificationConfigurationError("Live Maven verification requires a repository workspace.")

        coordinate = _parse_package_name(vulnerability_details.package_name, version=vulnerability_details.installed_version)
        metadata = self.maven_runner.fetch_metadata(coordinate)
        if target_version not in metadata.versions:
            return MavenVerification(
                package_name=vulnerability_details.package_name,
                current_version=vulnerability_details.installed_version,
                target_version=target_version,
                dependency_kind=MavenDependencyKind.DIRECT,
                status=VerificationStatus.REJECTED,
                compatibility_risk=CompatibilityRisk.HIGH,
                resolver_note="Target version is not present in Maven metadata.",
            )

        dependency_tree = self.maven_runner.dependency_tree(
            Path(repository_workspace.local_path),
            settings_xml=Path(maven_plan.settings_xml) if maven_plan and maven_plan.settings_xml else None,
            jdk_home=Path(maven_plan.java_home) if maven_plan and maven_plan.java_home else None,
        )
        matching_entries = [
            entry
            for entry in dependency_tree
            if entry.coordinate.group_id == coordinate.group_id and entry.coordinate.artifact_id == coordinate.artifact_id
        ]
        if not matching_entries:
            return MavenVerification(
                package_name=vulnerability_details.package_name,
                current_version=vulnerability_details.installed_version,
                target_version=target_version,
                dependency_kind=MavenDependencyKind.DIRECT,
                status=VerificationStatus.REJECTED,
                compatibility_risk=CompatibilityRisk.HIGH,
                resolver_note="Dependency tree did not include the vulnerable package.",
            )

        dependency_kind = (
            MavenDependencyKind.DIRECT
            if any(entry.direct for entry in matching_entries)
            else MavenDependencyKind.TRANSITIVE
        )
        compatibility_risk = _build_compatibility_risk(
            vulnerability_details.package_name,
            current_version=vulnerability_details.installed_version,
            target_version=target_version,
            eol_packages=_load_eol_packages(self.eol_packages_path),
        )
        return MavenVerification(
            package_name=vulnerability_details.package_name,
            current_version=vulnerability_details.installed_version,
            target_version=target_version,
            dependency_kind=dependency_kind,
            status=VerificationStatus.VERIFIED,
            compatibility_risk=compatibility_risk,
            resolver_note=_build_resolver_note(
                dependency_kind=dependency_kind,
                compatibility_risk=compatibility_risk,
            ),
        )


def _parse_package_name(package_name: str, *, version: str) -> DependencyCoordinate:
    try:
        group_id, artifact_id = package_name.split(":", 1)
    except ValueError as exc:
        raise VerificationConfigurationError(f"Invalid Maven package coordinate: {package_name}") from exc
    return DependencyCoordinate(group_id=group_id, artifact_id=artifact_id, version=version)


def _build_compatibility_risk(
    package_name: str,
    *,
    current_version: str,
    target_version: str,
    eol_packages: set[str],
) -> CompatibilityRisk:
    if package_name in eol_packages:
        return CompatibilityRisk.HIGH
    current_major, current_minor = _parse_major_minor(current_version)
    target_major, target_minor = _parse_major_minor(target_version)
    if current_major != target_major:
        return CompatibilityRisk.HIGH
    if current_minor != target_minor:
        return CompatibilityRisk.MEDIUM
    return CompatibilityRisk.LOW


def _parse_major_minor(version: str) -> tuple[int, int]:
    parts = version.split(".")
    major = int(parts[0]) if parts and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return major, minor


def _load_eol_packages(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    loaded = json.loads(path.read_text()) if path.suffix == ".json" else _load_yaml(path)
    packages = loaded.get("packages") if isinstance(loaded, dict) else None
    if not isinstance(packages, list):
        return set()
    return {package for package in packages if isinstance(package, str)}


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    loaded = yaml.safe_load(path.read_text()) or {}
    return loaded if isinstance(loaded, dict) else {}


def _build_resolver_note(
    *,
    dependency_kind: MavenDependencyKind,
    compatibility_risk: CompatibilityRisk,
) -> str:
    if dependency_kind == MavenDependencyKind.TRANSITIVE:
        return (
            "Target version is only present transitively, so remediation should add "
            f"a dependencyManagement override with {compatibility_risk} compatibility risk."
        )
    return f"Target version is available directly with {compatibility_risk} compatibility risk."
