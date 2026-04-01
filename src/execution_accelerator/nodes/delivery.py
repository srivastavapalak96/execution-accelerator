"""Day 10 delivery and Jira completion nodes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx

from execution_accelerator.config import RuntimeConfig
from execution_accelerator.adapters import DeliveryAdapter, DeliveryAdapterError
from execution_accelerator.schemas import ApprovalRecord, ApprovalStage
from execution_accelerator.schemas import AuditEvent, WorkflowStatus
from execution_accelerator.state import RemediationState, WorkflowError, require_state_field
from execution_accelerator.validation_summary import select_primary_validation_check


def build_publish_remediation_node(
    delivery_adapter: DeliveryAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that records publication and Jira completion metadata."""

    def publish_remediation(state: RemediationState) -> dict[str, object]:
        current_working_repo = require_state_field(
            state.current_working_repo,
            source="publish_remediation",
            field_name="current_working_repo",
            message="Delivery publication requires the current working repository to be set.",
        )
        workspace = state.repo_map.get(current_working_repo)
        branch_publication = state.branch_publication
        pull_request_summary = state.pull_request_summary
        jira_completion = state.jira_completion
        try:
            if branch_publication is None:
                branch_publication = delivery_adapter.load_branch_publication(
                    repository=current_working_repo,
                    workspace_path=Path(workspace.local_path) if workspace is not None else None,
                    ticket_id=state.initial_ticket_id,
                    package_name=state.vulnerability_details.package_name if state.vulnerability_details is not None else None,
                    proxy_jump=workspace.proxy_jump if workspace is not None else None,
                    ssh_key=Path(workspace.ssh_key) if workspace is not None and workspace.ssh_key is not None else None,
                )
            if pull_request_summary is None:
                pull_request_summary = delivery_adapter.load_pull_request(
                    repository=current_working_repo,
                    owner=workspace.owner if workspace is not None else None,
                    base_branch=workspace.default_branch if workspace is not None else None,
                    head_branch=branch_publication.branch_name,
                    ticket_id=state.initial_ticket_id,
                    package_name=state.vulnerability_details.package_name if state.vulnerability_details is not None else None,
                    draft_pull_request=not _has_delivery_approval(state) if state.requires_delivery_approval else None,
                    body=_build_pull_request_body(state),
                )
            if jira_completion is None:
                jira_completion = delivery_adapter.load_jira_completion(
                    ticket_id=state.initial_ticket_id,
                    repository=current_working_repo,
                    pull_request_url=pull_request_summary.url,
                    comment=_build_jira_completion_comment(state, pull_request_summary.url),
                )
        except (DeliveryAdapterError, httpx.HTTPError) as error:
            return _build_delivery_failure_update(
                state=state,
                error=error,
                branch_publication=branch_publication,
                pull_request_summary=pull_request_summary,
                jira_completion=jira_completion,
            )

        completed_repos = list(state.completed_repos)
        if current_working_repo not in completed_repos:
            completed_repos.append(current_working_repo)
        pending_repos = [repo for repo in state.pending_repos if repo != current_working_repo]
        continuation_update = _build_repo_continuation_update(
            state,
            pending_repos=pending_repos,
            completed_repos=completed_repos,
        )

        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="delivery.publish",
                message=f"Recorded branch, PR, and Jira completion for {current_working_repo}.",
                details={
                    "repository": current_working_repo,
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
            **continuation_update,
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
    lines.extend(_build_repo_progress_lines(state))
    if state.maven_verification is not None:
        lines.append(f"- Target version: {state.maven_verification.target_version}")
        lines.append(f"- Dependency kind: {state.maven_verification.dependency_kind}")
    if state.route_decision is not None:
        lines.append(f"- Route: {state.route_decision.strategy}")
        lines.append(f"- Route rationale: {state.route_decision.reason}")
    if state.remediation_plan is not None:
        lines.append(f"- Plan summary: {state.remediation_plan.summary}")
        lines.append(f"- Plan rationale: {state.remediation_plan.rationale}")
    if state.validation_results:
        validation = state.validation_results[-1]
        lines.append(f"- Validation status: {validation.status}")
        if validation.summary:
            lines.append(f"- Validation summary: {validation.summary}")
        primary_check = select_primary_validation_check(validation)
        if primary_check is not None:
            lines.append(f"- Primary validation check: {primary_check.name} ({primary_check.status})")
            if primary_check.details:
                lines.append(f"- Primary validation detail: {primary_check.details}")
    if state.code_diffs:
        lines.append(f"- Changed file count: {len(state.code_diffs)}")
        lines.append(f"- Primary change: {state.code_diffs[0].change_summary}")
        lines.append(f"- Total additions: {sum(diff.additions for diff in state.code_diffs)}")
        lines.append(f"- Total deletions: {sum(diff.deletions for diff in state.code_diffs)}")
    latest_approval = _find_latest_approved_record(state)
    if latest_approval is not None:
        lines.append(f"- Approval stage: {latest_approval.stage}")
        if latest_approval.reviewer is not None:
            lines.append(f"- Approved by: {latest_approval.reviewer}")
        if latest_approval.comments is not None:
            lines.append(f"- Approval comments: {latest_approval.comments}")
    if state.complex_remediation_plan is not None:
        lines.append(f"- Complex migration tactic: {state.complex_remediation_plan.migration_tactic}")
        if state.complex_remediation_plan.target_files:
            lines.append(f"- Primary target file: {state.complex_remediation_plan.target_files[0].file_path}")
        if state.complex_remediation_plan.open_questions:
            lines.append(f"- Open question: {state.complex_remediation_plan.open_questions[0]}")
    return lines


def _build_repo_progress_lines(state: RemediationState) -> list[str]:
    current_repo = state.current_working_repo
    if current_repo is None:
        return []

    completed_repos = list(state.completed_repos)
    if current_repo not in completed_repos:
        completed_repos.append(current_repo)
    remaining_repos = [repo for repo in state.pending_repos if repo != current_repo]
    skipped_repos = [f"{repo.name} ({repo.reason})" for repo in state.skipped_repos]
    total_repos = len(completed_repos) + len(remaining_repos) + len(skipped_repos)
    if total_repos <= 1:
        return []

    lines = [
        f"- Current repository: {current_repo}",
        f"- Repository progress: {len(completed_repos) + len(skipped_repos)}/{total_repos} addressed",
        f"- Completed repositories: {', '.join(completed_repos)}",
    ]
    if remaining_repos:
        lines.append(f"- Remaining repositories: {', '.join(remaining_repos)}")
    if skipped_repos:
        lines.append(f"- Skipped repositories: {'; '.join(skipped_repos)}")
    return lines


def _build_delivery_failure_update(
    *,
    state: RemediationState,
    error: DeliveryAdapterError | httpx.HTTPError,
    branch_publication: object,
    pull_request_summary: object,
    jira_completion: object,
) -> dict[str, object]:
    error_code = _build_delivery_error_code(branch_publication, pull_request_summary, jira_completion)
    workflow_error = WorkflowError(
        code=error_code,
        message=_build_delivery_error_message(error_code, error),
        recoverable=_is_recoverable_delivery_error(error),
        repository=state.current_working_repo,
    )
    errors = list(state.errors)
    errors.append(workflow_error)
    audit_events = list(state.audit_events)
    audit_events.append(
        AuditEvent(
            event_type="delivery.failure",
            message=f"Delivery failed for {state.current_working_repo}.",
            details={
                "repository": state.current_working_repo,
                "error_code": workflow_error.code,
                "recoverable": workflow_error.recoverable,
            },
        )
    )
    return {
        "branch_publication": branch_publication,
        "pull_request_summary": pull_request_summary,
        "jira_completion": jira_completion,
        "errors": errors,
        "workflow_status": WorkflowStatus.FAILED,
        "audit_events": audit_events,
    }


def _build_delivery_error_code(
    branch_publication: object,
    pull_request_summary: object,
    jira_completion: object,
) -> str:
    if branch_publication is None:
        return "delivery_branch_publication_failed"
    if pull_request_summary is None:
        return "delivery_pull_request_failed"
    if jira_completion is None:
        return "delivery_jira_failed"
    return "delivery_failed"


def _build_delivery_error_message(error_code: str, error: DeliveryAdapterError | httpx.HTTPError) -> str:
    stage = {
        "delivery_branch_publication_failed": "branch publication",
        "delivery_pull_request_failed": "pull request publication",
        "delivery_jira_failed": "Jira completion",
    }.get(error_code, "delivery")
    return f"{stage.capitalize()} failed: {error}"


def _is_recoverable_delivery_error(error: DeliveryAdapterError | httpx.HTTPError) -> bool:
    if isinstance(error, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in {408, 409, 425, 429, 500, 502, 503, 504}
    return False


def _find_latest_approved_record(state: RemediationState) -> ApprovalRecord | None:
    for record in reversed(state.approval_history):
        if record.decision == "approved":
            return record
    return None


def build_skip_publish_for_dry_run_node(
    runtime_config: RuntimeConfig,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that completes successfully without delivery side effects."""

    def skip_publish_for_dry_run(state: RemediationState) -> dict[str, object]:
        current_working_repo = require_state_field(
            state.current_working_repo,
            source="skip_publish_for_dry_run",
            field_name="current_working_repo",
            message="Dry-run publication skipping requires the current working repository to be set.",
        )

        completed_repos = list(state.completed_repos)
        if current_working_repo not in completed_repos:
            completed_repos.append(current_working_repo)
        pending_repos = [repo for repo in state.pending_repos if repo != current_working_repo]
        continuation_update = _build_repo_continuation_update(
            state,
            pending_repos=pending_repos,
            completed_repos=completed_repos,
        )

        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="delivery.skipped_dry_run",
                message=f"Skipped publication side effects for {current_working_repo} in dry-run mode.",
                details={
                    "repository": current_working_repo,
                    "dry_run": runtime_config.dry_run,
                },
            )
        )

        return {
            **continuation_update,
            "audit_events": audit_events,
        }

    return skip_publish_for_dry_run


def _build_repo_continuation_update(
    state: RemediationState,
    *,
    pending_repos: list[str],
    completed_repos: list[str],
) -> dict[str, object]:
    if not pending_repos:
        return {
            "completed_repos": completed_repos,
            "pending_repos": pending_repos,
            "pending_approval_stage": None,
            "pending_approval_reason": None,
            "failure_classifications": [],
            "errors": [],
            "retry_decision": None,
            "workflow_status": WorkflowStatus.COMPLETED,
        }

    return {
        "completed_repos": completed_repos,
        "pending_repos": pending_repos,
        "current_working_repo": None,
        "current_target_index": _find_target_index(state, pending_repos[0]),
        "workflow_status": WorkflowStatus.IN_PROGRESS,
        "route_decision": None,
        "pom_mutation_plan": None,
        "preflight_resolution": None,
        "artifact_candidates": [],
        "compatibility_diff": None,
        "complex_remediation_plan": None,
        "decompiled_artifacts": [],
        "symbol_mappings": [],
        "code_change_plan": None,
        "maven_plan": None,
        "maven_verification": None,
        "remediation_plan": None,
        "modified_files": [],
        "code_diffs": [],
        "validation_results": [],
        "rollback_plan": None,
        "branch_publication": None,
        "pull_request_summary": None,
        "jira_completion": None,
        "total_attempts": 0,
        "failure_classifications": [],
        "policy_decisions": [],
        "errors": [],
        "retry_count": 0,
        "retry_decision": None,
        "requires_human_approval": False,
        "requires_delivery_approval": False,
        "pending_approval_stage": None,
        "pending_approval_reason": None,
        "human_feedback": None,
        "approval_history": [],
    }


def _find_target_index(state: RemediationState, repository_name: str) -> int:
    for index, target in enumerate(state.targets):
        if target.repository_name == repository_name:
            return index
    return state.current_target_index
