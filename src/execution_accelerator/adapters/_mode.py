"""Shared execution-mode helpers for fixture and live adapters."""

from __future__ import annotations

from execution_accelerator.schemas import ExecutionMode


def require_fixture_mode(mode: ExecutionMode, *, capability: str) -> None:
    """Raise until the requested capability is implemented for live mode."""

    if mode == ExecutionMode.LIVE:
        raise NotImplementedError(f"{capability} is not implemented for EA_MODE=live yet.")
