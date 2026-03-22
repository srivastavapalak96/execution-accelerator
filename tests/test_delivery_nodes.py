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
            self.body: str | None = None
            self.comment: str | None = None

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
            self.body = kwargs.get("body")
            return PullRequestSummary(
                repository="payments-service",
                number=42,
                url="https://example.test/pr/42",
                title="SEC-123: remediate legacy-json",
                status="open",
            )

        def load_jira_completion(self, **_: object) -> JiraCompletionResult:
            self.comment = _.get("comment")
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
        vulnerability_details={
            "package_name": "org.example:legacy-json",
            "installed_version": "1.2.3",
            "summary": "Upgrade legacy-json",
        },
        maven_verification={
            "package_name": "org.example:legacy-json",
            "current_version": "1.2.3",
            "target_version": "2.0.0",
            "resolver_note": "Resolved to 2.0.0.",
        },
        route_decision={"strategy": "complex_refactor", "confidence": 0.78, "reason": "Breaking API changes."},
        validation_results=[{"repository": "payments-service", "status": "passed", "summary": "Validation passed."}],
        code_diffs=[
            {
                "file_path": "src/main/java/com/example/payments/LegacyJsonAdapter.java",
                "change_summary": "Replace removed parser entry point with the builder-backed parser.",
                "additions": 12,
                "deletions": 0,
            }
        ],
        complex_remediation_plan={
            "repository": "payments-service",
            "summary": "Analyze the major-version jump before attempting code changes.",
            "compatibility_diff": {
                "package_name": "org.example:legacy-json",
                "baseline_version": "1.2.3",
                "target_version": "2.0.0",
                "summary": "Major-version upgrade removes legacy parser entry points.",
                "risk": "high",
                "breaking_changes": [
                    {
                        "symbol": "org.example.LegacyParser#parse",
                        "change_type": "removed",
                        "impact": "Call sites must migrate to JsonParserBuilder.",
                    }
                ],
            },
            "migration_tactic": "adapter_shim",
            "target_files": [
                {
                    "file_path": "src/main/java/com/example/payments/LegacyJsonAdapter.java",
                    "change_summary": "Replace removed parser entry point with the builder-backed parser.",
                }
            ],
            "open_questions": ["Should adapter construction move behind a Spring bean factory?"],
        },
    )

    update = node(state)

    assert adapter.draft_pull_request is False
    assert adapter.body is not None
    assert adapter.comment is not None
    assert "Complex migration tactic: adapter_shim" in adapter.body
    assert "Changed file count: 1" in adapter.body
    assert "Primary change: Replace removed parser entry point with the builder-backed parser." in adapter.body
    assert "Primary target file: src/main/java/com/example/payments/LegacyJsonAdapter.java" in adapter.body
    assert "Pull request: https://example.test/pr/42" in adapter.comment
    assert cast(PullRequestSummary, update["pull_request_summary"]).status == "open"
