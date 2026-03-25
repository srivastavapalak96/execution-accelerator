from __future__ import annotations

from pathlib import Path

from execution_accelerator.cli.main import main
from execution_accelerator.config import load_runtime_config
from execution_accelerator.graph import BootstrapRunResult
from execution_accelerator.state import RemediationState
from tests.conftest import seed_bootstrap_workspace_pom


def test_main_prints_version(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["execution-accelerator", "--version"])

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "0.1.0"


def test_main_prints_config(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr("sys.argv", ["execution-accelerator", "--show-config"])
    monkeypatch.setenv("EA_MODE", "fixture")
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv("EA_JIRA_DONE_TRANSITION_ID", "31")
    monkeypatch.setenv("EA_JIRA_DONE_STATUS_NAME", "Done")
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(tmp_path / "fixtures" / "jira_issue.json"))
    monkeypatch.setenv(
        "EA_REPOSITORY_INVENTORY_FIXTURE_PATH",
        str(tmp_path / "fixtures" / "repository_inventory.json"),
    )
    monkeypatch.setenv("EA_ADVISORY_FIXTURE_PATH", str(tmp_path / "fixtures" / "advisory_verification.json"))
    monkeypatch.setenv(
        "EA_MAVEN_VERIFICATION_FIXTURE_PATH",
        str(tmp_path / "fixtures" / "maven_verification.json"),
    )
    monkeypatch.setenv("EA_POM_FIXTURE_BEFORE_PATH", str(tmp_path / "fixtures" / "pom_before.xml"))
    monkeypatch.setenv("EA_POM_FIXTURE_AFTER_PATH", str(tmp_path / "fixtures" / "pom_after.xml"))
    monkeypatch.setenv(
        "EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH",
        str(tmp_path / "fixtures" / "preflight_resolution.json"),
    )
    monkeypatch.setenv(
        "EA_COMPLEX_ARTIFACT_FIXTURE_PATH",
        str(tmp_path / "fixtures" / "complex_artifacts.json"),
    )
    monkeypatch.setenv(
        "EA_COMPATIBILITY_DIFF_FIXTURE_PATH",
        str(tmp_path / "fixtures" / "compatibility_diff.json"),
    )
    monkeypatch.setenv(
        "EA_DECOMPILED_ARTIFACT_FIXTURE_PATH",
        str(tmp_path / "fixtures" / "decompiled_artifacts.json"),
    )
    monkeypatch.setenv(
        "EA_SYMBOL_MAPPING_FIXTURE_PATH",
        str(tmp_path / "fixtures" / "symbol_mappings.json"),
    )
    monkeypatch.setenv(
        "EA_CODE_CHANGE_PLAN_FIXTURE_PATH",
        str(tmp_path / "fixtures" / "code_change_plan.json"),
    )
    monkeypatch.setenv(
        "EA_VALIDATION_RESULT_FIXTURE_PATH",
        str(tmp_path / "fixtures" / "validation_result.json"),
    )
    monkeypatch.setenv(
        "EA_ROLLBACK_FIXTURE_PATH",
        str(tmp_path / "fixtures" / "rollback_plan.json"),
    )
    monkeypatch.setenv(
        "EA_BRANCH_PUBLICATION_FIXTURE_PATH",
        str(tmp_path / "fixtures" / "branch_publication.json"),
    )
    monkeypatch.setenv(
        "EA_PULL_REQUEST_FIXTURE_PATH",
        str(tmp_path / "fixtures" / "pull_request.json"),
    )
    monkeypatch.setenv(
        "EA_JIRA_COMPLETION_FIXTURE_PATH",
        str(tmp_path / "fixtures" / "jira_completion.json"),
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "repo_root=" in captured.out
    assert "execution_mode=fixture" in captured.out
    assert "dry_run=False" in captured.out
    assert "keep_workspace=False" in captured.out
    assert f"data_dir={tmp_path / 'data'}" in captured.out
    assert f"workspace_dir={tmp_path / 'workspace'}" in captured.out
    assert f"logs_dir={tmp_path / 'logs'}" in captured.out
    assert f"checkpoints_path={tmp_path / 'state' / 'checkpoints.sqlite'}" in captured.out
    assert "jira_done_transition_id=31" in captured.out
    assert "jira_done_status_name=Done" in captured.out
    assert f"jira_fixture_path={tmp_path / 'fixtures' / 'jira_issue.json'}" in captured.out
    assert (
        f"repository_inventory_fixture_path={tmp_path / 'fixtures' / 'repository_inventory.json'}"
        in captured.out
    )
    assert f"advisory_fixture_path={tmp_path / 'fixtures' / 'advisory_verification.json'}" in captured.out
    assert (
        f"maven_verification_fixture_path={tmp_path / 'fixtures' / 'maven_verification.json'}"
        in captured.out
    )
    assert f"pom_fixture_before_path={tmp_path / 'fixtures' / 'pom_before.xml'}" in captured.out
    assert f"pom_fixture_after_path={tmp_path / 'fixtures' / 'pom_after.xml'}" in captured.out
    assert (
        f"preflight_resolution_fixture_path={tmp_path / 'fixtures' / 'preflight_resolution.json'}"
        in captured.out
    )
    assert f"complex_artifact_fixture_path={tmp_path / 'fixtures' / 'complex_artifacts.json'}" in captured.out
    assert f"compatibility_diff_fixture_path={tmp_path / 'fixtures' / 'compatibility_diff.json'}" in captured.out
    assert f"decompiled_artifact_fixture_path={tmp_path / 'fixtures' / 'decompiled_artifacts.json'}" in captured.out
    assert f"symbol_mapping_fixture_path={tmp_path / 'fixtures' / 'symbol_mappings.json'}" in captured.out
    assert f"code_change_plan_fixture_path={tmp_path / 'fixtures' / 'code_change_plan.json'}" in captured.out
    assert f"validation_result_fixture_path={tmp_path / 'fixtures' / 'validation_result.json'}" in captured.out
    assert f"rollback_fixture_path={tmp_path / 'fixtures' / 'rollback_plan.json'}" in captured.out
    assert f"branch_publication_fixture_path={tmp_path / 'fixtures' / 'branch_publication.json'}" in captured.out
    assert f"pull_request_fixture_path={tmp_path / 'fixtures' / 'pull_request.json'}" in captured.out
    assert f"jira_completion_fixture_path={tmp_path / 'fixtures' / 'jira_completion.json'}" in captured.out


def test_main_bootstraps_ticket(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--bootstrap-ticket",
            "SEC-401",
            "--thread-id",
            "sec-401-dev",
        ],
    )
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv(
        "EA_JIRA_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "jira_issue.json"),
    )
    monkeypatch.setenv(
        "EA_REPOSITORY_INVENTORY_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "repository_inventory.json"),
    )
    monkeypatch.setenv(
        "EA_ADVISORY_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "advisory_verification.json"),
    )
    monkeypatch.setenv(
        "EA_MAVEN_VERIFICATION_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "maven_verification.json"),
    )
    monkeypatch.setenv(
        "EA_POM_FIXTURE_BEFORE_PATH",
        str(Path(__file__).parent / "fixtures" / "pom_before.xml"),
    )
    monkeypatch.setenv(
        "EA_POM_FIXTURE_AFTER_PATH",
        str(Path(__file__).parent / "fixtures" / "pom_after.xml"),
    )
    monkeypatch.setenv(
        "EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "preflight_resolution.json"),
    )
    monkeypatch.setenv(
        "EA_COMPLEX_ARTIFACT_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "complex_artifacts.json"),
    )
    monkeypatch.setenv(
        "EA_COMPATIBILITY_DIFF_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "compatibility_diff.json"),
    )
    monkeypatch.setenv(
        "EA_DECOMPILED_ARTIFACT_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "decompiled_artifacts.json"),
    )
    monkeypatch.setenv(
        "EA_SYMBOL_MAPPING_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "symbol_mappings.json"),
    )
    monkeypatch.setenv(
        "EA_CODE_CHANGE_PLAN_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "code_change_plan.json"),
    )
    monkeypatch.setenv(
        "EA_VALIDATION_RESULT_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "validation_result.json"),
    )
    monkeypatch.setenv(
        "EA_ROLLBACK_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "rollback_plan.json"),
    )
    monkeypatch.setenv(
        "EA_BRANCH_PUBLICATION_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "branch_publication.json"),
    )
    monkeypatch.setenv(
        "EA_PULL_REQUEST_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "pull_request.json"),
    )
    monkeypatch.setenv(
        "EA_JIRA_COMPLETION_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "jira_completion.json"),
    )
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-401",
        repository_name="payments-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_before.xml",
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "thread_id=sec-401-dev" in captured.out
    assert f"checkpoint_path={tmp_path / 'state' / 'checkpoints.sqlite'}" in captured.out
    assert "workflow_status=completed" in captured.out
    assert "target_count=1" in captured.out
    assert "current_target_index=0" in captured.out
    assert "audit_event_count=13" in captured.out
    assert "package_name=org.example:legacy-json" in captured.out
    assert "severity=high" in captured.out
    assert "recommended_fix_version=1.2.4" in captured.out
    assert "dependency_kind=direct" in captured.out
    assert "pending_repos=" in captured.out
    assert "completed_repos=payments-service" in captured.out
    assert "route_strategy=simple_update" in captured.out
    assert "route_confidence=0.93" in captured.out
    assert (
        "route_reason=Verified target is direct, available, and low-risk, so the simple update lane is appropriate."
        in captured.out
    )
    assert "plan_strategy=simple_update" in captured.out
    assert "pom_change_kind=direct_version_bump" in captured.out
    assert "pom_change_target_section=project_dependencies" in captured.out
    assert "current_working_repo=payments-service" in captured.out
    assert "modified_file_count=1" in captured.out
    assert f"modified_file={tmp_path / 'workspace' / 'sec-401' / 'payments-service' / 'pom.xml'}" in captured.out
    assert "preflight_status=passed" in captured.out
    assert "preflight_dependency_kind=direct" in captured.out
    assert "preflight_resolved_version=1.2.4" in captured.out
    assert "validation_status=passed" in captured.out
    assert "validation_check_count=3" in captured.out
    assert "retry_count=0" in captured.out
    assert "branch_name=sec-123-remediate-legacy-json" in captured.out
    assert "pull_request_number=42" in captured.out
    assert "jira_ticket_status=done" in captured.out


def test_main_prints_escalation_bundle_for_failed_ticket(monkeypatch, capsys, tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--bootstrap-ticket",
            "SEC-500",
            "--thread-id",
            "sec-500-dev",
        ],
    )
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(fixture_dir / "jira_issue.json"))
    monkeypatch.setenv(
        "EA_REPOSITORY_INVENTORY_FIXTURE_PATH",
        str(fixture_dir / "repository_inventory.json"),
    )
    monkeypatch.setenv("EA_ADVISORY_FIXTURE_PATH", str(fixture_dir / "advisory_verification.json"))
    monkeypatch.setenv("EA_MAVEN_VERIFICATION_FIXTURE_PATH", str(fixture_dir / "maven_verification.json"))
    monkeypatch.setenv("EA_POM_FIXTURE_BEFORE_PATH", str(fixture_dir / "pom_before.xml"))
    monkeypatch.setenv("EA_POM_FIXTURE_AFTER_PATH", str(fixture_dir / "pom_after.xml"))
    monkeypatch.setenv("EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH", str(fixture_dir / "preflight_resolution.json"))
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixture_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixture_dir / "code_change_plan.json"))
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixture_dir / "validation_result_failure.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixture_dir / "rollback_plan.json"))
    monkeypatch.setenv("EA_BRANCH_PUBLICATION_FIXTURE_PATH", str(fixture_dir / "branch_publication.json"))
    monkeypatch.setenv("EA_PULL_REQUEST_FIXTURE_PATH", str(fixture_dir / "pull_request.json"))
    monkeypatch.setenv("EA_JIRA_COMPLETION_FIXTURE_PATH", str(fixture_dir / "jira_completion.json"))
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-500",
        repository_name="payments-service",
        fixture_path=fixture_dir / "pom_before.xml",
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "thread_id=sec-500-dev" in captured.out
    assert "workflow_status=failed" in captured.out
    assert "validation_status=failed" in captured.out
    assert "rollback_status=applied" in captured.out
    assert "error_count=1" in captured.out
    assert "latest_error_code=validation_failed" in captured.out
    assert "retry_count=0" in captured.out
    bundle_line = next(
        line for line in captured.out.splitlines() if line.startswith("escalation_bundle_path=")
    )
    bundle_path = Path(bundle_line.removeprefix("escalation_bundle_path="))
    assert bundle_path.exists()
    assert bundle_path.parent == tmp_path / "data" / "escalations"


def test_main_prints_skipped_repository_summary(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--bootstrap-ticket",
            "SEC-700",
            "--thread-id",
            "sec-700-skip",
        ],
    )
    monkeypatch.setattr(
        "execution_accelerator.cli.main.bootstrap_ticket_run",
        lambda ticket_id, runtime_config, thread_id=None: BootstrapRunResult(
            thread_id=thread_id or "sec-700-skip",
            checkpoint_path=tmp_path / "state" / "checkpoints.sqlite",
            state=RemediationState(
                initial_ticket_id=ticket_id,
                skipped_repos=[
                    {
                        "name": "payments-service",
                        "reason": "existing_pr:https://github.com/example/payments-service/pull/7",
                    }
                ],
            ),
        ),
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "skipped_repo_count=1" in captured.out
    assert "skipped_repo_1=payments-service" in captured.out
    assert "skipped_repo_reason_1=existing_pr:https://github.com/example/payments-service/pull/7" in captured.out


def test_main_prints_latest_error_summary(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--bootstrap-ticket",
            "SEC-701",
            "--thread-id",
            "sec-701-error",
        ],
    )
    monkeypatch.setattr(
        "execution_accelerator.cli.main.bootstrap_ticket_run",
        lambda ticket_id, runtime_config, thread_id=None: BootstrapRunResult(
            thread_id=thread_id or "sec-701-error",
            checkpoint_path=tmp_path / "state" / "checkpoints.sqlite",
            state=RemediationState(
                initial_ticket_id=ticket_id,
                workflow_status="failed",
                errors=[
                    {
                        "code": "approval_rejected",
                        "message": "Human reviewer rejected automated remediation.",
                        "recoverable": False,
                    }
                ],
            ),
        ),
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "error_count=1" in captured.out
    assert "latest_error_code=approval_rejected" in captured.out
    assert "latest_error_message=Human reviewer rejected automated remediation." in captured.out


def test_main_prints_delivery_approval_stage_summary(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--bootstrap-ticket",
            "SEC-779",
            "--thread-id",
            "sec-779-delivery-approval",
        ],
    )
    monkeypatch.setattr(
        "execution_accelerator.cli.main.bootstrap_ticket_run",
        lambda ticket_id, runtime_config, thread_id=None: BootstrapRunResult(
            thread_id=thread_id or "sec-779-delivery-approval",
            checkpoint_path=tmp_path / "state" / "checkpoints.sqlite",
            state=RemediationState(
                initial_ticket_id=ticket_id,
                workflow_status="pending",
                requires_human_approval=True,
                pending_approval_stage="delivery",
                pending_approval_reason="Policy requires approval before publishing complex remediation results.",
            ),
        ),
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "pending_approval_stage=delivery" in captured.out
    assert "approval_reason=Policy requires approval before publishing complex remediation results." in captured.out


def test_main_loads_persisted_thread_state(monkeypatch, capsys, tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(fixture_dir / "jira_issue.json"))
    monkeypatch.setenv(
        "EA_REPOSITORY_INVENTORY_FIXTURE_PATH",
        str(fixture_dir / "repository_inventory.json"),
    )
    monkeypatch.setenv(
        "EA_ADVISORY_FIXTURE_PATH",
        str(fixture_dir / "advisory_verification.json"),
    )
    monkeypatch.setenv(
        "EA_MAVEN_VERIFICATION_FIXTURE_PATH",
        str(fixture_dir / "maven_verification.json"),
    )
    monkeypatch.setenv("EA_POM_FIXTURE_BEFORE_PATH", str(fixture_dir / "pom_before.xml"))
    monkeypatch.setenv("EA_POM_FIXTURE_AFTER_PATH", str(fixture_dir / "pom_after.xml"))
    monkeypatch.setenv(
        "EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH",
        str(fixture_dir / "preflight_resolution.json"),
    )
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixture_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixture_dir / "code_change_plan.json"))
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixture_dir / "validation_result.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixture_dir / "rollback_plan.json"))
    monkeypatch.setenv("EA_BRANCH_PUBLICATION_FIXTURE_PATH", str(fixture_dir / "branch_publication.json"))
    monkeypatch.setenv("EA_PULL_REQUEST_FIXTURE_PATH", str(fixture_dir / "pull_request.json"))
    monkeypatch.setenv("EA_JIRA_COMPLETION_FIXTURE_PATH", str(fixture_dir / "jira_completion.json"))
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-402",
        repository_name="payments-service",
        fixture_path=fixture_dir / "pom_before.xml",
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--bootstrap-ticket",
            "SEC-402",
            "--thread-id",
            "sec-402-dev",
        ],
    )
    assert main() == 0
    capsys.readouterr()

    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--show-thread-state",
            "sec-402-dev",
        ],
    )
    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "thread_id=sec-402-dev" in captured.out
    assert "workflow_status=completed" in captured.out
    assert "target_count=1" in captured.out
    assert "pending_repos=" in captured.out
    assert "completed_repos=payments-service" in captured.out
    assert "audit_event_count=13" in captured.out
    assert "package_name=org.example:legacy-json" in captured.out
    assert "recommended_fix_version=1.2.4" in captured.out
    assert "route_strategy=simple_update" in captured.out
    assert "pom_change_kind=direct_version_bump" in captured.out
    assert "pom_change_target_section=project_dependencies" in captured.out
    assert "current_working_repo=payments-service" in captured.out
    assert "modified_file_count=1" in captured.out
    assert f"modified_file={tmp_path / 'workspace' / 'sec-402' / 'payments-service' / 'pom.xml'}" in captured.out
    assert "preflight_status=passed" in captured.out
    assert "preflight_dependency_kind=direct" in captured.out
    assert "preflight_resolved_version=1.2.4" in captured.out
    assert "validation_status=passed" in captured.out
    assert "validation_check_count=3" in captured.out
    assert "branch_name=sec-123-remediate-legacy-json" in captured.out
    assert "pull_request_number=42" in captured.out
    assert "jira_ticket_status=done" in captured.out


def test_main_bootstraps_transitive_ticket(monkeypatch, capsys, tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--bootstrap-ticket",
            "SEC-499",
            "--thread-id",
            "sec-499-transitive",
        ],
    )
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(fixture_dir / "jira_issue.json"))
    monkeypatch.setenv("EA_REPOSITORY_INVENTORY_FIXTURE_PATH", str(fixture_dir / "repository_inventory.json"))
    monkeypatch.setenv("EA_ADVISORY_FIXTURE_PATH", str(fixture_dir / "advisory_verification.json"))
    monkeypatch.setenv(
        "EA_MAVEN_VERIFICATION_FIXTURE_PATH",
        str(fixture_dir / "maven_verification_transitive.json"),
    )
    monkeypatch.setenv("EA_POM_FIXTURE_BEFORE_PATH", str(fixture_dir / "pom_transitive_before.xml"))
    monkeypatch.setenv("EA_POM_FIXTURE_AFTER_PATH", str(fixture_dir / "pom_transitive_after.xml"))
    monkeypatch.setenv(
        "EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH",
        str(fixture_dir / "preflight_resolution_transitive.json"),
    )
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixture_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixture_dir / "code_change_plan.json"))
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixture_dir / "validation_result.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixture_dir / "rollback_plan.json"))
    monkeypatch.setenv("EA_BRANCH_PUBLICATION_FIXTURE_PATH", str(fixture_dir / "branch_publication.json"))
    monkeypatch.setenv("EA_PULL_REQUEST_FIXTURE_PATH", str(fixture_dir / "pull_request.json"))
    monkeypatch.setenv("EA_JIRA_COMPLETION_FIXTURE_PATH", str(fixture_dir / "jira_completion.json"))
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-499",
        repository_name="payments-service",
        fixture_path=fixture_dir / "pom_transitive_before.xml",
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "thread_id=sec-499-transitive" in captured.out
    assert "route_strategy=transitive_override" in captured.out
    assert "route_confidence=0.88" in captured.out
    assert "plan_strategy=transitive_override" in captured.out
    assert "pom_change_kind=dependency_management_override" in captured.out
    assert "pom_change_target_section=dependency_management" in captured.out
    assert "preflight_status=passed" in captured.out
    assert "preflight_dependency_kind=transitive" in captured.out
    assert "preflight_resolved_version=1.2.4" in captured.out
    assert "validation_status=passed" in captured.out
    assert "validation_check_count=3" in captured.out
    assert "branch_name=sec-123-remediate-legacy-json" in captured.out
    assert "pull_request_number=42" in captured.out
    assert "jira_ticket_status=done" in captured.out


def test_main_bootstraps_complex_ticket(monkeypatch, capsys, tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--bootstrap-ticket",
            "SEC-799",
            "--thread-id",
            "sec-799-complex",
        ],
    )
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(fixture_dir / "jira_issue.json"))
    monkeypatch.setenv("EA_REPOSITORY_INVENTORY_FIXTURE_PATH", str(fixture_dir / "repository_inventory.json"))
    monkeypatch.setenv("EA_ADVISORY_FIXTURE_PATH", str(fixture_dir / "advisory_verification_complex.json"))
    monkeypatch.setenv("EA_MAVEN_VERIFICATION_FIXTURE_PATH", str(fixture_dir / "maven_verification_complex.json"))
    monkeypatch.setenv("EA_POM_FIXTURE_BEFORE_PATH", str(fixture_dir / "pom_before.xml"))
    monkeypatch.setenv("EA_POM_FIXTURE_AFTER_PATH", str(fixture_dir / "pom_after.xml"))
    monkeypatch.setenv("EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH", str(fixture_dir / "preflight_resolution.json"))
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixture_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixture_dir / "code_change_plan.json"))
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixture_dir / "validation_result.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixture_dir / "rollback_plan.json"))
    monkeypatch.setenv("EA_BRANCH_PUBLICATION_FIXTURE_PATH", str(fixture_dir / "branch_publication.json"))
    monkeypatch.setenv("EA_PULL_REQUEST_FIXTURE_PATH", str(fixture_dir / "pull_request.json"))
    monkeypatch.setenv("EA_JIRA_COMPLETION_FIXTURE_PATH", str(fixture_dir / "jira_completion.json"))

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "thread_id=sec-799-complex" in captured.out
    assert "route_strategy=complex_refactor" in captured.out
    assert "route_confidence=0.78" in captured.out
    assert "requires_human_approval=True" in captured.out
    assert "approval_decision=pending" in captured.out
    assert "approval_reason=" in captured.out
    assert "validation_status=" not in captured.out
    assert "branch_name=" not in captured.out
    assert "pull_request_number=" not in captured.out
    assert "jira_ticket_status=" not in captured.out


def test_main_bootstraps_transitive_ticket_and_reports_policy_approval_reason(monkeypatch, capsys, tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    policy_dir = tmp_path / "config"
    policy_dir.mkdir()
    (policy_dir / "policy.yaml").write_text("transitive_override_requires_human_approval: true\n")
    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--bootstrap-ticket",
            "SEC-421",
            "--thread-id",
            "sec-421-transitive",
        ],
    )
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(fixture_dir / "jira_issue.json"))
    monkeypatch.setenv("EA_REPOSITORY_INVENTORY_FIXTURE_PATH", str(fixture_dir / "repository_inventory.json"))
    monkeypatch.setenv("EA_ADVISORY_FIXTURE_PATH", str(fixture_dir / "advisory_verification.json"))
    monkeypatch.setenv("EA_MAVEN_VERIFICATION_FIXTURE_PATH", str(fixture_dir / "maven_verification_transitive.json"))
    monkeypatch.setenv("EA_POM_FIXTURE_BEFORE_PATH", str(fixture_dir / "pom_transitive_before.xml"))
    monkeypatch.setenv("EA_POM_FIXTURE_AFTER_PATH", str(fixture_dir / "pom_transitive_after.xml"))
    monkeypatch.setenv("EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH", str(fixture_dir / "preflight_resolution_transitive.json"))
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixture_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixture_dir / "code_change_plan.json"))
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixture_dir / "validation_result.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixture_dir / "rollback_plan.json"))
    monkeypatch.setenv("EA_BRANCH_PUBLICATION_FIXTURE_PATH", str(fixture_dir / "branch_publication.json"))
    monkeypatch.setenv("EA_PULL_REQUEST_FIXTURE_PATH", str(fixture_dir / "pull_request.json"))
    monkeypatch.setenv("EA_JIRA_COMPLETION_FIXTURE_PATH", str(fixture_dir / "jira_completion.json"))
    monkeypatch.setattr(
        "execution_accelerator.cli.main.load_runtime_config",
        lambda: load_runtime_config(repo_root=tmp_path),
    )
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-421",
        repository_name="payments-service",
        fixture_path=fixture_dir / "pom_transitive_before.xml",
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "thread_id=sec-421-transitive" in captured.out
    assert "route_strategy=transitive_override" in captured.out
    assert "requires_human_approval=True" in captured.out
    assert "approval_decision=pending" in captured.out
    assert "approval_reason=Policy requires approval for transitive_override remediation." in captured.out
    assert "validation_status=" not in captured.out


def test_main_resumes_complex_ticket_after_approval(monkeypatch, capsys, tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(fixture_dir / "jira_issue.json"))
    monkeypatch.setenv("EA_REPOSITORY_INVENTORY_FIXTURE_PATH", str(fixture_dir / "repository_inventory.json"))
    monkeypatch.setenv("EA_ADVISORY_FIXTURE_PATH", str(fixture_dir / "advisory_verification_complex.json"))
    monkeypatch.setenv("EA_MAVEN_VERIFICATION_FIXTURE_PATH", str(fixture_dir / "maven_verification_complex.json"))
    monkeypatch.setenv("EA_POM_FIXTURE_BEFORE_PATH", str(fixture_dir / "pom_before.xml"))
    monkeypatch.setenv("EA_POM_FIXTURE_AFTER_PATH", str(fixture_dir / "pom_after.xml"))
    monkeypatch.setenv("EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH", str(fixture_dir / "preflight_resolution.json"))
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixture_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixture_dir / "code_change_plan.json"))
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixture_dir / "validation_result.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixture_dir / "rollback_plan.json"))
    monkeypatch.setenv("EA_BRANCH_PUBLICATION_FIXTURE_PATH", str(fixture_dir / "branch_publication.json"))
    monkeypatch.setenv("EA_PULL_REQUEST_FIXTURE_PATH", str(fixture_dir / "pull_request.json"))
    monkeypatch.setenv("EA_JIRA_COMPLETION_FIXTURE_PATH", str(fixture_dir / "jira_completion.json"))

    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--bootstrap-ticket",
            "SEC-799",
            "--thread-id",
            "sec-799-approval",
        ],
    )
    assert main() == 0
    capsys.readouterr()

    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--resume",
            "sec-799-approval",
            "--approval-decision",
            "approved",
            "--reviewer",
            "security-lead",
            "--approval-comments",
            "Approved for automation.",
        ],
    )
    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "thread_id=sec-799-approval" in captured.out
    assert "workflow_status=completed" in captured.out
    assert "approval_decision=approved" in captured.out
    assert "approval_reviewer=security-lead" in captured.out
    assert "approval_comments=Approved for automation." in captured.out
    assert (
        "route_reason=Verified target introduces high compatibility risk and needs the complex remediation lane."
        in captured.out
    )
    assert "plan_summary=Analyze org.example:legacy-json from 1.2.3 to 2.0.0 before attempting code changes. Prepared deterministic scaffold edits for 2 files." in captured.out
    assert "plan_rationale=Removed APIs and constructor changes suggest insulating callers behind a compatibility adapter while parser and serializer internals migrate. Current scaffold covers 2 target files and 2 unresolved questions." in captured.out
    assert "complex_candidate_count=2" in captured.out
    assert "complex_migration_tactic=adapter_shim" in captured.out
    assert "complex_migration_step_count=2" in captured.out
    assert "complex_target_symbol_count=2" in captured.out
    assert "complex_primary_legacy_symbol=org.example.LegacyParser#parse" in captured.out
    assert "complex_primary_replacement_symbol=org.example.JsonParserBuilder#create().parse" in captured.out
    assert "complex_target_file_count=2" in captured.out
    assert (
        "complex_primary_target_file="
        "src/main/java/com/example/payments/LegacyJsonAdapter.java"
    ) in captured.out
    assert "complex_open_question_count=2" in captured.out
    assert "complex_primary_open_question=Should adapter construction move behind a Spring bean factory?" in captured.out
    assert "complex_planned_file_count=2" in captured.out
    assert "modified_file_count=2" in captured.out
    assert (
        "modified_file="
        f"{tmp_path / 'workspace' / 'sec-799' / 'payments-service' / 'src/main/java/com/example/payments/LegacyJsonAdapter.java'}"
    ) in captured.out
    assert "code_diff_count=2" in captured.out
    assert (
        "primary_code_diff_summary=Replace removed parser entry point with the builder-backed parser."
    ) in captured.out
    assert "code_diff_total_additions=22" in captured.out
    assert "code_diff_total_deletions=0" in captured.out
    assert "validation_status=passed" in captured.out
    assert "pull_request_number=42" in captured.out
    assert "primary_validation_check=compile" in captured.out
    assert "primary_validation_check_status=passed" in captured.out
    assert "primary_validation_check_details=Maven compile completed successfully." in captured.out


def test_main_bootstraps_ticket_in_dry_run_mode(monkeypatch, capsys, tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    custom_workspace = tmp_path / "custom-workspace"
    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--bootstrap-ticket",
            "SEC-450",
            "--thread-id",
            "sec-450-dry-run",
            "--dry-run",
            "--keep-workspace",
            "--workspace-dir",
            str(custom_workspace),
        ],
    )
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(fixture_dir / "jira_issue.json"))
    monkeypatch.setenv("EA_REPOSITORY_INVENTORY_FIXTURE_PATH", str(fixture_dir / "repository_inventory.json"))
    monkeypatch.setenv("EA_ADVISORY_FIXTURE_PATH", str(fixture_dir / "advisory_verification.json"))
    monkeypatch.setenv("EA_MAVEN_VERIFICATION_FIXTURE_PATH", str(fixture_dir / "maven_verification.json"))
    monkeypatch.setenv("EA_POM_FIXTURE_BEFORE_PATH", str(fixture_dir / "pom_before.xml"))
    monkeypatch.setenv("EA_POM_FIXTURE_AFTER_PATH", str(fixture_dir / "pom_after.xml"))
    monkeypatch.setenv("EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH", str(fixture_dir / "preflight_resolution.json"))
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixture_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixture_dir / "code_change_plan.json"))
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixture_dir / "validation_result.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixture_dir / "rollback_plan.json"))
    monkeypatch.setenv("EA_BRANCH_PUBLICATION_FIXTURE_PATH", str(fixture_dir / "branch_publication.json"))
    monkeypatch.setenv("EA_PULL_REQUEST_FIXTURE_PATH", str(fixture_dir / "pull_request.json"))
    monkeypatch.setenv("EA_JIRA_COMPLETION_FIXTURE_PATH", str(fixture_dir / "jira_completion.json"))
    seed_bootstrap_workspace_pom(
        custom_workspace,
        ticket_id="SEC-450",
        repository_name="payments-service",
        fixture_path=fixture_dir / "pom_before.xml",
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "thread_id=sec-450-dry-run" in captured.out
    assert "workflow_status=completed" in captured.out
    assert "target_count=1" in captured.out
    assert "completed_repos=payments-service" in captured.out
    assert f"modified_file={custom_workspace / 'sec-450' / 'payments-service' / 'pom.xml'}" in captured.out
    assert "branch_name=" not in captured.out
    assert "pull_request_number=" not in captured.out
    assert "jira_ticket_status=" not in captured.out


def test_main_resumes_persisted_thread(monkeypatch, capsys, tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(fixture_dir / "jira_issue.json"))
    monkeypatch.setenv("EA_REPOSITORY_INVENTORY_FIXTURE_PATH", str(fixture_dir / "repository_inventory.json"))
    monkeypatch.setenv("EA_ADVISORY_FIXTURE_PATH", str(fixture_dir / "advisory_verification.json"))
    monkeypatch.setenv("EA_MAVEN_VERIFICATION_FIXTURE_PATH", str(fixture_dir / "maven_verification.json"))
    monkeypatch.setenv("EA_POM_FIXTURE_BEFORE_PATH", str(fixture_dir / "pom_before.xml"))
    monkeypatch.setenv("EA_POM_FIXTURE_AFTER_PATH", str(fixture_dir / "pom_after.xml"))
    monkeypatch.setenv("EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH", str(fixture_dir / "preflight_resolution.json"))
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixture_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixture_dir / "code_change_plan.json"))
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixture_dir / "validation_result.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixture_dir / "rollback_plan.json"))
    monkeypatch.setenv("EA_BRANCH_PUBLICATION_FIXTURE_PATH", str(fixture_dir / "branch_publication.json"))
    monkeypatch.setenv("EA_PULL_REQUEST_FIXTURE_PATH", str(fixture_dir / "pull_request.json"))
    monkeypatch.setenv("EA_JIRA_COMPLETION_FIXTURE_PATH", str(fixture_dir / "jira_completion.json"))
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-460",
        repository_name="payments-service",
        fixture_path=fixture_dir / "pom_before.xml",
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--bootstrap-ticket",
            "SEC-460",
            "--thread-id",
            "sec-460-resume",
        ],
    )
    assert main() == 0
    capsys.readouterr()

    monkeypatch.setattr(
        "sys.argv",
        [
            "execution-accelerator",
            "--resume",
            "sec-460-resume",
        ],
    )
    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "thread_id=sec-460-resume" in captured.out
    assert f"checkpoint_path={tmp_path / 'state' / 'checkpoints.sqlite'}" in captured.out
    assert "workflow_status=completed" in captured.out
    assert "target_count=1" in captured.out
    assert "completed_repos=payments-service" in captured.out
