"""Jira intake adapter for local development and future remote integration."""

from __future__ import annotations

import json
from pathlib import Path

from execution_accelerator.config import RuntimeConfig
from execution_accelerator.schemas import JiraIssuePayload, VulnerabilityDetails


class JiraAdapterError(RuntimeError):
    """Base error for Jira adapter failures."""


class JiraConfigurationError(JiraAdapterError):
    """Raised when Jira intake is not configured for the requested operation."""


class JiraTicketMismatchError(JiraAdapterError):
    """Raised when a loaded fixture does not match the requested ticket id."""


class JiraAdapter:
    """Load Jira issues from local fixtures during Day 3 development."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        project_key: str | None = None,
        fixture_path: Path | None = None,
    ) -> None:
        self.base_url = base_url
        self.project_key = project_key
        self.fixture_path = fixture_path

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "JiraAdapter":
        """Create a Jira adapter from the runtime configuration."""

        return cls(
            base_url=config.jira_base_url,
            project_key=config.jira_project_key,
            fixture_path=config.jira_fixture_path,
        )

    def load_issue(
        self,
        ticket_id: str,
        *,
        fixture_path: Path | None = None,
        strict_ticket_match: bool = True,
    ) -> JiraIssuePayload:
        """Load a Jira issue payload for the provided ticket id."""

        resolved_fixture_path = fixture_path or self.fixture_path
        if resolved_fixture_path is None:
            raise JiraConfigurationError(
                "Jira fixture path is not configured. Set EA_JIRA_FIXTURE_PATH for local Day 3 intake."
            )

        payload = JiraIssuePayload.model_validate(json.loads(resolved_fixture_path.read_text()))
        if payload.ticket_id != ticket_id:
            if not strict_ticket_match:
                return payload.model_copy(update={"ticket_id": ticket_id})
            raise JiraTicketMismatchError(
                f"Requested ticket '{ticket_id}' does not match fixture ticket '{payload.ticket_id}'."
            )
        return payload

    def load_vulnerability_details(
        self,
        ticket_id: str,
        *,
        fixture_path: Path | None = None,
    ) -> VulnerabilityDetails:
        """Convert a Jira issue payload into workflow vulnerability details."""

        issue = self.load_issue(
            ticket_id,
            fixture_path=fixture_path,
            strict_ticket_match=False,
        )
        return VulnerabilityDetails(
            package_name=issue.package_name,
            installed_version=issue.installed_version,
            summary=issue.summary,
            cve_id=next((reference.identifier for reference in issue.references if reference.source == "cve"), None),
            fixed_version=issue.fixed_version,
            severity=issue.severity,
            affected_repositories=issue.affected_repositories,
            references=issue.references,
        )
