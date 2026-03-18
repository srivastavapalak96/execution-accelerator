from __future__ import annotations

from pathlib import Path

from execution_accelerator.config import load_runtime_config
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


def test_escalate_node_writes_bundle(tmp_path: Path) -> None:
    config = load_runtime_config(repo_root=tmp_path)
    node = __import__("execution_accelerator.nodes", fromlist=["build_escalate_node"]).build_escalate_node(config)
    state = RemediationState(
        initial_ticket_id="SEC-123",
        total_attempts=1,
        failure_classifications=[FailureClassification.COMPILE_ERROR],
        modified_files=["/tmp/workspace/pom.xml"],
        errors=[{"code": "validation_failed", "message": "Compile failed.", "recoverable": False}],
    )

    update = node(state)

    assert update["workflow_status"] == "failed"
    bundle_path = Path(update["escalation_bundle"].bundle_path)
    assert bundle_path.exists()
    assert update["audit_events"][-1].details["bundle_path"] == str(bundle_path)
