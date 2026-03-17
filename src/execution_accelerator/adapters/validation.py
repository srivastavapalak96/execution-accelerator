"""Fixture-backed validation and rollback helpers for the Day 9 workflow."""

from __future__ import annotations

import json
from pathlib import Path

from execution_accelerator.adapters._mode import require_fixture_mode
from execution_accelerator.config import RuntimeConfig, load_credentials
from execution_accelerator.execution import (
    GitRunner,
    MavenCommandError,
    MavenRunner,
    SurefireReportSummary,
    parse_surefire_reports,
)
from execution_accelerator.schemas import (
    ExecutionMode,
    MavenExecutionPlan,
    RepositoryValidationResult,
    RollbackPlan,
    RollbackStatus,
    ValidationCheck,
    ValidationStatus,
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
    ) -> None:
        self.validation_result_fixture_path = validation_result_fixture_path
        self.rollback_fixture_path = rollback_fixture_path
        self.mode = mode
        self.maven_runner = maven_runner
        self.git_runner = git_runner

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
                settings_xml=credentials.maven_settings,
                java_home=config.java_home,
            ),
            git_runner=GitRunner(
                log_dir=config.logs_dir / "git",
                secrets=tuple(secret for secret in (credentials.github_token,) if secret),
            ),
        )

    def load_validation_result(
        self,
        *,
        repository: str,
        workspace_path: Path | None = None,
        execution_plan: MavenExecutionPlan | None = None,
        fixture_path: Path | None = None,
    ) -> RepositoryValidationResult:
        """Load the placeholder validation result for one repository."""

        if self.mode == ExecutionMode.LIVE:
            return self._load_live_validation_result(
                repository=repository,
                workspace_path=workspace_path,
                execution_plan=execution_plan,
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
        fixture_path: Path | None = None,
    ) -> RollbackPlan:
        """Load the placeholder rollback plan for one repository."""

        if self.mode == ExecutionMode.LIVE:
            return self._load_live_rollback_plan(
                repository=repository,
                workspace_path=workspace_path,
                modified_files=modified_files or [],
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
    ) -> RollbackPlan:
        if self.git_runner is None:
            raise ValidationConfigurationError("Live rollback requires a configured Git runner.")
        if workspace_path is None:
            raise ValidationConfigurationError("Live rollback requires a workspace path.")

        files_to_restore = _relative_restore_paths(workspace_path, modified_files)
        if files_to_restore:
            self.git_runner.restore_paths(workspace_path, paths=files_to_restore)
            status = RollbackStatus.APPLIED
            reason = "Restored modified files from HEAD after validation failure."
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
