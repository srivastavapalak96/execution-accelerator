"""Persistence helpers for local LangGraph execution."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re
from typing import Iterator

from langgraph.checkpoint.sqlite import SqliteSaver

from execution_accelerator.config import RuntimeConfig


THREAD_ID_PATTERN = re.compile(r"[^a-z0-9]+")


def ensure_runtime_directories(config: RuntimeConfig) -> None:
    """Create the local directories required for development execution."""

    for directory in (config.data_dir, config.workspace_dir, config.logs_dir):
        directory.mkdir(parents=True, exist_ok=True)
    config.checkpoints_path.parent.mkdir(parents=True, exist_ok=True)


def build_thread_config(thread_id: str) -> dict[str, dict[str, str]]:
    """Return the LangGraph runtime config for a persisted thread."""

    return {"configurable": {"thread_id": thread_id}}


def build_default_thread_id(ticket_id: str) -> str:
    """Derive a stable thread identifier from the Jira ticket id."""

    slug = THREAD_ID_PATTERN.sub("-", ticket_id.strip().lower()).strip("-")
    return f"ticket-{slug or 'bootstrap'}"


@contextmanager
def sqlite_checkpointer(config: RuntimeConfig) -> Iterator[SqliteSaver]:
    """Yield a SQLite-backed LangGraph checkpointer for local development."""

    ensure_runtime_directories(config)
    checkpoint_path = str(Path(config.checkpoints_path))
    with SqliteSaver.from_conn_string(checkpoint_path) as saver:
        yield saver
