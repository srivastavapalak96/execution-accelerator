from __future__ import annotations

from pathlib import Path
import subprocess
from typing import cast

from execution_accelerator.adapters import ValidationAdapter
from execution_accelerator.execution import GitRunner, MavenRunner
from execution_accelerator.nodes import build_handle_validation_failure_node, build_validate_remediation_node
from execution_accelerator.schemas import (
    AuditEvent,
    ExecutionMode,
    MavenExecutionPlan,
    RepositoryValidationResult,
    RollbackPlan,
    ValidationStatus,
    WorkflowStatus,
)
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

    assert cast(list[RepositoryValidationResult], update["validation_results"])[-1].status == ValidationStatus.PASSED
    assert update["workflow_status"] == WorkflowStatus.IN_PROGRESS
    assert cast(list[AuditEvent], update["audit_events"])[-1].event_type == "validation.run"


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

    assert cast(RollbackPlan, update["rollback_plan"]).status == "applied"
    assert update["workflow_status"] == WorkflowStatus.FAILED
    assert update["errors"][-1].code == "validation_compile_failed"
    assert update["errors"][-1].recoverable is False
    assert cast(list[AuditEvent], update["audit_events"])[-1].event_type == "validation.rollback"


def test_handle_validation_failure_node_marks_test_failures_recoverable() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    failure_node = build_handle_validation_failure_node(
        ValidationAdapter(
            validation_result_fixture_path=fixture_dir / "validation_result_failure.json",
            rollback_fixture_path=fixture_dir / "rollback_plan.json",
        )
    )
    state = RemediationState(
        initial_ticket_id="SEC-124",
        current_working_repo="payments-service",
        validation_results=[
            RepositoryValidationResult(
                repository="payments-service",
                status=ValidationStatus.FAILED,
                checks=[
                    {
                        "name": "compile",
                        "status": ValidationStatus.PASSED,
                        "details": "Compilation succeeded.",
                    },
                    {
                        "name": "unit-tests",
                        "status": ValidationStatus.FAILED,
                        "details": "Two tests failed after remediation.",
                    },
                ],
                summary="Unit tests failed after remediation execution.",
            )
        ],
    )

    update = failure_node(state)

    assert cast(RollbackPlan, update["rollback_plan"]).status == "applied"
    assert update["errors"][-1].code == "validation_test_failed"
    assert update["errors"][-1].recoverable is True


def test_handle_validation_failure_node_marks_license_failures_non_recoverable() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    failure_node = build_handle_validation_failure_node(
        ValidationAdapter(
            validation_result_fixture_path=fixture_dir / "validation_result_failure.json",
            rollback_fixture_path=fixture_dir / "rollback_plan.json",
        )
    )
    state = RemediationState(
        initial_ticket_id="SEC-125",
        current_working_repo="payments-service",
        validation_results=[
            RepositoryValidationResult(
                repository="payments-service",
                status=ValidationStatus.FAILED,
                checks=[
                    {
                        "name": "compile",
                        "status": ValidationStatus.PASSED,
                        "details": "Compilation succeeded.",
                    },
                    {
                        "name": "unit-tests",
                        "status": ValidationStatus.PASSED,
                        "details": "All tests passed.",
                    },
                    {
                        "name": "license-scan",
                        "status": ValidationStatus.FAILED,
                        "details": "Disallowed GPL dependency detected.",
                    },
                ],
                summary="Live validation detected a disallowed or unverifiable dependency license.",
            )
        ],
    )

    update = failure_node(state)

    assert cast(RollbackPlan, update["rollback_plan"]).status == "applied"
    assert update["errors"][-1].code == "validation_license_failed"
    assert update["errors"][-1].recoverable is False


def test_handle_validation_failure_node_does_not_mark_mixed_failures_recoverable() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    failure_node = build_handle_validation_failure_node(
        ValidationAdapter(
            validation_result_fixture_path=fixture_dir / "validation_result_failure.json",
            rollback_fixture_path=fixture_dir / "rollback_plan.json",
        )
    )
    state = RemediationState(
        initial_ticket_id="SEC-126",
        current_working_repo="payments-service",
        validation_results=[
            RepositoryValidationResult(
                repository="payments-service",
                status=ValidationStatus.FAILED,
                checks=[
                    {
                        "name": "unit-tests",
                        "status": ValidationStatus.FAILED,
                        "details": "Two tests failed after remediation.",
                    },
                    {
                        "name": "license-scan",
                        "status": ValidationStatus.FAILED,
                        "details": "Disallowed GPL dependency detected.",
                    },
                ],
                summary="Validation found test and license failures.",
            )
        ],
    )

    update = failure_node(state)

    assert update["errors"][-1].code == "validation_test_failed"
    assert update["errors"][-1].recoverable is False


def test_validate_remediation_node_runs_live_validation(tmp_path: Path) -> None:
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

    assert cast(list[RepositoryValidationResult], update["validation_results"])[-1].status == ValidationStatus.PASSED
    assert update["workflow_status"] == WorkflowStatus.IN_PROGRESS


def test_handle_validation_failure_node_runs_live_rollback(tmp_path: Path) -> None:
    workspace = tmp_path / "live-rollback-workspace"
    workspace.mkdir(exist_ok=True)
    pom_path = workspace / "pom.xml"
    pom_path.write_text("<project><version>1</version></project>\n")
    wrapper = workspace / "mvnw"
    wrapper.write_text("#!/bin/sh\necho '[ERROR] verify failed' >&2\nexit 1\n")
    wrapper.chmod(0o755)
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "add", "pom.xml", "mvnw"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=workspace, check=True, capture_output=True)
    pom_path.write_text("<project><version>2</version></project>\n")
    adapter = ValidationAdapter(
        mode=ExecutionMode.LIVE,
        maven_runner=MavenRunner(log_dir=workspace / "logs"),
        git_runner=GitRunner(log_dir=workspace / "logs"),
    )
    validate_node = build_validate_remediation_node(adapter)
    failure_node = build_handle_validation_failure_node(adapter)
    base_state = RemediationState(
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
        modified_files=[str(pom_path)],
    )
    failed_state = base_state.model_copy(update=validate_node(base_state))

    update = failure_node(failed_state)

    assert cast(RollbackPlan, update["rollback_plan"]).status == "applied"
    assert pom_path.read_text() == "<project><version>1</version></project>\n"
    assert update["workflow_status"] == WorkflowStatus.FAILED
    assert cast(list[AuditEvent], update["audit_events"])[-1].event_type == "validation.rollback"
