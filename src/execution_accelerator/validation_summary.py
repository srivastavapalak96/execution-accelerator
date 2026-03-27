"""Helpers for surfacing the most relevant validation check in operator output."""

from __future__ import annotations

from execution_accelerator.schemas import RepositoryValidationResult, ValidationCheck, ValidationStatus


def select_primary_validation_check(validation_result: RepositoryValidationResult) -> ValidationCheck | None:
    """Prefer the first failed validation check, falling back to the first available check."""

    for check in validation_result.checks:
        if check.status == ValidationStatus.FAILED:
            return check
    if validation_result.checks:
        return validation_result.checks[0]
    return None
