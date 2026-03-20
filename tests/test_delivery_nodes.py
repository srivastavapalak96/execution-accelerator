from __future__ import annotations

from pathlib import Path
from typing import cast

from execution_accelerator.adapters import DeliveryAdapter
from execution_accelerator.schemas import AuditEvent, BranchPublicationResult, JiraCompletionResult, PullRequestSummary
from execution_accelerator.nodes import build_publish_remediation_node
from execution_accelerator.schemas import WorkflowStatus
from execution_accelerator.state import RemediationState


def test_publish_remediation_node_records_delivery_metadata() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    node = build_publish_remediation_node(
        DeliveryAdapter(
            branch_publication_fixture_path=fixture_dir / "branch_publication.json",
            pull_request_fixture_path=fixture_dir / "pull_request.json",
            jira_completion_fixture_path=fixture_dir / "jira_completion.json",
        )
    )
    state = RemediationState(
        initial_ticket_id="SEC-123",
        current_working_repo="payments-service",
        pending_repos=["payments-service"],
    )

    update = node(state)

    assert update["workflow_status"] == WorkflowStatus.COMPLETED
    assert update["completed_repos"] == ["payments-service"]
    assert update["pending_repos"] == []
    assert cast(PullRequestSummary, update["pull_request_summary"]).number == 42
    assert cast(JiraCompletionResult, update["jira_completion"]).status == "done"
    assert cast(list[AuditEvent], update["audit_events"])[-1].event_type == "delivery.publish"


def test_publish_remediation_node_creates_ready_pr_after_delivery_approval() -> None:
    class StubDeliveryAdapter:
        def __init__(self) -> None:
            self.draft_pull_request: bool | None = None

        def load_branch_publication(self, **_: object) -> BranchPublicationResult:
            return BranchPublicationResult(
                repository="payments-service",
                branch_name="sec-123-remediate-legacy-json",
                commit_sha="abc123",
                commit_message="chore: remediate legacy-json for SEC-123",
                pushed=True,
            )

        def load_pull_request(self, **kwargs: object) -> PullRequestSummary:
            self.draft_pull_request = kwargs.get("draft_pull_request")
            return PullRequestSummary(
                repository="payments-service",
                number=42,
                url="https://example.test/pr/42",
                title="SEC-123: remediate legacy-json",
                status="open",
            )

        def load_jira_completion(self, **_: object) -> JiraCompletionResult:
            return JiraCompletionResult(
                ticket_id="SEC-123",
                status="commented",
                comment="done",
            )

    adapter = StubDeliveryAdapter()
    node = build_publish_remediation_node(cast(DeliveryAdapter, adapter))
    state = RemediationState(
        initial_ticket_id="SEC-123",
        current_working_repo="payments-service",
        pending_repos=["payments-service"],
        requires_delivery_approval=True,
        approval_history=[{"stage": "delivery", "decision": "approved", "reviewer": "release-manager"}],
    )

    update = node(state)

    assert adapter.draft_pull_request is False
    assert cast(PullRequestSummary, update["pull_request_summary"]).status == "open"
