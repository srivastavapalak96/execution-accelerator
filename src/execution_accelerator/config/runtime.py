"""Runtime configuration primitives for local development."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class RuntimeConfig:
    """Resolved filesystem and environment settings for local execution."""

    repo_root: Path
    data_dir: Path
    workspace_dir: Path
    logs_dir: Path
    jira_base_url: str | None
    jira_project_key: str | None
    github_owner: str | None


def load_runtime_config(repo_root: Path | None = None) -> RuntimeConfig:
    """Load runtime settings from the environment and sensible local defaults."""

    resolved_root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    data_dir = Path(os.getenv("EA_DATA_DIR", resolved_root / ".local" / "data"))
    workspace_dir = Path(os.getenv("EA_WORKSPACE_DIR", resolved_root / ".local" / "workspace"))
    logs_dir = Path(os.getenv("EA_LOGS_DIR", resolved_root / ".local" / "logs"))

    return RuntimeConfig(
        repo_root=resolved_root,
        data_dir=data_dir,
        workspace_dir=workspace_dir,
        logs_dir=logs_dir,
        jira_base_url=os.getenv("EA_JIRA_BASE_URL"),
        jira_project_key=os.getenv("EA_JIRA_PROJECT_KEY"),
        github_owner=os.getenv("EA_GITHUB_OWNER"),
    )
