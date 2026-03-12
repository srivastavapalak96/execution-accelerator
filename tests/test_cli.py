from __future__ import annotations

from pathlib import Path

from execution_accelerator.cli.main import main


def test_main_prints_version(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["execution-accelerator", "--version"])

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "0.1.0"


def test_main_prints_config(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr("sys.argv", ["execution-accelerator", "--show-config"])
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
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

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "repo_root=" in captured.out
    assert f"data_dir={tmp_path / 'data'}" in captured.out
    assert f"workspace_dir={tmp_path / 'workspace'}" in captured.out
    assert f"logs_dir={tmp_path / 'logs'}" in captured.out
    assert f"checkpoints_path={tmp_path / 'state' / 'checkpoints.sqlite'}" in captured.out
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

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "thread_id=sec-401-dev" in captured.out
    assert f"checkpoint_path={tmp_path / 'state' / 'checkpoints.sqlite'}" in captured.out
    assert "workflow_status=planning_ready" in captured.out
    assert "audit_event_count=8" in captured.out
    assert "package_name=org.example:legacy-json" in captured.out
    assert "severity=high" in captured.out
    assert "recommended_fix_version=1.2.4" in captured.out
    assert "dependency_kind=direct" in captured.out
    assert "pending_repos=payments-service" in captured.out
    assert "route_strategy=simple_update" in captured.out
    assert "route_confidence=0.93" in captured.out
    assert "plan_strategy=simple_update" in captured.out
    assert "pom_change_kind=direct_version_bump" in captured.out
    assert "pom_change_target_section=project_dependencies" in captured.out
    assert "current_working_repo=payments-service" in captured.out
    assert "modified_file_count=1" in captured.out
    assert f"modified_file={tmp_path / 'workspace' / 'sec-401' / 'payments-service' / 'pom.xml'}" in captured.out
    assert "preflight_status=passed" in captured.out
    assert "preflight_dependency_kind=direct" in captured.out
    assert "preflight_resolved_version=1.2.4" in captured.out


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
    assert "workflow_status=planning_ready" in captured.out
    assert "pending_repos=payments-service" in captured.out
    assert "completed_repos=" in captured.out
    assert "audit_event_count=8" in captured.out
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

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "thread_id=sec-799-complex" in captured.out
    assert "route_strategy=complex_refactor" in captured.out
    assert "route_confidence=0.78" in captured.out
    assert "plan_strategy=complex_refactor" in captured.out
    assert "complex_candidate_count=2" in captured.out
    assert "complex_breaking_change_count=2" in captured.out
