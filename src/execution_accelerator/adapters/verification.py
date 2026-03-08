"""Fixture-backed advisory and Maven verification adapters for Day 4."""

from __future__ import annotations

import json
from pathlib import Path

from execution_accelerator.config import RuntimeConfig
from execution_accelerator.schemas import AdvisoryVerification, MavenVerification, VulnerabilityDetails


class VerificationAdapterError(RuntimeError):
    """Base error for advisory and Maven verification failures."""


class VerificationConfigurationError(VerificationAdapterError):
    """Raised when local verification fixtures are not configured."""


class AdvisoryVerificationMismatchError(VerificationAdapterError):
    """Raised when advisory verification fixture data does not match the requested package."""


class MavenVerificationMismatchError(VerificationAdapterError):
    """Raised when Maven verification fixture data does not match the requested package."""


class AdvisoryVerificationAdapter:
    """Load normalized advisory verification data from a local fixture."""

    def __init__(self, *, fixture_path: Path | None = None) -> None:
        self.fixture_path = fixture_path

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "AdvisoryVerificationAdapter":
        """Create the advisory adapter from runtime configuration."""

        return cls(fixture_path=config.advisory_fixture_path)

    def load_verification(
        self,
        vulnerability_details: VulnerabilityDetails,
        *,
        fixture_path: Path | None = None,
    ) -> AdvisoryVerification:
        """Load advisory verification data for the requested vulnerability."""

        resolved_fixture_path = fixture_path or self.fixture_path
        if resolved_fixture_path is None:
            raise VerificationConfigurationError(
                "Advisory fixture path is not configured. Set EA_ADVISORY_FIXTURE_PATH for local Day 4 verification."
            )

        verification = AdvisoryVerification.model_validate(json.loads(resolved_fixture_path.read_text()))
        if verification.package_name != vulnerability_details.package_name:
            raise AdvisoryVerificationMismatchError(
                "Advisory verification fixture package does not match the requested vulnerability package."
            )

        return verification


class MavenVerificationAdapter:
    """Load Maven verification data from a local fixture."""

    def __init__(self, *, fixture_path: Path | None = None) -> None:
        self.fixture_path = fixture_path

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "MavenVerificationAdapter":
        """Create the Maven verification adapter from runtime configuration."""

        return cls(fixture_path=config.maven_verification_fixture_path)

    def load_verification(
        self,
        vulnerability_details: VulnerabilityDetails,
        *,
        target_version: str,
        fixture_path: Path | None = None,
    ) -> MavenVerification:
        """Load Maven verification data for the selected remediation target."""

        resolved_fixture_path = fixture_path or self.fixture_path
        if resolved_fixture_path is None:
            raise VerificationConfigurationError(
                "Maven verification fixture path is not configured. "
                "Set EA_MAVEN_VERIFICATION_FIXTURE_PATH for local Day 4 verification."
            )

        verification = MavenVerification.model_validate(json.loads(resolved_fixture_path.read_text()))
        if verification.package_name != vulnerability_details.package_name:
            raise MavenVerificationMismatchError(
                "Maven verification fixture package does not match the requested vulnerability package."
            )
        if verification.target_version != target_version:
            raise MavenVerificationMismatchError(
                "Maven verification fixture target version does not match the requested remediation target."
            )

        return verification
