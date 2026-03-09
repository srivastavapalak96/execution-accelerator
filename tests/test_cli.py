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
    monkeypatch.setenv("EA_ADVISORY_FIXTURE_PATH", str(fixture_dir / "advisory_verification.json"))
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
