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
    """Create an initial remediation plan before downstream verification refines it."""

    target_repositories = list(state.pending_repos or state.repo_map.keys())
    remediation_plan = state.remediation_plan or _build_initial_remediation_plan(
        state=state,
        target_repositories=target_repositories,
    )

    audit_events = list(state.audit_events)
    audit_events.append(
        AuditEvent(
            event_type="graph.plan_stub",
            message="Prepared initial remediation plan for the bootstrap graph.",
            details={
                "target_repo_count": len(remediation_plan.target_repositories),
                "package_name": (
                    state.vulnerability_details.package_name if state.vulnerability_details is not None else None
                ),
            },
        )
    )

    return {
        "workflow_status": WorkflowStatus.PLANNING_READY,
        "remediation_plan": remediation_plan,
        "requires_human_approval": remediation_plan.requires_human_approval,
        "audit_events": audit_events,
    }


def _build_initial_remediation_plan(
    *,
    state: RemediationState,
    target_repositories: list[str],
) -> RemediationPlan:
    vulnerability = state.vulnerability_details
    if vulnerability is None:
        return RemediationPlan(
            strategy=RemediationStrategy.UNKNOWN,
            summary=f"Assess remediation scope for {state.initial_ticket_id}.",
            rationale=(
                "Bootstrap established repository scope; advisory verification and Maven analysis "
                "will refine the remediation route before code changes are applied."
            ),
            target_repositories=target_repositories,
            requires_human_approval=False,
        )

    target_version = vulnerability.fixed_version or "a verified safe version"
    repository_label = "repository" if len(target_repositories) == 1 else "repositories"
    return RemediationPlan(
        strategy=RemediationStrategy.UNKNOWN,
        summary=(
            f"Assess remediation for {vulnerability.package_name} from "
            f"{vulnerability.installed_version} to {target_version} across "
            f"{len(target_repositories)} {repository_label}."
        ),
        rationale=(
            f"Bootstrap captured the ticket scope for {vulnerability.summary}; advisory verification "
            "and Maven analysis will refine the remediation route before automated changes are applied."
        ),
        target_repositories=target_repositories,
        requires_human_approval=False,
    )
