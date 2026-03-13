from __future__ import annotations

from pathlib import Path

import pytest

from execution_accelerator.adapters import JiraAdapter, JiraConfigurationError, JiraTicketMismatchError
from execution_accelerator.config import load_runtime_config
from execution_accelerator.schemas import ExecutionMode, Severity


def test_jira_adapter_loads_issue_from_runtime_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "jira_issue.json"
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(fixture_path))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = JiraAdapter.from_runtime_config(config)

    issue = adapter.load_issue("SEC-123")

    assert issue.ticket_id == "SEC-123"
    assert issue.affected_repositories[0].name == "payments-service"


def test_jira_adapter_converts_issue_to_vulnerability_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_jira_adapter_loads_live_issue_from_mapped_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "jira.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            [
                "project_key: SEC",
                "fields:",
                "  package_name: customfield_10010",
                "  installed_version: customfield_10011",
                "  fixed_version: customfield_10012",
                "  severity: customfield_10013",
                "  affected_repositories: customfield_10014",
                "  cve_id: customfield_10015",
                "  references: customfield_10016",
            ]
        )
        + "\n"
    )
    adapter = JiraAdapter(
        base_url="https://jira.example.com",
        mode=ExecutionMode.LIVE,
        config_path=config_path,
        issue_loader=lambda ticket_id: {
            "key": ticket_id,
            "fields": {
                "summary": "Upgrade vulnerable JSON dependency",
                "description": {
                    "type": "doc",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Tracked in Jira"}]}],
                },
                "customfield_10010": "org.example:legacy-json",
                "customfield_10011": "1.2.3",
                "customfield_10012": "1.2.4",
                "customfield_10013": {"value": "High"},
                "customfield_10014": [
                    {
                        "name": "payments-service",
                        "clone_url": "https://github.com/example/payments-service.git",
                        "default_branch": "main",
                        "manifest_path": "pom.xml",
                    }
                ],
                "customfield_10015": "CVE-2026-12345",
                "customfield_10016": [
                    {
                        "source": "ghsa",
                        "identifier": "GHSA-1234",
                        "url": "https://example.com/ghsa-1234",
                    }
                ],
            },
        },
    )

    issue = adapter.load_issue("SEC-900")

    assert issue.ticket_id == "SEC-900"
    assert issue.package_name == "org.example:legacy-json"
    assert issue.installed_version == "1.2.3"
    assert issue.fixed_version == "1.2.4"
    assert issue.severity == Severity.HIGH
    assert issue.affected_repositories[0].name == "payments-service"
    assert issue.references[0].identifier == "GHSA-1234"
    assert issue.references[-1].identifier == "CVE-2026-12345"


def test_jira_adapter_uses_description_fallbacks_in_live_mode(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "jira.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("project_key: SEC\nfields: {}\n")
    adapter = JiraAdapter(
        base_url="https://jira.example.com",
        mode=ExecutionMode.LIVE,
        config_path=config_path,
        issue_loader=lambda ticket_id: {
            "key": ticket_id,
            "fields": {
                "summary": "Upgrade vulnerable JSON dependency",
                "description": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Package: org.example:legacy-json\n"
                                        "Installed Version: 1.2.3\n"
                                        "Fixed Version: 1.2.4\n"
                                        "Severity: High\n"
                                        "Repository: payments-service\n"
                                        "Reference: cve|CVE-2026-12345|https://example.com/advisories/CVE-2026-12345"
                                    ),
                                }
                            ],
                        }
                    ],
                },
            },
        },
    )

    details = adapter.load_vulnerability_details("SEC-901")

    assert details.package_name == "org.example:legacy-json"
    assert details.installed_version == "1.2.3"
    assert details.fixed_version == "1.2.4"
    assert details.severity == Severity.HIGH
    assert details.cve_id == "CVE-2026-12345"
    assert details.affected_repositories[0].name == "payments-service"
    assert details.references[0].source == "cve"
    assert details.references[0].url == "https://example.com/advisories/CVE-2026-12345"


def test_jira_adapter_requires_live_config_file(tmp_path: Path) -> None:
    adapter = JiraAdapter(
        base_url="https://jira.example.com",
        mode=ExecutionMode.LIVE,
        config_path=tmp_path / "missing-jira.yaml",
        issue_loader=lambda ticket_id: {"key": ticket_id, "fields": {}},
    )

    with pytest.raises(JiraConfigurationError):
        adapter.load_issue("SEC-902")
