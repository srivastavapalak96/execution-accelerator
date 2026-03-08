from __future__ import annotations

from pathlib import Path

import pytest

from execution_accelerator.adapters import (
    AdvisoryVerificationAdapter,
    AdvisoryVerificationMismatchError,
    MavenVerificationAdapter,
    MavenVerificationMismatchError,
    VerificationConfigurationError,
)
from execution_accelerator.config import load_runtime_config
from execution_accelerator.schemas import AffectedRepository, Severity, VulnerabilityDetails, VerificationStatus


def build_vulnerability_details() -> VulnerabilityDetails:
    return VulnerabilityDetails(
        package_name="org.example:legacy-json",
        installed_version="1.2.3",
        fixed_version="1.2.4",
        summary="Verification adapter test vulnerability",
        cve_id="CVE-2026-12345",
        severity=Severity.HIGH,
        affected_repositories=[
            AffectedRepository(name="payments-service", manifest_path="pom.xml")
        ],
    )


def test_advisory_verification_adapter_loads_fixture(tmp_path, monkeypatch) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "advisory_verification.json"
    monkeypatch.setenv("EA_ADVISORY_FIXTURE_PATH", str(fixture_path))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = AdvisoryVerificationAdapter.from_runtime_config(config)

    verification = adapter.load_verification(build_vulnerability_details())

    assert verification.status == VerificationStatus.VERIFIED
    assert verification.recommended_fix_version == "1.2.4"


def test_maven_verification_adapter_loads_fixture(tmp_path, monkeypatch) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "maven_verification.json"
    monkeypatch.setenv("EA_MAVEN_VERIFICATION_FIXTURE_PATH", str(fixture_path))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = MavenVerificationAdapter.from_runtime_config(config)

    verification = adapter.load_verification(
        build_vulnerability_details(),
        target_version="1.2.4",
    )

    assert verification.status == VerificationStatus.VERIFIED
    assert verification.target_version == "1.2.4"


def test_advisory_verification_adapter_requires_configuration() -> None:
    adapter = AdvisoryVerificationAdapter()

    with pytest.raises(VerificationConfigurationError):
        adapter.load_verification(build_vulnerability_details())


def test_maven_verification_adapter_rejects_target_mismatch() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "maven_verification.json"
    adapter = MavenVerificationAdapter(fixture_path=fixture_path)

    with pytest.raises(MavenVerificationMismatchError):
        adapter.load_verification(build_vulnerability_details(), target_version="2.0.0")


def test_advisory_verification_adapter_rejects_package_mismatch() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "advisory_verification.json"
    adapter = AdvisoryVerificationAdapter(fixture_path=fixture_path)
    details = build_vulnerability_details().model_copy(update={"package_name": "org.example:other-lib"})

    with pytest.raises(AdvisoryVerificationMismatchError):
        adapter.load_verification(details)
