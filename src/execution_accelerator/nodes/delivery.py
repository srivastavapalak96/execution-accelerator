"""Day 10 delivery and Jira completion nodes."""

from __future__ import annotations

from execution_accelerator.adapters import DeliveryAdapter
from execution_accelerator.schemas import AuditEvent, WorkflowStatus
from execution_accelerator.state import RemediationState


def build_publish_remediation_node(delivery_adapter: DeliveryAdapter):
    """Create a node that records publication and Jira completion metadata."""

    def publish_remediation(state: RemediationState) -> dict[str, object]:
        assert state.current_working_repo is not None

        branch_publication = delivery_adapter.load_branch_publication(
            repository=state.current_working_repo
        )
        pull_request_summary = delivery_adapter.load_pull_request(repository=state.current_working_repo)
        jira_completion = delivery_adapter.load_jira_completion(ticket_id=state.initial_ticket_id)

        completed_repos = list(state.completed_repos)
        if state.current_working_repo not in completed_repos:
            completed_repos.append(state.current_working_repo)
        pending_repos = [repo for repo in state.pending_repos if repo != state.current_working_repo]

        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="delivery.publish",
                message=f"Recorded branch, PR, and Jira completion for {state.current_working_repo}.",
                details={
                    "repository": state.current_working_repo,
                    "branch_name": branch_publication.branch_name,
                    "pull_request_number": pull_request_summary.number,
                    "jira_status": jira_completion.status,
                },
            )
        )

        return {
            "branch_publication": branch_publication,
            "pull_request_summary": pull_request_summary,
            "jira_completion": jira_completion,
            "completed_repos": completed_repos,
            "pending_repos": pending_repos,
            "workflow_status": WorkflowStatus.COMPLETED,
            "audit_events": audit_events,
        }

    return publish_remediation
