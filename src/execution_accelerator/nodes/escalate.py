"""Phase 0 escalation stub."""

from __future__ import annotations

from execution_accelerator.schemas import AuditEvent, WorkflowStatus
from execution_accelerator.state import RemediationState


def escalate(state: RemediationState) -> dict[str, object]:
    """Record an escalation event for the latest classified failure."""

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
