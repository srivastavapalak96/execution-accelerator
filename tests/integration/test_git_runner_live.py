"""Integration test: real ``git`` subprocess invocation against a local bare repo.

Uses a bare repo created in ``tmp_path`` so the test does not depend on internet
access and cannot leak branches to a shared remote.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from execution_accelerator.execution.git_runner import GitRunner


def _git_available() -> bool:
    return shutil.which("git") is not None


def test_clone_local_bare_repo(temp_git_remote: Path, tmp_path: Path) -> None:
    """``GitRunner.clone`` against a local bare repo produces a real working tree."""

    if not _git_available():
        pytest.skip("git not on PATH")

    # Seed the bare repo with one commit so clone succeeds (cloning an empty
    # bare repo is an edge case that real GitHub never produces).
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(seed_dir)], check=True, capture_output=True)
    (seed_dir / "README.md").write_text("# integration sample\n")
    subprocess.run(["git", "-C", str(seed_dir), "add", "README.md"], check=True, capture_output=True)
    # Use a per-repo identity so this test never depends on the user's global
    # git config (which may be missing in CI).
    subprocess.run(
        [
            "git", "-C", str(seed_dir),
            "-c", "user.name=integration",
            "-c", "user.email=integration@example.com",
            "commit", "-m", "seed",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(seed_dir), "remote", "add", "origin", str(temp_git_remote)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(seed_dir), "push", "origin", "main"],
        check=True,
        capture_output=True,
    )

    # Now run our wrapper.
    destination = tmp_path / "clone"
    runner = GitRunner(log_dir=tmp_path / "logs")
    cloned_dir = runner.clone(str(temp_git_remote), destination, branch="main")

    assert cloned_dir == destination
    assert (destination / ".git").is_dir()
    assert (destination / "README.md").read_text() == "# integration sample\n"


def test_head_sha_returns_real_sha(temp_git_remote: Path, tmp_path: Path) -> None:
    """``head_sha`` returns the same SHA git itself reports."""

    if not _git_available():
        pytest.skip("git not on PATH")

    # Seed + clone (same shape as above; consider extracting if more tests need this).
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(seed_dir)], check=True, capture_output=True)
    (seed_dir / "file.txt").write_text("content\n")
    subprocess.run(["git", "-C", str(seed_dir), "add", "file.txt"], check=True, capture_output=True)
    subprocess.run(
        [
            "git", "-C", str(seed_dir),
            "-c", "user.name=integration",
            "-c", "user.email=integration@example.com",
            "commit", "-m", "seed",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(seed_dir), "remote", "add", "origin", str(temp_git_remote)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(seed_dir), "push", "origin", "main"],
        check=True,
        capture_output=True,
    )

    destination = tmp_path / "clone"
    runner = GitRunner(log_dir=tmp_path / "logs")
    runner.clone(str(temp_git_remote), destination, branch="main")

    sha = runner.head_sha(destination)
    assert len(sha) == 40, f"Expected a 40-char SHA, got {sha!r}"
    # Sanity-check against `git rev-parse HEAD`.
    expected = subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert sha == expected


def test_clone_threads_proxy_jump_into_env(temp_git_remote: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``proxy_jump`` shows up in ``GIT_SSH_COMMAND`` for the clone subprocess.

    We can't actually go through a bastion in a hermetic test; we just verify
    the env wiring by intercepting the subprocess invocation.
    """

    if not _git_available():
        pytest.skip("git not on PATH")

    runner = GitRunner(log_dir=tmp_path / "logs")
    captured: dict[str, dict[str, str] | None] = {"env": None}

    def spy_run_command(cmd, *, cwd, timeout, env=None, log_path=None, secrets=None):  # type: ignore[no-untyped-def]
        captured["env"] = env
        # Don't actually run; return a fake successful result so clone() finishes its post-steps.
        from execution_accelerator.execution.sandbox import CommandResult

        return CommandResult(
            command=tuple(cmd),
            cwd=cwd,
            returncode=0,
            stdout="",
            stderr="",
            log_path=log_path or (tmp_path / "fake.log"),
        )

    monkeypatch.setattr(
        "execution_accelerator.execution.git_runner.run_command",
        spy_run_command,
    )

    runner.clone(
        str(temp_git_remote),
        tmp_path / "fake-clone",
        branch="main",
        proxy_jump="user@bastion.example.com",
    )

    assert captured["env"] is not None
    assert "GIT_SSH_COMMAND" in captured["env"]
    assert "-J user@bastion.example.com" in captured["env"]["GIT_SSH_COMMAND"]
