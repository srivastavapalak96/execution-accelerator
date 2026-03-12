"""Fixture-backed delivery helpers for the Day 10 workflow."""

from __future__ import annotations

import json
from pathlib import Path

from execution_accelerator.config import RuntimeConfig
from execution_accelerator.schemas import (
    BranchPublicationResult,
    JiraCompletionResult,
    PullRequestSummary,
)


class DeliveryAdapterError(RuntimeError):
    """Base error for Day 10 delivery helpers."""


class DeliveryConfigurationError(DeliveryAdapterError):
    """Raised when delivery fixture configuration is missing."""


class DeliveryAdapter:
    """Load placeholder publication and completion payloads from fixtures."""

    def __init__(
        self,
        *,
        branch_publication_fixture_path: Path | None = None,
        pull_request_fixture_path: Path | None = None,
        jira_completion_fixture_path: Path | None = None,
    ) -> None:
        self.branch_publication_fixture_path = branch_publication_fixture_path
        self.pull_request_fixture_path = pull_request_fixture_path
        self.jira_completion_fixture_path = jira_completion_fixture_path

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "DeliveryAdapter":
        """Create the delivery adapter from runtime configuration."""

        return cls(
            branch_publication_fixture_path=config.branch_publication_fixture_path,
            pull_request_fixture_path=config.pull_request_fixture_path,
            jira_completion_fixture_path=config.jira_completion_fixture_path,
        )

    def load_branch_publication(
        self,
        *,
        repository: str,
        fixture_path: Path | None = None,
    ) -> BranchPublicationResult:
        """Load placeholder branch and commit publication metadata."""

        resolved_fixture_path = fixture_path or self.branch_publication_fixture_path
        if resolved_fixture_path is None:
            raise DeliveryConfigurationError(
                "Branch publication fixture path is not configured. "
                "Set EA_BRANCH_PUBLICATION_FIXTURE_PATH for local Day 10 delivery."
            )

        result = BranchPublicationResult.model_validate(json.loads(resolved_fixture_path.read_text()))
        return result.model_copy(update={"repository": repository})

    def load_pull_request(
        self,
        *,
        repository: str,
        fixture_path: Path | None = None,
    ) -> PullRequestSummary:
        """Load placeholder pull request metadata."""

        resolved_fixture_path = fixture_path or self.pull_request_fixture_path
        if resolved_fixture_path is None:
            raise DeliveryConfigurationError(
                "Pull request fixture path is not configured. "
                "Set EA_PULL_REQUEST_FIXTURE_PATH for local Day 10 delivery."
            )

        result = PullRequestSummary.model_validate(json.loads(resolved_fixture_path.read_text()))
        return result.model_copy(update={"repository": repository})

    def load_jira_completion(
        self,
        *,
        ticket_id: str,
        fixture_path: Path | None = None,
    ) -> JiraCompletionResult:
        """Load placeholder Jira completion metadata."""

        resolved_fixture_path = fixture_path or self.jira_completion_fixture_path
        if resolved_fixture_path is None:
            raise DeliveryConfigurationError(
                "Jira completion fixture path is not configured. "
                "Set EA_JIRA_COMPLETION_FIXTURE_PATH for local Day 10 delivery."
            )

        result = JiraCompletionResult.model_validate(json.loads(resolved_fixture_path.read_text()))
        return result.model_copy(update={"ticket_id": ticket_id})
