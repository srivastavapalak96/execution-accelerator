from __future__ import annotations

from pathlib import Path
import subprocess
import typing

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
    assert targets[0].maven_settings == str((tmp_path / "config" / "settings.xml").resolve())
    assert targets[0].proxy_jump == "bastion.internal"
    assert targets[0].ssh_key == str((tmp_path / "config" / "id_ed25519").resolve())


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
    assert workspace.maven_settings == str((tmp_path / "config" / "settings.xml").resolve())
    assert workspace.ssh_key == str((tmp_path / "config" / "id_ed25519").resolve())


def test_repository_inventory_adapter_passes_proxy_jump_to_git_runner(tmp_path: Path) -> None:
    config_path = _write_live_inventory_config(tmp_path, clone_url="ssh://git@example.com/payments-service.git")
    calls: list[dict[str, object]] = []

    class CapturingGitRunner:
        def clone(
            self,
            url: str,
            dest: Path,
            *,
            branch: str | None = None,
            depth: int = 1,
            proxy_jump: str | None = None,
            ssh_key: Path | None = None,
        ) -> Path:
            calls.append(
                {
                    "url": url,
                    "dest": dest,
                    "branch": branch,
                    "depth": depth,
                    "proxy_jump": proxy_jump,
                    "ssh_key": ssh_key,
                }
            )
            dest.mkdir(parents=True, exist_ok=True)
            (dest / ".git").mkdir()
            return dest

        def head_sha(
            self,
            repo_dir: Path,
            *,
            proxy_jump: str | None = None,
            ssh_key: Path | None = None,
        ) -> str:
            del repo_dir, proxy_jump, ssh_key
            return "abc123"

    adapter = RepositoryInventoryAdapter(
        config_path=config_path,
        workspace_root=tmp_path / "workspace",
        mode=ExecutionMode.LIVE,
        git_runner=CapturingGitRunner(),  # type: ignore[arg-type]
    )
    repository = adapter.load_inventory().repositories[0]

    adapter.prepare_workspace(ticket_id="SEC-655", repository=repository)

    assert calls[0]["proxy_jump"] == "bastion.internal"
    assert calls[0]["ssh_key"] == (tmp_path / "config" / "id_ed25519").resolve()


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


def test_repository_inventory_adapter_live_idempotency_checks_recently_closed_prs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_live_inventory_config(tmp_path)
    adapter = RepositoryInventoryAdapter(
        config_path=config_path,
        workspace_root=tmp_path / "workspace",
        mode=ExecutionMode.LIVE,
    )
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("GITHUB_OWNER", "payments-platform")
    queries: list[str] = []

    class DummyResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_get(*args: typing.Any, **kwargs: typing.Any) -> DummyResponse:
        query = str(kwargs["params"]["q"])
        queries.append(query)
        if "is:open" in query:
            return DummyResponse({"items": []})
        return DummyResponse({"items": [{"html_url": "https://github.com/example/payments-service/pull/88"}]})

    monkeypatch.setattr("execution_accelerator.adapters.repository_inventory.httpx.get", fake_get)
    targets = adapter.build_targets(ticket_id="SEC-777", vulnerability_details=build_vulnerability_details())

    existing_pr = adapter.find_existing_pull_request(targets[0])

    assert existing_pr == "https://github.com/example/payments-service/pull/88"
    assert "is:open" in queries[0]
    assert "is:closed" in queries[1]
    assert "updated:>=" in queries[1]


def test_repository_inventory_adapter_live_idempotency_ignores_old_closed_prs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_live_inventory_config(tmp_path)
    adapter = RepositoryInventoryAdapter(
        config_path=config_path,
        workspace_root=tmp_path / "workspace",
        mode=ExecutionMode.LIVE,
    )
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("GITHUB_OWNER", "payments-platform")

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"items": []}

    monkeypatch.setattr(
        "execution_accelerator.adapters.repository_inventory.httpx.get",
        lambda *args, **kwargs: DummyResponse(),
    )
    targets = adapter.build_targets(ticket_id="SEC-777", vulnerability_details=build_vulnerability_details())

    existing_pr = adapter.find_existing_pull_request(targets[0])

    assert existing_pr is None


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
    (config_path.parent / "settings.xml").write_text("<settings />\n")
    (config_path.parent / "id_ed25519").write_text("not-a-real-key\n")
    config_path.write_text(
        "\n".join(
            [
                "repositories:",
                "  - name: payments-service",
                f"    clone_url: {clone_url}",
                "    default_branch: main",
                "    build_system: maven",
                "    manifest_path: pom.xml",
                "    maven_settings: settings.xml",
                "    proxy_jump: bastion.internal",
                "    ssh_key: id_ed25519",
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
