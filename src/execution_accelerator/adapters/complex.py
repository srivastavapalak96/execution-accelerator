"""Fixture-backed artifact and compatibility helpers for the Day 7 complex lane."""

from __future__ import annotations

import json
from pathlib import Path

from execution_accelerator.config import RuntimeConfig
from execution_accelerator.schemas import ArtifactCandidate, CompatibilityDiffResult


class ComplexRemediationAdapterError(RuntimeError):
    """Base error for Day 7 complex remediation helpers."""


class ComplexRemediationConfigurationError(ComplexRemediationAdapterError):
    """Raised when complex-lane fixture configuration is missing."""


class ComplexRemediationAdapter:
    """Load fixture-backed artifact candidates and compatibility diffs."""

    def __init__(
        self,
        *,
        artifact_fixture_path: Path | None = None,
        compatibility_diff_fixture_path: Path | None = None,
    ) -> None:
        self.artifact_fixture_path = artifact_fixture_path
        self.compatibility_diff_fixture_path = compatibility_diff_fixture_path

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "ComplexRemediationAdapter":
        """Create the complex adapter from runtime configuration."""

        return cls(
            artifact_fixture_path=config.complex_artifact_fixture_path,
            compatibility_diff_fixture_path=config.compatibility_diff_fixture_path,
        )

    def load_artifact_candidates(self, *, fixture_path: Path | None = None) -> list[ArtifactCandidate]:
        """Load candidate artifacts for the complex remediation lane."""

        resolved_fixture_path = fixture_path or self.artifact_fixture_path
        if resolved_fixture_path is None:
            raise ComplexRemediationConfigurationError(
                "Complex artifact fixture path is not configured. "
                "Set EA_COMPLEX_ARTIFACT_FIXTURE_PATH for local Day 7 remediation."
            )

        payload = json.loads(resolved_fixture_path.read_text())
        return [ArtifactCandidate.model_validate(item) for item in payload["artifact_candidates"]]

    def load_compatibility_diff(self, *, fixture_path: Path | None = None) -> CompatibilityDiffResult:
        """Load the placeholder compatibility diff result."""

        resolved_fixture_path = fixture_path or self.compatibility_diff_fixture_path
        if resolved_fixture_path is None:
            raise ComplexRemediationConfigurationError(
                "Compatibility diff fixture path is not configured. "
                "Set EA_COMPATIBILITY_DIFF_FIXTURE_PATH for local Day 7 remediation."
            )

        return CompatibilityDiffResult.model_validate(json.loads(resolved_fixture_path.read_text()))
