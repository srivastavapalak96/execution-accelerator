"""Fixture-backed delivery helpers for the Day 10 workflow."""

from __future__ import annotations

import json
from pathlib import Path

import re

from execution_accelerator.adapters._mode import require_fixture_mode
from execution_accelerator.config import RuntimeConfig, load_credentials
from execution_accelerator.execution import GitRunner
from execution_accelerator.schemas import (
    BranchPublicationResult,
    ExecutionMode,
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
        mode: ExecutionMode = ExecutionMode.FIXTURE,
        git_runner: GitRunner | None = None,
        git_user_name: str | None = None,
        git_user_email: str | None = None,
    ) -> None:
        self.branch_publication_fixture_path = branch_publication_fixture_path
        self.pull_request_fixture_path = pull_request_fixture_path
        self.jira_completion_fixture_path = jira_completion_fixture_path
        self.mode = mode
        self.git_runner = git_runner
        self.git_user_name = git_user_name
        self.git_user_email = git_user_email

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "DeliveryAdapter":
        """Create the delivery adapter from runtime configuration."""

        credentials = load_credentials(repo_root=config.repo_root)
        return cls(
            branch_publication_fixture_path=config.branch_publication_fixture_path,
            pull_request_fixture_path=config.pull_request_fixture_path,
            jira_completion_fixture_path=config.jira_completion_fixture_path,
            mode=config.execution_mode,
            git_runner=GitRunner(
                log_dir=config.logs_dir / "git",
                secrets=tuple(secret for secret in (credentials.github_token,) if secret),
            ),
            git_user_name=credentials.git_user_name,
            git_user_email=credentials.git_user_email,
        )

    def load_branch_publication(
        self,
        *,
        repository: str,
        workspace_path: Path | None = None,
        ticket_id: str | None = None,
        package_name: str | None = None,
        fixture_path: Path | None = None,
    ) -> BranchPublicationResult:
        """Load placeholder branch and commit publication metadata."""

        if self.mode == ExecutionMode.LIVE:
            return self._load_live_branch_publication(
                repository=repository,
                workspace_path=workspace_path,
                ticket_id=ticket_id,
                package_name=package_name,
            )
        require_fixture_mode(self.mode, capability="Delivery live publication")
        resolved_fixture_path = fixture_path or self.branch_publication_fixture_path
        if resolved_fixture_path is None:
            raise DeliveryConfigurationError(
                "Branch publication fixture path is not configured. "
                "Set EA_BRANCH_PUBLICATION_FIXTURE_PATH for local Day 10 delivery."
            )

        result = BranchPublicationResult.model_validate(json.loads(resolved_fixture_path.read_text()))
        return result.model_copy(update={"repository": repository})

    def _load_live_branch_publication(
        self,
        *,
        repository: str,
        workspace_path: Path | None,
        ticket_id: str | None,
        package_name: str | None,
    ) -> BranchPublicationResult:
        if self.git_runner is None:
            raise DeliveryConfigurationError("Live branch publication requires a configured Git runner.")
        if workspace_path is None:
            raise DeliveryConfigurationError("Live branch publication requires a workspace path.")
        if not ticket_id:
            raise DeliveryConfigurationError("Live branch publication requires a ticket id.")
        if not self.git_user_name or not self.git_user_email:
            raise DeliveryConfigurationError(
                "Live branch publication requires EA_GIT_USER_NAME and EA_GIT_USER_EMAIL."
            )

        sanitized_package = _slugify(package_name or repository)
        branch_name = f"{ticket_id.lower()}-remediate-{sanitized_package}"
        commit_message = f"chore: remediate {package_name or repository} for {ticket_id}"
        self.git_runner.configure_user(
            workspace_path,
            name=self.git_user_name,
            email=self.git_user_email,
        )
        self.git_runner.create_branch(workspace_path, branch_name)
        self.git_runner.add_all(workspace_path)
        if self.git_runner.status_clean(workspace_path):
            raise DeliveryAdapterError(f"No changes to publish for repository '{repository}'.")
        self.git_runner.commit(workspace_path, message=commit_message)
        commit_sha = self.git_runner.head_sha(workspace_path)
        self.git_runner.push(workspace_path, branch_name=branch_name)
        return BranchPublicationResult(
            repository=repository,
            branch_name=branch_name,
            commit_sha=commit_sha,
            commit_message=commit_message,
            pushed=True,
        )

    def load_pull_request(
        self,
        *,
        repository: str,
        fixture_path: Path | None = None,
    ) -> PullRequestSummary:
        """Load placeholder pull request metadata."""

        require_fixture_mode(self.mode, capability="Delivery live pull-request creation")
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

        require_fixture_mode(self.mode, capability="Delivery live Jira completion")
        resolved_fixture_path = fixture_path or self.jira_completion_fixture_path
        if resolved_fixture_path is None:
            raise DeliveryConfigurationError(
                "Jira completion fixture path is not configured. "
                "Set EA_JIRA_COMPLETION_FIXTURE_PATH for local Day 10 delivery."
            )

        result = JiraCompletionResult.model_validate(json.loads(resolved_fixture_path.read_text()))
        return result.model_copy(update={"ticket_id": ticket_id})


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "remediation"
