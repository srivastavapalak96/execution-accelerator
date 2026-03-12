from __future__ import annotations

from pathlib import Path

from execution_accelerator.adapters import ValidationAdapter
from execution_accelerator.nodes import (
    build_handle_validation_failure_node,
    build_validate_remediation_node,
)
from execution_accelerator.schemas import ValidationStatus, WorkflowStatus
from execution_accelerator.state import RemediationState


def test_validate_remediation_node_records_passed_result() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    node = build_validate_remediation_node(
        ValidationAdapter(
            validation_result_fixture_path=fixture_dir / "validation_result.json",
            rollback_fixture_path=fixture_dir / "rollback_plan.json",
        )
    )
    state = RemediationState(
        initial_ticket_id="SEC-123",
        current_working_repo="payments-service",
    )

    update = node(state)

    assert update["validation_results"][-1].status == ValidationStatus.PASSED
    assert update["workflow_status"] == WorkflowStatus.IN_PROGRESS
    assert update["audit_events"][-1].event_type == "validation.run"


def test_handle_validation_failure_node_records_rollback_plan() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    adapter = ValidationAdapter(
        validation_result_fixture_path=fixture_dir / "validation_result_failure.json",
        rollback_fixture_path=fixture_dir / "rollback_plan.json",
    )
    validate_node = build_validate_remediation_node(adapter)
    failure_node = build_handle_validation_failure_node(adapter)
    base_state = RemediationState(
        initial_ticket_id="SEC-123",
        current_working_repo="payments-service",
    )
    failed_state = base_state.model_copy(update=validate_node(base_state))

    update = failure_node(failed_state)

    assert update["rollback_plan"].status == "applied"
    assert update["retry_count"] == 1
    assert update["workflow_status"] == WorkflowStatus.FAILED
    assert update["audit_events"][-1].event_type == "validation.rollback"
