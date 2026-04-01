"""Day 3 Jira intake and repository context nodes."""

from __future__ import annotations

from collections.abc import Callable

from execution_accelerator.adapters import JiraAdapter, RepositoryInventoryAdapter
from execution_accelerator.config import RuntimeConfig, load_credentials, probe_credentials
from execution_accelerator.schemas import AuditEvent, RepositoryInventoryRecord, WorkflowStatus
from execution_accelerator.state import RemediationState, SkippedRepository, require_state_field


def build_probe_credentials_node(
    runtime_config: RuntimeConfig,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that probes live credentials and skips in fixture mode."""

    def probe_live_credentials(state: RemediationState) -> dict[str, object]:
        report = probe_credentials(
            load_credentials(repo_root=runtime_config.repo_root),
            execution_mode=runtime_config.execution_mode,
        )
        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="credentials.probe",
                message=(
                    "Skipped live credential probe for fixture mode."
                    if report.skipped
                    else "Validated live Jira and GitHub credentials."
                ),
                details={
                    "execution_mode": runtime_config.execution_mode,
                    "skipped": report.skipped,
                    "jira_ok": report.jira_ok,
                    "github_ok": report.github_ok,
                },
            )
        )
        return {"audit_events": audit_events}

    return probe_live_credentials


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
    """Create a node that resolves affected repositories into remediation targets."""

    def load_repository_context(state: RemediationState) -> dict[str, object]:
        vulnerability_details = require_state_field(
            state.vulnerability_details,
            source="load_repository_context",
            field_name="vulnerability_details",
            message="Repository context loading requires vulnerability details from Jira intake.",
        )

        resolved_repositories = repository_inventory_adapter.resolve_repositories(vulnerability_details)
        targets = repository_inventory_adapter.build_targets(
            ticket_id=state.initial_ticket_id,
            vulnerability_details=vulnerability_details,
        )
        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="repository.context_load",
                message=f"Resolved repository intake context for {state.initial_ticket_id}.",
                details={
                    "ticket_id": state.initial_ticket_id,
                    "resolved_repos": [repository.name for repository in resolved_repositories],
                    "target_count": len(targets),
                },
            )
        )

        return {
            "targets": targets,
            "current_target_index": 0,
            "audit_events": audit_events,
        }

    return load_repository_context


def build_check_repository_idempotency_node(
    repository_inventory_adapter: RepositoryInventoryAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that checks PR idempotency before workspace preparation."""

    def check_repository_idempotency(state: RemediationState) -> dict[str, object]:
        repo_map = dict(state.repo_map)
        skipped_repos = list(state.skipped_repos)
        pending_repos: list[str] = []

        for target in state.targets:
            existing_pull_request = repository_inventory_adapter.find_existing_pull_request(target)
            if existing_pull_request is not None:
                skipped_repos.append(
                    SkippedRepository(
                        name=target.repository_name,
                        reason=f"existing_pr:{existing_pull_request}",
                    )
                )
                continue
            repository = RepositoryInventoryRecord(
                name=target.repository_name,
                clone_url=target.clone_url,
                default_branch=target.default_branch,
                build_system=target.build_system,
                manifest_path=target.manifest_path,
                maven_settings=target.maven_settings,
                proxy_jump=target.proxy_jump,
                owner=target.owner,
                tags=target.tags,
            )
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
            pending_repos.append(repository.name)

        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="repository.idempotency_check",
                message=f"Checked repository idempotency for {state.initial_ticket_id}.",
                details={
                    "ticket_id": state.initial_ticket_id,
                    "pending_repo_count": len(pending_repos),
                    "skipped_repo_count": len(skipped_repos),
                },
            )
        )

        return {
            "repo_map": repo_map,
            "pending_repos": pending_repos,
            "skipped_repos": skipped_repos,
            "workflow_status": (
                WorkflowStatus.COMPLETED if not pending_repos else state.workflow_status
            ),
            "audit_events": audit_events,
        }

    return check_repository_idempotency
