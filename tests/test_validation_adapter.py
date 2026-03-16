from __future__ import annotations

from pathlib import Path

from execution_accelerator.execution import MavenRunner
import pytest

from execution_accelerator.adapters import (
    ValidationAdapter,
    ValidationConfigurationError,
)
from execution_accelerator.config import load_runtime_config
from execution_accelerator.schemas import ExecutionMode, MavenExecutionPlan


def test_validation_adapter_loads_validation_result(tmp_path, monkeypatch) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixture_dir / "validation_result.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixture_dir / "rollback_plan.json"))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = ValidationAdapter.from_runtime_config(config)

    result = adapter.load_validation_result(repository="payments-service")

    assert result.status == "passed"
    assert len(result.checks) == 3


def test_validation_adapter_loads_rollback_plan(tmp_path, monkeypatch) -> None:
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
    )

    assert result.status == "passed"
    assert result.checks[0].name == "compile"
    assert result.checks[1].name == "unit-tests"
    assert "3 tests" in (result.checks[1].details or "")


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
