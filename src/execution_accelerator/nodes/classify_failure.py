"""Failure classification and retry routing helpers."""

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
    max_retry_attempts = int(os.getenv("EA_MAX_RETRY_ATTEMPTS", "0"))
    retry_next_node = _select_retry_node(state)
    latest_error = state.errors[-1] if state.errors else None
    can_retry = (
        retry_next_node is not None
        and _is_retryable_classification(classification)
        and total_attempts < max_total_attempts
        and state.retry_count < max_retry_attempts
        and latest_error is not None
        and latest_error.recoverable
    )
    reason = _build_retry_reason(
        can_retry=can_retry,
        classification=classification,
        total_attempts=total_attempts,
        max_total_attempts=max_total_attempts,
        retry_count=state.retry_count,
        max_retry_attempts=max_retry_attempts,
        latest_error_recoverable=latest_error.recoverable if latest_error is not None else False,
    )
    retry_decision = RetryDecision(
        classification=classification,
        next_node=retry_next_node if can_retry and retry_next_node is not None else "escalate",
        max_attempts=max_total_attempts,
        reason=reason,
    )
    retry_count = state.retry_count + 1 if retry_decision.next_node != "escalate" else state.retry_count

    audit_events = list(state.audit_events)
    audit_events.append(
        AuditEvent(
            event_type="failure.classify",
            message=f"Classified failure for {state.initial_ticket_id} as {classification}.",
            details={
                "classification": classification,
                "total_attempts": total_attempts,
                "next_node": retry_decision.next_node,
                "retry_count": retry_count,
            },
        )
    )

    return {
        "total_attempts": total_attempts,
        "failure_classifications": failure_classifications,
        "retry_count": retry_count,
        "retry_decision": retry_decision,
        "workflow_status": WorkflowStatus.IN_PROGRESS if retry_decision.next_node != "escalate" else WorkflowStatus.FAILED,
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


def _select_retry_node(state: RemediationState) -> str | None:
    if state.route_decision is None:
        return None
    if state.route_decision.strategy == "simple_update":
        return "remediate_simple"
    if state.route_decision.strategy == "transitive_override":
        return "remediate_transitive"
    if state.route_decision.strategy == "complex_refactor":
        return "execute_complex_scaffold"
    return None


def _is_retryable_classification(classification: FailureClassification) -> bool:
    return classification == FailureClassification.TEST_FAILURE


def _build_retry_reason(
    *,
    can_retry: bool,
    classification: FailureClassification,
    total_attempts: int,
    max_total_attempts: int,
    retry_count: int,
    max_retry_attempts: int,
    latest_error_recoverable: bool,
) -> str:
    if can_retry:
        return "Retryable test failure will rerun the active remediation lane."
    if total_attempts >= max_total_attempts:
        return "Total attempt budget reached; escalation is required."
    if not _is_retryable_classification(classification):
        return f"{classification} failures are not automatically retried."
    if retry_count >= max_retry_attempts:
        return "Retry budget reached; escalation is required."
    if not latest_error_recoverable:
        return "Failure is not retryable by the current retry matrix."
    return "Failure is not retryable by the current retry matrix."
