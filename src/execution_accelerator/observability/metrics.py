"""Per-run metrics CSV sink.

One row per completed run, appended to ``.local/metrics.csv``. Header is
created lazily so the file does not need to be initialized during ``make
install`` or fixture-mode tests.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from execution_accelerator.schemas import WorkflowStatus
from execution_accelerator.state import RemediationState


METRICS_HEADER: tuple[str, ...] = (
    "thread_id",
    "ticket_id",
    "workflow_status",
    "route_strategy",
    "total_attempts",
    "retry_count",
    "completed_repo_count",
    "pending_repo_count",
    "skipped_repo_count",
    "validation_status",
    "modified_file_count",
    "code_diff_total_additions",
    "code_diff_total_deletions",
    "llm_call_count",
    "llm_tokens_used",
    "pull_request_url",
    "escalation_bundle_path",
)


def append_metrics_row(
    *,
    metrics_path: Path,
    thread_id: str,
    state: RemediationState,
) -> None:
    """Append one row of run-level metrics to ``metrics_path``."""

    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    file_existed = metrics_path.exists()
    with metrics_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if not file_existed:
            writer.writerow(METRICS_HEADER)
        writer.writerow(_row_for(thread_id=thread_id, state=state))


def _row_for(*, thread_id: str, state: RemediationState) -> tuple[str, ...]:
    validation_status = (
        state.validation_results[-1].status if state.validation_results else ""
    )
    additions, deletions = _diff_totals(state.code_diffs)
    return (
        thread_id,
        state.initial_ticket_id,
        _stringify_status(state.workflow_status),
        _stringify_strategy(state),
        str(state.total_attempts),
        str(state.retry_count),
        str(len(state.completed_repos)),
        str(len(state.pending_repos)),
        str(len(state.skipped_repos)),
        str(validation_status),
        str(len(state.modified_files)),
        str(additions),
        str(deletions),
        str(len(state.llm_calls)),
        str(state.llm_tokens_used),
        state.pull_request_summary.url if state.pull_request_summary else "",
        state.escalation_bundle.bundle_path if state.escalation_bundle else "",
    )


def _diff_totals(diffs: Iterable[object]) -> tuple[int, int]:
    additions = 0
    deletions = 0
    for diff in diffs:
        additions += int(getattr(diff, "additions", 0) or 0)
        deletions += int(getattr(diff, "deletions", 0) or 0)
    return additions, deletions


def _stringify_status(status: WorkflowStatus) -> str:
    return str(status.value if hasattr(status, "value") else status)


def _stringify_strategy(state: RemediationState) -> str:
    if state.route_decision is None:
        return ""
    strategy = state.route_decision.strategy
    return str(strategy.value if hasattr(strategy, "value") else strategy)
