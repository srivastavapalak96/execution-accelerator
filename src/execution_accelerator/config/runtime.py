"""Runtime configuration primitives for local development."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


def _resolve_path_setting(value: str | Path, *, repo_root: Path) -> Path:
    """Resolve path settings relative to the repository root when needed."""

    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


@dataclass(frozen=True)
class RuntimeConfig:
    """Resolved filesystem and environment settings for local execution."""

    repo_root: Path
    data_dir: Path
    workspace_dir: Path
    logs_dir: Path
    checkpoints_path: Path
    jira_base_url: str | None
    jira_project_key: str | None
    jira_fixture_path: Path | None
    repository_inventory_fixture_path: Path | None
    github_owner: str | None


def load_runtime_config(repo_root: Path | None = None) -> RuntimeConfig:
    """Load runtime settings from the environment and sensible local defaults."""

    resolved_root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    data_dir = _resolve_path_setting(
        os.getenv("EA_DATA_DIR", resolved_root / ".local" / "data"),
        repo_root=resolved_root,
    )
    workspace_dir = _resolve_path_setting(
        os.getenv("EA_WORKSPACE_DIR", resolved_root / ".local" / "workspace"),
        repo_root=resolved_root,
    )
    logs_dir = _resolve_path_setting(
        os.getenv("EA_LOGS_DIR", resolved_root / ".local" / "logs"),
        repo_root=resolved_root,
    )
    checkpoints_path = _resolve_path_setting(
        os.getenv("EA_CHECKPOINTS_PATH", data_dir / "checkpoints.sqlite"),
        repo_root=resolved_root,
    )
    jira_fixture_path_value = os.getenv(
        "EA_JIRA_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "jira_issue.json"),
    )
    repository_inventory_fixture_path_value = os.getenv(
        "EA_REPOSITORY_INVENTORY_FIXTURE_PATH",
        str(resolved_root / "tests" / "fixtures" / "repository_inventory.json"),
    )

    return RuntimeConfig(
        repo_root=resolved_root,
        data_dir=data_dir,
        workspace_dir=workspace_dir,
        logs_dir=logs_dir,
        checkpoints_path=checkpoints_path,
        jira_base_url=os.getenv("EA_JIRA_BASE_URL"),
        jira_project_key=os.getenv("EA_JIRA_PROJECT_KEY"),
        jira_fixture_path=(
            _resolve_path_setting(jira_fixture_path_value, repo_root=resolved_root)
            if jira_fixture_path_value
            else None
        ),
        repository_inventory_fixture_path=(
            _resolve_path_setting(repository_inventory_fixture_path_value, repo_root=resolved_root)
            if repository_inventory_fixture_path_value
            else None
        ),
        github_owner=os.getenv("EA_GITHUB_OWNER"),
    )
