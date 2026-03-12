from __future__ import annotations

from pathlib import Path


def seed_workspace_pom(workspace_root: Path, fixture_path: Path, *, manifest_path: str = "pom.xml") -> Path:
    """Seed a workspace manifest from a fixture before remediation mutates it."""

    pom_path = workspace_root / manifest_path
    pom_path.parent.mkdir(parents=True, exist_ok=True)
    pom_path.write_text(fixture_path.read_text())
    return pom_path
