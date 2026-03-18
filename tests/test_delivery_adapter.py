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
from tests.live_support import ResponseSpec, serve_routes


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


def test_delivery_adapter_creates_live_pull_request_and_jira_comment(tmp_path: Path) -> None:
    with serve_routes(
        {
            (
                "POST",
                "/repos/payments-platform/payments-service/pulls",
            ): ResponseSpec(
                status=201,
                body=(
                    b'{"number": 42, "html_url": "https://example.test/pr/42", '
                    b'"title": "SEC-123: remediate legacy-json", "state": "open"}'
                ),
            ),
            ("POST", "/rest/api/3/issue/SEC-123/comment"): ResponseSpec(status=201, body=b'{"id":"10001"}'),
        }
    ) as base_url:
        adapter = DeliveryAdapter(
            mode=ExecutionMode.LIVE,
            github_api_base=base_url,
            github_token="ghp_testtoken",
            github_owner="payments-platform",
            jira_base_url=base_url,
            jira_email="jira@example.com",
            jira_token="jira-token",
        )

        pull_request = adapter.load_pull_request(
            repository="payments-service",
            owner="payments-platform",
            base_branch="main",
            head_branch="sec-123-remediate-legacy-json",
            ticket_id="SEC-123",
            package_name="legacy-json",
        )
        jira_completion = adapter.load_jira_completion(
            ticket_id="SEC-123",
            repository="payments-service",
            pull_request_url=pull_request.url,
        )

    assert pull_request.number == 42
    assert pull_request.url == "https://example.test/pr/42"
    assert jira_completion.status == "commented"
    assert "https://example.test/pr/42" in jira_completion.comment


def test_delivery_adapter_transitions_jira_ticket_when_configured() -> None:
    requests_log: list[tuple[str, str, bytes]] = []
    with serve_routes(
        {
            ("POST", "/rest/api/3/issue/SEC-123/comment"): ResponseSpec(status=201, body=b'{"id":"10001"}'),
            ("POST", "/rest/api/3/issue/SEC-123/transitions"): ResponseSpec(status=204, body=b""),
        },
        requests_log=requests_log,
    ) as base_url:
        adapter = DeliveryAdapter(
            mode=ExecutionMode.LIVE,
            jira_base_url=base_url,
            jira_email="jira@example.com",
            jira_token="jira-token",
            jira_done_transition_id="31",
            jira_done_status_name="Done",
        )

        jira_completion = adapter.load_jira_completion(
            ticket_id="SEC-123",
            repository="payments-service",
            pull_request_url="https://example.test/pr/42",
        )

    assert jira_completion.status == "Done"
    assert [path for _, path, _ in requests_log] == [
        "/rest/api/3/issue/SEC-123/comment",
        "/rest/api/3/issue/SEC-123/transitions",
    ]
