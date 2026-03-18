"""Phase 0 failure classification stub."""

from __future__ import annotations

import os

from execution_accelerator.schemas import AuditEvent, FailureClassification, RetryDecision, WorkflowStatus
from execution_accelerator.state import RemediationState


def classify_failure(state: RemediationState) -> dict[str, object]:
    """Classify the latest failure and prepare the next routing decision."""

    total_attempts = state.total_attempts + 1
    failure_classifications = list(state.failure_classifications)
    classification = _classify_latest_failure(state)
    failure_classifications.append(classification)

    max_total_attempts = int(os.getenv("EA_MAX_TOTAL_ATTEMPTS", "10"))
    reason = (
        "Total attempt budget reached; escalation is required."
        if total_attempts >= max_total_attempts
        else "Retry matrix is not implemented yet, so failures escalate after classification."
    )
    retry_decision = RetryDecision(
        classification=classification,
        next_node="escalate",
        max_attempts=max_total_attempts,
        reason=reason,
    )

    audit_events = list(state.audit_events)
    audit_events.append(
        AuditEvent(
            event_type="failure.classify",
            message=f"Classified failure for {state.initial_ticket_id} as {classification}.",
            details={
                "classification": classification,
                "total_attempts": total_attempts,
                "next_node": retry_decision.next_node,
            },
        )
    )

    return {
        "total_attempts": total_attempts,
        "failure_classifications": failure_classifications,
        "workflow_status": WorkflowStatus.FAILED,
        "audit_events": audit_events,
    }


def _classify_latest_failure(state: RemediationState) -> FailureClassification:
    if state.errors:
        latest_error = state.errors[-1]
        if latest_error.code in {"policy_blocked", "approval_rejected"}:
            return FailureClassification.POLICY_BLOCK
    if not state.validation_results:
        return FailureClassification.UNKNOWN

    latest_result = state.validation_results[-1]
    for check in latest_result.checks:
        if check.status != "failed":
            continue
        if "compile" in check.name:
            return FailureClassification.COMPILE_ERROR
        if "test" in check.name:
            return FailureClassification.TEST_FAILURE
    return FailureClassification.UNKNOWN
