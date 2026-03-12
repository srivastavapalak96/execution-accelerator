from __future__ import annotations

from pathlib import Path

import pytest

from execution_accelerator.adapters import (
    ValidationAdapter,
    ValidationConfigurationError,
)
from execution_accelerator.config import load_runtime_config


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
