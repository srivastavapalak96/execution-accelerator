"""Day 3 Jira intake and repository context nodes."""

from __future__ import annotations

from collections.abc import Callable

from execution_accelerator.adapters import JiraAdapter, RepositoryInventoryAdapter
from execution_accelerator.schemas import AuditEvent, WorkflowStatus
from execution_accelerator.state import RemediationState


def build_ingest_and_parse_jira_node(
    jira_adapter: JiraAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that loads Jira ticket details into workflow state."""

    def ingest_and_parse_jira(state: RemediationState) -> dict[str, object]:
        vulnerability_details = jira_adapter.load_vulnerability_details(state.initial_ticket_id)
        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="jira.ingest",
                message=f"Loaded Jira vulnerability context for {state.initial_ticket_id}.",
                details={
                    "ticket_id": state.initial_ticket_id,
                    "affected_repo_count": len(vulnerability_details.affected_repositories),
                    "package_name": vulnerability_details.package_name,
                },
            )
        )

        return {
            "workflow_status": WorkflowStatus.IN_PROGRESS,
            "vulnerability_details": vulnerability_details,
            "audit_events": audit_events,
        }

    return ingest_and_parse_jira


def build_load_repository_context_node(
    repository_inventory_adapter: RepositoryInventoryAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that resolves affected repositories and materializes workspaces."""

    def load_repository_context(state: RemediationState) -> dict[str, object]:
        assert state.vulnerability_details is not None

        resolved_repositories = repository_inventory_adapter.resolve_repositories(state.vulnerability_details)
        repo_map = dict(state.repo_map)

        for repository in resolved_repositories:
            workspace = repository_inventory_adapter.prepare_workspace(
                ticket_id=state.initial_ticket_id,
                repository=repository,
            )
            repo_map[workspace.name] = workspace.model_copy(
                update={
                    "clone_url": repository.clone_url,
                    "manifest_path": repository.manifest_path,
                    "owner": repository.owner,
                    "tags": repository.tags,
                }
            )

        pending_repos = [repository.name for repository in resolved_repositories]
        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="repository.context_load",
                message=f"Resolved repository intake context for {state.initial_ticket_id}.",
                details={
                    "ticket_id": state.initial_ticket_id,
                    "resolved_repos": pending_repos,
                },
            )
        )

        return {
            "repo_map": repo_map,
            "pending_repos": pending_repos,
            "audit_events": audit_events,
        }

    return load_repository_context
