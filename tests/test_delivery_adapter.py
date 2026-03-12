from __future__ import annotations

from pathlib import Path

import pytest

from execution_accelerator.adapters import (
    DeliveryAdapter,
    DeliveryConfigurationError,
)
from execution_accelerator.config import load_runtime_config


def test_delivery_adapter_loads_branch_and_pull_request_metadata(tmp_path, monkeypatch) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv(
        "EA_BRANCH_PUBLICATION_FIXTURE_PATH",
        str(fixture_dir / "branch_publication.json"),
    )
    monkeypatch.setenv("EA_PULL_REQUEST_FIXTURE_PATH", str(fixture_dir / "pull_request.json"))
    monkeypatch.setenv("EA_JIRA_COMPLETION_FIXTURE_PATH", str(fixture_dir / "jira_completion.json"))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = DeliveryAdapter.from_runtime_config(config)

    branch = adapter.load_branch_publication(repository="payments-service")
    pull_request = adapter.load_pull_request(repository="payments-service")
    jira_completion = adapter.load_jira_completion(ticket_id="SEC-123")

    assert branch.branch_name == "sec-123-remediate-legacy-json"
    assert pull_request.number == 42
    assert jira_completion.status == "done"


def test_delivery_adapter_requires_configuration() -> None:
    adapter = DeliveryAdapter()

    with pytest.raises(DeliveryConfigurationError):
        adapter.load_branch_publication(repository="payments-service")
