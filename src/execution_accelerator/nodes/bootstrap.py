"""Bootstrap nodes for the minimal Day 2 remediation graph."""

from __future__ import annotations

from execution_accelerator.schemas import AuditEvent, RemediationPlan, RemediationStrategy, WorkflowStatus
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


def prepare_planning_stub(state: RemediationState) -> dict[str, object]:
    """Create a placeholder plan until real intake and planner adapters land."""

    target_repositories = list(state.pending_repos or state.repo_map.keys())
    remediation_plan = state.remediation_plan or RemediationPlan(
        strategy=RemediationStrategy.UNKNOWN,
        summary=f"Bootstrap plan initialized for {state.initial_ticket_id}.",
        rationale=(
            "Day 2 establishes typed state, persistence, and graph bootstrap before "
            "Jira intake and remediation planning adapters are implemented."
        ),
        target_repositories=target_repositories,
        requires_human_approval=False,
    )

    audit_events = list(state.audit_events)
    audit_events.append(
        AuditEvent(
            event_type="graph.plan_stub",
            message="Created placeholder remediation plan for the bootstrap graph.",
            details={"target_repo_count": len(remediation_plan.target_repositories)},
        )
    )

    return {
        "workflow_status": WorkflowStatus.PLANNING_READY,
        "remediation_plan": remediation_plan,
        "requires_human_approval": remediation_plan.requires_human_approval,
        "audit_events": audit_events,
    }
