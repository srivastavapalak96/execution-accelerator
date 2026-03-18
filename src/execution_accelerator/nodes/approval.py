"""Human approval gating nodes."""

from __future__ import annotations

from collections.abc import Callable

from execution_accelerator.schemas import ApprovalDecision, AuditEvent, WorkflowStatus
from execution_accelerator.state import RemediationState, WorkflowError


def build_review_approval_node() -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that records the latest human approval decision."""

    def review_approval(state: RemediationState) -> dict[str, object]:
        audit_events = list(state.audit_events)
        decision = state.human_approval_decision
        reviewer = state.human_feedback.reviewer if state.human_feedback is not None else None
        comments = state.human_feedback.comments if state.human_feedback is not None else None
        repository = state.current_working_repo

        if decision == ApprovalDecision.PENDING:
            audit_events.append(
                AuditEvent(
                    event_type="approval.pending",
                    message="Waiting for human approval before remediation execution.",
                    details={
                        "repository": repository,
                        "decision": decision,
                    },
                )
            )
            return {
                "workflow_status": WorkflowStatus.PENDING,
                "audit_events": audit_events,
            }

        if decision == ApprovalDecision.APPROVED:
            audit_events.append(
                AuditEvent(
                    event_type="approval.approved",
                    message="Human approval granted; remediation may continue.",
                    details={
                        "repository": repository,
                        "decision": decision,
                        "reviewer": reviewer,
                        "comments": comments,
                    },
                )
            )
            return {
                "workflow_status": WorkflowStatus.IN_PROGRESS,
                "audit_events": audit_events,
            }

        errors = list(state.errors)
        errors.append(
            WorkflowError(
                code="approval_rejected",
                message=comments or "Human approval rejected remediation.",
                recoverable=False,
                repository=repository,
            )
        )
        audit_events.append(
            AuditEvent(
                event_type="approval.rejected",
                message="Human approval rejected remediation execution.",
                details={
                    "repository": repository,
                    "decision": decision,
                    "reviewer": reviewer,
                    "comments": comments,
                },
            )
        )
        return {
            "errors": errors,
            "workflow_status": WorkflowStatus.FAILED,
            "audit_events": audit_events,
        }

    return review_approval
