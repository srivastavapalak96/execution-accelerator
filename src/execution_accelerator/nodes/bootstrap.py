"""Bootstrap nodes for the persisted remediation graph."""

from __future__ import annotations

from execution_accelerator.schemas import AuditEvent, WorkflowStatus
from execution_accelerator.state import RemediationState


def bootstrap_state(state: RemediationState) -> dict[str, object]:
    """Initialize audit state and derive the first pending repositories."""

    pending_repos = list(state.pending_repos)
    if not pending_repos and state.vulnerability_details is not None:
        pending_repos = [repo.name for repo in state.vulnerability_details.affected_repositories]

    audit_events = list(state.audit_events)
    audit_events.append(
        AuditEvent(
            event_type="graph.bootstrap",
            message=f"Bootstrapped remediation workflow for {state.initial_ticket_id}.",
            details={"ticket_id": state.initial_ticket_id},
        )
    )

    return {
        "workflow_status": WorkflowStatus.BOOTSTRAPPED,
        "pending_repos": pending_repos,
        "audit_events": audit_events,
    }
