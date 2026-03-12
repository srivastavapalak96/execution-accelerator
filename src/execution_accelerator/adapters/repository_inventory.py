"""Repository inventory and local intake adapter for Day 3 development."""

from __future__ import annotations

import json
from pathlib import Path
import re

from execution_accelerator.adapters._mode import require_fixture_mode
from execution_accelerator.config import RuntimeConfig
from execution_accelerator.schemas import (
    ExecutionMode,
    RepositoryInventoryPayload,
    RepositoryInventoryRecord,
    VulnerabilityDetails,
)
from execution_accelerator.state import RepositoryWorkspace


REPOSITORY_DIR_PATTERN = re.compile(r"[^a-z0-9]+")


class RepositoryInventoryAdapterError(RuntimeError):
    """Base error for repository inventory and intake failures."""


class RepositoryInventoryConfigurationError(RepositoryInventoryAdapterError):
    """Raised when local repository inventory configuration is missing."""


class RepositoryInventoryLookupError(RepositoryInventoryAdapterError):
    """Raised when an affected repository cannot be resolved from inventory."""


class RepositoryInventoryAdapter:
    """Load fixture-backed inventory and prepare local repository workspaces."""

    def __init__(
        self,
        *,
        fixture_path: Path | None = None,
        workspace_root: Path | None = None,
        mode: ExecutionMode = ExecutionMode.FIXTURE,
    ) -> None:
        self.fixture_path = fixture_path
        self.workspace_root = workspace_root
        self.mode = mode

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "RepositoryInventoryAdapter":
        """Create an adapter from runtime configuration."""

        return cls(
            fixture_path=config.repository_inventory_fixture_path,
            workspace_root=config.workspace_dir,
            mode=config.execution_mode,
        )

    def load_inventory(self, *, fixture_path: Path | None = None) -> RepositoryInventoryPayload:
        """Load the repository inventory fixture."""

        require_fixture_mode(self.mode, capability="Repository inventory live resolution")
        resolved_fixture_path = fixture_path or self.fixture_path
        if resolved_fixture_path is None:
            raise RepositoryInventoryConfigurationError(
                "Repository inventory fixture path is not configured. "
                "Set EA_REPOSITORY_INVENTORY_FIXTURE_PATH for local Day 3 intake."
            )
        return RepositoryInventoryPayload.model_validate(json.loads(resolved_fixture_path.read_text()))

    def resolve_repositories(
        self,
        vulnerability_details: VulnerabilityDetails,
        *,
        fixture_path: Path | None = None,
    ) -> list[RepositoryInventoryRecord]:
        """Resolve affected repositories from the loaded inventory."""

        inventory = self.load_inventory(fixture_path=fixture_path)
        records_by_name = {record.name: record for record in inventory.repositories}
        resolved_records: list[RepositoryInventoryRecord] = []

        for affected_repo in vulnerability_details.affected_repositories:
            record = records_by_name.get(affected_repo.name)
            if record is None:
                raise RepositoryInventoryLookupError(
                    f"Repository '{affected_repo.name}' is not present in the configured inventory fixture."
                )
            resolved_records.append(record)

        return resolved_records

    def prepare_workspace(
        self,
        *,
        ticket_id: str,
        repository: RepositoryInventoryRecord,
        workspace_root: Path | None = None,
    ) -> RepositoryWorkspace:
        """Create a local workspace directory for a resolved repository."""

        require_fixture_mode(self.mode, capability="Repository live clone preparation")
        resolved_workspace_root = workspace_root or self.workspace_root
        if resolved_workspace_root is None:
            raise RepositoryInventoryConfigurationError("Workspace root is not configured for repository intake.")

        ticket_dir = resolved_workspace_root / _normalize_path_segment(ticket_id)
        repository_dir = ticket_dir / _normalize_path_segment(repository.name)
        repository_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = repository_dir / ".execution-accelerator-repo.json"
        metadata_path.write_text(
            json.dumps(repository.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        )

        return RepositoryWorkspace(
            name=repository.name,
            local_path=str(repository_dir),
            default_branch=repository.default_branch,
            build_system=repository.build_system,
        )


def _normalize_path_segment(value: str) -> str:
    """Normalize a string into a filesystem-friendly path segment."""

    slug = REPOSITORY_DIR_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or "workspace"
