"""Fixture-backed delivery helpers for the Day 10 workflow."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import re

from execution_accelerator.adapters._mode import require_fixture_mode
from execution_accelerator.config import RuntimeConfig, load_credentials
from execution_accelerator.execution import GitRunner
from execution_accelerator.policy import PolicyEngine
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
        github_api_base: str | None = None,
        github_token: str | None = None,
        github_owner: str | None = None,
        jira_base_url: str | None = None,
        jira_email: str | None = None,
        jira_token: str | None = None,
        jira_done_transition_id: str | None = None,
        jira_done_status_name: str | None = None,
        draft_pull_requests: bool = True,
    ) -> None:
        self.branch_publication_fixture_path = branch_publication_fixture_path
        self.pull_request_fixture_path = pull_request_fixture_path
        self.jira_completion_fixture_path = jira_completion_fixture_path
        self.mode = mode
        self.git_runner = git_runner
        self.git_user_name = git_user_name
        self.git_user_email = git_user_email
        self.github_api_base = github_api_base
        self.github_token = github_token
        self.github_owner = github_owner
        self.jira_base_url = jira_base_url
        self.jira_email = jira_email
        self.jira_token = jira_token
        self.jira_done_transition_id = jira_done_transition_id
        self.jira_done_status_name = jira_done_status_name
        self.draft_pull_requests = draft_pull_requests

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "DeliveryAdapter":
        """Create the delivery adapter from runtime configuration."""

        credentials = load_credentials(repo_root=config.repo_root)
        policy_config = PolicyEngine(config_path=config.repo_root / "config" / "policy.yaml").load_config()
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
            github_api_base=credentials.github_api_base,
            github_token=credentials.github_token,
            github_owner=credentials.github_owner,
            jira_base_url=credentials.jira_base_url,
            jira_email=credentials.jira_email,
            jira_token=credentials.jira_token,
            jira_done_transition_id=config.jira_done_transition_id,
            jira_done_status_name=config.jira_done_status_name,
            draft_pull_requests=policy_config.draft_pr_only,
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
        owner: str | None = None,
        base_branch: str | None = None,
        head_branch: str | None = None,
        ticket_id: str | None = None,
        package_name: str | None = None,
        draft_pull_request: bool | None = None,
        body: str | None = None,
        fixture_path: Path | None = None,
    ) -> PullRequestSummary:
        """Load placeholder pull request metadata."""

        if self.mode == ExecutionMode.LIVE:
            return self._load_live_pull_request(
                repository=repository,
                owner=owner,
                base_branch=base_branch,
                head_branch=head_branch,
                ticket_id=ticket_id,
                package_name=package_name,
                draft_pull_request=draft_pull_request,
                body=body,
            )
        require_fixture_mode(self.mode, capability="Delivery live pull-request creation")
        resolved_fixture_path = fixture_path or self.pull_request_fixture_path
        if resolved_fixture_path is None:
            raise DeliveryConfigurationError(
                "Pull request fixture path is not configured. "
                "Set EA_PULL_REQUEST_FIXTURE_PATH for local Day 10 delivery."
            )

        result = PullRequestSummary.model_validate(json.loads(resolved_fixture_path.read_text()))
        return result.model_copy(update={"repository": repository})

    def _load_live_pull_request(
        self,
        *,
        repository: str,
        owner: str | None,
        base_branch: str | None,
        head_branch: str | None,
        ticket_id: str | None,
        package_name: str | None,
        draft_pull_request: bool | None,
        body: str | None,
    ) -> PullRequestSummary:
        if not self.github_api_base or not self.github_token:
            raise DeliveryConfigurationError("Live pull-request creation requires GitHub API credentials.")
        repository_owner = owner or self.github_owner
        if not repository_owner:
            raise DeliveryConfigurationError("Live pull-request creation requires a repository owner.")
        if not head_branch:
            raise DeliveryConfigurationError("Live pull-request creation requires a published head branch.")

        title = (
            f"{ticket_id}: remediate {package_name or repository}"
            if ticket_id
            else f"Remediate {package_name or repository}"
        )
        effective_draft = self.draft_pull_requests if draft_pull_request is None else draft_pull_request
        pull_request_body = body or f"Automated remediation for {ticket_id or repository}."
        response = httpx.post(
            f"{self.github_api_base.rstrip('/')}/repos/{repository_owner}/{repository}/pulls",
            headers={
                "Authorization": f"Bearer {self.github_token}",
                "Accept": "application/vnd.github+json",
            },
            json={
                "title": title,
                "head": head_branch,
                "base": base_branch or "main",
                "body": pull_request_body,
                "draft": effective_draft,
            },
            timeout=30.0,
        )
        if response.status_code == 422:
            existing_pull_request = self._load_existing_pull_request(
                repository=repository,
                owner=repository_owner,
                head_branch=head_branch,
                base_branch=base_branch,
            )
            if existing_pull_request is not None:
                return existing_pull_request
        response.raise_for_status()
        return _build_pull_request_summary(
            repository=repository,
            payload=response.json(),
            default_title=title,
            default_draft=effective_draft,
        )

    def _load_existing_pull_request(
        self,
        *,
        repository: str,
        owner: str,
        head_branch: str,
        base_branch: str | None,
    ) -> PullRequestSummary | None:
        assert self.github_api_base is not None
        assert self.github_token is not None
        response = httpx.get(
            f"{self.github_api_base.rstrip('/')}/repos/{owner}/{repository}/pulls",
            headers={
                "Authorization": f"Bearer {self.github_token}",
                "Accept": "application/vnd.github+json",
            },
            params={
                "head": f"{owner}:{head_branch}",
                "state": "open",
                "base": base_branch or "main",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            return None
        return _build_pull_request_summary(
            repository=repository,
            payload=payload[0],
            default_title=f"Remediate {repository}",
            default_draft=self.draft_pull_requests,
        )

    def load_jira_completion(
        self,
        *,
        ticket_id: str,
        repository: str | None = None,
        pull_request_url: str | None = None,
        comment: str | None = None,
        fixture_path: Path | None = None,
    ) -> JiraCompletionResult:
        """Load placeholder Jira completion metadata."""

        if self.mode == ExecutionMode.LIVE:
            return self._load_live_jira_completion(
                ticket_id=ticket_id,
                repository=repository,
                pull_request_url=pull_request_url,
                comment=comment,
            )
        require_fixture_mode(self.mode, capability="Delivery live Jira completion")
        resolved_fixture_path = fixture_path or self.jira_completion_fixture_path
        if resolved_fixture_path is None:
            raise DeliveryConfigurationError(
                "Jira completion fixture path is not configured. "
                "Set EA_JIRA_COMPLETION_FIXTURE_PATH for local Day 10 delivery."
            )

        result = JiraCompletionResult.model_validate(json.loads(resolved_fixture_path.read_text()))
        return result.model_copy(update={"ticket_id": ticket_id})

    def _load_live_jira_completion(
        self,
        *,
        ticket_id: str,
        repository: str | None,
        pull_request_url: str | None,
        comment: str | None,
    ) -> JiraCompletionResult:
        if not self.jira_base_url or not self.jira_email or not self.jira_token:
            raise DeliveryConfigurationError("Live Jira completion requires Jira credentials.")

        resolved_comment = comment or _build_jira_comment(repository=repository, pull_request_url=pull_request_url)
        response = httpx.post(
            f"{self.jira_base_url.rstrip('/')}/rest/api/3/issue/{ticket_id}/comment",
            auth=(self.jira_email, self.jira_token),
            json={"body": _build_jira_doc(resolved_comment)},
            timeout=30.0,
        )
        response.raise_for_status()
        status = "commented"
        if self.jira_done_transition_id:
            transition_response = httpx.post(
                f"{self.jira_base_url.rstrip('/')}/rest/api/3/issue/{ticket_id}/transitions",
                auth=(self.jira_email, self.jira_token),
                json={"transition": {"id": self.jira_done_transition_id}},
                timeout=30.0,
            )
            if transition_response.is_success:
                status = self.jira_done_status_name or "done"
            elif self.jira_done_status_name and _is_transition_already_applied(transition_response):
                current_status = self._load_live_jira_status(ticket_id=ticket_id)
                if current_status == self.jira_done_status_name:
                    status = current_status
                else:
                    transition_response.raise_for_status()
            else:
                transition_response.raise_for_status()
        return JiraCompletionResult(
            ticket_id=ticket_id,
            status=status,
            comment=resolved_comment,
        )

    def _load_live_jira_status(self, *, ticket_id: str) -> str:
        assert self.jira_base_url is not None
        assert self.jira_email is not None
        assert self.jira_token is not None
        response = httpx.get(
            f"{self.jira_base_url.rstrip('/')}/rest/api/3/issue/{ticket_id}",
            auth=(self.jira_email, self.jira_token),
            params={"fields": "status"},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        fields = payload.get("fields")
        if not isinstance(fields, dict):
            raise DeliveryAdapterError(f"Live Jira issue payload for '{ticket_id}' is missing fields.")
        status_payload = fields.get("status")
        if not isinstance(status_payload, dict):
            raise DeliveryAdapterError(f"Live Jira issue payload for '{ticket_id}' is missing a status name.")
        status_name = status_payload.get("name")
        if not isinstance(status_name, str):
            raise DeliveryAdapterError(f"Live Jira issue payload for '{ticket_id}' is missing a status name.")
        return status_name


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "remediation"


def _build_jira_comment(*, repository: str | None, pull_request_url: str | None) -> str:
    repository_label = repository or "repository"
    if pull_request_url:
        return f"Automated remediation prepared for {repository_label}. Pull request: {pull_request_url}"
    return f"Automated remediation prepared for {repository_label}."


def _build_jira_doc(text: str) -> dict[str, object]:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": text,
                    }
                ],
            }
        ],
    }


def _build_pull_request_summary(
    *,
    repository: str,
    payload: object,
    default_title: str,
    default_draft: bool,
) -> PullRequestSummary:
    if not isinstance(payload, dict):
        raise DeliveryAdapterError("Live pull-request payload was not an object.")
    draft = bool(payload.get("draft", default_draft))
    return PullRequestSummary(
        repository=repository,
        number=int(payload["number"]),
        url=str(payload["html_url"]),
        title=str(payload.get("title") or default_title),
        status="draft" if draft else str(payload.get("state") or "open"),
    )


def _is_transition_already_applied(response: httpx.Response) -> bool:
    if response.status_code not in (400, 409):
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    error_messages = payload.get("errorMessages", [])
    errors = payload.get("errors", {})
    fragments: list[str] = []
    if isinstance(error_messages, list):
        fragments.extend(str(message) for message in error_messages)
    if isinstance(errors, dict):
        fragments.extend(str(value) for value in errors.values())
    lowered = " ".join(fragments).lower()
    return "already" in lowered or "current status" in lowered
