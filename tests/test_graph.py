from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from execution_accelerator.config import load_runtime_config
from execution_accelerator.graph import bootstrap_ticket_run, load_remediation_state
from execution_accelerator.schemas import WorkflowStatus


def _configure_runtime(monkeypatch, tmp_path, *, transitive: bool = False, complex_refactor: bool = False) -> None:
    fixtures_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(fixtures_dir / "jira_issue.json"))
    monkeypatch.setenv(
        "EA_REPOSITORY_INVENTORY_FIXTURE_PATH",
        str(fixtures_dir / "repository_inventory.json"),
    )
    monkeypatch.setenv(
        "EA_ADVISORY_FIXTURE_PATH",
        str(
            fixtures_dir
            / ("advisory_verification_complex.json" if complex_refactor else "advisory_verification.json")
        ),
    )
    monkeypatch.setenv(
        "EA_MAVEN_VERIFICATION_FIXTURE_PATH",
        str(
            fixtures_dir
            / (
                "maven_verification_complex.json"
                if complex_refactor
                else ("maven_verification_transitive.json" if transitive else "maven_verification.json")
            )
        ),
    )
    monkeypatch.setenv(
        "EA_POM_FIXTURE_BEFORE_PATH",
        str(fixtures_dir / ("pom_transitive_before.xml" if transitive else "pom_before.xml")),
    )
    monkeypatch.setenv(
        "EA_POM_FIXTURE_AFTER_PATH",
        str(fixtures_dir / ("pom_transitive_after.xml" if transitive else "pom_after.xml")),
    )
    monkeypatch.setenv(
        "EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH",
        str(
            fixtures_dir
            / ("preflight_resolution_transitive.json" if transitive else "preflight_resolution.json")
        ),
    )
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixtures_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixtures_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixtures_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixtures_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixtures_dir / "code_change_plan.json"))
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixtures_dir / "validation_result.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixtures_dir / "rollback_plan.json"))
    monkeypatch.setenv("EA_BRANCH_PUBLICATION_FIXTURE_PATH", str(fixtures_dir / "branch_publication.json"))
    monkeypatch.setenv("EA_PULL_REQUEST_FIXTURE_PATH", str(fixtures_dir / "pull_request.json"))
    monkeypatch.setenv("EA_JIRA_COMPLETION_FIXTURE_PATH", str(fixtures_dir / "jira_completion.json"))


def test_bootstrap_ticket_run_persists_checkpointed_state(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-42",
        runtime_config=config,
        thread_id="sec-42-thread",
    )
    loaded_state = load_remediation_state(
        runtime_config=config,
        thread_id="sec-42-thread",
    )

    assert result.thread_id == "sec-42-thread"
    assert result.checkpoint_path == config.checkpoints_path
    assert result.state.workflow_status == WorkflowStatus.COMPLETED
    assert result.state.vulnerability_details is not None
    assert result.state.vulnerability_details.package_name == "org.example:legacy-json"
    assert result.state.advisory_verification is not None
    assert result.state.advisory_verification.recommended_fix_version == "1.2.4"
    assert result.state.maven_verification is not None
    assert result.state.maven_verification.target_version == "1.2.4"
    assert result.state.route_decision is not None
    assert result.state.route_decision.strategy == "simple_update"
    assert result.state.remediation_plan is not None
    assert result.state.remediation_plan.strategy == "simple_update"
    assert result.state.pom_mutation_plan is not None
    assert result.state.pom_mutation_plan.changes[0].target_version == "1.2.4"
    assert result.state.preflight_resolution is not None
    assert result.state.preflight_resolution.resolved_version == "1.2.4"
    assert result.state.current_working_repo == "payments-service"
    assert len(result.state.modified_files) == 1
    assert result.state.pending_repos == []
    assert result.state.completed_repos == ["payments-service"]
    assert result.state.repo_map["payments-service"].owner == "payments-platform"
    assert config.checkpoints_path.exists()
    assert loaded_state.initial_ticket_id == "SEC-42"
    assert loaded_state.workflow_status == WorkflowStatus.COMPLETED
    assert len(loaded_state.audit_events) == 10
    assert Path(loaded_state.repo_map["payments-service"].local_path).is_dir()
    assert (
        Path(loaded_state.repo_map["payments-service"].local_path) / ".execution-accelerator-repo.json"
    ).exists()
    assert Path(loaded_state.modified_files[0]).exists()
    assert result.state.validation_results[-1].status == "passed"
    assert result.state.branch_publication is not None
    assert result.state.pull_request_summary is not None
    assert result.state.jira_completion is not None


def test_bootstrap_ticket_run_persists_transitive_override_state(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path, transitive=True)
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-420",
        runtime_config=config,
        thread_id="sec-420-thread",
    )
    loaded_state = load_remediation_state(
        runtime_config=config,
        thread_id="sec-420-thread",
    )

    assert result.thread_id == "sec-420-thread"
    assert result.state.route_decision is not None
    assert result.state.route_decision.strategy == "transitive_override"
    assert result.state.remediation_plan is not None
    assert result.state.remediation_plan.strategy == "transitive_override"
    assert result.state.pom_mutation_plan is not None
    assert result.state.pom_mutation_plan.changes[0].target_section == "dependency_management"
    assert result.state.preflight_resolution is not None
    assert result.state.preflight_resolution.dependency_kind == "transitive"
    assert len(result.state.audit_events) == 10
    mutated_root = ET.fromstring(Path(result.state.modified_files[0]).read_text())
    version = mutated_root.find(
        ".//{http://maven.apache.org/POM/4.0.0}dependencyManagement/"
        "{http://maven.apache.org/POM/4.0.0}dependencies/"
        "{http://maven.apache.org/POM/4.0.0}dependency/"
        "{http://maven.apache.org/POM/4.0.0}version"
    )
    assert version is not None
    assert version.text == "1.2.4"
    assert loaded_state.route_decision is not None
    assert loaded_state.route_decision.strategy == "transitive_override"
    assert loaded_state.validation_results[-1].status == "passed"
    assert loaded_state.workflow_status == WorkflowStatus.COMPLETED
    assert loaded_state.completed_repos == ["payments-service"]


def test_bootstrap_ticket_run_persists_complex_refactor_state(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path, complex_refactor=True)
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-777",
        runtime_config=config,
        thread_id="sec-777-thread",
    )
    loaded_state = load_remediation_state(
        runtime_config=config,
        thread_id="sec-777-thread",
    )

    assert result.state.route_decision is not None
    assert result.state.route_decision.strategy == "complex_refactor"
    assert result.state.complex_remediation_plan is not None
    assert len(result.state.complex_remediation_plan.artifact_candidates) == 2
    assert result.state.compatibility_diff is not None
    assert result.state.compatibility_diff.risk == "high"
    assert len(result.state.decompiled_artifacts) == 2
    assert len(result.state.symbol_mappings) == 2
    assert result.state.code_change_plan is not None
    assert len(result.state.code_change_plan.target_files) == 2
    assert result.state.preflight_resolution is None
    assert result.state.pom_mutation_plan is None
    assert len(result.state.validation_results) == 1
    assert result.state.validation_results[-1].status == "passed"
    assert result.state.workflow_status == WorkflowStatus.COMPLETED
    assert result.state.completed_repos == ["payments-service"]
    assert result.state.pending_repos == []
    assert len(result.state.audit_events) == 10
    assert loaded_state.complex_remediation_plan is not None
    assert loaded_state.complex_remediation_plan.compatibility_diff.target_version == "2.0.0"
    assert loaded_state.code_change_plan is not None
    assert loaded_state.code_change_plan.target_files[0].file_path.endswith("LegacyJsonAdapter.java")
    assert loaded_state.workflow_status == WorkflowStatus.COMPLETED
    assert loaded_state.pull_request_summary is not None
    assert loaded_state.jira_completion is not None


def test_bootstrap_ticket_run_records_failure_and_rollback_state(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "EA_VALIDATION_RESULT_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "validation_result_failure.json"),
    )
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-500",
        runtime_config=config,
        thread_id="sec-500-thread",
    )

    assert result.state.workflow_status == WorkflowStatus.FAILED
    assert result.state.validation_results[-1].status == "failed"
    assert result.state.rollback_plan is not None
    assert result.state.rollback_plan.status == "applied"
    assert result.state.retry_count == 1
    assert result.state.errors[-1].code == "validation_failed"
    assert len(result.state.audit_events) == 10
