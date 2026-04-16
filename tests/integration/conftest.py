"""Integration-test gating and shared fixtures.

The whole package is skipped unless ``EA_INTEGRATION=1`` is set, so it never runs
under the default ``make test`` and never burns CI minutes on real network /
subprocess work.

Tests in this package may shell out to ``mvn`` / ``git`` and may make real HTTP
calls (e.g., OSV). Each test must clean up after itself: workspaces go under
``tmp_path``, branches must not leak to shared remotes, and any temp git repos
must be initialized inside ``tmp_path`` too.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

INTEGRATION_ENV_VAR = "EA_INTEGRATION"
SAMPLE_PROJECT_ROOT = Path(__file__).parent / "sample_projects" / "simple-maven"


_INTEGRATION_PACKAGE_DIR = Path(__file__).parent.resolve()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip integration-package tests unless EA_INTEGRATION=1.

    pytest passes the *entire* test session's items list to every conftest's
    collection hook, so we must restrict our marker to tests that actually live
    under ``tests/integration/`` — otherwise we would skip the whole unit suite.
    """

    if os.getenv(INTEGRATION_ENV_VAR) == "1":
        return
    skip_marker = pytest.mark.skip(
        reason=f"Integration tests are gated; set {INTEGRATION_ENV_VAR}=1 to run."
    )
    for item in items:
        item_path = Path(getattr(item, "path", item.fspath)).resolve()
        try:
            item_path.relative_to(_INTEGRATION_PACKAGE_DIR)
        except ValueError:
            continue
        item.add_marker(skip_marker)


@pytest.fixture
def sample_maven_project(tmp_path: Path) -> Path:
    """Copy the checked-in sample Maven project to a tmp workspace.

    Returns the workspace root. Each test gets its own copy so tests cannot
    pollute each other via stale ``target/`` directories or mutated POMs.
    """

    if not SAMPLE_PROJECT_ROOT.exists():
        pytest.fail(
            f"Sample Maven project missing at {SAMPLE_PROJECT_ROOT}; "
            "tests/integration/sample_projects/simple-maven/ should be checked in."
        )
    destination = tmp_path / "simple-maven"
    shutil.copytree(SAMPLE_PROJECT_ROOT, destination)
    return destination


@pytest.fixture
def java_home() -> str | None:
    """Resolve ``JAVA_HOME`` for ``mvn`` if not already set in the environment.

    macOS users often rely on ``/usr/libexec/java_home``; this fixture lets tests
    inject the resolved value into the subprocess env. Returns None if no JDK is
    available, in which case dependent tests should ``pytest.skip``.
    """

    if "JAVA_HOME" in os.environ:
        return os.environ["JAVA_HOME"]
    java_home_helper = Path("/usr/libexec/java_home")
    if not java_home_helper.exists():
        return None
    import subprocess

    try:
        result = subprocess.run(
            [str(java_home_helper), "-v", "21"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


@pytest.fixture
def temp_git_remote(tmp_path: Path) -> Iterator[Path]:
    """Initialize a bare git repository inside tmp_path for clone-target tests.

    Using a local bare repo means the test does not depend on internet access
    and cannot accidentally interact with a real GitHub remote.
    """

    import subprocess

    bare = tmp_path / "remote.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    yield bare
    # tmp_path is cleaned by pytest automatically; nothing else to do.
