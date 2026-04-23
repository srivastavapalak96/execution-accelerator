from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
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
    proxy_jump: str | None = None
    ssh_key: Path | None = None
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

    def checkout(
        self,
        repo_dir: Path,
        ref: str,
        *,
        proxy_jump: str | None = None,
        ssh_key: Path | None = None,
    ) -> None:
        try:
            self._run_git(["checkout", ref], cwd=repo_dir, action="checkout", proxy_jump=proxy_jump, ssh_key=ssh_key)
        except GitCommandError as error:
            remote_ref = f"origin/{ref}"
            if self._git_ref_exists(repo_dir, f"refs/remotes/{remote_ref}", proxy_jump=proxy_jump, ssh_key=ssh_key):
                self._run_git(
                    ["checkout", "--track", remote_ref],
                    cwd=repo_dir,
                    action="checkout-track",
                    proxy_jump=proxy_jump,
                    ssh_key=ssh_key,
                )
                return
            raise error

    def current_branch(self, repo_dir: Path, *, proxy_jump: str | None = None, ssh_key: Path | None = None) -> str:
        result = self._run_git(
            ["rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_dir,
            action="current-branch",
            proxy_jump=proxy_jump,
            ssh_key=ssh_key,
        )
        return result.stdout.strip()

    def create_branch(
        self,
        repo_dir: Path,
        branch_name: str,
        *,
        proxy_jump: str | None = None,
        ssh_key: Path | None = None,
    ) -> None:
        self._run_git(
            ["checkout", "-B", branch_name],
            cwd=repo_dir,
            action="checkout-branch",
            proxy_jump=proxy_jump,
            ssh_key=ssh_key,
        )

    def add_all(self, repo_dir: Path, *, proxy_jump: str | None = None, ssh_key: Path | None = None) -> None:
        self._run_git(["add", "--all"], cwd=repo_dir, action="add-all", proxy_jump=proxy_jump, ssh_key=ssh_key)

    def commit(
        self,
        repo_dir: Path,
        *,
        message: str,
        proxy_jump: str | None = None,
        ssh_key: Path | None = None,
    ) -> None:
        self._run_git(["commit", "-m", message], cwd=repo_dir, action="commit", proxy_jump=proxy_jump, ssh_key=ssh_key)

    def push(
        self,
        repo_dir: Path,
        *,
        remote: str = "origin",
        branch_name: str,
        proxy_jump: str | None = None,
        ssh_key: Path | None = None,
    ) -> None:
        self._run_git(
            ["push", "--set-upstream", remote, branch_name],
            cwd=repo_dir,
            action="push",
            proxy_jump=proxy_jump,
            ssh_key=ssh_key,
        )

    def delete_remote_branch(
        self,
        repo_dir: Path,
        *,
        remote: str = "origin",
        branch_name: str,
        proxy_jump: str | None = None,
        ssh_key: Path | None = None,
    ) -> None:
        """Delete ``branch_name`` from ``remote`` for post-push rollback.

        Used when validation fails after the branch has already been pushed and
        a draft PR may have been opened. Best-effort: if the remote branch is
        already gone, the failed git invocation is swallowed so local rollback
        bookkeeping still completes.
        """

        try:
            self._run_git(
                ["push", remote, "--delete", branch_name],
                cwd=repo_dir,
                action="push-delete",
                proxy_jump=proxy_jump,
                ssh_key=ssh_key,
            )
        except GitCommandError:
            return

    def restore_paths(
        self,
        repo_dir: Path,
        *,
        paths: list[str],
        proxy_jump: str | None = None,
        ssh_key: Path | None = None,
    ) -> None:
        if not paths:
            return
        self._run_git(
            ["restore", "--source=HEAD", "--staged", "--worktree", "--", *paths],
            cwd=repo_dir,
            action="restore",
            proxy_jump=proxy_jump,
            ssh_key=ssh_key,
        )

    def partition_tracked_paths(
        self,
        repo_dir: Path,
        *,
        paths: list[str],
        proxy_jump: str | None = None,
        ssh_key: Path | None = None,
    ) -> tuple[list[str], list[str]]:
        tracked: list[str] = []
        untracked: list[str] = []
        for path in paths:
            result = run_command(
                ["git", "ls-files", "--error-unmatch", "--", path],
                cwd=Path(repo_dir).resolve(),
                timeout=self.timeout,
                env=self._build_git_env(proxy_jump=proxy_jump, ssh_key=ssh_key),
                log_path=self._next_log_path("ls-files"),
                secrets=self.secrets,
            )
            if result.returncode == 0:
                tracked.append(path)
            else:
                untracked.append(path)
        return tracked, untracked

    def remove_untracked_paths(self, repo_dir: Path, *, paths: list[str]) -> None:
        repo_root = Path(repo_dir).resolve()
        for path in paths:
            candidate = (repo_root / path).resolve()
            try:
                candidate.relative_to(repo_root)
            except ValueError:
                continue
            if candidate.is_dir():
                shutil.rmtree(candidate)
            elif candidate.exists():
                candidate.unlink()

    def status_clean(self, repo_dir: Path, *, proxy_jump: str | None = None, ssh_key: Path | None = None) -> bool:
        result = self._run_git(["status", "--porcelain"], cwd=repo_dir, action="status", proxy_jump=proxy_jump, ssh_key=ssh_key)
        return result.stdout.strip() == ""

    def head_sha(self, repo_dir: Path, *, proxy_jump: str | None = None, ssh_key: Path | None = None) -> str:
        result = self._run_git(["rev-parse", "HEAD"], cwd=repo_dir, action="head-sha", proxy_jump=proxy_jump, ssh_key=ssh_key)
        return result.stdout.strip()

    def configure_user(
        self,
        repo_dir: Path,
        *,
        name: str,
        email: str,
        proxy_jump: str | None = None,
        ssh_key: Path | None = None,
    ) -> None:
        self._run_git(
            ["config", "user.name", name],
            cwd=repo_dir,
            action="config-user-name",
            proxy_jump=proxy_jump,
            ssh_key=ssh_key,
        )
        self._run_git(
            ["config", "user.email", email],
            cwd=repo_dir,
            action="config-user-email",
            proxy_jump=proxy_jump,
            ssh_key=ssh_key,
        )

    def signing_key(
        self,
        repo_dir: Path,
        key_id: str,
        *,
        proxy_jump: str | None = None,
        ssh_key: Path | None = None,
    ) -> None:
        self._run_git(
            ["config", "user.signingkey", key_id],
            cwd=repo_dir,
            action="config-signing-key",
            proxy_jump=proxy_jump,
            ssh_key=ssh_key,
        )
        self._run_git(
            ["config", "commit.gpgsign", "true"],
            cwd=repo_dir,
            action="config-gpg-sign",
            proxy_jump=proxy_jump,
            ssh_key=ssh_key,
        )

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

    def _git_ref_exists(
        self,
        repo_dir: Path,
        ref: str,
        *,
        proxy_jump: str | None = None,
        ssh_key: Path | None = None,
    ) -> bool:
        result = run_command(
            ["git", "show-ref", "--verify", "--quiet", ref],
            cwd=Path(repo_dir).resolve(),
            timeout=self.timeout,
            env=self._build_git_env(proxy_jump=proxy_jump, ssh_key=ssh_key),
            log_path=self._next_log_path("show-ref"),
            secrets=self.secrets,
        )
        return result.returncode == 0

    def _build_git_env(self, *, proxy_jump: str | None, ssh_key: Path | None) -> dict[str, str] | None:
        resolved_proxy_jump = proxy_jump if proxy_jump is not None else self.proxy_jump
        resolved_ssh_key = ssh_key if ssh_key is not None else self.ssh_key
        ssh_parts = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
        if resolved_proxy_jump:
            ssh_parts.extend(["-J", resolved_proxy_jump])
        if resolved_ssh_key:
            ssh_parts.extend(["-i", str(Path(resolved_ssh_key).resolve())])
        if len(ssh_parts) == 5:
            return None
        return {"GIT_SSH_COMMAND": shlex.join(ssh_parts)}

    def _next_log_path(self, action: str) -> Path:
        self._command_index += 1
        return Path(self.log_dir).resolve() / f"{self._command_index:03d}-{action}.log"
