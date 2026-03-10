from __future__ import annotations

from pathlib import Path

import pytest

from execution_accelerator.adapters import (
    ComplexRemediationAdapter,
    ComplexRemediationConfigurationError,
)
from execution_accelerator.config import load_runtime_config
from execution_accelerator.schemas import CompatibilityRisk


def test_complex_remediation_adapter_loads_artifact_candidates(tmp_path, monkeypatch) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = ComplexRemediationAdapter.from_runtime_config(config)

    candidates = adapter.load_artifact_candidates()

    assert len(candidates) == 2
    assert candidates[0].coordinate.version == "2.0.0"


def test_complex_remediation_adapter_loads_compatibility_diff(tmp_path, monkeypatch) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixture_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixture_dir / "compatibility_diff.json"))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = ComplexRemediationAdapter.from_runtime_config(config)

    diff = adapter.load_compatibility_diff()

    assert diff.risk == CompatibilityRisk.HIGH
    assert diff.breaking_changes[0].symbol == "org.example.LegacyParser#parse"


def test_complex_remediation_adapter_requires_configuration() -> None:
    adapter = ComplexRemediationAdapter()

    with pytest.raises(ComplexRemediationConfigurationError):
        adapter.load_artifact_candidates()
