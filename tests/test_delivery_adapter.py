from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from execution_accelerator.adapters import (
    DeliveryAdapter,
    DeliveryConfigurationError,
)
from execution_accelerator.config import load_runtime_config
from execution_accelerator.execution import GitRunner
from execution_accelerator.schemas import ExecutionMode


def test_delivery_adapter_loads_branch_and_pull_request_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv(
        "EA_BRANCH_PUBLICATION_FIXTURE_PATH",
        str(fixture_dir / "branch_publication.json"),
    )
    monkeypatch.setenv("EA_PULL_REQUEST_FIXTURE_PATH", str(fixture_dir / "pull_request.json"))
    monkeypatch.setenv("EA_JIRA_COMPLETION_FIXTURE_PATH", str(fixture_dir / "jira_completion.json"))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = DeliveryAdapter.from_runtime_config(config)

    branch = adapter.load_branch_publication(repository="payments-service")
    pull_request = adapter.load_pull_request(repository="payments-service")
    jira_completion = adapter.load_jira_completion(ticket_id="SEC-123")

    assert branch.branch_name == "sec-123-remediate-legacy-json"
    assert pull_request.number == 42
    assert jira_completion.status == "done"


def test_delivery_adapter_publishes_live_branch(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "pom.xml").write_text("<project />\n")
    subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "add", "pom.xml"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=workspace, check=True, capture_output=True)
    (workspace / "pom.xml").write_text("<project><version>2</version></project>\n")

    adapter = DeliveryAdapter(
        mode=ExecutionMode.LIVE,
        git_runner=GitRunner(log_dir=tmp_path / "logs"),
        git_user_name="Automation Bot",
        git_user_email="bot@example.com",
    )

    branch = adapter.load_branch_publication(
        repository="payments-service",
        workspace_path=workspace,
        ticket_id="SEC-123",
        package_name="legacy-json",
    )

    remote_heads = subprocess.run(
        ["git", "ls-remote", "--heads", str(origin), "sec-123-remediate-legacy-json"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert branch.branch_name == "sec-123-remediate-legacy-json"
    assert branch.commit_message == "chore: remediate legacy-json for SEC-123"
    assert remote_heads.stdout.strip()


def test_delivery_adapter_requires_configuration() -> None:
    adapter = DeliveryAdapter()

    with pytest.raises(DeliveryConfigurationError):
        adapter.load_branch_publication(repository="payments-service")
