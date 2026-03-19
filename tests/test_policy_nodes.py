from __future__ import annotations

from pathlib import Path

from execution_accelerator.nodes import build_apply_policy_node
from execution_accelerator.policy import PolicyEngine
from execution_accelerator.schemas import RemediationRouteDecision, RemediationStrategy, WorkflowStatus
from execution_accelerator.state import RemediationState, RepositoryWorkspace


def test_apply_policy_node_records_allowed_decision(tmp_path: Path) -> None:
    config_path = tmp_path / "policy.yaml"
    config_path.write_text("complex_refactor_requires_human_approval: false\n")
    node = build_apply_policy_node(PolicyEngine(config_path=config_path))
    state = RemediationState(
        initial_ticket_id="SEC-123",
        route_decision=RemediationRouteDecision(
            strategy=RemediationStrategy.SIMPLE_UPDATE,
            reason="simple",
            confidence=0.9,
        ),
    )

    update = node(state)

    assert update["policy_decisions"][-1].allowed is True
    assert update["audit_events"][-1].event_type == "policy.apply"


def test_apply_policy_node_records_pending_approval_reason(tmp_path: Path) -> None:
    config_path = tmp_path / "policy.yaml"
    config_path.write_text("transitive_override_requires_human_approval: true\n")
    node = build_apply_policy_node(PolicyEngine(config_path=config_path))
    state = RemediationState(
        initial_ticket_id="SEC-420",
        current_working_repo="payments-service",
        route_decision=RemediationRouteDecision(
            strategy=RemediationStrategy.TRANSITIVE_OVERRIDE,
            reason="transitive",
            confidence=0.88,
        ),
    )

    update = node(state)

    assert update["policy_decisions"][-1].requires_human_approval is True
    assert update["policy_decisions"][-1].approval_reason is not None
    assert update["workflow_status"] == WorkflowStatus.PENDING
    assert update["audit_events"][-1].event_type == "approval.required"
    assert update["audit_events"][-1].details["approval_reason"] == (
        "Policy requires approval for transitive_override remediation."
    )


def test_apply_policy_node_blocks_blocked_repository_tags(tmp_path: Path) -> None:
    config_path = tmp_path / "policy.yaml"
    config_path.write_text("blocked_tags:\n  - no-auto-remediate\n")
    node = build_apply_policy_node(PolicyEngine(config_path=config_path))
    state = RemediationState(
        initial_ticket_id="SEC-123",
        current_working_repo="payments-service",
        route_decision=RemediationRouteDecision(
            strategy=RemediationStrategy.SIMPLE_UPDATE,
            reason="simple",
            confidence=0.9,
        ),
        repo_map={
            "payments-service": RepositoryWorkspace(
                name="payments-service",
                local_path=str(tmp_path / "repo"),
                tags=["no-auto-remediate"],
            )
        },
    )

    update = node(state)

    assert update["policy_decisions"][-1].allowed is False
    assert update["workflow_status"] == WorkflowStatus.FAILED
