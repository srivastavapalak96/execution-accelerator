"""Append-only JSONL audit sink for remediation runs.

Every node already records :class:`AuditEvent` objects on the workflow state.
``write_audit_jsonl`` serializes that list to ``.local/logs/audit-{thread_id}.jsonl``
so a real run leaves a forensic trail that survives the SQLite checkpoint.

The function is idempotent for a given ``(thread_id, audit_events)`` pair: it
overwrites the file rather than appending duplicates, because the source of
truth is always ``RemediationState.audit_events``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from execution_accelerator.schemas import AuditEvent


def write_audit_jsonl(
    *,
    audit_events: Iterable[AuditEvent],
    logs_dir: Path,
    thread_id: str,
) -> Path:
    """Serialize ``audit_events`` to ``logs_dir/audit-{thread_id}.jsonl`` and return the path.

    One JSON document per line. Events are written in their stored order so the
    sink can be diffed against a previous run.
    """

    logs_dir.mkdir(parents=True, exist_ok=True)
    target = logs_dir / f"audit-{_sanitize(thread_id)}.jsonl"
    with target.open("w", encoding="utf-8") as fh:
        for event in audit_events:
            fh.write(json.dumps(event.model_dump(mode="json"), sort_keys=True))
            fh.write("\n")
    return target


def _sanitize(thread_id: str) -> str:
    """Make ``thread_id`` filesystem-safe without losing readability."""

    safe = []
    for character in thread_id:
        if character.isalnum() or character in {"-", "_"}:
            safe.append(character)
        else:
            safe.append("_")
    return "".join(safe) or "unknown"
