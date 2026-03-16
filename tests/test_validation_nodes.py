from __future__ import annotations

from pathlib import Path

from execution_accelerator.adapters import ValidationAdapter
from execution_accelerator.nodes import (
    build_handle_validation_failure_node,
    build_validate_remediation_node,
)
from execution_accelerator.execution import MavenRunner
from execution_accelerator.schemas import ExecutionMode, MavenExecutionPlan, ValidationStatus, WorkflowStatus
from execution_accelerator.state import RemediationState, RepositoryWorkspace


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
    assert update["workflow_status"] == WorkflowStatus.FAILED
    assert update["audit_events"][-1].event_type == "validation.rollback"


def test_validate_remediation_node_runs_live_validation(tmp_path) -> None:
    workspace = tmp_path / "live-validation-workspace"
    workspace.mkdir(exist_ok=True)
    wrapper = workspace / "mvnw"
    wrapper.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "mkdir -p target/surefire-reports",
                "cat <<'EOF' > target/surefire-reports/TEST-demo.xml",
                '<testsuite name="demo" tests="2" failures="0" errors="0" skipped="0" />',
                "EOF",
                "echo '[INFO] BUILD SUCCESS'",
            ]
        )
        + "\n"
    )
    wrapper.chmod(0o755)
    node = build_validate_remediation_node(
        ValidationAdapter(
            mode=ExecutionMode.LIVE,
            maven_runner=MavenRunner(log_dir=workspace / "logs"),
        )
    )
    state = RemediationState(
        initial_ticket_id="SEC-123",
        current_working_repo="payments-service",
        repo_map={
            "payments-service": RepositoryWorkspace(
                name="payments-service",
                local_path=str(workspace),
                clone_url="https://example.test/payments-service.git",
                default_branch="main",
                build_system="maven",
                manifest_path="pom.xml",
            )
        },
        maven_plan=MavenExecutionPlan(
            repository="payments-service",
            command=["./mvnw"],
            root_pom_path=str(workspace / "pom.xml"),
            uses_wrapper=True,
        ),
    )

    update = node(state)

    assert update["validation_results"][-1].status == ValidationStatus.PASSED
    assert update["workflow_status"] == WorkflowStatus.IN_PROGRESS
