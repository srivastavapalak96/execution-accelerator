from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shlex
from typing import Final

from .sandbox import CommandResult, run_command


_DEFAULT_GIT_TIMEOUT: Final[float] = 300.0


class GitCommandError(RuntimeError):
    """Raised when a git subprocess exits unsuccessfully."""

    def __init__(self, action: str, result: CommandResult) -> None:
        self.action = action
        self.result = result
        super().__init__(f"git {action} failed with exit code {result.returncode}")


@dataclass
class GitRunner:
    """Thin git CLI wrapper that persists command logs for live operations."""

    log_dir: Path
    timeout: float = _DEFAULT_GIT_TIMEOUT
    secrets: tuple[str, ...] = ()
    _command_index: int = field(init=False, default=0)

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
        if depth < 1:
            raise ValueError("depth must be >= 1")

        destination = Path(dest).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)

        command = ["clone"]
        if branch:
            command.extend(["--branch", branch, "--no-single-branch"])
        command.extend(["--depth", str(depth), url, str(destination)])
        self._run_git(command, cwd=destination.parent, action="clone", proxy_jump=proxy_jump, ssh_key=ssh_key)
        return destination

    def checkout(self, repo_dir: Path, ref: str) -> None:
        try:
            self._run_git(["checkout", ref], cwd=repo_dir, action="checkout")
        except GitCommandError as error:
            remote_ref = f"origin/{ref}"
            if self._git_ref_exists(repo_dir, f"refs/remotes/{remote_ref}"):
                self._run_git(["checkout", "--track", remote_ref], cwd=repo_dir, action="checkout-track")
                return
            raise error

    def current_branch(self, repo_dir: Path) -> str:
        result = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir, action="current-branch")
        return result.stdout.strip()

    def create_branch(self, repo_dir: Path, branch_name: str) -> None:
        self._run_git(["checkout", "-B", branch_name], cwd=repo_dir, action="checkout-branch")

    def add_all(self, repo_dir: Path) -> None:
        self._run_git(["add", "--all"], cwd=repo_dir, action="add-all")

    def commit(self, repo_dir: Path, *, message: str) -> None:
        self._run_git(["commit", "-m", message], cwd=repo_dir, action="commit")

    def push(self, repo_dir: Path, *, remote: str = "origin", branch_name: str) -> None:
        self._run_git(["push", "--set-upstream", remote, branch_name], cwd=repo_dir, action="push")

    def restore_paths(self, repo_dir: Path, *, paths: list[str]) -> None:
        if not paths:
            return
        self._run_git(
            ["restore", "--source=HEAD", "--staged", "--worktree", "--", *paths],
            cwd=repo_dir,
            action="restore",
        )

    def status_clean(self, repo_dir: Path) -> bool:
        result = self._run_git(["status", "--porcelain"], cwd=repo_dir, action="status")
        return result.stdout.strip() == ""

    def head_sha(self, repo_dir: Path) -> str:
        result = self._run_git(["rev-parse", "HEAD"], cwd=repo_dir, action="head-sha")
        return result.stdout.strip()

    def configure_user(self, repo_dir: Path, *, name: str, email: str) -> None:
        self._run_git(["config", "user.name", name], cwd=repo_dir, action="config-user-name")
        self._run_git(["config", "user.email", email], cwd=repo_dir, action="config-user-email")

    def signing_key(self, repo_dir: Path, key_id: str) -> None:
        self._run_git(["config", "user.signingkey", key_id], cwd=repo_dir, action="config-signing-key")
        self._run_git(["config", "commit.gpgsign", "true"], cwd=repo_dir, action="config-gpg-sign")

    def _run_git(
        self,
        args: list[str],
        *,
        cwd: Path,
        action: str,
        proxy_jump: str | None = None,
        ssh_key: Path | None = None,
    ) -> CommandResult:
        result = run_command(
            ["git", *args],
            cwd=Path(cwd).resolve(),
            timeout=self.timeout,
            env=self._build_git_env(proxy_jump=proxy_jump, ssh_key=ssh_key),
            log_path=self._next_log_path(action),
            secrets=self.secrets,
        )
        if result.returncode != 0:
            raise GitCommandError(action, result)
        return result

    def _git_ref_exists(self, repo_dir: Path, ref: str) -> bool:
        result = run_command(
            ["git", "show-ref", "--verify", "--quiet", ref],
            cwd=Path(repo_dir).resolve(),
            timeout=self.timeout,
            env=None,
            log_path=self._next_log_path("show-ref"),
            secrets=self.secrets,
        )
        return result.returncode == 0

    def _build_git_env(self, *, proxy_jump: str | None, ssh_key: Path | None) -> dict[str, str] | None:
        ssh_parts = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
        if proxy_jump:
            ssh_parts.extend(["-J", proxy_jump])
        if ssh_key:
            ssh_parts.extend(["-i", str(Path(ssh_key).resolve())])
        if len(ssh_parts) == 5:
            return None
        return {"GIT_SSH_COMMAND": shlex.join(ssh_parts)}

    def _next_log_path(self, action: str) -> Path:
        self._command_index += 1
        return Path(self.log_dir).resolve() / f"{self._command_index:03d}-{action}.log"
