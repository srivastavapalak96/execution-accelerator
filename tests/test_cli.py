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

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "thread_id=sec-401-dev" in captured.out
    assert f"checkpoint_path={tmp_path / 'state' / 'checkpoints.sqlite'}" in captured.out
    assert "workflow_status=planning_ready" in captured.out
    assert "audit_event_count=4" in captured.out
    assert "package_name=org.example:legacy-json" in captured.out
    assert "severity=high" in captured.out
    assert "pending_repos=payments-service" in captured.out
    assert "plan_strategy=unknown" in captured.out
