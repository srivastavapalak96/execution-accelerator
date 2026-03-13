from __future__ import annotations

from pathlib import Path

import pytest

from execution_accelerator.config import MissingCredentialError, load_credentials, probe_credentials
from execution_accelerator.schemas import ExecutionMode


def test_load_credentials_reads_environment_and_resolves_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EA_JIRA_BASE_URL", "https://jira.example.com")
    monkeypatch.setenv("EA_JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_JIRA_TOKEN", "jira-token")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setenv("GITHUB_OWNER", "octo-org")
    monkeypatch.setenv("EA_GITHUB_API_BASE", "https://github.example.com/api/v3")
    monkeypatch.setenv("EA_GIT_USER_NAME", "Execution Bot")
    monkeypatch.setenv("EA_GIT_USER_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_MAVEN_SETTINGS", ".m2/settings.xml")

    credentials = load_credentials(repo_root=tmp_path)

    assert credentials.jira_base_url == "https://jira.example.com"
    assert credentials.jira_email == "bot@example.com"
    assert credentials.jira_token == "jira-token"
    assert credentials.github_token == "github-token"
    assert credentials.github_owner == "octo-org"
    assert credentials.github_api_base == "https://github.example.com/api/v3"
    assert credentials.git_user_name == "Execution Bot"
    assert credentials.git_user_email == "bot@example.com"
    assert credentials.maven_settings == Path(tmp_path / ".m2" / "settings.xml")


def test_probe_credentials_skips_checks_in_fixture_mode(tmp_path: Path) -> None:
    credentials = load_credentials(repo_root=tmp_path)

    report = probe_credentials(credentials, execution_mode=ExecutionMode.FIXTURE)

    assert report.skipped is True
    assert report.jira_ok is False
    assert report.github_ok is False


def test_probe_credentials_requires_live_fields_before_running_probes(tmp_path: Path) -> None:
    credentials = load_credentials(repo_root=tmp_path)

    with pytest.raises(MissingCredentialError) as exc_info:
        probe_credentials(credentials, execution_mode=ExecutionMode.LIVE)

    assert "EA_JIRA_BASE_URL" in str(exc_info.value)
    assert "GITHUB_TOKEN" in str(exc_info.value)


def test_probe_credentials_runs_injected_live_probes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EA_JIRA_BASE_URL", "https://jira.example.com")
    monkeypatch.setenv("EA_JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_JIRA_TOKEN", "jira-token")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setenv("GITHUB_OWNER", "octo-org")
    monkeypatch.setenv("EA_GIT_USER_NAME", "Execution Bot")
    monkeypatch.setenv("EA_GIT_USER_EMAIL", "bot@example.com")
    credentials = load_credentials(repo_root=tmp_path)
    calls: list[str] = []

    report = probe_credentials(
        credentials,
        execution_mode=ExecutionMode.LIVE,
        jira_probe=lambda creds: calls.append(f"jira:{creds.jira_base_url}"),
        github_probe=lambda creds: calls.append(f"github:{creds.github_owner}"),
    )

    assert report.skipped is False
    assert report.jira_ok is True
    assert report.github_ok is True
    assert calls == ["jira:https://jira.example.com", "github:octo-org"]
