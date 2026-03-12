from __future__ import annotations

from pathlib import Path
import re


PATH_SEGMENT_PATTERN = re.compile(r"[^a-z0-9]+")


def seed_workspace_pom(workspace_root: Path, fixture_path: Path, *, manifest_path: str = "pom.xml") -> Path:
    """Seed a workspace manifest from a fixture before remediation mutates it."""

    pom_path = workspace_root / manifest_path
    pom_path.parent.mkdir(parents=True, exist_ok=True)
    pom_path.write_text(fixture_path.read_text())
    return pom_path


def seed_bootstrap_workspace_pom(
    workspace_root: Path,
    *,
    ticket_id: str,
    repository_name: str,
    fixture_path: Path,
    manifest_path: str = "pom.xml",
) -> Path:
    """Seed the workspace path that fixture bootstrap runs will resolve for a repo."""

    ticket_dir = workspace_root / _normalize_path_segment(ticket_id)
    repository_dir = ticket_dir / _normalize_path_segment(repository_name)
    return seed_workspace_pom(repository_dir, fixture_path, manifest_path=manifest_path)


def _normalize_path_segment(value: str) -> str:
    slug = PATH_SEGMENT_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or "workspace"
