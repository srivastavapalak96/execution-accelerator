"""Fixture-backed validation and rollback helpers for the Day 9 workflow."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from execution_accelerator.adapters._mode import require_fixture_mode
from execution_accelerator.config import RuntimeConfig, load_credentials
from execution_accelerator.execution import (
    DependencyTreeEntry,
    GitRunner,
    MavenCommandError,
    MavenRunner,
    SurefireReportSummary,
    parse_surefire_reports,
)
from execution_accelerator.schemas import (
    DependencyCoordinate,
    ExecutionMode,
    MavenExecutionPlan,
    MavenVerification,
    RepositoryValidationResult,
    RollbackPlan,
    RollbackStatus,
    ValidationCheck,
    ValidationStatus,
    VulnerabilityDetails,
)


class ValidationAdapterError(RuntimeError):
    """Base error for Day 9 validation helpers."""


class ValidationConfigurationError(ValidationAdapterError):
    """Raised when validation fixture configuration is missing."""


class ValidationAdapter:
    """Load placeholder validation and rollback payloads from fixtures."""

    def __init__(
        self,
        *,
        validation_result_fixture_path: Path | None = None,
        rollback_fixture_path: Path | None = None,
        mode: ExecutionMode = ExecutionMode.FIXTURE,
        maven_runner: MavenRunner | None = None,
        git_runner: GitRunner | None = None,
        license_denylist: tuple[str, ...] = (),
        license_allowlist: tuple[str, ...] = (),
    ) -> None:
        self.validation_result_fixture_path = validation_result_fixture_path
        self.rollback_fixture_path = rollback_fixture_path
        self.mode = mode
        self.maven_runner = maven_runner
        self.git_runner = git_runner
        self.license_denylist = license_denylist
        self.license_allowlist = license_allowlist

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "ValidationAdapter":
        """Create the validation adapter from runtime configuration."""

        credentials = load_credentials(repo_root=config.repo_root)
        return cls(
            validation_result_fixture_path=config.validation_result_fixture_path,
            rollback_fixture_path=config.rollback_fixture_path,
            mode=config.execution_mode,
            maven_runner=MavenRunner(
                log_dir=config.logs_dir / "maven",
                metadata_base_url=config.maven_metadata_base_url,
                settings_xml=credentials.maven_settings,
                java_home=config.java_home,
            ),
            git_runner=GitRunner(
                log_dir=config.logs_dir / "git",
                secrets=tuple(secret for secret in (credentials.github_token,) if secret),
            ),
            license_denylist=config.license_denylist,
            license_allowlist=config.license_allowlist,
        )

    def load_validation_result(
        self,
        *,
        repository: str,
        workspace_path: Path | None = None,
        execution_plan: MavenExecutionPlan | None = None,
        vulnerability_details: VulnerabilityDetails | None = None,
        maven_verification: MavenVerification | None = None,
        fixture_path: Path | None = None,
    ) -> RepositoryValidationResult:
        """Load the placeholder validation result for one repository."""

        if self.mode == ExecutionMode.LIVE:
            return self._load_live_validation_result(
                repository=repository,
                workspace_path=workspace_path,
                execution_plan=execution_plan,
                vulnerability_details=vulnerability_details,
                maven_verification=maven_verification,
            )

        require_fixture_mode(self.mode, capability="Validation live execution")
        resolved_fixture_path = fixture_path or self.validation_result_fixture_path
        if resolved_fixture_path is None:
            raise ValidationConfigurationError(
                "Validation result fixture path is not configured. "
                "Set EA_VALIDATION_RESULT_FIXTURE_PATH for local Day 9 validation."
            )

        result = RepositoryValidationResult.model_validate(json.loads(resolved_fixture_path.read_text()))
        return result.model_copy(update={"repository": repository})

    def _load_live_validation_result(
        self,
        *,
        repository: str,
        workspace_path: Path | None,
        execution_plan: MavenExecutionPlan | None,
        vulnerability_details: VulnerabilityDetails | None,
        maven_verification: MavenVerification | None,
    ) -> RepositoryValidationResult:
        if self.maven_runner is None:
            raise ValidationConfigurationError("Live validation requires a configured Maven runner.")
        if workspace_path is None:
            raise ValidationConfigurationError("Live validation requires a workspace path.")

        checks: list[ValidationCheck] = []
        status = ValidationStatus.PASSED
        summary = "Live Maven verify and Surefire validation passed."
        try:
            self.maven_runner.verify(
                workspace_path,
                settings_xml=Path(execution_plan.settings_xml) if execution_plan and execution_plan.settings_xml else None,
                jdk_home=Path(execution_plan.java_home) if execution_plan and execution_plan.java_home else None,
            )
            checks.append(
                ValidationCheck(
                    name="compile",
                    status=ValidationStatus.PASSED,
                    details="Maven verify completed successfully.",
                )
            )
        except MavenCommandError as exc:
            status = ValidationStatus.FAILED
            summary = "Live Maven verify failed."
            checks.append(
                ValidationCheck(
                    name="compile",
                    status=ValidationStatus.FAILED,
                    details=(exc.result.stderr or exc.result.stdout or "Maven verify failed.").strip(),
                )
            )

        surefire_summary = _collect_test_reports(workspace_path)
        if surefire_summary is None:
            checks.append(
                ValidationCheck(
                    name="unit-tests",
                    status=ValidationStatus.PASSED if status == ValidationStatus.PASSED else ValidationStatus.PENDING,
                    details="No Surefire/Failsafe XML reports were produced.",
                )
            )
        else:
            test_status = ValidationStatus.PASSED if surefire_summary.passed else ValidationStatus.FAILED
            if test_status == ValidationStatus.FAILED:
                status = ValidationStatus.FAILED
                summary = "Live validation detected test failures."
            checks.append(
                ValidationCheck(
                    name="unit-tests",
                    status=test_status,
                    details=(
                        f"{surefire_summary.total_tests} tests, "
                        f"{surefire_summary.total_failures} failures, "
                        f"{surefire_summary.total_errors} errors, "
                        f"{surefire_summary.total_skipped} skipped."
                    ),
                )
            )

        dependency_tree, dependency_tree_error = _load_dependency_tree_scan(
            maven_runner=self.maven_runner,
            workspace_path=workspace_path,
            execution_plan=execution_plan,
        )
        security_check = _build_security_check(
            dependency_tree=dependency_tree,
            dependency_tree_error=dependency_tree_error,
            vulnerability_details=vulnerability_details,
            maven_verification=maven_verification,
        )
        checks.append(security_check)
        if security_check.status == ValidationStatus.FAILED:
            status = ValidationStatus.FAILED
            summary = (
                "Live validation could not inspect the remediated dependency tree."
                if _is_transient_validation_check(security_check)
                else "Live validation detected an unresolved vulnerable dependency."
            )

        license_check = _build_license_check(
            maven_runner=self.maven_runner,
            dependency_tree=dependency_tree,
            dependency_tree_error=dependency_tree_error,
            denylisted_licenses=self.license_denylist,
            allowlisted_licenses=self.license_allowlist,
        )
        checks.append(license_check)
        if license_check.status == ValidationStatus.FAILED:
            status = ValidationStatus.FAILED
            summary = (
                "Live validation encountered transient dependency license inspection failures."
                if _is_transient_validation_check(license_check)
                else "Live validation detected a disallowed or unverifiable dependency license."
            )

        return RepositoryValidationResult(
            repository=repository,
            status=status,
            checks=checks,
            summary=summary,
        )

    def load_rollback_plan(
        self,
        *,
        repository: str,
        workspace_path: Path | None = None,
        modified_files: list[str] | None = None,
        proxy_jump: str | None = None,
        ssh_key: Path | None = None,
        fixture_path: Path | None = None,
    ) -> RollbackPlan:
        """Load the placeholder rollback plan for one repository."""

        if self.mode == ExecutionMode.LIVE:
            return self._load_live_rollback_plan(
                repository=repository,
                workspace_path=workspace_path,
                modified_files=modified_files or [],
                proxy_jump=proxy_jump,
                ssh_key=ssh_key,
            )
        require_fixture_mode(self.mode, capability="Rollback live execution")
        resolved_fixture_path = fixture_path or self.rollback_fixture_path
        if resolved_fixture_path is None:
            raise ValidationConfigurationError(
                "Rollback fixture path is not configured. "
                "Set EA_ROLLBACK_FIXTURE_PATH for local Day 9 rollback handling."
            )

        plan = RollbackPlan.model_validate(json.loads(resolved_fixture_path.read_text()))
        return plan.model_copy(update={"repository": repository})

    def _load_live_rollback_plan(
        self,
        *,
        repository: str,
        workspace_path: Path | None,
        modified_files: list[str],
        proxy_jump: str | None,
        ssh_key: Path | None,
    ) -> RollbackPlan:
        if self.git_runner is None:
            raise ValidationConfigurationError("Live rollback requires a configured Git runner.")
        if workspace_path is None:
            raise ValidationConfigurationError("Live rollback requires a workspace path.")

        files_to_restore = _relative_restore_paths(workspace_path, modified_files)
        if files_to_restore:
            tracked_paths, untracked_paths = self.git_runner.partition_tracked_paths(
                workspace_path,
                paths=files_to_restore,
                proxy_jump=proxy_jump,
                ssh_key=ssh_key,
            )
            if tracked_paths:
                self.git_runner.restore_paths(
                    workspace_path,
                    paths=tracked_paths,
                    proxy_jump=proxy_jump,
                    ssh_key=ssh_key,
                )
            if untracked_paths:
                self.git_runner.remove_untracked_paths(workspace_path, paths=untracked_paths)
            status = RollbackStatus.APPLIED
            reason = (
                "Restored tracked files from HEAD and removed untracked remediation files after validation failure."
            )
        else:
            status = RollbackStatus.SKIPPED
            reason = "No tracked file changes were available for rollback."
        return RollbackPlan(
            repository=repository,
            status=status,
            reason=reason,
            files_to_restore=files_to_restore,
        )


def _collect_test_reports(workspace_path: Path) -> SurefireReportSummary | None:
    summaries = []
    for directory_name in ("target/surefire-reports", "target/failsafe-reports"):
        reports_dir = workspace_path / directory_name
        if not reports_dir.exists():
            continue
        summary = parse_surefire_reports(reports_dir)
        if summary.suites:
            summaries.append(summary)
    if not summaries:
        return None

    total_tests = sum(summary.total_tests for summary in summaries)
    total_failures = sum(summary.total_failures for summary in summaries)
    total_errors = sum(summary.total_errors for summary in summaries)
    total_skipped = sum(summary.total_skipped for summary in summaries)

    return SurefireReportSummary(
        suites=tuple(suite for summary in summaries for suite in summary.suites),
        total_tests=total_tests,
        total_failures=total_failures,
        total_errors=total_errors,
        total_skipped=total_skipped,
    )


def _load_dependency_tree_scan(
    *,
    maven_runner: MavenRunner,
    workspace_path: Path,
    execution_plan: MavenExecutionPlan | None,
) -> tuple[list[DependencyTreeEntry], str | None]:
    try:
        return (
            maven_runner.dependency_tree(
                workspace_path,
                settings_xml=Path(execution_plan.settings_xml) if execution_plan and execution_plan.settings_xml else None,
                jdk_home=Path(execution_plan.java_home) if execution_plan and execution_plan.java_home else None,
            ),
            None,
        )
    except MavenCommandError as exc:
        return [], (exc.result.stderr or exc.result.stdout or "Failed to inspect the Maven dependency tree.").strip()


def _build_security_check(
    *,
    dependency_tree: list[DependencyTreeEntry],
    dependency_tree_error: str | None,
    vulnerability_details: VulnerabilityDetails | None,
    maven_verification: MavenVerification | None,
) -> ValidationCheck:
    if vulnerability_details is None or maven_verification is None:
        return ValidationCheck(
            name="security-scan",
            status=ValidationStatus.PENDING,
            details="Live security rescan skipped; verified dependency context was unavailable.",
        )

    if dependency_tree_error is not None:
        return ValidationCheck(
            name="security-scan",
            status=ValidationStatus.FAILED,
            details=f"Live security rescan could not inspect the Maven dependency tree: {dependency_tree_error}",
        )

    group_id, artifact_id = vulnerability_details.package_name.split(":", maxsplit=1)
    matching_versions = sorted(
        {
            entry.coordinate.version
            for entry in dependency_tree
            if entry.coordinate.group_id == group_id and entry.coordinate.artifact_id == artifact_id
        }
    )
    if not matching_versions:
        return ValidationCheck(
            name="security-scan",
            status=ValidationStatus.PASSED,
            details=f"{vulnerability_details.package_name} no longer appears in the Maven dependency tree.",
        )
    if matching_versions == [maven_verification.target_version]:
        return ValidationCheck(
            name="security-scan",
            status=ValidationStatus.PASSED,
            details=(
                f"{vulnerability_details.package_name} resolves only "
                f"{maven_verification.target_version} after remediation."
            ),
        )
    return ValidationCheck(
        name="security-scan",
        status=ValidationStatus.FAILED,
        details=(
            f"{vulnerability_details.package_name} still resolves versions "
            f"{', '.join(matching_versions)}; expected only {maven_verification.target_version}."
        ),
    )


def _build_license_check(
    *,
    maven_runner: MavenRunner,
    dependency_tree: list[DependencyTreeEntry],
    dependency_tree_error: str | None,
    denylisted_licenses: tuple[str, ...],
    allowlisted_licenses: tuple[str, ...],
) -> ValidationCheck:
    if dependency_tree_error is not None:
        return ValidationCheck(
            name="license-scan",
            status=ValidationStatus.FAILED if denylisted_licenses or allowlisted_licenses else ValidationStatus.PENDING,
            details=(
                "Live license scan could not inspect the Maven dependency tree: "
                f"{dependency_tree_error}"
            ),
        )

    coordinates = _iter_license_scan_coordinates(dependency_tree)
    if not coordinates:
        return ValidationCheck(
            name="license-scan",
            status=ValidationStatus.PASSED,
            details="No non-test dependencies were present for license scanning.",
        )

    denylist = tuple(entry.lower() for entry in denylisted_licenses)
    allowlist = tuple(entry.lower() for entry in allowlisted_licenses)
    unresolved: list[str] = []
    fetch_failures: list[str] = []
    disallowed: list[str] = []
    outside_allowlist: list[str] = []
    discovered: list[str] = []
    for coordinate in coordinates:
        try:
            licenses = maven_runner.fetch_pom_licenses(coordinate)
        except httpx.HTTPError as exc:
            fetch_failures.append(f"{_format_coordinate(coordinate)} ({exc})")
            continue
        except ValueError as exc:
            unresolved.append(f"{_format_coordinate(coordinate)} ({exc})")
            continue
        if not licenses:
            unresolved.append(f"{_format_coordinate(coordinate)} (no license metadata)")
            continue
        for license_name in licenses:
            if license_name not in discovered:
                discovered.append(license_name)
        if any(_license_matches_denylist(license_name, denylist) for license_name in licenses):
            disallowed.append(f"{_format_coordinate(coordinate)} ({', '.join(licenses)})")
            continue
        if allowlist and not any(_license_matches_allowlist(license_name, allowlist) for license_name in licenses):
            outside_allowlist.append(f"{_format_coordinate(coordinate)} ({', '.join(licenses)})")

    if disallowed:
        return ValidationCheck(
            name="license-scan",
            status=ValidationStatus.FAILED,
            details=(
                "Disallowed dependency licenses detected for "
                f"{len(disallowed)} dependencies against denylist [{', '.join(denylisted_licenses)}]: "
                f"{'; '.join(disallowed[:3])}."
            ),
        )
    if outside_allowlist:
        return ValidationCheck(
            name="license-scan",
            status=ValidationStatus.FAILED,
            details=(
                "Dependency licenses outside allowlist detected for "
                f"{len(outside_allowlist)} dependencies against allowlist [{', '.join(allowlisted_licenses)}]: "
                f"{'; '.join(outside_allowlist[:3])}."
            ),
        )
    if fetch_failures:
        return ValidationCheck(
            name="license-scan",
            status=ValidationStatus.FAILED if denylisted_licenses or allowlisted_licenses else ValidationStatus.PENDING,
            details=(
                "Live license scan encountered transient metadata fetch failures for "
                f"{len(fetch_failures)} dependencies"
                + (
                    " while enforcing "
                    + " and ".join(
                        filter(
                            None,
                            [
                                f"denylist [{', '.join(denylisted_licenses)}]" if denylisted_licenses else "",
                                f"allowlist [{', '.join(allowlisted_licenses)}]" if allowlisted_licenses else "",
                            ],
                        )
                    )
                    if denylisted_licenses or allowlisted_licenses
                    else ""
                )
                + f": {'; '.join(fetch_failures[:3])}."
            ),
        )
    if unresolved:
        return ValidationCheck(
            name="license-scan",
            status=ValidationStatus.FAILED if denylisted_licenses or allowlisted_licenses else ValidationStatus.PENDING,
            details=(
                "Live license scan could not resolve license metadata for "
                f"{len(unresolved)} dependencies"
                + (
                    " while enforcing "
                    + " and ".join(
                        filter(
                            None,
                            [
                                f"denylist [{', '.join(denylisted_licenses)}]" if denylisted_licenses else "",
                                f"allowlist [{', '.join(allowlisted_licenses)}]" if allowlisted_licenses else "",
                            ],
                        )
                    )
                    if denylisted_licenses or allowlisted_licenses
                    else ""
                )
                + f": {'; '.join(unresolved[:3])}."
            ),
        )

    return ValidationCheck(
        name="license-scan",
        status=ValidationStatus.PASSED,
        details=(
            f"Scanned {len(coordinates)} non-test dependencies; "
            + (
                f"no denylisted licenses found against [{', '.join(denylisted_licenses)}]. "
                if denylisted_licenses
                else ""
            )
            + (
                f"all dependency licenses matched allowlist [{', '.join(allowlisted_licenses)}]. "
                if allowlisted_licenses
                else ""
            )
            + (
                f"Observed licenses: {', '.join(discovered[:5])}."
                if discovered
                else "No dependency licenses were reported."
            )
        ),
    )


def _iter_license_scan_coordinates(dependency_tree: list[DependencyTreeEntry]) -> list[DependencyCoordinate]:
    seen: set[tuple[str, str, str]] = set()
    coordinates: list[DependencyCoordinate] = []
    for entry in dependency_tree:
        if entry.scope == "test":
            continue
        coordinate_key = (
            entry.coordinate.group_id,
            entry.coordinate.artifact_id,
            entry.coordinate.version,
        )
        if coordinate_key in seen:
            continue
        seen.add(coordinate_key)
        coordinates.append(
            DependencyCoordinate(
                group_id=entry.coordinate.group_id,
                artifact_id=entry.coordinate.artifact_id,
                version=entry.coordinate.version,
            )
        )
    return coordinates


def _license_matches_denylist(license_name: str, denylist: tuple[str, ...]) -> bool:
    return _license_matches_policy(license_name, denylist)


def _license_matches_allowlist(license_name: str, allowlist: tuple[str, ...]) -> bool:
    return _license_matches_policy(license_name, allowlist)


def _license_matches_policy(license_name: str, patterns: tuple[str, ...]) -> bool:
    normalized_name = license_name.lower()
    return any(alias in normalized_name for pattern in patterns for alias in _expand_license_pattern(pattern))


def _expand_license_pattern(pattern: str) -> tuple[str, ...]:
    normalized_pattern = pattern.lower()
    aliases = [normalized_pattern]
    if normalized_pattern == "gpl":
        aliases.extend(["gnu general public license", "general public license"])
    elif normalized_pattern == "lgpl":
        aliases.extend(["gnu lesser general public license", "lesser general public license"])
    elif normalized_pattern == "agpl":
        aliases.extend(["gnu affero general public license", "affero general public license"])
    return tuple(aliases)


def _format_coordinate(coordinate: DependencyCoordinate) -> str:
    return f"{coordinate.group_id}:{coordinate.artifact_id}:{coordinate.version}"


def _is_transient_validation_check(check: ValidationCheck) -> bool:
    if check.status != ValidationStatus.FAILED:
        return False
    details = (check.details or "").lower()
    return (
        "could not inspect the maven dependency tree" in details
        or "transient metadata fetch failures" in details
    )


def _relative_restore_paths(workspace_path: Path, modified_files: list[str]) -> list[str]:
    relative_paths: list[str] = []
    for file_path in modified_files:
        candidate = Path(file_path)
        if candidate.is_absolute():
            try:
                candidate = candidate.relative_to(workspace_path)
            except ValueError:
                continue
        relative_paths.append(candidate.as_posix())
    return relative_paths
