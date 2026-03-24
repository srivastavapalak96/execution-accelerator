from __future__ import annotations

from execution_accelerator.nodes.bootstrap import prepare_planning_stub
from execution_accelerator.schemas import RemediationPlan, RemediationStrategy, WorkflowStatus
from execution_accelerator.state import RemediationState


def test_prepare_planning_stub_builds_concrete_initial_plan_from_vulnerability_scope() -> None:
    state = RemediationState(
        initial_ticket_id="SEC-123",
        pending_repos=["payments-service"],
        vulnerability_details={
            "package_name": "org.example:legacy-json",
            "installed_version": "1.2.3",
            "fixed_version": "1.2.4",
            "summary": "Legacy parser CVE remediation",
        },
    )

    update = prepare_planning_stub(state)

    remediation_plan = update["remediation_plan"]
    assert update["workflow_status"] == WorkflowStatus.PLANNING_READY
    assert remediation_plan.strategy == RemediationStrategy.UNKNOWN
    assert remediation_plan.summary == (
        "Assess remediation for org.example:legacy-json from 1.2.3 to 1.2.4 across 1 repository."
    )
    assert "Legacy parser CVE remediation" in remediation_plan.rationale
    assert remediation_plan.target_repositories == ["payments-service"]
    assert update["audit_events"][-1].message == "Prepared initial remediation plan for the bootstrap graph."
    assert update["audit_events"][-1].details["package_name"] == "org.example:legacy-json"


def test_prepare_planning_stub_preserves_existing_plan() -> None:
    existing_plan = RemediationPlan(
        strategy=RemediationStrategy.SIMPLE_UPDATE,
        summary="Use the verified direct upgrade plan.",
        rationale="Advisory and Maven verification already selected a direct remediation route.",
        target_repositories=["payments-service"],
        requires_human_approval=False,
    )
    state = RemediationState(
        initial_ticket_id="SEC-124",
        remediation_plan=existing_plan,
        repo_map={"payments-service": {"name": "payments-service", "local_path": "/tmp/payments-service"}},
    )

    update = prepare_planning_stub(state)

    assert update["remediation_plan"] == existing_plan
    assert update["audit_events"][-1].details["target_repo_count"] == 1
