from __future__ import annotations

from pathlib import Path

import pytest

from execution_accelerator.adapters import JiraAdapter, JiraConfigurationError, JiraTicketMismatchError
from execution_accelerator.config import load_runtime_config
from execution_accelerator.schemas import Severity


def test_jira_adapter_loads_issue_from_runtime_fixture(tmp_path, monkeypatch) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "jira_issue.json"
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(fixture_path))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = JiraAdapter.from_runtime_config(config)

    issue = adapter.load_issue("SEC-123")

    assert issue.ticket_id == "SEC-123"
    assert issue.affected_repositories[0].name == "payments-service"


def test_jira_adapter_converts_issue_to_vulnerability_details(tmp_path, monkeypatch) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "jira_issue.json"
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(fixture_path))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = JiraAdapter.from_runtime_config(config)

    details = adapter.load_vulnerability_details("SEC-123")

    assert details.package_name == "org.example:legacy-json"
    assert details.fixed_version == "1.2.4"
    assert details.severity == Severity.HIGH
    assert details.cve_id == "CVE-2026-12345"


def test_jira_adapter_requires_fixture_configuration() -> None:
    adapter = JiraAdapter()

    with pytest.raises(JiraConfigurationError):
        adapter.load_issue("SEC-123")


def test_jira_adapter_rejects_ticket_mismatch() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "jira_issue.json"
    adapter = JiraAdapter(fixture_path=fixture_path)

    with pytest.raises(JiraTicketMismatchError):
        adapter.load_issue("SEC-999")
