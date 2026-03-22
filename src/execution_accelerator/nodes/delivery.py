"""Day 10 delivery and Jira completion nodes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from execution_accelerator.config import RuntimeConfig
from execution_accelerator.adapters import DeliveryAdapter
from execution_accelerator.schemas import ApprovalStage
from execution_accelerator.schemas import AuditEvent, WorkflowStatus
from execution_accelerator.state import RemediationState


def build_publish_remediation_node(
    delivery_adapter: DeliveryAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that records publication and Jira completion metadata."""

    def publish_remediation(state: RemediationState) -> dict[str, object]:
        assert state.current_working_repo is not None
        workspace = state.repo_map.get(state.current_working_repo)

        branch_publication = delivery_adapter.load_branch_publication(
            repository=state.current_working_repo,
            workspace_path=Path(workspace.local_path) if workspace is not None else None,
            ticket_id=state.initial_ticket_id,
            package_name=state.vulnerability_details.package_name if state.vulnerability_details is not None else None,
        )
        pull_request_summary = delivery_adapter.load_pull_request(
            repository=state.current_working_repo,
            owner=workspace.owner if workspace is not None else None,
            base_branch=workspace.default_branch if workspace is not None else None,
            head_branch=branch_publication.branch_name,
            ticket_id=state.initial_ticket_id,
            package_name=state.vulnerability_details.package_name if state.vulnerability_details is not None else None,
            draft_pull_request=not _has_delivery_approval(state) if state.requires_delivery_approval else None,
            body=_build_pull_request_body(state),
        )
        jira_completion = delivery_adapter.load_jira_completion(
            ticket_id=state.initial_ticket_id,
            repository=state.current_working_repo,
            pull_request_url=pull_request_summary.url,
            comment=_build_jira_completion_comment(state, pull_request_summary.url),
        )

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
            "pending_approval_stage": None,
            "pending_approval_reason": None,
            "workflow_status": WorkflowStatus.COMPLETED,
            "audit_events": audit_events,
        }

    return publish_remediation


def _has_delivery_approval(state: RemediationState) -> bool:
    return any(record.stage == ApprovalStage.DELIVERY and record.decision == "approved" for record in state.approval_history)


def _build_pull_request_body(state: RemediationState) -> str:
    return "\n".join(_build_delivery_summary_lines(state))


def _build_jira_completion_comment(state: RemediationState, pull_request_url: str) -> str:
    lines = _build_delivery_summary_lines(state)
    lines.append(f"- Pull request: {pull_request_url}")
    return "\n".join(lines)


def _build_delivery_summary_lines(state: RemediationState) -> list[str]:
    lines = [f"Automated remediation for {state.initial_ticket_id}."]
    if state.vulnerability_details is not None:
        lines.append("")
        lines.append(f"- Package: {state.vulnerability_details.package_name}")
        lines.append(f"- Installed version: {state.vulnerability_details.installed_version}")
    if state.maven_verification is not None:
        lines.append(f"- Target version: {state.maven_verification.target_version}")
        lines.append(f"- Dependency kind: {state.maven_verification.dependency_kind}")
    if state.route_decision is not None:
        lines.append(f"- Route: {state.route_decision.strategy}")
    if state.validation_results:
        validation = state.validation_results[-1]
        lines.append(f"- Validation status: {validation.status}")
        if validation.summary:
            lines.append(f"- Validation summary: {validation.summary}")
    if state.complex_remediation_plan is not None:
        lines.append(f"- Complex migration tactic: {state.complex_remediation_plan.migration_tactic}")
        if state.complex_remediation_plan.target_files:
            lines.append(f"- Primary target file: {state.complex_remediation_plan.target_files[0].file_path}")
        if state.complex_remediation_plan.open_questions:
            lines.append(f"- Open question: {state.complex_remediation_plan.open_questions[0]}")
    return lines


def build_skip_publish_for_dry_run_node(
    runtime_config: RuntimeConfig,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that completes successfully without delivery side effects."""

    def skip_publish_for_dry_run(state: RemediationState) -> dict[str, object]:
        assert state.current_working_repo is not None

        completed_repos = list(state.completed_repos)
        if state.current_working_repo not in completed_repos:
            completed_repos.append(state.current_working_repo)
        pending_repos = [repo for repo in state.pending_repos if repo != state.current_working_repo]

        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="delivery.skipped_dry_run",
                message=f"Skipped publication side effects for {state.current_working_repo} in dry-run mode.",
                details={
                    "repository": state.current_working_repo,
                    "dry_run": runtime_config.dry_run,
                },
            )
        )

        return {
            "completed_repos": completed_repos,
            "pending_repos": pending_repos,
            "workflow_status": WorkflowStatus.COMPLETED,
            "audit_events": audit_events,
        }

    return skip_publish_for_dry_run
