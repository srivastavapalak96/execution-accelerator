from __future__ import annotations

from pathlib import Path
import subprocess

from execution_accelerator.execution import GitRunner


def test_git_runner_clone_and_read_repo_state(tmp_path: Path) -> None:
    source_repo = _create_source_repo(tmp_path / "source")
    _create_branch(source_repo, "release")
    runner = GitRunner(log_dir=tmp_path / "logs")

    cloned_repo = runner.clone(str(source_repo), tmp_path / "clone", branch="main")

    assert (cloned_repo / ".git").is_dir()
    assert runner.current_branch(cloned_repo) == "main"
    assert len(runner.head_sha(cloned_repo)) == 40
    assert runner.status_clean(cloned_repo) is True
    assert sorted(path.name for path in (tmp_path / "logs").iterdir()) == [
        "001-clone.log",
        "002-current-branch.log",
        "003-head-sha.log",
        "004-status.log",
    ]


def test_git_runner_checkout_and_detect_dirty_workspace(tmp_path: Path) -> None:
    source_repo = _create_source_repo(tmp_path / "source")
    _create_branch(source_repo, "release")
    runner = GitRunner(log_dir=tmp_path / "logs")
    cloned_repo = runner.clone(str(source_repo), tmp_path / "clone", branch="main")

    runner.checkout(cloned_repo, "release")
    (cloned_repo / "README.md").write_text("modified\n")

    assert runner.current_branch(cloned_repo) == "release"
    assert runner.status_clean(cloned_repo) is False


def test_git_runner_configures_user_and_signing_settings(tmp_path: Path) -> None:
    source_repo = _create_source_repo(tmp_path / "source")
    runner = GitRunner(log_dir=tmp_path / "logs")
    cloned_repo = runner.clone(str(source_repo), tmp_path / "clone", branch="main")

    runner.configure_user(cloned_repo, name="Execution Bot", email="bot@example.com")
    runner.signing_key(cloned_repo, "ABC123")

    assert _git_output(cloned_repo, "config", "--get", "user.name") == "Execution Bot"
    assert _git_output(cloned_repo, "config", "--get", "user.email") == "bot@example.com"
    assert _git_output(cloned_repo, "config", "--get", "user.signingkey") == "ABC123"
    assert _git_output(cloned_repo, "config", "--get", "commit.gpgsign") == "true"


def test_git_runner_partitions_and_removes_untracked_paths(tmp_path: Path) -> None:
    source_repo = _create_source_repo(tmp_path / "source")
    runner = GitRunner(log_dir=tmp_path / "logs")
    cloned_repo = runner.clone(str(source_repo), tmp_path / "clone", branch="main")
    tracked_file = cloned_repo / "README.md"
    untracked_file = cloned_repo / "notes.txt"
    untracked_file.write_text("temporary\n")

    tracked, untracked = runner.partition_tracked_paths(
        cloned_repo,
        paths=["README.md", "notes.txt"],
    )
    runner.remove_untracked_paths(cloned_repo, paths=untracked)

    assert tracked == ["README.md"]
    assert untracked == ["notes.txt"]
    assert tracked_file.exists() is True
    assert untracked_file.exists() is False


def _create_source_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path.parent, "init", "--initial-branch=main", str(path))
    _git(path, "config", "user.name", "Fixture User")
    _git(path, "config", "user.email", "fixture@example.com")
    (path / "README.md").write_text("hello\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "Initial commit")
    return path


def _create_branch(path: Path, branch: str) -> None:
    _git(path, "checkout", "-b", branch)
    (path / f"{branch}.txt").write_text(f"{branch}\n")
    _git(path, "add", f"{branch}.txt")
    _git(path, "commit", "-m", f"Add {branch}")
    _git(path, "checkout", "main")


def _git_output(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _git(path: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
