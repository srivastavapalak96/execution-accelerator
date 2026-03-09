from __future__ import annotations

from pathlib import Path

from execution_accelerator.config import load_runtime_config
from execution_accelerator.graph import bootstrap_ticket_run, load_remediation_state
from execution_accelerator.schemas import WorkflowStatus


def test_bootstrap_ticket_run_persists_checkpointed_state(tmp_path, monkeypatch) -> None:
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
    monkeypatch.setenv("EA_ADVISORY_FIXTURE_PATH", str(fixtures_dir / "advisory_verification.json"))
    monkeypatch.setenv(
        "EA_MAVEN_VERIFICATION_FIXTURE_PATH",
        str(fixtures_dir / "maven_verification.json"),
    )
    monkeypatch.setenv("EA_POM_FIXTURE_BEFORE_PATH", str(fixtures_dir / "pom_before.xml"))
    monkeypatch.setenv("EA_POM_FIXTURE_AFTER_PATH", str(fixtures_dir / "pom_after.xml"))
    monkeypatch.setenv(
        "EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH",
        str(fixtures_dir / "preflight_resolution.json"),
    )
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
    assert result.state.workflow_status == WorkflowStatus.PLANNING_READY
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
    assert result.state.pending_repos == ["payments-service"]
    assert result.state.repo_map["payments-service"].owner == "payments-platform"
    assert config.checkpoints_path.exists()
    assert loaded_state.initial_ticket_id == "SEC-42"
    assert loaded_state.workflow_status == WorkflowStatus.PLANNING_READY
    assert len(loaded_state.audit_events) == 8
    assert Path(loaded_state.repo_map["payments-service"].local_path).is_dir()
    assert (
        Path(loaded_state.repo_map["payments-service"].local_path) / ".execution-accelerator-repo.json"
    ).exists()
    assert Path(loaded_state.modified_files[0]).exists()
