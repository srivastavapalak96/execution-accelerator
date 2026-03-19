from __future__ import annotations

from pathlib import Path

from execution_accelerator.policy import PolicyEngine
from execution_accelerator.schemas import RemediationRouteDecision, RemediationStrategy
from execution_accelerator.state import RemediationState, RepositoryWorkspace


def test_policy_engine_requires_human_approval_for_complex_refactor(tmp_path: Path) -> None:
    config_path = tmp_path / "policy.yaml"
    config_path.write_text("complex_refactor_requires_human_approval: true\n")
    engine = PolicyEngine(config_path=config_path)
    state = RemediationState(
        initial_ticket_id="SEC-123",
        current_working_repo="payments-service",
        route_decision=RemediationRouteDecision(
            strategy=RemediationStrategy.COMPLEX_REFACTOR,
            reason="complex",
            confidence=0.8,
            requires_human_approval=False,
        ),
    )

    decision = engine.evaluate(state)

    assert decision.allowed is True
    assert decision.requires_human_approval is True
    assert decision.approval_reason is not None
    assert "complex_refactor" in decision.approval_reason


def test_policy_engine_requires_human_approval_for_transitive_override_when_configured(tmp_path: Path) -> None:
    config_path = tmp_path / "policy.yaml"
    config_path.write_text("transitive_override_requires_human_approval: true\n")
    engine = PolicyEngine(config_path=config_path)
    state = RemediationState(
        initial_ticket_id="SEC-420",
        current_working_repo="payments-service",
        route_decision=RemediationRouteDecision(
            strategy=RemediationStrategy.TRANSITIVE_OVERRIDE,
            reason="transitive",
            confidence=0.88,
            requires_human_approval=False,
        ),
    )

    decision = engine.evaluate(state)

    assert decision.allowed is True
    assert decision.requires_human_approval is True
    assert decision.approval_reason == "Policy requires approval for transitive_override remediation."


def test_policy_engine_blocks_repositories_with_blocked_tags(tmp_path: Path) -> None:
    config_path = tmp_path / "policy.yaml"
    config_path.write_text("blocked_tags:\n  - legacy-blocked\n")
    engine = PolicyEngine(config_path=config_path)
    state = RemediationState(
        initial_ticket_id="SEC-123",
        current_working_repo="payments-service",
        repo_map={
            "payments-service": RepositoryWorkspace(
                name="payments-service",
                local_path=str(tmp_path / "repo"),
                tags=["legacy-blocked"],
            )
        },
    )

    decision = engine.evaluate(state)

    assert decision.allowed is False
    assert "legacy-blocked" in (decision.blocked_reason or "")


def test_policy_engine_requires_human_approval_for_approval_required_tags(tmp_path: Path) -> None:
    config_path = tmp_path / "policy.yaml"
    config_path.write_text("approval_required_tags:\n  - approval-required\n")
    engine = PolicyEngine(config_path=config_path)
    state = RemediationState(
        initial_ticket_id="SEC-123",
        current_working_repo="payments-service",
        route_decision=RemediationRouteDecision(
            strategy=RemediationStrategy.SIMPLE_UPDATE,
            reason="simple",
            confidence=0.93,
        ),
        repo_map={
            "payments-service": RepositoryWorkspace(
                name="payments-service",
                local_path=str(tmp_path / "repo"),
                tags=["approval-required"],
            )
        },
    )

    decision = engine.evaluate(state)

    assert decision.allowed is True
    assert decision.requires_human_approval is True
    assert decision.approval_reason == "Repository tags require approval: approval-required"
