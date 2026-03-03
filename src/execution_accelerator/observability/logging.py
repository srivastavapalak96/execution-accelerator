"""Basic logging setup for local development and CLI execution."""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure a consistent root logger for the application."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
