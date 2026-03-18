from __future__ import annotations

from pathlib import Path

from execution_accelerator.config import load_runtime_config
from execution_accelerator.schemas import ExecutionMode


def test_load_runtime_config_uses_repo_relative_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("EA_DATA_DIR", raising=False)
    monkeypatch.delenv("EA_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("EA_LOGS_DIR", raising=False)
    monkeypatch.delenv("EA_CHECKPOINTS_PATH", raising=False)
    monkeypatch.delenv("EA_DRY_RUN", raising=False)
    monkeypatch.delenv("EA_KEEP_WORKSPACE", raising=False)

    config = load_runtime_config(repo_root=tmp_path)

    assert config.repo_root == tmp_path
    assert config.execution_mode == ExecutionMode.FIXTURE
    assert config.dry_run is False
    assert config.keep_workspace is False
    assert config.data_dir == Path(tmp_path / ".local" / "data")
    assert config.workspace_dir == Path(tmp_path / ".local" / "workspace")
    assert config.logs_dir == Path(tmp_path / ".local" / "logs")
    assert config.checkpoints_path == Path(tmp_path / ".local" / "data" / "checkpoints.sqlite")


def test_load_runtime_config_reads_optional_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EA_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EA_JIRA_PROJECT_KEY", "SEC")
    monkeypatch.setenv("EA_JIRA_DONE_TRANSITION_ID", "31")
    monkeypatch.setenv("EA_JIRA_DONE_STATUS_NAME", "Done")
    monkeypatch.setenv("EA_GITHUB_OWNER", "srivastavapalak96")
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "checkpoints.sqlite"))

    config = load_runtime_config(repo_root=tmp_path)

    assert config.jira_base_url == "https://example.atlassian.net"
    assert config.jira_project_key == "SEC"
    assert config.jira_done_transition_id == "31"
    assert config.jira_done_status_name == "Done"
    assert config.github_owner == "srivastavapalak96"
    assert config.checkpoints_path == Path(tmp_path / "checkpoints.sqlite")


def test_load_runtime_config_reads_execution_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EA_MODE", "live")

    config = load_runtime_config(repo_root=tmp_path)

    assert config.execution_mode == ExecutionMode.LIVE


def test_load_runtime_config_reads_dry_run_and_keep_workspace_flags(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EA_DRY_RUN", "1")
    monkeypatch.setenv("EA_KEEP_WORKSPACE", "1")

    config = load_runtime_config(repo_root=tmp_path)

    assert config.dry_run is True
    assert config.keep_workspace is True


def test_load_runtime_config_resolves_relative_environment_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EA_DATA_DIR", ".runtime/data")
    monkeypatch.setenv("EA_WORKSPACE_DIR", ".runtime/workspace")
    monkeypatch.setenv("EA_LOGS_DIR", ".runtime/logs")
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", ".runtime/state/checkpoints.sqlite")

    config = load_runtime_config(repo_root=tmp_path)

    assert config.data_dir == Path(tmp_path / ".runtime" / "data")
    assert config.workspace_dir == Path(tmp_path / ".runtime" / "workspace")
    assert config.logs_dir == Path(tmp_path / ".runtime" / "logs")
    assert config.checkpoints_path == Path(tmp_path / ".runtime" / "state" / "checkpoints.sqlite")
