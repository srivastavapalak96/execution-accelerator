from __future__ import annotations

from pathlib import Path
import subprocess

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
    assert len(result.checks) == 3


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


def test_validation_adapter_runs_live_verify_and_parses_surefire_reports(tmp_path: Path) -> None:
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

    assert result.status == "passed"
    assert result.checks[0].name == "compile"
    assert result.checks[1].name == "unit-tests"
    assert "3 tests" in (result.checks[1].details or "")
    assert result.checks[2].name == "security"
    assert "1.2.4" in (result.checks[2].details or "")


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
    assert result.checks[-1].name == "security"
    assert result.checks[-1].status == "failed"
