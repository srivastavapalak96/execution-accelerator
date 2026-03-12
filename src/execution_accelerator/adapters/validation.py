"""Fixture-backed validation and rollback helpers for the Day 9 workflow."""

from __future__ import annotations

import json
from pathlib import Path

from execution_accelerator.adapters._mode import require_fixture_mode
from execution_accelerator.config import RuntimeConfig
from execution_accelerator.schemas import ExecutionMode, RepositoryValidationResult, RollbackPlan


class ValidationAdapterError(RuntimeError):
    """Base error for Day 9 validation helpers."""


class ValidationConfigurationError(ValidationAdapterError):
    """Raised when validation fixture configuration is missing."""


class ValidationAdapter:
    """Load placeholder validation and rollback payloads from fixtures."""

    def __init__(
        self,
        *,
        validation_result_fixture_path: Path | None = None,
        rollback_fixture_path: Path | None = None,
        mode: ExecutionMode = ExecutionMode.FIXTURE,
    ) -> None:
        self.validation_result_fixture_path = validation_result_fixture_path
        self.rollback_fixture_path = rollback_fixture_path
        self.mode = mode

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "ValidationAdapter":
        """Create the validation adapter from runtime configuration."""

        return cls(
            validation_result_fixture_path=config.validation_result_fixture_path,
            rollback_fixture_path=config.rollback_fixture_path,
            mode=config.execution_mode,
        )

    def load_validation_result(
        self,
        *,
        repository: str,
        fixture_path: Path | None = None,
    ) -> RepositoryValidationResult:
        """Load the placeholder validation result for one repository."""

        require_fixture_mode(self.mode, capability="Validation live execution")
        resolved_fixture_path = fixture_path or self.validation_result_fixture_path
        if resolved_fixture_path is None:
            raise ValidationConfigurationError(
                "Validation result fixture path is not configured. "
                "Set EA_VALIDATION_RESULT_FIXTURE_PATH for local Day 9 validation."
            )

        result = RepositoryValidationResult.model_validate(json.loads(resolved_fixture_path.read_text()))
        return result.model_copy(update={"repository": repository})

    def load_rollback_plan(
        self,
        *,
        repository: str,
        fixture_path: Path | None = None,
    ) -> RollbackPlan:
        """Load the placeholder rollback plan for one repository."""

        require_fixture_mode(self.mode, capability="Rollback live execution")
        resolved_fixture_path = fixture_path or self.rollback_fixture_path
        if resolved_fixture_path is None:
            raise ValidationConfigurationError(
                "Rollback fixture path is not configured. "
                "Set EA_ROLLBACK_FIXTURE_PATH for local Day 9 rollback handling."
            )

        plan = RollbackPlan.model_validate(json.loads(resolved_fixture_path.read_text()))
        return plan.model_copy(update={"repository": repository})
