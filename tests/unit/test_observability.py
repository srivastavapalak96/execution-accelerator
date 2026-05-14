"""Unit tests for execution_accelerator.observability.{audit_sink,metrics}."""

from __future__ import annotations

import csv
import json
from pathlib import Path


from execution_accelerator.observability import (
    METRICS_HEADER,
    append_metrics_row,
    write_audit_jsonl,
)
from execution_accelerator.schemas import (
    AuditEvent,
    EscalationBundle,
    FailureClassification,
    LlmCallRecord,
    PullRequestSummary,
    RemediationRouteDecision,
    RemediationStrategy,
    WorkflowStatus,
)
from execution_accelerator.state import RemediationState


def _state_with_route() -> RemediationState:
    return RemediationState(
        initial_ticket_id="SEC-METRICS-1",
        workflow_status=WorkflowStatus.COMPLETED,
        route_decision=RemediationRouteDecision(
            strategy=RemediationStrategy.SIMPLE_UPDATE,
            confidence=0.95,
            reason="direct dep, low risk",
        ),
        completed_repos=["payments-service"],
        modified_files=["pom.xml"],
        llm_tokens_used=42,
        llm_calls=[
            LlmCallRecord(provider="ollama", model="llama3.1:8b", prompt_name="probe", token_count=42)
        ],
    )


# --- audit JSONL --------------------------------------------------------------


def test_write_audit_jsonl_one_event_per_line(tmp_path: Path) -> None:
    events = [
        AuditEvent(event_type="bootstrap", message="ok"),
        AuditEvent(event_type="route", message="simple", details={"strategy": "simple_update"}),
    ]
    path = write_audit_jsonl(audit_events=events, logs_dir=tmp_path, thread_id="sec-1-thread")

    assert path.name == "audit-sec-1-thread.jsonl"
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "bootstrap"
    assert json.loads(lines[1])["details"] == {"strategy": "simple_update"}


def test_write_audit_jsonl_overwrites_idempotently(tmp_path: Path) -> None:
    """A second call replaces the file rather than appending duplicates."""

    events_v1 = [AuditEvent(event_type="t1", message="m1")]
    events_v2 = [
        AuditEvent(event_type="t1", message="m1"),
        AuditEvent(event_type="t2", message="m2"),
    ]
    write_audit_jsonl(audit_events=events_v1, logs_dir=tmp_path, thread_id="t")
    path = write_audit_jsonl(audit_events=events_v2, logs_dir=tmp_path, thread_id="t")

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2


def test_write_audit_jsonl_sanitizes_thread_id(tmp_path: Path) -> None:
    events = [AuditEvent(event_type="t", message="m")]
    path = write_audit_jsonl(audit_events=events, logs_dir=tmp_path, thread_id="weird/thread:id$")
    # Slashes and colons must not appear in the resulting filename.
    assert "/" not in path.name
    assert ":" not in path.name


# --- metrics CSV --------------------------------------------------------------


def test_append_metrics_row_writes_header_then_row(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.csv"
    append_metrics_row(metrics_path=metrics_path, thread_id="sec-1-thread", state=_state_with_route())

    rows = list(csv.reader(metrics_path.open()))
    assert rows[0] == list(METRICS_HEADER)
    assert rows[1][0] == "sec-1-thread"
    assert rows[1][1] == "SEC-METRICS-1"
    assert rows[1][3] == "simple_update"


def test_append_metrics_row_skips_header_on_existing_file(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.csv"
    state = _state_with_route()
    append_metrics_row(metrics_path=metrics_path, thread_id="t1", state=state)
    append_metrics_row(metrics_path=metrics_path, thread_id="t2", state=state)

    rows = list(csv.reader(metrics_path.open()))
    assert rows[0] == list(METRICS_HEADER)
    assert rows[1][0] == "t1"
    assert rows[2][0] == "t2"
    assert len(rows) == 3


def test_append_metrics_row_captures_pr_url_and_escalation(tmp_path: Path) -> None:
    state = _state_with_route()
    state.pull_request_summary = PullRequestSummary(
        repository="payments-service",
        number=42,
        url="https://github.com/example/repo/pull/42",
        title="bump",
        status="open",
    )
    state.escalation_bundle = EscalationBundle(
        bundle_path="/tmp/bundle.json",
        failure_classification=FailureClassification.UNKNOWN,
    )

    metrics_path = tmp_path / "metrics.csv"
    append_metrics_row(metrics_path=metrics_path, thread_id="t1", state=state)

    rows = list(csv.reader(metrics_path.open()))
    header = rows[0]
    row = dict(zip(header, rows[1], strict=True))
    assert row["pull_request_url"] == "https://github.com/example/repo/pull/42"
    assert row["escalation_bundle_path"] == "/tmp/bundle.json"


def test_validation_status_blank_when_no_results(tmp_path: Path) -> None:
    state = RemediationState(
        initial_ticket_id="SEC-NO-VALIDATION",
        workflow_status=WorkflowStatus.IN_PROGRESS,
    )
    metrics_path = tmp_path / "metrics.csv"
    append_metrics_row(metrics_path=metrics_path, thread_id="t", state=state)

    rows = list(csv.reader(metrics_path.open()))
    row = dict(zip(rows[0], rows[1], strict=True))
    assert row["validation_status"] == ""
    assert row["route_strategy"] == ""
