from __future__ import annotations

from pathlib import Path

import pytest

from execution_accelerator.adapters import (
    ComplexRemediationAdapter,
    ComplexRemediationConfigurationError,
)
from execution_accelerator.config import load_runtime_config
from execution_accelerator.schemas import CompatibilityRisk, ComplexMigrationTactic


def test_complex_remediation_adapter_loads_artifact_candidates(tmp_path, monkeypatch) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixture_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixture_dir / "code_change_plan.json"))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = ComplexRemediationAdapter.from_runtime_config(config)

    candidates = adapter.load_artifact_candidates()

    assert len(candidates) == 2
    assert candidates[0].coordinate.version == "2.0.0"


def test_complex_remediation_adapter_loads_compatibility_diff(tmp_path, monkeypatch) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixture_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixture_dir / "code_change_plan.json"))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = ComplexRemediationAdapter.from_runtime_config(config)

    diff = adapter.load_compatibility_diff()

    assert diff.risk == CompatibilityRisk.HIGH
    assert diff.breaking_changes[0].symbol == "org.example.LegacyParser#parse"


def test_complex_remediation_adapter_loads_execution_scaffold_fixtures(tmp_path, monkeypatch) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixture_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixture_dir / "code_change_plan.json"))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = ComplexRemediationAdapter.from_runtime_config(config)

    decompiled_artifacts = adapter.load_decompiled_artifacts()
    symbol_mappings = adapter.load_symbol_mappings()
    code_change_plan = adapter.load_code_change_plan()

    assert decompiled_artifacts[0].symbol_count == 184
    assert symbol_mappings[0].confidence == 0.94
    assert len(code_change_plan.target_files) == 2


def test_complex_remediation_adapter_selects_adapter_shim_for_mixed_breaking_changes(
    tmp_path, monkeypatch
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = ComplexRemediationAdapter.from_runtime_config(config)

    tactic, rationale = adapter.select_migration_tactic(adapter.load_compatibility_diff())

    assert tactic == ComplexMigrationTactic.ADAPTER_SHIM
    assert "compatibility adapter" in rationale


def test_complex_remediation_adapter_requires_configuration() -> None:
    adapter = ComplexRemediationAdapter()

    with pytest.raises(ComplexRemediationConfigurationError):
        adapter.load_artifact_candidates()
