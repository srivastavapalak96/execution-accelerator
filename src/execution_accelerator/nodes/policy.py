"""Basic remediation policy node."""

from __future__ import annotations

from collections.abc import Callable

from execution_accelerator.policy import PolicyEngine
from execution_accelerator.schemas import AuditEvent, WorkflowStatus
from execution_accelerator.state import RemediationState, WorkflowError


def build_apply_policy_node(
    policy_engine: PolicyEngine,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that evaluates the current remediation route against policy."""

    def apply_policy(state: RemediationState) -> dict[str, object]:
        decision = policy_engine.evaluate(state)
        policy_decisions = list(state.policy_decisions)
        policy_decisions.append(decision)

        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="policy.apply",
                message="Evaluated remediation policy for the selected route.",
                details={
                    "allowed": decision.allowed,
                    "requires_human_approval": decision.requires_human_approval,
                    "approval_reason": decision.approval_reason,
                    "blocked_reason": decision.blocked_reason,
                },
            )
        )

        update: dict[str, object] = {
            "policy_decisions": policy_decisions,
            "requires_human_approval": decision.requires_human_approval,
            "audit_events": audit_events,
        }
        if decision.requires_human_approval:
            audit_events.append(
                AuditEvent(
                    event_type="approval.required",
                    message="Human approval is required before remediation can continue.",
                    details={
                        "repository": state.current_working_repo,
                        "approval_reason": decision.approval_reason,
                    },
                )
            )
            update["workflow_status"] = WorkflowStatus.PENDING
        if not decision.allowed:
            errors = list(state.errors)
            errors.append(
                WorkflowError(
                    code="policy_blocked",
                    message=decision.blocked_reason or "Policy blocked remediation.",
                    recoverable=False,
                    repository=state.current_working_repo,
                )
            )
            update["errors"] = errors
            update["workflow_status"] = WorkflowStatus.FAILED
        return update

    return apply_policy
