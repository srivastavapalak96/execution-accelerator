"""Human approval gating nodes."""

from __future__ import annotations

from collections.abc import Callable

from execution_accelerator.schemas import ApprovalDecision, ApprovalRecord, ApprovalStage, AuditEvent, WorkflowStatus
from execution_accelerator.state import RemediationState, WorkflowError


def build_review_approval_node(
    stage: ApprovalStage = ApprovalStage.REMEDIATION,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that records the latest human approval decision."""

    def review_approval(state: RemediationState) -> dict[str, object]:
        audit_events = list(state.audit_events)
        approval_history = list(state.approval_history)
        decision = state.human_approval_decision
        reviewer = state.human_feedback.reviewer if state.human_feedback is not None else None
        comments = state.human_feedback.comments if state.human_feedback is not None else None
        repository = state.current_working_repo
        action_label = "remediation execution" if stage == ApprovalStage.REMEDIATION else "delivery publication"

        if decision == ApprovalDecision.PENDING:
            audit_events.append(
                AuditEvent(
                    event_type="approval.pending",
                    message=f"Waiting for human approval before {action_label}.",
                    details={
                        "repository": repository,
                        "decision": decision,
                        "approval_stage": stage,
                    },
                )
            )
            return {
                "workflow_status": WorkflowStatus.PENDING,
                "audit_events": audit_events,
            }

        approval_history.append(
            ApprovalRecord(
                stage=stage,
                decision=decision,
                reviewer=reviewer,
                comments=comments,
            )
        )
        if decision == ApprovalDecision.APPROVED:
            audit_events.append(
                AuditEvent(
                    event_type="approval.approved",
                    message=f"Human approval granted; {action_label} may continue.",
                    details={
                        "repository": repository,
                        "decision": decision,
                        "reviewer": reviewer,
                        "comments": comments,
                        "approval_stage": stage,
                    },
                )
            )
            return {
                "workflow_status": WorkflowStatus.IN_PROGRESS,
                "approval_history": approval_history,
                "pending_approval_stage": None,
                "pending_approval_reason": None,
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
                message=f"Human approval rejected {action_label}.",
                details={
                    "repository": repository,
                    "decision": decision,
                    "reviewer": reviewer,
                    "comments": comments,
                    "approval_stage": stage,
                },
            )
        )
        return {
            "errors": errors,
            "workflow_status": WorkflowStatus.FAILED,
            "approval_history": approval_history,
            "pending_approval_stage": None,
            "pending_approval_reason": None,
            "audit_events": audit_events,
        }

    return review_approval


def build_prepare_delivery_approval_node() -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that stages a persisted delivery approval pause."""

    def prepare_delivery_approval(state: RemediationState) -> dict[str, object]:
        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="approval.required",
                message="Human approval is required before delivery publication can continue.",
                details={
                    "repository": state.current_working_repo,
                    "approval_stage": ApprovalStage.DELIVERY,
                    "approval_reason": "Policy requires approval before publishing complex remediation results.",
                },
            )
        )
        return {
            "workflow_status": WorkflowStatus.PENDING,
            "pending_approval_stage": ApprovalStage.DELIVERY,
            "pending_approval_reason": "Policy requires approval before publishing complex remediation results.",
            "human_feedback": None,
            "audit_events": audit_events,
        }

    return prepare_delivery_approval
