"""Failure escalation helpers."""

from __future__ import annotations

import json
from collections.abc import Callable

from execution_accelerator.config import RuntimeConfig
from execution_accelerator.schemas import ApprovalRecord, AuditEvent, EscalationBundle, FailureClassification, WorkflowStatus
from execution_accelerator.state import RemediationState


def build_escalate_node(runtime_config: RuntimeConfig) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that persists an escalation bundle for the failed run."""

    def escalate(state: RemediationState) -> dict[str, object]:
        latest_classification = state.failure_classifications[-1] if state.failure_classifications else "unknown"
        bundle = _write_escalation_bundle(state=state, runtime_config=runtime_config)
        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="failure.escalate",
                message=f"Escalated remediation failure for {state.initial_ticket_id}.",
                details={
                    "classification": latest_classification,
                    "total_attempts": state.total_attempts,
                    "bundle_path": bundle.bundle_path,
                },
            )
        )

        return {
            "workflow_status": WorkflowStatus.FAILED,
            "escalation_bundle": bundle,
            "audit_events": audit_events,
        }

    return escalate


def escalate(state: RemediationState) -> dict[str, object]:
    """Retain a no-runtime fallback for direct unit tests and legacy callers."""

    latest_classification = state.failure_classifications[-1] if state.failure_classifications else "unknown"
    audit_events = list(state.audit_events)
    audit_events.append(
        AuditEvent(
            event_type="failure.escalate",
            message=f"Escalated remediation failure for {state.initial_ticket_id}.",
            details={
                "classification": latest_classification,
                "total_attempts": state.total_attempts,
            },
        )
    )

    return {
        "workflow_status": WorkflowStatus.FAILED,
        "audit_events": audit_events,
    }


def _write_escalation_bundle(*, state: RemediationState, runtime_config: RuntimeConfig) -> EscalationBundle:
    escalation_dir = runtime_config.data_dir / "escalations"
    escalation_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = escalation_dir / f"{state.initial_ticket_id.lower()}-{len(state.audit_events) + 1:03d}.json"
    log_files = sorted(str(path) for path in runtime_config.logs_dir.rglob("*.log"))
    failure_classification = (
        state.failure_classifications[-1] if state.failure_classifications else FailureClassification.UNKNOWN
    )
    latest_approved_record = _find_latest_approved_record(state)
    latest_validation = state.validation_results[-1] if state.validation_results else None
    primary_validation_check = latest_validation.checks[0] if latest_validation and latest_validation.checks else None
    complex_plan = state.complex_remediation_plan
    complex_target_files = [target.file_path for target in complex_plan.target_files] if complex_plan is not None else []
    complex_open_questions = list(complex_plan.open_questions) if complex_plan is not None else []
    code_diff_summaries = [code_diff.change_summary for code_diff in state.code_diffs]
    payload = {
        "ticket_id": state.initial_ticket_id,
        "workflow_status": state.workflow_status,
        "failure_classification": failure_classification,
        "error_codes": [error.code for error in state.errors],
        "route_strategy": state.route_decision.strategy if state.route_decision is not None else None,
        "route_reason": state.route_decision.reason if state.route_decision is not None else None,
        "approval_stage": latest_approved_record.stage if latest_approved_record is not None else None,
        "approval_reviewer": latest_approved_record.reviewer if latest_approved_record is not None else None,
        "approval_comments": latest_approved_record.comments if latest_approved_record is not None else None,
        "errors": [error.model_dump(mode="python") for error in state.errors],
        "validation_status": latest_validation.status if latest_validation is not None else None,
        "validation_summary": latest_validation.summary if latest_validation is not None else None,
        "primary_validation_check": primary_validation_check.name if primary_validation_check is not None else None,
        "primary_validation_check_status": (
            primary_validation_check.status if primary_validation_check is not None else None
        ),
        "primary_validation_check_details": (
            primary_validation_check.details if primary_validation_check is not None else None
        ),
        "modified_files": state.modified_files,
        "code_diff_summaries": code_diff_summaries,
        "complex_migration_tactic": complex_plan.migration_tactic if complex_plan is not None else None,
        "complex_target_files": complex_target_files,
        "complex_open_questions": complex_open_questions,
        "log_files": log_files,
        "audit_event_count": len(state.audit_events),
    }
    bundle_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    return EscalationBundle(
        bundle_path=str(bundle_path),
        failure_classification=failure_classification,
        error_codes=[error.code for error in state.errors],
        route_strategy=state.route_decision.strategy if state.route_decision is not None else None,
        route_reason=state.route_decision.reason if state.route_decision is not None else None,
        approval_stage=latest_approved_record.stage if latest_approved_record is not None else None,
        approval_reviewer=latest_approved_record.reviewer if latest_approved_record is not None else None,
        approval_comments=latest_approved_record.comments if latest_approved_record is not None else None,
        validation_status=latest_validation.status if latest_validation is not None else None,
        validation_summary=latest_validation.summary if latest_validation is not None else None,
        primary_validation_check=primary_validation_check.name if primary_validation_check is not None else None,
        primary_validation_check_status=primary_validation_check.status if primary_validation_check is not None else None,
        primary_validation_check_details=(
            primary_validation_check.details if primary_validation_check is not None else None
        ),
        modified_files=list(state.modified_files),
        code_diff_summaries=code_diff_summaries,
        complex_migration_tactic=complex_plan.migration_tactic if complex_plan is not None else None,
        complex_target_files=complex_target_files,
        complex_open_questions=complex_open_questions,
        log_files=log_files,
        audit_event_count=len(state.audit_events),
    )


def _find_latest_approved_record(state: RemediationState) -> ApprovalRecord | None:
    for record in reversed(state.approval_history):
        if record.decision == "approved":
            return record
    return None
