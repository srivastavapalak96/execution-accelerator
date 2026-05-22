"""Unit tests for post-push rollback helpers (B4):

* GitRunner.delete_remote_branch -- best-effort remote branch delete
* DeliveryAdapter.close_pull_request -- best-effort PR close via GitHub REST
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from execution_accelerator.adapters.delivery import DeliveryAdapter
from execution_accelerator.execution.git_runner import GitCommandError, GitRunner
from execution_accelerator.execution.sandbox import CommandResult


# --- GitRunner.delete_remote_branch ------------------------------------------


def _make_command_result(returncode: int, stderr: str = "", stdout: str = "") -> CommandResult:
    return CommandResult(
        command=("git",),
        cwd=Path("/tmp"),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        log_path=Path("/tmp/log"),
    )


def test_delete_remote_branch_passes_correct_args(tmp_path: Path) -> None:
    runner = GitRunner(log_dir=tmp_path / "logs")
    captured: dict[str, Any] = {}

    def spy(cmd: list[str], **kwargs: Any) -> CommandResult:
        captured["cmd"] = list(cmd)
        return _make_command_result(0)

    with patch("execution_accelerator.execution.git_runner.run_command", side_effect=spy):
        runner.delete_remote_branch(
            tmp_path / "repo",
            branch_name="remediate/sec-1",
        )

    assert captured["cmd"][:2] == ["git", "push"]
    assert "--delete" in captured["cmd"]
    assert "remediate/sec-1" in captured["cmd"]


def test_delete_remote_branch_threads_proxy_jump(tmp_path: Path) -> None:
    runner = GitRunner(log_dir=tmp_path / "logs")
    captured: dict[str, Any] = {}

    def spy(cmd: list[str], **kwargs: Any) -> CommandResult:
        captured["env"] = kwargs.get("env")
        return _make_command_result(0)

    with patch("execution_accelerator.execution.git_runner.run_command", side_effect=spy):
        runner.delete_remote_branch(
            tmp_path / "repo",
            branch_name="remediate/sec-1",
            proxy_jump="bot@bastion.example.com",
        )

    env = captured["env"]
    assert env is not None
    assert "GIT_SSH_COMMAND" in env
    assert "-J bot@bastion.example.com" in env["GIT_SSH_COMMAND"]


def test_delete_remote_branch_swallows_failure(tmp_path: Path) -> None:
    """A non-existent remote branch must not raise; rollback is best-effort."""

    runner = GitRunner(log_dir=tmp_path / "logs")

    def failing(cmd: list[str], **kwargs: Any) -> CommandResult:
        return _make_command_result(1, stderr="error: unable to delete 'foo': remote ref does not exist\n")

    with patch("execution_accelerator.execution.git_runner.run_command", side_effect=failing):
        runner.delete_remote_branch(tmp_path / "repo", branch_name="foo")
        # Did not raise -- that's the contract.


def test_delete_remote_branch_swallows_thrown_command_error(tmp_path: Path) -> None:
    """If the underlying _run_git surfaces GitCommandError, swallow it."""

    runner = GitRunner(log_dir=tmp_path / "logs")

    def explode(cmd: list[str], **kwargs: Any) -> CommandResult:
        result = _make_command_result(1, stderr="boom")
        # _run_git turns non-zero into GitCommandError; mimic that here.
        raise GitCommandError("push-delete", result)

    with patch.object(runner, "_run_git", side_effect=GitCommandError("push-delete", _make_command_result(1))):
        runner.delete_remote_branch(tmp_path / "repo", branch_name="foo")
        # No raise.


# --- DeliveryAdapter.close_pull_request --------------------------------------


def _delivery_adapter() -> DeliveryAdapter:
    return DeliveryAdapter(
        github_api_base="https://api.github.example",
        github_token="ghp_fake_token",
        github_owner="example",
    )


def test_close_pull_request_returns_false_when_unconfigured() -> None:
    adapter = DeliveryAdapter()
    assert adapter.close_pull_request(repository="repo", pull_request_number=1) is False


def test_close_pull_request_issues_patch_with_closed_state() -> None:
    adapter = _delivery_adapter()
    captured: dict[str, Any] = {}

    def spy_patch(url: str, **kwargs: Any) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        request = httpx.Request("PATCH", url)
        return httpx.Response(200, json={"state": "closed"}, request=request)

    with patch("httpx.patch", side_effect=spy_patch):
        result = adapter.close_pull_request(
            repository="payments-service",
            pull_request_number=42,
            reason="planted compile failure",
        )

    assert result is True
    assert captured["url"].endswith("/repos/example/payments-service/pulls/42")
    assert captured["json"]["state"] == "closed"
    assert "planted compile failure" in captured["json"]["body"]


def test_close_pull_request_swallows_http_error() -> None:
    adapter = _delivery_adapter()

    def raising_patch(url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.HTTPError("connection reset")

    with patch("httpx.patch", side_effect=raising_patch):
        result = adapter.close_pull_request(repository="repo", pull_request_number=1)

    # Best-effort contract: errors do not propagate.
    assert result is False


def test_close_pull_request_swallows_4xx() -> None:
    adapter = _delivery_adapter()

    def four_oh_three(url: str, **kwargs: Any) -> httpx.Response:
        # Build a minimal request so .raise_for_status has the request context it
        # expects.
        request = httpx.Request("PATCH", url)
        return httpx.Response(403, json={"message": "Resource not accessible"}, request=request)

    with patch("httpx.patch", side_effect=four_oh_three):
        # raise_for_status will raise httpx.HTTPStatusError, which is a
        # subclass of httpx.HTTPError -- the adapter must catch it.
        result = adapter.close_pull_request(repository="repo", pull_request_number=1)

    assert result is False


def test_close_pull_request_requires_keyword_arguments() -> None:
    """The public surface uses keyword-only args; passing positionals must fail."""

    adapter = _delivery_adapter()
    with pytest.raises(TypeError):
        adapter.close_pull_request("repo", 1)  # type: ignore[misc]
