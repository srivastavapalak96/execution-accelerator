"""Fixture-backed artifact and compatibility helpers for the Day 7 complex lane."""

from __future__ import annotations

import json
from pathlib import Path

from execution_accelerator.adapters._mode import require_fixture_mode
from execution_accelerator.config import RuntimeConfig
from execution_accelerator.schemas import (
    ExecutionMode,
    ArtifactCandidate,
    ComplexCodeChangePlan,
    ComplexMigrationTactic,
    CompatibilityDiffResult,
    DecompiledArtifactSummary,
    SymbolMappingEntry,
)


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
        decompiled_artifact_fixture_path: Path | None = None,
        symbol_mapping_fixture_path: Path | None = None,
        code_change_plan_fixture_path: Path | None = None,
        mode: ExecutionMode = ExecutionMode.FIXTURE,
    ) -> None:
        self.artifact_fixture_path = artifact_fixture_path
        self.compatibility_diff_fixture_path = compatibility_diff_fixture_path
        self.decompiled_artifact_fixture_path = decompiled_artifact_fixture_path
        self.symbol_mapping_fixture_path = symbol_mapping_fixture_path
        self.code_change_plan_fixture_path = code_change_plan_fixture_path
        self.mode = mode

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "ComplexRemediationAdapter":
        """Create the complex adapter from runtime configuration."""

        return cls(
            artifact_fixture_path=config.complex_artifact_fixture_path,
            compatibility_diff_fixture_path=config.compatibility_diff_fixture_path,
            decompiled_artifact_fixture_path=config.decompiled_artifact_fixture_path,
            symbol_mapping_fixture_path=config.symbol_mapping_fixture_path,
            code_change_plan_fixture_path=config.code_change_plan_fixture_path,
            mode=config.execution_mode,
        )

    def load_artifact_candidates(self, *, fixture_path: Path | None = None) -> list[ArtifactCandidate]:
        """Load candidate artifacts for the complex remediation lane."""

        require_fixture_mode(self.mode, capability="Complex live artifact analysis")
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

        require_fixture_mode(self.mode, capability="Complex live compatibility diffing")
        resolved_fixture_path = fixture_path or self.compatibility_diff_fixture_path
        if resolved_fixture_path is None:
            raise ComplexRemediationConfigurationError(
                "Compatibility diff fixture path is not configured. "
                "Set EA_COMPATIBILITY_DIFF_FIXTURE_PATH for local Day 7 remediation."
            )

        return CompatibilityDiffResult.model_validate(json.loads(resolved_fixture_path.read_text()))

    def load_decompiled_artifacts(
        self,
        *,
        fixture_path: Path | None = None,
    ) -> list[DecompiledArtifactSummary]:
        """Load placeholder decompiled-artifact summaries."""

        require_fixture_mode(self.mode, capability="Complex live decompilation")
        resolved_fixture_path = fixture_path or self.decompiled_artifact_fixture_path
        if resolved_fixture_path is None:
            raise ComplexRemediationConfigurationError(
                "Decompiled artifact fixture path is not configured. "
                "Set EA_DECOMPILED_ARTIFACT_FIXTURE_PATH for local Day 8 remediation."
            )

        payload = json.loads(resolved_fixture_path.read_text())
        return [DecompiledArtifactSummary.model_validate(item) for item in payload["decompiled_artifacts"]]

    def load_symbol_mappings(self, *, fixture_path: Path | None = None) -> list[SymbolMappingEntry]:
        """Load placeholder symbol mappings for the complex remediation lane."""

        require_fixture_mode(self.mode, capability="Complex live symbol mapping")
        resolved_fixture_path = fixture_path or self.symbol_mapping_fixture_path
        if resolved_fixture_path is None:
            raise ComplexRemediationConfigurationError(
                "Symbol mapping fixture path is not configured. "
                "Set EA_SYMBOL_MAPPING_FIXTURE_PATH for local Day 8 remediation."
            )

        payload = json.loads(resolved_fixture_path.read_text())
        return [SymbolMappingEntry.model_validate(item) for item in payload["symbol_mappings"]]

    def load_code_change_plan(self, *, fixture_path: Path | None = None) -> ComplexCodeChangePlan:
        """Load the placeholder code-change plan for the complex remediation lane."""

        require_fixture_mode(self.mode, capability="Complex live code-change planning")
        resolved_fixture_path = fixture_path or self.code_change_plan_fixture_path
        if resolved_fixture_path is None:
            raise ComplexRemediationConfigurationError(
                "Code change plan fixture path is not configured. "
                "Set EA_CODE_CHANGE_PLAN_FIXTURE_PATH for local Day 8 remediation."
            )

        return ComplexCodeChangePlan.model_validate(json.loads(resolved_fixture_path.read_text()))

    def select_migration_tactic(
        self, compatibility_diff: CompatibilityDiffResult
    ) -> tuple[ComplexMigrationTactic, str]:
        """Choose a primary migration tactic from the compatibility diff."""

        change_types = {change.change_type for change in compatibility_diff.breaking_changes}
        if {"removed", "modified"}.issubset(change_types):
            return (
                ComplexMigrationTactic.ADAPTER_SHIM,
                "Removed APIs and constructor changes suggest insulating callers behind a compatibility adapter "
                "while parser and serializer internals migrate.",
            )
        if any("<init>" in change.symbol for change in compatibility_diff.breaking_changes):
            return (
                ComplexMigrationTactic.FACTORY_INTRODUCTION,
                "Constructor changes suggest introducing an explicit factory/config seam before touching call sites.",
            )
        return (
            ComplexMigrationTactic.TARGETED_SYMBOL_REWRITE,
            "Breaking changes are narrow enough to handle with direct symbol replacements in affected files.",
        )
