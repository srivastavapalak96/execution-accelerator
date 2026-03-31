"""Day 9 validation and rollback nodes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from execution_accelerator.adapters import ValidationAdapter
from execution_accelerator.schemas import AuditEvent, RepositoryValidationResult, ValidationStatus, WorkflowStatus
from execution_accelerator.state import RemediationState, WorkflowError, require_state_field


def build_validate_remediation_node(
    validation_adapter: ValidationAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that records validation results for one repository."""

    def validate_remediation(state: RemediationState) -> dict[str, object]:
        current_working_repo = require_state_field(
            state.current_working_repo,
            source="validate_remediation",
            field_name="current_working_repo",
            message="Validation requires the current working repository to be set.",
        )

        workspace = state.repo_map.get(current_working_repo)
        validation_result = validation_adapter.load_validation_result(
            repository=current_working_repo,
            workspace_path=Path(workspace.local_path) if workspace is not None else None,
            execution_plan=state.maven_plan,
            vulnerability_details=state.vulnerability_details,
            maven_verification=state.maven_verification,
        )
        validation_results = list(state.validation_results)
        validation_results.append(validation_result)

        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="validation.run",
                message=f"Completed validation checks for {current_working_repo}.",
                details={
                    "repository": current_working_repo,
                    "status": validation_result.status,
                    "check_count": len(validation_result.checks),
                },
            )
        )

        workflow_status = (
            WorkflowStatus.FAILED
            if validation_result.status == ValidationStatus.FAILED
            else WorkflowStatus.IN_PROGRESS
        )
        return {
            "validation_results": validation_results,
            "workflow_status": workflow_status,
            "rollback_plan": None if validation_result.status != ValidationStatus.FAILED else state.rollback_plan,
            "retry_decision": None if validation_result.status != ValidationStatus.FAILED else state.retry_decision,
            "audit_events": audit_events,
        }

    return validate_remediation


def build_handle_validation_failure_node(
    validation_adapter: ValidationAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that records rollback metadata after validation failure."""

    def handle_validation_failure(state: RemediationState) -> dict[str, object]:
        current_working_repo = require_state_field(
            state.current_working_repo,
            source="handle_validation_failure",
            field_name="current_working_repo",
            message="Validation failure handling requires the current working repository to be set.",
        )
        require_state_field(
            state.validation_results[-1] if state.validation_results else None,
            source="handle_validation_failure",
            field_name="validation_results",
            message="Validation failure handling requires at least one validation result.",
            repository=current_working_repo,
        )

        validation_result = state.validation_results[-1]
        workspace = state.repo_map.get(current_working_repo)
        rollback_plan = validation_adapter.load_rollback_plan(
            repository=current_working_repo,
            workspace_path=Path(workspace.local_path) if workspace is not None else None,
            modified_files=state.modified_files,
        )
        errors = list(state.errors)
        errors.append(
            WorkflowError(
                code=_build_validation_error_code(validation_result),
                message=validation_result.summary or "Validation failed after remediation execution.",
                recoverable=_is_recoverable_validation_failure(validation_result),
                repository=current_working_repo,
            )
        )

        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="validation.rollback",
                message=f"Recorded rollback plan for {current_working_repo}.",
                details={
                    "repository": current_working_repo,
                    "rollback_status": rollback_plan.status,
                    "files_to_restore": rollback_plan.files_to_restore,
                },
            )
        )

        return {
            "rollback_plan": rollback_plan,
            "errors": errors,
            "workflow_status": WorkflowStatus.FAILED,
            "audit_events": audit_events,
        }

    return handle_validation_failure


def _is_recoverable_validation_failure(validation_result: RepositoryValidationResult) -> bool:
    has_retryable_failure = False
    for check in validation_result.checks:
        if check.status != ValidationStatus.FAILED:
            continue
        normalized_name = check.name.lower()
        if "test" in normalized_name or _is_transient_validation_check(check.name, check.details):
            has_retryable_failure = True
            continue
        return False
    return has_retryable_failure


def _build_validation_error_code(validation_result: RepositoryValidationResult) -> str:
    for check in validation_result.checks:
        if check.status != ValidationStatus.FAILED:
            continue
        normalized_name = check.name.lower()
        if _is_transient_validation_check(check.name, check.details):
            return "validation_transient_failed"
        if "compile" in normalized_name:
            return "validation_compile_failed"
        if "test" in normalized_name:
            return "validation_test_failed"
        if "security" in normalized_name:
            return "validation_security_failed"
        if "license" in normalized_name:
            return "validation_license_failed"
    return "validation_failed"


def _is_transient_validation_check(check_name: str, check_details: str | None) -> bool:
    normalized_name = check_name.lower()
    normalized_details = (check_details or "").lower()
    if "security" not in normalized_name and "license" not in normalized_name:
        return False
    return (
        "could not inspect the maven dependency tree" in normalized_details
        or "transient metadata fetch failures" in normalized_details
    )
