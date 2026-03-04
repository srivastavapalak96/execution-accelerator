from __future__ import annotations

from pathlib import Path

from execution_accelerator.config import load_runtime_config


def test_load_runtime_config_uses_repo_relative_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("EA_DATA_DIR", raising=False)
    monkeypatch.delenv("EA_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("EA_LOGS_DIR", raising=False)

    config = load_runtime_config(repo_root=tmp_path)

    assert config.repo_root == tmp_path
    assert config.data_dir == Path(tmp_path / ".local" / "data")
    assert config.workspace_dir == Path(tmp_path / ".local" / "workspace")
    assert config.logs_dir == Path(tmp_path / ".local" / "logs")


def test_load_runtime_config_reads_optional_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EA_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EA_JIRA_PROJECT_KEY", "SEC")
    monkeypatch.setenv("EA_GITHUB_OWNER", "srivastavapalak96")

    config = load_runtime_config(repo_root=tmp_path)

    assert config.jira_base_url == "https://example.atlassian.net"
    assert config.jira_project_key == "SEC"
    assert config.github_owner == "srivastavapalak96"
