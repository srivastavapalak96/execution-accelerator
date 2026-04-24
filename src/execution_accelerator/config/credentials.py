from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import os

import httpx
import yaml

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
    gpg_signing_key: str | None
    maven_settings: Path | None
    jira_probe_ticket: str | None
    github_probe_repository: str | None
    skip_write_scope_probe: bool


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
        gpg_signing_key=os.getenv("EA_GPG_SIGNING_KEY"),
        maven_settings=(
            _resolve_path(maven_settings_value, repo_root=resolved_root)
            if maven_settings_value
            else None
        ),
        jira_probe_ticket=os.getenv("EA_JIRA_PROBE_TICKET"),
        github_probe_repository=(
            os.getenv("EA_GITHUB_PROBE_REPOSITORY") or _load_default_github_probe_repository(repo_root=resolved_root)
        ),
        skip_write_scope_probe=_read_bool_env("EA_SKIP_WRITE_SCOPE_PROBE"),
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
    if credentials.skip_write_scope_probe:
        return
    if not credentials.jira_probe_ticket:
        raise MissingCredentialError(
            "EA_JIRA_PROBE_TICKET is required for live Jira write-scope probing."
        )
    transitions_url = (
        f"{credentials.jira_base_url.rstrip('/')}/rest/api/3/issue/"
        f"{credentials.jira_probe_ticket}/transitions"
    )
    try:
        transitions_response = httpx.get(
            transitions_url,
            auth=(credentials.jira_email, credentials.jira_token),
            timeout=15.0,
        )
        transitions_response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 403:
            raise MissingCredentialError(
                "jira token lacks transitions scope: GET /transitions returned 403."
            ) from exc
        raise MissingCredentialError(
            f"jira write-scope probe failed for {credentials.jira_probe_ticket}: "
            f"GET /transitions returned {status_code}."
        ) from exc


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
    _validate_github_scopes(response.headers.get("x-oauth-scopes"))
    if credentials.skip_write_scope_probe:
        return
    if not credentials.github_owner or not credentials.github_probe_repository:
        raise MissingCredentialError(
            "GitHub write-scope probe requires a repository target; set EA_GITHUB_PROBE_REPOSITORY "
            "or configure config/repositories.yaml."
        )
    repo_response = httpx.get(
        (
            f"{credentials.github_api_base.rstrip('/')}/repos/"
            f"{credentials.github_owner}/{credentials.github_probe_repository}"
        ),
        headers={
            "Authorization": f"Bearer {credentials.github_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15.0,
    )
    repo_response.raise_for_status()
    payload = repo_response.json()
    if not isinstance(payload, dict):
        raise MissingCredentialError("GitHub repository probe returned an unexpected payload.")
    permissions = payload.get("permissions")
    if isinstance(permissions, dict):
        push_permission = permissions.get("push")
        if push_permission is False:
            raise MissingCredentialError(
                "github token lacks push permission for the configured probe repository."
            )


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


def _load_default_github_probe_repository(*, repo_root: Path) -> str | None:
    config_path = repo_root / "config" / "repositories.yaml"
    if not config_path.exists():
        return None
    loaded = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(loaded, dict):
        return None
    repositories = loaded.get("repositories")
    if not isinstance(repositories, list) or not repositories:
        return None
    first_repository = repositories[0]
    if not isinstance(first_repository, dict):
        return None
    repository_name = first_repository.get("name")
    return repository_name if isinstance(repository_name, str) and repository_name.strip() else None


def _read_bool_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _validate_github_scopes(scopes_header: str | None) -> None:
    if not scopes_header:
        return
    scopes = {scope.strip().lower() for scope in scopes_header.split(",") if scope.strip()}
    if "repo" in scopes:
        return
    if {"contents:write", "pull_requests:write"}.issubset(scopes):
        return
    raise MissingCredentialError(
        "github token is missing required push/PR scopes; need classic 'repo' or "
        "fine-grained 'contents:write' + 'pull_requests:write'."
    )
