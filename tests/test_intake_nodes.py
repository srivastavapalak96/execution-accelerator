from __future__ import annotations

from pathlib import Path

from execution_accelerator.adapters import JiraAdapter, RepositoryInventoryAdapter
from execution_accelerator.config import load_runtime_config
from execution_accelerator.nodes import (
    build_ingest_and_parse_jira_node,
    build_load_repository_context_node,
    build_probe_credentials_node,
)
from execution_accelerator.schemas import ExecutionMode, WorkflowStatus
from execution_accelerator.state import RemediationState


def test_ingest_jira_node_loads_vulnerability_details() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "jira_issue.json"
    node = build_ingest_and_parse_jira_node(JiraAdapter(fixture_path=fixture_path))

    update = node(RemediationState(initial_ticket_id="SEC-123"))

    assert update["workflow_status"] == WorkflowStatus.IN_PROGRESS
    assert update["vulnerability_details"].package_name == "org.example:legacy-json"
    assert update["audit_events"][-1].event_type == "jira.ingest"


def test_load_repository_context_node_creates_repo_map(tmp_path) -> None:
    inventory_fixture_path = Path(__file__).parent / "fixtures" / "repository_inventory.json"
    adapter = RepositoryInventoryAdapter(
        fixture_path=inventory_fixture_path,
        workspace_root=tmp_path / "workspace",
    )
    node = build_load_repository_context_node(adapter)
    state = RemediationState(
        initial_ticket_id="SEC-123",
        vulnerability_details=JiraAdapter(
            fixture_path=Path(__file__).parent / "fixtures" / "jira_issue.json"
        ).load_vulnerability_details("SEC-123"),
    )

    update = node(state)

    assert len(update["targets"]) == 1
    assert update["targets"][0].repository_name == "payments-service"
    assert update["pending_repos"] == ["payments-service"]
    workspace = update["repo_map"]["payments-service"]
    assert workspace.clone_url == "https://github.com/example/payments-service.git"
    assert workspace.owner == "payments-platform"
    assert Path(workspace.local_path).is_dir()
    assert update["audit_events"][-1].event_type == "repository.context_load"


def test_probe_credentials_node_skips_fixture_mode(tmp_path, monkeypatch) -> None:
    config = load_runtime_config(repo_root=tmp_path)
    node = build_probe_credentials_node(config)

    update = node(RemediationState(initial_ticket_id="SEC-123"))

    assert update["audit_events"][-1].event_type == "credentials.probe"
    assert update["audit_events"][-1].details["skipped"] is True


def test_load_repository_context_node_skips_existing_live_pr(tmp_path) -> None:
    config_path = tmp_path / "config" / "repositories.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            [
                "repositories:",
                "  - name: payments-service",
                "    clone_url: https://github.com/example/payments-service.git",
                "    default_branch: main",
                "    build_system: maven",
                "    manifest_path: pom.xml",
                "    owner: payments-platform",
            ]
        )
        + "\n"
    )
    adapter = RepositoryInventoryAdapter(
        config_path=config_path,
        workspace_root=tmp_path / "workspace",
        mode=ExecutionMode.LIVE,
        existing_pull_request_lookup=lambda target: f"https://github.com/example/{target.repository_name}/pull/7",
    )
    node = build_load_repository_context_node(adapter)
    state = RemediationState(
        initial_ticket_id="SEC-700",
        vulnerability_details=JiraAdapter(
            fixture_path=Path(__file__).parent / "fixtures" / "jira_issue.json"
        ).load_vulnerability_details("SEC-700"),
    )

    update = node(state)

    assert len(update["targets"]) == 1
    assert update["pending_repos"] == []
    assert update["repo_map"] == {}
    assert update["skipped_repos"][0].name == "payments-service"
    assert update["skipped_repos"][0].reason.startswith("existing_pr:")
