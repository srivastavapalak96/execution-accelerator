from __future__ import annotations

from execution_accelerator.nodes import build_review_approval_node
from execution_accelerator.schemas import ApprovalDecision, HumanFeedback, WorkflowStatus
from execution_accelerator.state import RemediationState


def test_review_approval_node_marks_pending_without_feedback() -> None:
    node = build_review_approval_node()
    state = RemediationState(
        initial_ticket_id="SEC-123",
        current_working_repo="payments-service",
        requires_human_approval=True,
    )

    update = node(state)

    assert update["workflow_status"] == WorkflowStatus.PENDING
    assert update["audit_events"][-1].event_type == "approval.pending"


def test_review_approval_node_records_approved_feedback() -> None:
    node = build_review_approval_node()
    state = RemediationState(
        initial_ticket_id="SEC-123",
        current_working_repo="payments-service",
        requires_human_approval=True,
        human_feedback=HumanFeedback(
            decision=ApprovalDecision.APPROVED,
            reviewer="security-lead",
            comments="Looks good.",
        ),
    )

    update = node(state)

    assert update["workflow_status"] == WorkflowStatus.IN_PROGRESS
    assert update["audit_events"][-1].event_type == "approval.approved"


def test_review_approval_node_records_rejected_feedback() -> None:
    node = build_review_approval_node()
    state = RemediationState(
        initial_ticket_id="SEC-123",
        current_working_repo="payments-service",
        requires_human_approval=True,
        human_feedback=HumanFeedback(
            decision=ApprovalDecision.REJECTED,
            reviewer="security-lead",
            comments="Needs manual migration.",
        ),
    )

    update = node(state)

    assert update["workflow_status"] == WorkflowStatus.FAILED
    assert update["errors"][-1].code == "approval_rejected"
    assert update["audit_events"][-1].event_type == "approval.rejected"
