from __future__ import annotations

from pathlib import Path
from typing import cast

import httpx

from execution_accelerator.adapters import DeliveryAdapter
from execution_accelerator.config import load_runtime_config
from execution_accelerator.schemas import AuditEvent, BranchPublicationResult, JiraCompletionResult, PullRequestSummary
from execution_accelerator.nodes import build_publish_remediation_node, build_skip_publish_for_dry_run_node
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
        approval_history=[
            {
                "stage": "delivery",
                "decision": "approved",
                "reviewer": "release-manager",
                "comments": "Ready for publication after final validation review.",
            }
        ],
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
        remediation_plan={
            "strategy": "complex_refactor",
            "summary": "Prepare adapter-backed parser migration before publication.",
            "rationale": "Removed parser entry points require a compatibility seam while downstream callers migrate.",
            "target_repositories": ["payments-service"],
            "requires_human_approval": True,
        },
        route_decision={"strategy": "complex_refactor", "confidence": 0.78, "reason": "Breaking API changes."},
        validation_results=[
            {
                "repository": "payments-service",
                "status": "passed",
                "summary": "Validation passed.",
                "checks": [
                    {
                        "name": "compile",
                        "status": "passed",
                        "details": "Maven compile completed successfully.",
                    }
                ],
            }
        ],
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
    assert "Approval stage: delivery" in adapter.body
    assert "Approved by: release-manager" in adapter.body
    assert "Approval comments: Ready for publication after final validation review." in adapter.body
    assert "Route rationale: Breaking API changes." in adapter.body
    assert "Plan summary: Prepare adapter-backed parser migration before publication." in adapter.body
    assert "Plan rationale: Removed parser entry points require a compatibility seam while downstream callers migrate." in adapter.body
    assert "Primary validation check: compile (passed)" in adapter.body
    assert "Primary validation detail: Maven compile completed successfully." in adapter.body
    assert "Complex migration tactic: adapter_shim" in adapter.body
    assert "Changed file count: 1" in adapter.body
    assert "Primary change: Replace removed parser entry point with the builder-backed parser." in adapter.body
    assert "Total additions: 12" in adapter.body
    assert "Total deletions: 0" in adapter.body
    assert "Primary target file: src/main/java/com/example/payments/LegacyJsonAdapter.java" in adapter.body
    assert "Approved by: release-manager" in adapter.comment
    assert "Approval comments: Ready for publication after final validation review." in adapter.comment
    assert "Route rationale: Breaking API changes." in adapter.comment
    assert "Plan summary: Prepare adapter-backed parser migration before publication." in adapter.comment
    assert "Primary validation check: compile (passed)" in adapter.comment
    assert "Total additions: 12" in adapter.comment
    assert "Pull request: https://example.test/pr/42" in adapter.comment
    assert cast(PullRequestSummary, update["pull_request_summary"]).status == "open"


def test_publish_remediation_node_uses_failed_validation_check_for_delivery_context() -> None:
    class StubDeliveryAdapter:
        def __init__(self) -> None:
            self.body: str | None = None
            self.comment: str | None = None

        def load_branch_publication(self, **_: object) -> BranchPublicationResult:
            return BranchPublicationResult(
                repository="payments-service",
                branch_name="sec-555-remediate-legacy-json",
                commit_sha="abc123",
                commit_message="chore: remediate legacy-json for SEC-555",
                pushed=True,
            )

        def load_pull_request(self, **kwargs: object) -> PullRequestSummary:
            self.body = kwargs.get("body")
            return PullRequestSummary(
                repository="payments-service",
                number=55,
                url="https://example.test/pr/55",
                title="SEC-555: remediate legacy-json",
                status="open",
            )

        def load_jira_completion(self, **kwargs: object) -> JiraCompletionResult:
            self.comment = kwargs.get("comment")
            return JiraCompletionResult(
                ticket_id="SEC-555",
                status="commented",
                comment="done",
            )

    adapter = StubDeliveryAdapter()
    node = build_publish_remediation_node(cast(DeliveryAdapter, adapter))
    state = RemediationState(
        initial_ticket_id="SEC-555",
        current_working_repo="payments-service",
        pending_repos=["payments-service"],
        validation_results=[
            {
                "repository": "payments-service",
                "status": "failed",
                "summary": "Validation found a blocked license.",
                "checks": [
                    {
                        "name": "compile",
                        "status": "passed",
                        "details": "Maven compile completed successfully.",
                    },
                    {
                        "name": "license-scan",
                        "status": "failed",
                        "details": "Disallowed GPL dependency detected.",
                    },
                ],
            }
        ],
    )

    node(state)

    assert adapter.body is not None
    assert adapter.comment is not None
    assert "Primary validation check: license-scan (failed)" in adapter.body
    assert "Primary validation detail: Disallowed GPL dependency detected." in adapter.body
    assert "Primary validation check: license-scan (failed)" in adapter.comment


def test_publish_remediation_node_prepares_next_pending_repository() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    node = build_publish_remediation_node(
        DeliveryAdapter(
            branch_publication_fixture_path=fixture_dir / "branch_publication.json",
            pull_request_fixture_path=fixture_dir / "pull_request.json",
            jira_completion_fixture_path=fixture_dir / "jira_completion.json",
        )
    )
    state = RemediationState(
        initial_ticket_id="SEC-777",
        current_working_repo="payments-service",
        current_target_index=0,
        pending_repos=["payments-service", "ledger-service"],
        targets=[
            {
                "ticket_id": "SEC-777",
                "repository_name": "payments-service",
                "package_name": "org.example:legacy-json",
                "installed_version": "1.2.3",
                "target_version": "1.2.4",
                "clone_url": "https://example.test/payments-service.git",
                "manifest_path": "pom.xml",
                "tags": ["tier-1"],
            },
            {
                "ticket_id": "SEC-777",
                "repository_name": "ledger-service",
                "package_name": "org.example:legacy-json",
                "installed_version": "1.2.3",
                "target_version": "1.2.4",
                "clone_url": "https://example.test/ledger-service.git",
                "manifest_path": "ledger-app/pom.xml",
                "tags": ["tier-2"],
            },
        ],
        repo_map={
            "payments-service": {
                "name": "payments-service",
                "local_path": str(Path("/tmp/payments-service")),
                "clone_url": "https://example.test/payments-service.git",
                "default_branch": "main",
                "build_system": "maven",
                "manifest_path": "pom.xml",
                "owner": "payments-platform",
            }
        },
        modified_files=["/tmp/payments-service/pom.xml"],
        validation_results=[
            {
                "repository": "payments-service",
                "status": "passed",
                "checks": [{"name": "compile", "status": "passed", "details": "Compile passed."}],
                "summary": "Validation passed.",
            }
        ],
        retry_count=1,
        total_attempts=2,
        approval_history=[
            {
                "stage": "delivery",
                "decision": "approved",
                "reviewer": "release-manager",
            }
        ],
    )

    update = node(state)

    assert update["workflow_status"] == WorkflowStatus.IN_PROGRESS
    assert update["completed_repos"] == ["payments-service"]
    assert update["pending_repos"] == ["ledger-service"]
    assert update["current_working_repo"] is None
    assert update["current_target_index"] == 1
    assert update["modified_files"] == []
    assert update["validation_results"] == []
    assert update["approval_history"] == []
    assert update["retry_count"] == 0
    assert update["total_attempts"] == 0


def test_publish_remediation_node_records_structured_delivery_failure() -> None:
    class StubDeliveryAdapter:
        def load_branch_publication(self, **_: object) -> BranchPublicationResult:
            return BranchPublicationResult(
                repository="payments-service",
                branch_name="sec-999-remediate-legacy-json",
                commit_sha="abc123",
                commit_message="chore: remediate legacy-json for SEC-999",
                pushed=True,
            )

        def load_pull_request(self, **_: object) -> PullRequestSummary:
            return PullRequestSummary(
                repository="payments-service",
                number=99,
                url="https://example.test/pr/99",
                title="SEC-999: remediate legacy-json",
                status="open",
            )

        def load_jira_completion(self, **_: object) -> JiraCompletionResult:
            raise httpx.ConnectError("jira gateway timeout")

    node = build_publish_remediation_node(cast(DeliveryAdapter, StubDeliveryAdapter()))
    state = RemediationState(
        initial_ticket_id="SEC-999",
        current_working_repo="payments-service",
        pending_repos=["payments-service"],
    )

    update = node(state)

    assert update["workflow_status"] == WorkflowStatus.FAILED
    assert cast(BranchPublicationResult, update["branch_publication"]).branch_name == "sec-999-remediate-legacy-json"
    assert cast(PullRequestSummary, update["pull_request_summary"]).number == 99
    assert update["jira_completion"] is None
    assert update["errors"][-1].code == "delivery_jira_failed"
    assert update["errors"][-1].recoverable is True
    assert cast(list[AuditEvent], update["audit_events"])[-1].event_type == "delivery.failure"


def test_publish_remediation_node_reuses_existing_delivery_state_on_retry() -> None:
    class StubDeliveryAdapter:
        def load_branch_publication(self, **_: object) -> BranchPublicationResult:
            raise AssertionError("branch publication should not rerun")

        def load_pull_request(self, **_: object) -> PullRequestSummary:
            raise AssertionError("pull request creation should not rerun")

        def load_jira_completion(self, **_: object) -> JiraCompletionResult:
            return JiraCompletionResult(
                ticket_id="SEC-1000",
                status="done",
                comment="Updated Jira ticket.",
            )

    node = build_publish_remediation_node(cast(DeliveryAdapter, StubDeliveryAdapter()))
    state = RemediationState(
        initial_ticket_id="SEC-1000",
        current_working_repo="payments-service",
        pending_repos=["payments-service"],
        branch_publication={
            "repository": "payments-service",
            "branch_name": "sec-1000-remediate-legacy-json",
            "commit_sha": "abc123",
            "commit_message": "Apply automated remediation for SEC-1000",
            "pushed": True,
        },
        pull_request_summary={
            "repository": "payments-service",
            "number": 100,
            "url": "https://example.test/pr/100",
            "title": "SEC-1000 remediate legacy-json",
            "status": "open",
        },
    )

    update = node(state)

    assert update["workflow_status"] == WorkflowStatus.COMPLETED
    assert cast(JiraCompletionResult, update["jira_completion"]).status == "done"
    assert cast(BranchPublicationResult, update["branch_publication"]).branch_name == "sec-1000-remediate-legacy-json"


def test_publish_remediation_node_includes_multi_repo_progress_in_delivery_context() -> None:
    class StubDeliveryAdapter:
        def __init__(self) -> None:
            self.body: str | None = None
            self.comment: str | None = None

        def load_branch_publication(self, **_: object) -> BranchPublicationResult:
            return BranchPublicationResult(
                repository="payments-service",
                branch_name="sec-888-remediate-legacy-json",
                commit_sha="abc123",
                commit_message="chore: remediate legacy-json for SEC-888",
                pushed=True,
            )

        def load_pull_request(self, **kwargs: object) -> PullRequestSummary:
            self.body = kwargs.get("body")
            return PullRequestSummary(
                repository="payments-service",
                number=88,
                url="https://example.test/pr/88",
                title="SEC-888: remediate legacy-json",
                status="open",
            )

        def load_jira_completion(self, **kwargs: object) -> JiraCompletionResult:
            self.comment = kwargs.get("comment")
            return JiraCompletionResult(
                ticket_id="SEC-888",
                status="commented",
                comment="done",
            )

    adapter = StubDeliveryAdapter()
    node = build_publish_remediation_node(cast(DeliveryAdapter, adapter))
    state = RemediationState(
        initial_ticket_id="SEC-888",
        current_working_repo="payments-service",
        pending_repos=["payments-service", "ledger-service"],
        completed_repos=["catalog-service"],
        skipped_repos=[
            {
                "name": "reporting-service",
                "reason": "existing_pr:https://example.test/pr/7",
            }
        ],
    )

    node(state)

    assert adapter.body is not None
    assert adapter.comment is not None
    assert "Current repository: payments-service" in adapter.body
    assert "Repository progress: 3/4 addressed" in adapter.body
    assert "Completed repositories: catalog-service, payments-service" in adapter.body
    assert "Remaining repositories: ledger-service" in adapter.body
    assert "Skipped repositories: reporting-service (existing_pr:https://example.test/pr/7)" in adapter.body
    assert "Repository progress: 3/4 addressed" in adapter.comment
    assert "Remaining repositories: ledger-service" in adapter.comment
    assert "Skipped repositories: reporting-service (existing_pr:https://example.test/pr/7)" in adapter.comment
    assert "Pull request: https://example.test/pr/88" in adapter.comment


def test_skip_publish_for_dry_run_prepares_next_pending_repository(tmp_path: Path) -> None:
    node = build_skip_publish_for_dry_run_node(load_runtime_config(repo_root=tmp_path))
    state = RemediationState(
        initial_ticket_id="SEC-778",
        current_working_repo="payments-service",
        current_target_index=0,
        pending_repos=["payments-service", "ledger-service"],
        targets=[
            {
                "ticket_id": "SEC-778",
                "repository_name": "payments-service",
                "package_name": "org.example:legacy-json",
                "installed_version": "1.2.3",
                "target_version": "1.2.4",
                "clone_url": "https://example.test/payments-service.git",
                "manifest_path": "pom.xml",
            },
            {
                "ticket_id": "SEC-778",
                "repository_name": "ledger-service",
                "package_name": "org.example:legacy-json",
                "installed_version": "1.2.3",
                "target_version": "1.2.4",
                "clone_url": "https://example.test/ledger-service.git",
                "manifest_path": "ledger-app/pom.xml",
            },
        ],
        modified_files=["/tmp/payments-service/pom.xml"],
        validation_results=[
            {
                "repository": "payments-service",
                "status": "passed",
                "checks": [{"name": "compile", "status": "passed", "details": "Compile passed."}],
                "summary": "Validation passed.",
            }
        ],
    )

    update = node(state)

    assert update["workflow_status"] == WorkflowStatus.IN_PROGRESS
    assert update["completed_repos"] == ["payments-service"]
    assert update["pending_repos"] == ["ledger-service"]
    assert update["current_working_repo"] is None
    assert update["current_target_index"] == 1
    assert update["modified_files"] == []
    assert update["validation_results"] == []
