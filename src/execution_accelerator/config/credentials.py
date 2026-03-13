from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import os

import httpx

from execution_accelerator.schemas import ExecutionMode


@dataclass(frozen=True)
class Credentials:
    """Credential bundle for live integrations."""

    jira_base_url: str | None
    jira_email: str | None
    jira_token: str | None
    github_token: str | None
    github_owner: str | None
    github_api_base: str
    git_user_name: str | None
    git_user_email: str | None
    maven_settings: Path | None


@dataclass(frozen=True)
class CredentialProbeReport:
    """Summary of credential probe execution."""

    skipped: bool
    jira_ok: bool
    github_ok: bool


class MissingCredentialError(ValueError):
    """Raised when live mode starts without the required credentials."""


def load_credentials(*, repo_root: Path | None = None) -> Credentials:
    """Load live-mode credentials and related identity settings from the environment."""

    resolved_root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    maven_settings_value = os.getenv("EA_MAVEN_SETTINGS")

    return Credentials(
        jira_base_url=os.getenv("EA_JIRA_BASE_URL"),
        jira_email=os.getenv("EA_JIRA_EMAIL"),
        jira_token=os.getenv("EA_JIRA_TOKEN"),
        github_token=os.getenv("GITHUB_TOKEN"),
        github_owner=os.getenv("GITHUB_OWNER") or os.getenv("EA_GITHUB_OWNER"),
        github_api_base=os.getenv("EA_GITHUB_API_BASE", "https://api.github.com"),
        git_user_name=os.getenv("EA_GIT_USER_NAME"),
        git_user_email=os.getenv("EA_GIT_USER_EMAIL"),
        maven_settings=(
            _resolve_path(maven_settings_value, repo_root=resolved_root)
            if maven_settings_value
            else None
        ),
    )


def probe_credentials(
    credentials: Credentials,
    *,
    execution_mode: ExecutionMode,
    jira_probe: Callable[[Credentials], None] | None = None,
    github_probe: Callable[[Credentials], None] | None = None,
) -> CredentialProbeReport:
    """Validate and probe credentials, skipping checks in fixture mode."""

    if execution_mode == ExecutionMode.FIXTURE:
        return CredentialProbeReport(skipped=True, jira_ok=False, github_ok=False)

    _require_live_credentials(credentials)

    resolved_jira_probe = jira_probe or _default_jira_probe
    resolved_github_probe = github_probe or _default_github_probe
    resolved_jira_probe(credentials)
    resolved_github_probe(credentials)
    return CredentialProbeReport(skipped=False, jira_ok=True, github_ok=True)


def _default_jira_probe(credentials: Credentials) -> None:
    if not credentials.jira_base_url or not credentials.jira_email or not credentials.jira_token:
        raise MissingCredentialError("missing live credentials: EA_JIRA_BASE_URL, EA_JIRA_EMAIL, EA_JIRA_TOKEN")
    response = httpx.get(
        f"{credentials.jira_base_url.rstrip('/')}/rest/api/3/myself",
        auth=(credentials.jira_email, credentials.jira_token),
        timeout=15.0,
    )
    response.raise_for_status()


def _default_github_probe(credentials: Credentials) -> None:
    if not credentials.github_token:
        raise MissingCredentialError("missing live credentials: GITHUB_TOKEN")
    response = httpx.get(
        f"{credentials.github_api_base.rstrip('/')}/user",
        headers={
            "Authorization": f"Bearer {credentials.github_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15.0,
    )
    response.raise_for_status()


def _require_live_credentials(credentials: Credentials) -> None:
    missing: list[str] = []
    if not credentials.jira_base_url:
        missing.append("EA_JIRA_BASE_URL")
    if not credentials.jira_email:
        missing.append("EA_JIRA_EMAIL")
    if not credentials.jira_token:
        missing.append("EA_JIRA_TOKEN")
    if not credentials.github_token:
        missing.append("GITHUB_TOKEN")
    if not credentials.github_owner:
        missing.append("GITHUB_OWNER")
    if not credentials.git_user_name:
        missing.append("EA_GIT_USER_NAME")
    if not credentials.git_user_email:
        missing.append("EA_GIT_USER_EMAIL")
    if missing:
        raise MissingCredentialError(f"missing live credentials: {', '.join(missing)}")


def _resolve_path(value: str, *, repo_root: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()
