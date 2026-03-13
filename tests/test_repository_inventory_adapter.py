from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from execution_accelerator.adapters import (
    RepositoryInventoryAdapter,
    RepositoryInventoryConfigurationError,
    RepositoryInventoryLookupError,
)
from execution_accelerator.execution import GitRunner
from execution_accelerator.config import load_runtime_config
from execution_accelerator.schemas import AffectedRepository, ExecutionMode, Severity, VulnerabilityDetails


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


def test_repository_inventory_adapter_resolves_affected_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "repository_inventory.json"
    monkeypatch.setenv("EA_REPOSITORY_INVENTORY_FIXTURE_PATH", str(fixture_path))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = RepositoryInventoryAdapter.from_runtime_config(config)

    resolved = adapter.resolve_repositories(build_vulnerability_details())

    assert len(resolved) == 1
    assert resolved[0].owner == "payments-platform"


def test_repository_inventory_adapter_creates_ticket_workspace(tmp_path: Path) -> None:
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


def test_repository_inventory_adapter_builds_targets_from_live_inventory(tmp_path: Path) -> None:
    config_path = _write_live_inventory_config(tmp_path)
    adapter = RepositoryInventoryAdapter(
        config_path=config_path,
        workspace_root=tmp_path / "workspace",
        mode=ExecutionMode.LIVE,
    )

    targets = adapter.build_targets(
        ticket_id="SEC-321",
        vulnerability_details=build_vulnerability_details(),
    )

    assert len(targets) == 1
    assert targets[0].ticket_id == "SEC-321"
    assert targets[0].repository_name == "payments-service"
    assert targets[0].package_name == "org.example:legacy-json"
    assert targets[0].target_version == "1.2.4"
    assert targets[0].owner == "payments-platform"


def test_repository_inventory_adapter_prepares_live_workspace_with_real_clone(tmp_path: Path) -> None:
    source_repo = _create_source_repo(tmp_path / "source")
    config_path = _write_live_inventory_config(tmp_path, clone_url=str(source_repo))
    adapter = RepositoryInventoryAdapter(
        config_path=config_path,
        workspace_root=tmp_path / "workspace",
        mode=ExecutionMode.LIVE,
        git_runner=GitRunner(log_dir=tmp_path / "logs"),
    )
    repository = adapter.load_inventory().repositories[0]

    workspace = adapter.prepare_workspace(ticket_id="SEC-654", repository=repository)

    workspace_path = Path(workspace.local_path)
    assert (workspace_path / ".git").is_dir()
    assert (workspace_path / ".execution-accelerator-repo.json").exists()
    assert workspace.clone_url == str(source_repo)


def test_repository_inventory_adapter_live_idempotency_uses_lookup_callback(tmp_path: Path) -> None:
    config_path = _write_live_inventory_config(tmp_path)
    adapter = RepositoryInventoryAdapter(
        config_path=config_path,
        workspace_root=tmp_path / "workspace",
        mode=ExecutionMode.LIVE,
        existing_pull_request_lookup=lambda target: f"https://github.com/example/{target.repository_name}/pull/42",
    )

    targets = adapter.build_targets(ticket_id="SEC-777", vulnerability_details=build_vulnerability_details())
    existing_pr = adapter.find_existing_pull_request(targets[0])

    assert existing_pr == "https://github.com/example/payments-service/pull/42"


def test_repository_inventory_adapter_cleans_up_live_workspace_when_not_kept(tmp_path: Path) -> None:
    source_repo = _create_source_repo(tmp_path / "source")
    config_path = _write_live_inventory_config(tmp_path, clone_url=str(source_repo))
    adapter = RepositoryInventoryAdapter(
        config_path=config_path,
        workspace_root=tmp_path / "workspace",
        mode=ExecutionMode.LIVE,
        git_runner=GitRunner(log_dir=tmp_path / "logs"),
        keep_workspace=False,
    )
    repository = adapter.load_inventory().repositories[0]
    workspace = adapter.prepare_workspace(ticket_id="SEC-888", repository=repository)

    adapter.cleanup_workspace(ticket_id="SEC-888", repository_name="payments-service")

    assert not Path(workspace.local_path).exists()


def _write_live_inventory_config(tmp_path: Path, *, clone_url: str = "https://github.com/example/payments-service.git") -> Path:
    config_path = tmp_path / "config" / "repositories.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            [
                "repositories:",
                "  - name: payments-service",
                f"    clone_url: {clone_url}",
                "    default_branch: main",
                "    build_system: maven",
                "    manifest_path: pom.xml",
                "    owner: payments-platform",
                "    tags:",
                "      - payments",
                "      - java",
            ]
        )
        + "\n"
    )
    return config_path


def _create_source_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path.parent, "init", "--initial-branch=main", str(path))
    _git(path, "config", "user.name", "Fixture User")
    _git(path, "config", "user.email", "fixture@example.com")
    (path / "pom.xml").write_text("<project />\n")
    _git(path, "add", "pom.xml")
    _git(path, "commit", "-m", "Initial commit")
    return path


def _git(path: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
