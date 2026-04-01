from __future__ import annotations

from pathlib import Path

import httpx
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
    monkeypatch.setenv("EA_JIRA_PROBE_TICKET", "SEC-1")
    monkeypatch.setenv("EA_SKIP_WRITE_SCOPE_PROBE", "1")

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
    assert credentials.jira_probe_ticket == "SEC-1"
    assert credentials.skip_write_scope_probe is True


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


def test_probe_credentials_accepts_github_repo_scope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EA_JIRA_BASE_URL", "https://jira.example.com")
    monkeypatch.setenv("EA_JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_JIRA_TOKEN", "jira-token")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setenv("GITHUB_OWNER", "octo-org")
    monkeypatch.setenv("EA_GIT_USER_NAME", "Execution Bot")
    monkeypatch.setenv("EA_GIT_USER_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_SKIP_WRITE_SCOPE_PROBE", "1")
    credentials = load_credentials(repo_root=tmp_path)

    def fake_get(url: str, **_: object) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-oauth-scopes": "repo, workflow"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("execution_accelerator.config.credentials.httpx.get", fake_get)

    report = probe_credentials(
        credentials,
        execution_mode=ExecutionMode.LIVE,
        jira_probe=lambda _: None,
    )

    assert report.github_ok is True


def test_probe_credentials_rejects_github_tokens_without_push_or_pr_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EA_JIRA_BASE_URL", "https://jira.example.com")
    monkeypatch.setenv("EA_JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_JIRA_TOKEN", "jira-token")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setenv("GITHUB_OWNER", "octo-org")
    monkeypatch.setenv("EA_GIT_USER_NAME", "Execution Bot")
    monkeypatch.setenv("EA_GIT_USER_EMAIL", "bot@example.com")
    credentials = load_credentials(repo_root=tmp_path)

    def fake_get(url: str, **_: object) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-oauth-scopes": "read:org, gist"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("execution_accelerator.config.credentials.httpx.get", fake_get)

    with pytest.raises(MissingCredentialError, match="push/PR scopes"):
        probe_credentials(
            credentials,
            execution_mode=ExecutionMode.LIVE,
            jira_probe=lambda _: None,
        )


def test_probe_credentials_requires_jira_probe_ticket_for_default_write_scope_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EA_JIRA_BASE_URL", "https://jira.example.com")
    monkeypatch.setenv("EA_JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_JIRA_TOKEN", "jira-token")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setenv("GITHUB_OWNER", "octo-org")
    monkeypatch.setenv("EA_GIT_USER_NAME", "Execution Bot")
    monkeypatch.setenv("EA_GIT_USER_EMAIL", "bot@example.com")
    credentials = load_credentials(repo_root=tmp_path)

    def fake_get(url: str, **_: object) -> httpx.Response:
        return httpx.Response(200, request=httpx.Request("GET", url))

    monkeypatch.setattr("execution_accelerator.config.credentials.httpx.get", fake_get)

    with pytest.raises(MissingCredentialError, match="EA_JIRA_PROBE_TICKET"):
        probe_credentials(
            credentials,
            execution_mode=ExecutionMode.LIVE,
            github_probe=lambda _: None,
        )


def test_probe_credentials_checks_jira_transitions_and_github_push_permission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EA_JIRA_BASE_URL", "https://jira.example.com")
    monkeypatch.setenv("EA_JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_JIRA_TOKEN", "jira-token")
    monkeypatch.setenv("EA_JIRA_PROBE_TICKET", "SEC-1")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setenv("GITHUB_OWNER", "octo-org")
    monkeypatch.setenv("EA_GIT_USER_NAME", "Execution Bot")
    monkeypatch.setenv("EA_GIT_USER_EMAIL", "bot@example.com")
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "repositories.yaml").write_text("repositories:\n  - name: payments-service\n")
    credentials = load_credentials(repo_root=tmp_path)
    requested_urls: list[str] = []

    def fake_get(url: str, **_: object) -> httpx.Response:
        requested_urls.append(url)
        if url.endswith("/rest/api/3/myself"):
            return httpx.Response(200, request=httpx.Request("GET", url))
        if url.endswith("/rest/api/3/issue/SEC-1/transitions"):
            return httpx.Response(200, request=httpx.Request("GET", url))
        if url.endswith("/user"):
            return httpx.Response(
                200,
                headers={"x-oauth-scopes": "repo, workflow"},
                request=httpx.Request("GET", url),
            )
        if url.endswith("/repos/octo-org/payments-service"):
            return httpx.Response(
                200,
                json={"permissions": {"push": True}},
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("execution_accelerator.config.credentials.httpx.get", fake_get)

    report = probe_credentials(credentials, execution_mode=ExecutionMode.LIVE)

    assert report.jira_ok is True
    assert report.github_ok is True
    assert requested_urls == [
        "https://jira.example.com/rest/api/3/myself",
        "https://jira.example.com/rest/api/3/issue/SEC-1/transitions",
        "https://api.github.com/user",
        "https://api.github.com/repos/octo-org/payments-service",
    ]


def test_probe_credentials_rejects_github_probe_repo_without_push_permission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EA_JIRA_BASE_URL", "https://jira.example.com")
    monkeypatch.setenv("EA_JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_JIRA_TOKEN", "jira-token")
    monkeypatch.setenv("EA_JIRA_PROBE_TICKET", "SEC-1")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setenv("GITHUB_OWNER", "octo-org")
    monkeypatch.setenv("EA_GIT_USER_NAME", "Execution Bot")
    monkeypatch.setenv("EA_GIT_USER_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_GITHUB_PROBE_REPOSITORY", "payments-service")
    credentials = load_credentials(repo_root=tmp_path)

    def fake_get(url: str, **_: object) -> httpx.Response:
        if url.endswith("/user"):
            return httpx.Response(
                200,
                headers={"x-oauth-scopes": "repo, workflow"},
                request=httpx.Request("GET", url),
            )
        if url.endswith("/repos/octo-org/payments-service"):
            return httpx.Response(
                200,
                json={"permissions": {"push": False}},
                request=httpx.Request("GET", url),
            )
        return httpx.Response(200, request=httpx.Request("GET", url))

    monkeypatch.setattr("execution_accelerator.config.credentials.httpx.get", fake_get)

    with pytest.raises(MissingCredentialError, match="push permission"):
        probe_credentials(
            credentials,
            execution_mode=ExecutionMode.LIVE,
            jira_probe=lambda _: None,
        )
