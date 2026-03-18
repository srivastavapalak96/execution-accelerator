"""Day 9 validation and rollback nodes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from execution_accelerator.adapters import ValidationAdapter
from execution_accelerator.schemas import AuditEvent, ValidationStatus, WorkflowStatus
from execution_accelerator.state import RemediationState, WorkflowError


def build_validate_remediation_node(
    validation_adapter: ValidationAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that records placeholder validation results for one repository."""

    def validate_remediation(state: RemediationState) -> dict[str, object]:
        assert state.current_working_repo is not None

        workspace = state.repo_map.get(state.current_working_repo)
        validation_result = validation_adapter.load_validation_result(
            repository=state.current_working_repo,
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
                message=f"Completed validation placeholder checks for {state.current_working_repo}.",
                details={
                    "repository": state.current_working_repo,
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
            "audit_events": audit_events,
        }

    return validate_remediation


def build_handle_validation_failure_node(
    validation_adapter: ValidationAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that records rollback metadata after validation failure."""

    def handle_validation_failure(state: RemediationState) -> dict[str, object]:
        assert state.current_working_repo is not None
        assert state.validation_results

        validation_result = state.validation_results[-1]
        workspace = state.repo_map.get(state.current_working_repo)
        rollback_plan = validation_adapter.load_rollback_plan(
            repository=state.current_working_repo,
            workspace_path=Path(workspace.local_path) if workspace is not None else None,
            modified_files=state.modified_files,
        )
        errors = list(state.errors)
        errors.append(
            WorkflowError(
                code="validation_failed",
                message=validation_result.summary or "Validation failed after remediation execution.",
                recoverable=True,
                repository=state.current_working_repo,
            )
        )

        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="validation.rollback",
                message=f"Recorded rollback plan for {state.current_working_repo}.",
                details={
                    "repository": state.current_working_repo,
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
