from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
import http.server
import httpx
import os
from pathlib import Path
import subprocess
import socketserver
import threading

from execution_accelerator.execution import GitRunner, MavenRunner
import pytest

from execution_accelerator.adapters import (
    ValidationAdapter,
    ValidationConfigurationError,
)
from execution_accelerator.config import load_runtime_config
from execution_accelerator.schemas import ExecutionMode, MavenDependencyKind, MavenExecutionPlan, MavenVerification, Severity, VulnerabilityDetails


def test_validation_adapter_loads_validation_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixture_dir / "validation_result.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixture_dir / "rollback_plan.json"))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = ValidationAdapter.from_runtime_config(config)

    result = adapter.load_validation_result(repository="payments-service")

    assert result.status == "passed"
    assert len(result.checks) == 4
    assert result.checks[-1].name == "license-scan"


def test_validation_adapter_loads_rollback_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixture_dir / "validation_result.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixture_dir / "rollback_plan.json"))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = ValidationAdapter.from_runtime_config(config)

    plan = adapter.load_rollback_plan(repository="payments-service")

    assert plan.status == "applied"
    assert plan.files_to_restore[0] == "pom.xml"


def test_validation_adapter_requires_configuration() -> None:
    adapter = ValidationAdapter()

    with pytest.raises(ValidationConfigurationError):
        adapter.load_validation_result(repository="payments-service")


def test_validation_adapter_from_runtime_config_uses_metadata_base_and_license_denylist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixture_dir / "validation_result.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixture_dir / "rollback_plan.json"))
    monkeypatch.setenv("EA_MAVEN_METADATA_BASE", "https://mirror.example.test/maven2")
    monkeypatch.setenv("EA_LICENSE_DENYLIST", "GPL, LGPL")
    monkeypatch.setenv("EA_LICENSE_ALLOWLIST", "Apache, MIT")
    config = load_runtime_config(repo_root=tmp_path)

    adapter = ValidationAdapter.from_runtime_config(config)

    assert adapter.maven_runner is not None
    assert adapter.maven_runner.metadata_base_url == "https://mirror.example.test/maven2"
    assert adapter.license_denylist == ("GPL", "LGPL")
    assert adapter.license_allowlist == ("Apache", "MIT")


def test_validation_adapter_runs_live_verify_and_parses_surefire_reports(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    pom_root = tmp_path / "pom-repo"
    pom_file = pom_root / "org" / "example" / "legacy-json" / "1.2.4" / "legacy-json-1.2.4.pom"
    pom_file.parent.mkdir(parents=True, exist_ok=True)
    pom_file.write_text(
        """
        <project xmlns="http://maven.apache.org/POM/4.0.0">
          <licenses>
            <license>
              <name>Apache License, Version 2.0</name>
            </license>
          </licenses>
        </project>
        """
    )
    wrapper = repo_dir / "mvnw"
    wrapper.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "if [ \"$1\" = \"dependency:tree\" ]; then",
                "  printf '[INFO] org.example:payments-service:jar:1.0.0\\n'",
                "  printf '[INFO] +- org.example:legacy-json:jar:1.2.4:compile\\n'",
                "  exit 0",
                "fi",
                "mkdir -p target/surefire-reports",
                "cat <<'EOF' > target/surefire-reports/TEST-demo.xml",
                '<testsuite name="demo" tests="3" failures="0" errors="0" skipped="1" />',
                "EOF",
                "echo '[INFO] BUILD SUCCESS'",
            ]
        )
        + "\n"
    )
    wrapper.chmod(0o755)
    with serve_directory(pom_root) as base_url:
        adapter = ValidationAdapter(
            mode=ExecutionMode.LIVE,
            maven_runner=MavenRunner(log_dir=tmp_path / "logs", metadata_base_url=base_url),
        )

        result = adapter.load_validation_result(
            repository="payments-service",
            workspace_path=repo_dir,
            execution_plan=MavenExecutionPlan(
                repository="payments-service",
                command=["./mvnw"],
                root_pom_path=str(repo_dir / "pom.xml"),
                uses_wrapper=True,
            ),
            vulnerability_details=VulnerabilityDetails(
                package_name="org.example:legacy-json",
                installed_version="1.2.3",
                fixed_version="1.2.4",
                summary="Upgrade legacy-json",
                severity=Severity.HIGH,
            ),
            maven_verification=MavenVerification(
                package_name="org.example:legacy-json",
                current_version="1.2.3",
                target_version="1.2.4",
                dependency_kind=MavenDependencyKind.DIRECT,
                resolver_note="Resolved to 1.2.4.",
            ),
        )

    assert result.status == "passed"
    assert result.checks[0].name == "compile"
    assert result.checks[1].name == "unit-tests"
    assert "3 tests" in (result.checks[1].details or "")
    assert result.checks[2].name == "security-scan"
    assert "1.2.4" in (result.checks[2].details or "")
    assert result.checks[3].name == "license-scan"
    assert "Apache License, Version 2.0" in (result.checks[3].details or "")


def test_validation_adapter_fails_live_license_scan_when_denylisted_license_is_detected(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    pom_root = tmp_path / "pom-repo"
    pom_file = pom_root / "org" / "example" / "legacy-json" / "1.2.4" / "legacy-json-1.2.4.pom"
    pom_file.parent.mkdir(parents=True, exist_ok=True)
    pom_file.write_text(
        """
        <project xmlns="http://maven.apache.org/POM/4.0.0">
          <licenses>
            <license>
              <name>GNU General Public License v3.0</name>
            </license>
          </licenses>
        </project>
        """
    )
    wrapper = repo_dir / "mvnw"
    wrapper.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "if [ \"$1\" = \"dependency:tree\" ]; then",
                "  printf '[INFO] org.example:payments-service:jar:1.0.0\\n'",
                "  printf '[INFO] +- org.example:legacy-json:jar:1.2.4:compile\\n'",
                "  exit 0",
                "fi",
                "echo '[INFO] BUILD SUCCESS'",
            ]
        )
        + "\n"
    )
    wrapper.chmod(0o755)

    with serve_directory(pom_root) as base_url:
        adapter = ValidationAdapter(
            mode=ExecutionMode.LIVE,
            maven_runner=MavenRunner(log_dir=tmp_path / "logs", metadata_base_url=base_url),
            license_denylist=("GPL",),
        )

        result = adapter.load_validation_result(
            repository="payments-service",
            workspace_path=repo_dir,
            execution_plan=MavenExecutionPlan(
                repository="payments-service",
                command=["./mvnw"],
                root_pom_path=str(repo_dir / "pom.xml"),
                uses_wrapper=True,
            ),
            vulnerability_details=VulnerabilityDetails(
                package_name="org.example:legacy-json",
                installed_version="1.2.3",
                fixed_version="1.2.4",
                summary="Upgrade legacy-json",
                severity=Severity.HIGH,
            ),
            maven_verification=MavenVerification(
                package_name="org.example:legacy-json",
                current_version="1.2.3",
                target_version="1.2.4",
                dependency_kind=MavenDependencyKind.DIRECT,
                resolver_note="Resolved to 1.2.4.",
            ),
        )

    assert result.status == "failed"
    assert result.checks[-1].name == "license-scan"
    assert result.checks[-1].status == "failed"
    assert "GNU General Public License v3.0" in (result.checks[-1].details or "")


def test_validation_adapter_passes_live_license_scan_when_license_is_allowlisted(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    pom_root = tmp_path / "pom-repo"
    pom_file = pom_root / "org" / "example" / "legacy-json" / "1.2.4" / "legacy-json-1.2.4.pom"
    pom_file.parent.mkdir(parents=True, exist_ok=True)
    pom_file.write_text(
        """
        <project xmlns="http://maven.apache.org/POM/4.0.0">
          <licenses>
            <license>
              <name>Apache License, Version 2.0</name>
            </license>
          </licenses>
        </project>
        """
    )
    wrapper = repo_dir / "mvnw"
    wrapper.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "if [ \"$1\" = \"dependency:tree\" ]; then",
                "  printf '[INFO] org.example:payments-service:jar:1.0.0\\n'",
                "  printf '[INFO] +- org.example:legacy-json:jar:1.2.4:compile\\n'",
                "  exit 0",
                "fi",
                "echo '[INFO] BUILD SUCCESS'",
            ]
        )
        + "\n"
    )
    wrapper.chmod(0o755)
    with serve_directory(pom_root) as base_url:
        adapter = ValidationAdapter(
            mode=ExecutionMode.LIVE,
            maven_runner=MavenRunner(log_dir=tmp_path / "logs", metadata_base_url=base_url),
            license_allowlist=("Apache", "MIT"),
        )

        result = adapter.load_validation_result(
            repository="payments-service",
            workspace_path=repo_dir,
            execution_plan=MavenExecutionPlan(
                repository="payments-service",
                command=["./mvnw"],
                root_pom_path=str(repo_dir / "pom.xml"),
                uses_wrapper=True,
            ),
            vulnerability_details=VulnerabilityDetails(
                package_name="org.example:legacy-json",
                installed_version="1.2.3",
                fixed_version="1.2.4",
                summary="Upgrade legacy-json",
                severity=Severity.HIGH,
            ),
            maven_verification=MavenVerification(
                package_name="org.example:legacy-json",
                current_version="1.2.3",
                target_version="1.2.4",
                dependency_kind=MavenDependencyKind.DIRECT,
                resolver_note="Resolved to 1.2.4.",
            ),
        )

    assert result.status == "passed"
    assert result.checks[-1].name == "license-scan"
    assert result.checks[-1].status == "passed"
    assert "allowlist [Apache, MIT]" in (result.checks[-1].details or "")


def test_validation_adapter_fails_live_license_scan_when_license_is_outside_allowlist(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    pom_root = tmp_path / "pom-repo"
    pom_file = pom_root / "org" / "example" / "legacy-json" / "1.2.4" / "legacy-json-1.2.4.pom"
    pom_file.parent.mkdir(parents=True, exist_ok=True)
    pom_file.write_text(
        """
        <project xmlns="http://maven.apache.org/POM/4.0.0">
          <licenses>
            <license>
              <name>Mozilla Public License 2.0</name>
            </license>
          </licenses>
        </project>
        """
    )
    wrapper = repo_dir / "mvnw"
    wrapper.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "if [ \"$1\" = \"dependency:tree\" ]; then",
                "  printf '[INFO] org.example:payments-service:jar:1.0.0\\n'",
                "  printf '[INFO] +- org.example:legacy-json:jar:1.2.4:compile\\n'",
                "  exit 0",
                "fi",
                "echo '[INFO] BUILD SUCCESS'",
            ]
        )
        + "\n"
    )
    wrapper.chmod(0o755)
    with serve_directory(pom_root) as base_url:
        adapter = ValidationAdapter(
            mode=ExecutionMode.LIVE,
            maven_runner=MavenRunner(log_dir=tmp_path / "logs", metadata_base_url=base_url),
            license_allowlist=("Apache", "MIT"),
        )

        result = adapter.load_validation_result(
            repository="payments-service",
            workspace_path=repo_dir,
            execution_plan=MavenExecutionPlan(
                repository="payments-service",
                command=["./mvnw"],
                root_pom_path=str(repo_dir / "pom.xml"),
                uses_wrapper=True,
            ),
            vulnerability_details=VulnerabilityDetails(
                package_name="org.example:legacy-json",
                installed_version="1.2.3",
                fixed_version="1.2.4",
                summary="Upgrade legacy-json",
                severity=Severity.HIGH,
            ),
            maven_verification=MavenVerification(
                package_name="org.example:legacy-json",
                current_version="1.2.3",
                target_version="1.2.4",
                dependency_kind=MavenDependencyKind.DIRECT,
                resolver_note="Resolved to 1.2.4.",
            ),
        )

    assert result.status == "failed"
    assert result.checks[-1].name == "license-scan"
    assert result.checks[-1].status == "failed"
    assert "outside allowlist" in (result.checks[-1].details or "")


def test_validation_adapter_marks_transient_license_fetch_failures_as_failed_when_policy_is_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    wrapper = repo_dir / "mvnw"
    wrapper.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "if [ \"$1\" = \"dependency:tree\" ]; then",
                "  printf '[INFO] org.example:payments-service:jar:1.0.0\\n'",
                "  printf '[INFO] +- org.example:legacy-json:jar:1.2.4:compile\\n'",
                "  exit 0",
                "fi",
                "echo '[INFO] BUILD SUCCESS'",
            ]
        )
        + "\n"
    )
    wrapper.chmod(0o755)
    maven_runner = MavenRunner(log_dir=tmp_path / "logs", metadata_base_url="https://mirror.example.test/maven2")
    monkeypatch.setattr(
        maven_runner,
        "fetch_pom_licenses",
        lambda coordinate: (_ for _ in ()).throw(httpx.ConnectError("repository mirror timeout")),
    )
    adapter = ValidationAdapter(
        mode=ExecutionMode.LIVE,
        maven_runner=maven_runner,
        license_allowlist=("Apache", "MIT"),
    )

    result = adapter.load_validation_result(
        repository="payments-service",
        workspace_path=repo_dir,
        execution_plan=MavenExecutionPlan(
            repository="payments-service",
            command=["./mvnw"],
            root_pom_path=str(repo_dir / "pom.xml"),
            uses_wrapper=True,
        ),
        vulnerability_details=VulnerabilityDetails(
            package_name="org.example:legacy-json",
            installed_version="1.2.3",
            fixed_version="1.2.4",
            summary="Upgrade legacy-json",
            severity=Severity.HIGH,
        ),
        maven_verification=MavenVerification(
            package_name="org.example:legacy-json",
            current_version="1.2.3",
            target_version="1.2.4",
            dependency_kind=MavenDependencyKind.DIRECT,
            resolver_note="Resolved to 1.2.4.",
        ),
    )

    assert result.status == "failed"
    assert result.summary == "Live validation encountered transient dependency license inspection failures."
    assert result.checks[-1].name == "license-scan"
    assert result.checks[-1].status == "failed"
    assert "transient metadata fetch failures" in (result.checks[-1].details or "")


def test_validation_adapter_reports_live_verify_failure(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    wrapper = repo_dir / "mvnw"
    wrapper.write_text("#!/bin/sh\necho '[ERROR] verify failed' >&2\nexit 1\n")
    wrapper.chmod(0o755)
    adapter = ValidationAdapter(
        mode=ExecutionMode.LIVE,
        maven_runner=MavenRunner(log_dir=tmp_path / "logs"),
    )

    result = adapter.load_validation_result(
        repository="payments-service",
        workspace_path=repo_dir,
        execution_plan=MavenExecutionPlan(
            repository="payments-service",
            command=["./mvnw"],
            root_pom_path=str(repo_dir / "pom.xml"),
            uses_wrapper=True,
        ),
    )

    assert result.status == "failed"
    assert result.checks[0].status == "failed"


def test_validation_adapter_applies_live_rollback(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    pom_path = repo_dir / "pom.xml"
    pom_path.write_text("<project><version>1</version></project>\n")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "add", "pom.xml"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_dir, check=True, capture_output=True)
    pom_path.write_text("<project><version>2</version></project>\n")
    adapter = ValidationAdapter(
        mode=ExecutionMode.LIVE,
        git_runner=GitRunner(log_dir=tmp_path / "logs"),
    )

    plan = adapter.load_rollback_plan(
        repository="payments-service",
        workspace_path=repo_dir,
        modified_files=[str(pom_path)],
    )

    assert plan.status == "applied"
    assert plan.files_to_restore == ["pom.xml"]
    assert pom_path.read_text() == "<project><version>1</version></project>\n"


def test_validation_adapter_removes_untracked_files_during_live_rollback(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    pom_path = repo_dir / "pom.xml"
    pom_path.write_text("<project><version>1</version></project>\n")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "add", "pom.xml"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_dir, check=True, capture_output=True)
    scaffold_path = repo_dir / "src/main/java/com/example/payments/LegacyJsonAdapter.java"
    scaffold_path.parent.mkdir(parents=True, exist_ok=True)
    scaffold_path.write_text("package com.example.payments;\n\npublic final class LegacyJsonAdapter {}\n")
    adapter = ValidationAdapter(
        mode=ExecutionMode.LIVE,
        git_runner=GitRunner(log_dir=tmp_path / "logs"),
    )

    plan = adapter.load_rollback_plan(
        repository="payments-service",
        workspace_path=repo_dir,
        modified_files=[str(scaffold_path)],
    )

    assert plan.status == "applied"
    assert plan.files_to_restore == ["src/main/java/com/example/payments/LegacyJsonAdapter.java"]
    assert scaffold_path.exists() is False


def test_validation_adapter_passes_proxy_jump_and_ssh_key_to_git_runner(tmp_path: Path) -> None:
    calls: list[tuple[str, str | None, Path | None]] = []

    class CapturingGitRunner:
        def partition_tracked_paths(self, repo_dir: Path, *, paths: list[str], proxy_jump: str | None = None, ssh_key: Path | None = None) -> tuple[list[str], list[str]]:
            del repo_dir, paths
            calls.append(("partition_tracked_paths", proxy_jump, ssh_key))
            return (["pom.xml"], [])

        def restore_paths(self, repo_dir: Path, *, paths: list[str], proxy_jump: str | None = None, ssh_key: Path | None = None) -> None:
            del repo_dir, paths
            calls.append(("restore_paths", proxy_jump, ssh_key))

        def remove_untracked_paths(self, repo_dir: Path, *, paths: list[str]) -> None:
            del repo_dir, paths
            calls.append(("remove_untracked_paths", None, None))

    ssh_key = tmp_path / "id_ed25519"
    adapter = ValidationAdapter(
        mode=ExecutionMode.LIVE,
        git_runner=CapturingGitRunner(),  # type: ignore[arg-type]
    )

    plan = adapter.load_rollback_plan(
        repository="payments-service",
        workspace_path=tmp_path / "workspace",
        modified_files=[str(tmp_path / "workspace" / "pom.xml")],
        proxy_jump="bastion.internal",
        ssh_key=ssh_key,
    )

    assert plan.status == "applied"
    assert [call[0] for call in calls] == ["partition_tracked_paths", "restore_paths"]
    assert all(call[1] == "bastion.internal" for call in calls)
    assert all(call[2] == ssh_key for call in calls)


def test_validation_adapter_reports_live_security_rescan_failure(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    wrapper = repo_dir / "mvnw"
    wrapper.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "if [ \"$1\" = \"dependency:tree\" ]; then",
                "  printf '[INFO] org.example:payments-service:jar:1.0.0\\n'",
                "  printf '[INFO] +- org.example:legacy-json:jar:1.2.3:compile\\n'",
                "  exit 0",
                "fi",
                "echo '[INFO] BUILD SUCCESS'",
            ]
        )
        + "\n"
    )
    wrapper.chmod(0o755)
    adapter = ValidationAdapter(
        mode=ExecutionMode.LIVE,
        maven_runner=MavenRunner(log_dir=tmp_path / "logs"),
    )

    result = adapter.load_validation_result(
        repository="payments-service",
        workspace_path=repo_dir,
        execution_plan=MavenExecutionPlan(
            repository="payments-service",
            command=["./mvnw"],
            root_pom_path=str(repo_dir / "pom.xml"),
            uses_wrapper=True,
        ),
        vulnerability_details=VulnerabilityDetails(
            package_name="org.example:legacy-json",
            installed_version="1.2.3",
            fixed_version="1.2.4",
            summary="Upgrade legacy-json",
            severity=Severity.HIGH,
        ),
        maven_verification=MavenVerification(
            package_name="org.example:legacy-json",
            current_version="1.2.3",
            target_version="1.2.4",
            dependency_kind=MavenDependencyKind.DIRECT,
            resolver_note="Resolved to 1.2.4.",
        ),
    )

    assert result.status == "failed"
    security_check = next(check for check in result.checks if check.name == "security-scan")
    assert security_check.status == "failed"


@contextmanager
def serve_directory(directory: Path) -> Iterator[str]:
    previous_cwd = Path.cwd()
    os.chdir(directory)
    try:
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

        with socketserver.TCPServer(("127.0.0.1", 0), QuietHandler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}"
            finally:
                server.shutdown()
                thread.join()
    finally:
        os.chdir(previous_cwd)
