"""Repository inventory and workspace preparation adapter."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import re
import shutil

import httpx
import yaml

from execution_accelerator.config import RuntimeConfig, load_credentials
from execution_accelerator.execution import GitRunner
from execution_accelerator.schemas import (
    ExecutionMode,
    RemediationTarget,
    RepositoryInventoryPayload,
    RepositoryInventoryRecord,
    VulnerabilityDetails,
)
from execution_accelerator.state import RepositoryWorkspace


REPOSITORY_DIR_PATTERN = re.compile(r"[^a-z0-9]+")


class RepositoryInventoryAdapterError(RuntimeError):
    """Base error for repository inventory and intake failures."""


class RepositoryInventoryConfigurationError(RepositoryInventoryAdapterError):
    """Raised when repository inventory configuration is missing."""


class RepositoryInventoryLookupError(RepositoryInventoryAdapterError):
    """Raised when an affected repository cannot be resolved from inventory."""


class RepositoryInventoryAdapter:
    """Load inventory metadata and prepare repository workspaces."""

    def __init__(
        self,
        *,
        fixture_path: Path | None = None,
        workspace_root: Path | None = None,
        mode: ExecutionMode = ExecutionMode.FIXTURE,
        config_path: Path | None = None,
        git_runner: GitRunner | None = None,
        keep_workspace: bool = False,
        existing_pull_request_lookup: Callable[[RemediationTarget], str | None] | None = None,
    ) -> None:
        self.fixture_path = fixture_path
        self.workspace_root = workspace_root
        self.mode = mode
        self.config_path = config_path
        self.git_runner = git_runner
        self.keep_workspace = keep_workspace
        self.existing_pull_request_lookup = existing_pull_request_lookup

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "RepositoryInventoryAdapter":
        """Create an adapter from runtime configuration."""

        return cls(
            fixture_path=config.repository_inventory_fixture_path,
            workspace_root=config.workspace_dir,
            mode=config.execution_mode,
            config_path=config.repo_root / "config" / "repositories.yaml",
            git_runner=GitRunner(log_dir=config.logs_dir / "git"),
            keep_workspace=config.keep_workspace,
        )

    def load_inventory(self, *, fixture_path: Path | None = None) -> RepositoryInventoryPayload:
        """Load repository inventory from fixtures or live config."""

        if self.mode == ExecutionMode.LIVE:
            return self._load_live_inventory()

        resolved_fixture_path = fixture_path or self.fixture_path
        if resolved_fixture_path is None:
            raise RepositoryInventoryConfigurationError(
                "Repository inventory fixture path is not configured. "
                "Set EA_REPOSITORY_INVENTORY_FIXTURE_PATH for local intake."
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
                    f"Repository '{affected_repo.name}' is not present in the configured inventory."
                )
            resolved_records.append(record)

        return resolved_records

    def build_targets(
        self,
        *,
        ticket_id: str,
        vulnerability_details: VulnerabilityDetails,
        target_version: str | None = None,
        fixture_path: Path | None = None,
    ) -> list[RemediationTarget]:
        """Build remediation targets for the repositories affected by a ticket."""

        resolved_repositories = self.resolve_repositories(vulnerability_details, fixture_path=fixture_path)
        effective_target_version = target_version or vulnerability_details.fixed_version
        return [
            RemediationTarget(
                ticket_id=ticket_id,
                repository_name=repository.name,
                package_name=vulnerability_details.package_name,
                installed_version=vulnerability_details.installed_version,
                target_version=effective_target_version,
                clone_url=repository.clone_url,
                default_branch=repository.default_branch,
                build_system=repository.build_system,
                manifest_path=repository.manifest_path,
                owner=repository.owner,
                tags=repository.tags,
            )
            for repository in resolved_repositories
        ]

    def find_existing_pull_request(self, target: RemediationTarget) -> str | None:
        """Look for an existing open remediation PR before cloning a workspace."""

        if self.mode != ExecutionMode.LIVE:
            return None
        if self.existing_pull_request_lookup is not None:
            return self.existing_pull_request_lookup(target)

        credentials = load_credentials()
        if not credentials.github_token:
            raise RepositoryInventoryConfigurationError(
                "GITHUB_TOKEN is required for live repository idempotency checks."
            )

        repository_owner = target.owner or credentials.github_owner
        if not repository_owner:
            raise RepositoryInventoryConfigurationError(
                f"Repository owner is missing for live idempotency checks on '{target.repository_name}'."
            )

        search_terms = " ".join(
            f"\"{term}\""
            for term in (target.ticket_id, target.package_name, target.target_version)
            if term
        )
        query = f"repo:{repository_owner}/{target.repository_name} is:pr is:open {search_terms}".strip()
        search_url = f"{credentials.github_api_base.rstrip('/')}/search/issues"
        try:
            response = httpx.get(
                search_url,
                params={"q": query, "per_page": 1},
                headers={
                    "Authorization": f"Bearer {credentials.github_token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise RepositoryInventoryAdapterError(
                f"Failed to search for existing PRs for '{target.repository_name}': {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise RepositoryInventoryAdapterError(
                f"Unexpected GitHub search payload type: {type(payload).__name__}"
            )
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return None
        first_match = items[0]
        if not isinstance(first_match, dict):
            return None
        html_url = first_match.get("html_url")
        return html_url if isinstance(html_url, str) and html_url else None

    def prepare_workspace(
        self,
        *,
        ticket_id: str,
        repository: RepositoryInventoryRecord,
        workspace_root: Path | None = None,
    ) -> RepositoryWorkspace:
        """Create a local workspace directory for a resolved repository."""

        resolved_workspace_root = workspace_root or self.workspace_root
        if resolved_workspace_root is None:
            raise RepositoryInventoryConfigurationError("Workspace root is not configured for repository intake.")

        ticket_dir = resolved_workspace_root / _normalize_path_segment(ticket_id)
        repository_dir = ticket_dir / _normalize_path_segment(repository.name)
        ticket_dir.mkdir(parents=True, exist_ok=True)

        if self.mode == ExecutionMode.LIVE:
            if self.git_runner is None:
                raise RepositoryInventoryConfigurationError("Live repository intake requires a configured GitRunner.")
            cloned_dir = self.git_runner.clone(
                repository.clone_url,
                repository_dir,
                branch=repository.default_branch,
            )
            head_sha = self.git_runner.head_sha(cloned_dir)
            metadata = {
                **repository.model_dump(mode="json"),
                "head_sha": head_sha,
            }
        else:
            repository_dir.mkdir(parents=True, exist_ok=True)
            metadata = repository.model_dump(mode="json")

        metadata_path = repository_dir / ".execution-accelerator-repo.json"
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")

        return RepositoryWorkspace(
            name=repository.name,
            local_path=str(repository_dir),
            clone_url=repository.clone_url,
            default_branch=repository.default_branch,
            build_system=repository.build_system,
            manifest_path=repository.manifest_path,
            owner=repository.owner,
            tags=repository.tags,
        )

    def cleanup_workspace(
        self,
        *,
        ticket_id: str,
        repository_name: str,
        workspace_root: Path | None = None,
    ) -> None:
        """Remove a workspace when live-mode cleanup is enabled."""

        if self.keep_workspace:
            return

        resolved_workspace_root = workspace_root or self.workspace_root
        if resolved_workspace_root is None:
            raise RepositoryInventoryConfigurationError("Workspace root is not configured for cleanup.")

        workspace_path = resolved_workspace_root / _normalize_path_segment(ticket_id) / _normalize_path_segment(
            repository_name
        )
        if workspace_path.exists():
            shutil.rmtree(workspace_path)

    def _load_live_inventory(self) -> RepositoryInventoryPayload:
        if self.config_path is None:
            raise RepositoryInventoryConfigurationError("Live repository intake requires config/repositories.yaml.")
        if not self.config_path.exists():
            raise RepositoryInventoryConfigurationError(
                f"Repository config file does not exist: {self.config_path}"
            )

        loaded = yaml.safe_load(self.config_path.read_text()) or {}
        if not isinstance(loaded, dict):
            raise RepositoryInventoryConfigurationError(
                f"Repository config must be a YAML mapping: {self.config_path}"
            )
        return RepositoryInventoryPayload.model_validate(loaded)


def _normalize_path_segment(value: str) -> str:
    """Normalize a string into a filesystem-friendly path segment."""

    slug = REPOSITORY_DIR_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or "workspace"
