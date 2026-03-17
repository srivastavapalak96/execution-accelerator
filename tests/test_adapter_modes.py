from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from execution_accelerator.adapters import ComplexRemediationAdapter
from execution_accelerator.schemas import AffectedRepository, ExecutionMode, Severity, VulnerabilityDetails


def build_vulnerability_details() -> VulnerabilityDetails:
    return VulnerabilityDetails(
        package_name="org.example:legacy-json",
        installed_version="1.2.3",
        fixed_version="1.2.4",
        summary="Execution mode test vulnerability",
        severity=Severity.HIGH,
        affected_repositories=[AffectedRepository(name="payments-service", manifest_path="pom.xml")],
    )


def test_live_mode_remaining_adapters_fail_fast_until_implemented() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"

    live_calls: list[Callable[[], object]] = [
        lambda: ComplexRemediationAdapter(
            artifact_fixture_path=fixture_dir / "complex_artifacts.json",
            mode=ExecutionMode.LIVE,
        ).load_artifact_candidates(),
    ]

    for live_call in live_calls:
        with pytest.raises(NotImplementedError, match="EA_MODE=live"):
            live_call()
