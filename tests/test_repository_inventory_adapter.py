from __future__ import annotations

from pathlib import Path

import pytest

from execution_accelerator.adapters import (
    RepositoryInventoryAdapter,
    RepositoryInventoryConfigurationError,
    RepositoryInventoryLookupError,
)
from execution_accelerator.config import load_runtime_config
from execution_accelerator.schemas import AffectedRepository, Severity, VulnerabilityDetails


def build_vulnerability_details(*, repository_name: str = "payments-service") -> VulnerabilityDetails:
    return VulnerabilityDetails(
        package_name="org.example:legacy-json",
        installed_version="1.2.3",
        fixed_version="1.2.4",
        summary="Repository inventory test vulnerability",
        severity=Severity.HIGH,
        affected_repositories=[
            AffectedRepository(
                name=repository_name,
                clone_url=f"https://github.com/example/{repository_name}.git",
                manifest_path="pom.xml",
            )
        ],
    )


def test_repository_inventory_adapter_resolves_affected_repository(tmp_path, monkeypatch) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "repository_inventory.json"
    monkeypatch.setenv("EA_REPOSITORY_INVENTORY_FIXTURE_PATH", str(fixture_path))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = RepositoryInventoryAdapter.from_runtime_config(config)

    resolved = adapter.resolve_repositories(build_vulnerability_details())

    assert len(resolved) == 1
    assert resolved[0].owner == "payments-platform"


def test_repository_inventory_adapter_creates_ticket_workspace(tmp_path) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "repository_inventory.json"
    adapter = RepositoryInventoryAdapter(fixture_path=fixture_path, workspace_root=tmp_path / "workspace")
    repository = adapter.load_inventory().repositories[0]

    workspace = adapter.prepare_workspace(ticket_id="SEC-123", repository=repository)

    workspace_path = Path(workspace.local_path)
    assert workspace.name == "payments-service"
    assert workspace_path.is_dir()
    assert (workspace_path / ".execution-accelerator-repo.json").exists()


def test_repository_inventory_adapter_requires_fixture_configuration() -> None:
    adapter = RepositoryInventoryAdapter()

    with pytest.raises(RepositoryInventoryConfigurationError):
        adapter.load_inventory()


def test_repository_inventory_adapter_rejects_missing_repository() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "repository_inventory.json"
    adapter = RepositoryInventoryAdapter(fixture_path=fixture_path)

    with pytest.raises(RepositoryInventoryLookupError):
        adapter.resolve_repositories(build_vulnerability_details(repository_name="missing-service"))
