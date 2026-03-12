from __future__ import annotations

from execution_accelerator.nodes import classify_failure, escalate
from execution_accelerator.schemas import FailureClassification, ValidationCheck, ValidationStatus
from execution_accelerator.state import RemediationState


def test_classify_failure_records_total_attempts() -> None:
    state = RemediationState(
        initial_ticket_id="SEC-123",
        validation_results=[
            {
                "repository": "payments-service",
                "status": ValidationStatus.FAILED,
                "checks": [
                    ValidationCheck(name="compile", status=ValidationStatus.FAILED, details="Compilation failed.")
                ],
                "summary": "Compile failed.",
            }
        ],
    )

    update = classify_failure(state)

    assert update["total_attempts"] == 1
    assert update["failure_classifications"][-1] == FailureClassification.COMPILE_ERROR
    assert update["audit_events"][-1].event_type == "failure.classify"


def test_escalate_records_terminal_audit_event() -> None:
    state = RemediationState(
        initial_ticket_id="SEC-123",
        total_attempts=1,
        failure_classifications=[FailureClassification.UNKNOWN],
    )

    update = escalate(state)

    assert update["workflow_status"] == "failed"
    assert update["audit_events"][-1].event_type == "failure.escalate"
