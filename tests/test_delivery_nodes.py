from __future__ import annotations

from pathlib import Path
from typing import cast

from execution_accelerator.adapters import DeliveryAdapter
from execution_accelerator.schemas import AuditEvent, JiraCompletionResult, PullRequestSummary
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
