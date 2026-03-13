"""Jira intake adapter for local development and future remote integration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

import httpx
import yaml

from execution_accelerator.config import RuntimeConfig, load_credentials
from execution_accelerator.schemas import (
    AffectedRepository,
    BaseSchemaModel,
    ExecutionMode,
    JiraIssuePayload,
    Severity,
    VulnerabilityDetails,
    VulnerabilityReference,
)


PACKAGE_PATTERN = re.compile(r"(?im)^(?:package|dependency|artifact)\s*:\s*(?P<value>\S+)\s*$")
INSTALLED_VERSION_PATTERN = re.compile(r"(?im)^installed version\s*:\s*(?P<value>\S+)\s*$")
FIXED_VERSION_PATTERN = re.compile(r"(?im)^(?:fixed|target) version\s*:\s*(?P<value>\S+)\s*$")
SEVERITY_PATTERN = re.compile(r"(?im)^severity\s*:\s*(?P<value>[A-Za-z]+)\s*$")
CVE_PATTERN = re.compile(r"(?im)\b(?P<value>CVE-\d{4}-\d+)\b")
REFERENCE_LINE_PATTERN = re.compile(
    r"^(?:(?:reference|ref)\s*:)?\s*(?P<source>[^|\n]+)\|(?P<identifier>[^|\n]+)(?:\|(?P<url>[^\n]+))?$",
    re.MULTILINE,
)
DESCRIPTION_REPOSITORY_PATTERN = re.compile(
    r"(?im)^(?:affected repos?(?:itories)?|repositories?|repository)\s*:\s*(?P<value>.+)$"
)


class JiraFieldMap(BaseSchemaModel):
    """Field ids used when extracting structured data from live Jira issues."""

    package_name: str | None = None
    installed_version: str | None = None
    fixed_version: str | None = None
    severity: str | None = None
    affected_repositories: str | None = None
    cve_id: str | None = None
    references: str | None = None


class JiraProjectConfig(BaseSchemaModel):
    """Minimal Jira extraction config loaded from config/jira.yaml."""

    project_key: str | None = None
    fields: JiraFieldMap = JiraFieldMap()


class JiraAdapterError(RuntimeError):
    """Base error for Jira adapter failures."""


class JiraConfigurationError(JiraAdapterError):
    """Raised when Jira intake is not configured for the requested operation."""


class JiraTicketMismatchError(JiraAdapterError):
    """Raised when a loaded issue does not match the requested ticket id."""


class JiraAdapter:
    """Load Jira issues from local fixtures or a live Jira instance."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        project_key: str | None = None,
        fixture_path: Path | None = None,
        mode: ExecutionMode = ExecutionMode.FIXTURE,
        config_path: Path | None = None,
        issue_loader: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.base_url = base_url
        self.project_key = project_key
        self.fixture_path = fixture_path
        self.mode = mode
        self.config_path = config_path
        self.issue_loader = issue_loader

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig) -> "JiraAdapter":
        """Create a Jira adapter from the runtime configuration."""

        return cls(
            base_url=config.jira_base_url,
            project_key=config.jira_project_key,
            fixture_path=config.jira_fixture_path,
            mode=config.execution_mode,
            config_path=config.repo_root / "config" / "jira.yaml",
        )

    def load_issue(
        self,
        ticket_id: str,
        *,
        fixture_path: Path | None = None,
        strict_ticket_match: bool = True,
    ) -> JiraIssuePayload:
        """Load a Jira issue payload for the provided ticket id."""

        if self.mode == ExecutionMode.LIVE:
            return self._load_live_issue(ticket_id, strict_ticket_match=strict_ticket_match)

        resolved_fixture_path = fixture_path or self.fixture_path
        if resolved_fixture_path is None:
            raise JiraConfigurationError(
                "Jira fixture path is not configured. Set EA_JIRA_FIXTURE_PATH for local intake."
            )

        payload = JiraIssuePayload.model_validate(json.loads(resolved_fixture_path.read_text()))
        if payload.ticket_id != ticket_id:
            if not strict_ticket_match:
                return payload.model_copy(update={"ticket_id": ticket_id})
            raise JiraTicketMismatchError(
                f"Requested ticket '{ticket_id}' does not match fixture ticket '{payload.ticket_id}'."
            )
        return payload

    def _load_live_issue(self, ticket_id: str, *, strict_ticket_match: bool) -> JiraIssuePayload:
        if self.base_url is None:
            raise JiraConfigurationError("EA_JIRA_BASE_URL must be configured for live Jira intake.")

        live_config = _load_jira_project_config(self.config_path)
        raw_issue = self.issue_loader(ticket_id) if self.issue_loader is not None else self._fetch_live_issue(ticket_id)
        issue = _parse_live_issue(
            raw_issue,
            ticket_id=ticket_id,
            project_key=self.project_key or live_config.project_key,
            config=live_config,
        )
        if issue.ticket_id != ticket_id:
            if not strict_ticket_match:
                return issue.model_copy(update={"ticket_id": ticket_id})
            raise JiraTicketMismatchError(
                f"Requested ticket '{ticket_id}' does not match live Jira ticket '{issue.ticket_id}'."
            )
        return issue

    def _fetch_live_issue(self, ticket_id: str) -> dict[str, Any]:
        credentials = load_credentials()
        if not credentials.jira_email or not credentials.jira_token:
            raise JiraConfigurationError("EA_JIRA_EMAIL and EA_JIRA_TOKEN are required for live Jira intake.")
        assert self.base_url is not None

        issue_url = f"{self.base_url.rstrip('/')}/rest/api/3/issue/{ticket_id}"
        try:
            with httpx.Client(auth=(credentials.jira_email, credentials.jira_token), timeout=30.0) as client:
                response = client.get(issue_url)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise JiraAdapterError(f"Failed to load Jira issue '{ticket_id}': {exc}") from exc

        if not isinstance(payload, dict):
            raise JiraAdapterError(f"Unexpected Jira response type for '{ticket_id}': {type(payload).__name__}")
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


@lru_cache(maxsize=8)
def _load_jira_project_config(config_path: Path | None) -> JiraProjectConfig:
    if config_path is None:
        raise JiraConfigurationError("Live Jira intake requires a config/jira.yaml mapping file.")
    if not config_path.exists():
        raise JiraConfigurationError(f"Jira config file does not exist: {config_path}")

    loaded = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(loaded, dict):
        raise JiraConfigurationError(f"Jira config must be a YAML mapping: {config_path}")
    return JiraProjectConfig.model_validate(loaded)


def _parse_live_issue(
    payload: Mapping[str, Any],
    *,
    ticket_id: str,
    project_key: str | None,
    config: JiraProjectConfig,
) -> JiraIssuePayload:
    fields = payload.get("fields")
    if not isinstance(fields, Mapping):
        raise JiraAdapterError(f"Live Jira payload for '{ticket_id}' is missing a fields object.")

    description_text = _extract_text(fields.get("description"))
    parsed_ticket_id = _coerce_scalar(payload.get("key")) or ticket_id
    if project_key and not parsed_ticket_id.startswith(f"{project_key}-"):
        raise JiraAdapterError(
            f"Live Jira ticket '{parsed_ticket_id}' does not match configured project key '{project_key}'."
        )

    package_name = _extract_text_field(
        fields,
        description_text,
        field_id=config.fields.package_name,
        pattern=PACKAGE_PATTERN,
    )
    installed_version = _extract_text_field(
        fields,
        description_text,
        field_id=config.fields.installed_version,
        pattern=INSTALLED_VERSION_PATTERN,
    )
    fixed_version = _extract_text_field(
        fields,
        description_text,
        field_id=config.fields.fixed_version,
        pattern=FIXED_VERSION_PATTERN,
    )
    severity = _extract_text_field(
        fields,
        description_text,
        field_id=config.fields.severity,
        pattern=SEVERITY_PATTERN,
    )
    cve_id = _extract_text_field(
        fields,
        description_text,
        field_id=config.fields.cve_id,
        pattern=CVE_PATTERN,
    )
    affected_repositories = _extract_repositories(
        fields,
        description_text,
        field_id=config.fields.affected_repositories,
    )
    references = _extract_references(
        fields,
        description_text,
        field_id=config.fields.references,
        cve_id=cve_id,
    )

    return JiraIssuePayload(
        ticket_id=parsed_ticket_id,
        summary=_coerce_scalar(fields.get("summary")) or f"Jira issue {ticket_id}",
        description=description_text or None,
        package_name=package_name or _raise_missing_live_field("package_name", ticket_id),
        installed_version=installed_version or _raise_missing_live_field("installed_version", ticket_id),
        fixed_version=fixed_version,
        severity=_normalize_severity(severity),
        affected_repositories=affected_repositories,
        references=references,
    )


def _raise_missing_live_field(field_name: str, ticket_id: str) -> str:
    raise JiraAdapterError(f"Unable to extract '{field_name}' from live Jira issue '{ticket_id}'.")


def _extract_text_field(
    fields: Mapping[str, Any],
    description_text: str,
    *,
    field_id: str | None,
    pattern: re.Pattern[str],
) -> str | None:
    if field_id is not None:
        structured_value = _coerce_scalar(fields.get(field_id))
        if structured_value:
            return structured_value
    match = pattern.search(description_text)
    if match is None:
        return None
    value = match.group("value").strip()
    return value or None


def _extract_repositories(
    fields: Mapping[str, Any],
    description_text: str,
    *,
    field_id: str | None,
) -> list[AffectedRepository]:
    structured_value = fields.get(field_id) if field_id is not None else None
    repositories = _parse_repository_value(structured_value)
    if repositories:
        return repositories

    description_match = DESCRIPTION_REPOSITORY_PATTERN.search(description_text)
    if description_match is None:
        return []

    return _parse_repository_value(description_match.group("value"))


def _parse_repository_value(value: Any) -> list[AffectedRepository]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [_parse_repository_mapping(value)]
    if isinstance(value, list):
        repositories: list[AffectedRepository] = []
        for item in value:
            repositories.extend(_parse_repository_value(item))
        return repositories
    if isinstance(value, str):
        repositories = []
        for raw_line in re.split(r"[\n,]+", value):
            line = raw_line.strip().lstrip("-").strip()
            if not line:
                continue
            repositories.append(_parse_repository_line(line))
        return repositories
    return []


def _parse_repository_mapping(value: Mapping[str, Any]) -> AffectedRepository:
    name = _coerce_scalar(value.get("name"))
    if not name:
        raise JiraAdapterError("Live Jira repository field is missing the repository name.")
    return AffectedRepository(
        name=name,
        clone_url=_coerce_scalar(value.get("clone_url")),
        default_branch=_coerce_scalar(value.get("default_branch")) or "main",
        build_system=_coerce_scalar(value.get("build_system")) or "maven",
        manifest_path=_coerce_scalar(value.get("manifest_path")),
    )


def _parse_repository_line(line: str) -> AffectedRepository:
    parts = [part.strip() for part in line.split("|")]
    if len(parts) == 1:
        return AffectedRepository(name=parts[0])
    if len(parts) == 3:
        name, clone_url, manifest_path = parts
        return AffectedRepository(name=name, clone_url=clone_url, manifest_path=manifest_path)
    if len(parts) >= 4:
        name, clone_url, default_branch, manifest_path = parts[:4]
        return AffectedRepository(
            name=name,
            clone_url=clone_url,
            default_branch=default_branch,
            manifest_path=manifest_path,
        )
    raise JiraAdapterError(f"Unsupported repository entry format in live Jira issue: {line}")


def _extract_references(
    fields: Mapping[str, Any],
    description_text: str,
    *,
    field_id: str | None,
    cve_id: str | None,
) -> list[VulnerabilityReference]:
    raw_value = fields.get(field_id) if field_id is not None else None
    references = _parse_references_value(raw_value)
    if not references:
        references = _parse_references_value(description_text)
    if cve_id and not any(reference.identifier == cve_id for reference in references):
        references.append(VulnerabilityReference(source="cve", identifier=cve_id))
    return references


def _parse_references_value(value: Any) -> list[VulnerabilityReference]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        source = _coerce_scalar(value.get("source"))
        identifier = _coerce_scalar(value.get("identifier"))
        if not source or not identifier:
            return []
        return [
            VulnerabilityReference(
                source=source,
                identifier=identifier,
                url=_coerce_scalar(value.get("url")),
            )
        ]
    if isinstance(value, list):
        references: list[VulnerabilityReference] = []
        for item in value:
            references.extend(_parse_references_value(item))
        return references
    if isinstance(value, str):
        references = []
        for match in REFERENCE_LINE_PATTERN.finditer(value):
            references.append(
                VulnerabilityReference(
                    source=match.group("source").strip().removeprefix("Reference:").strip().lower(),
                    identifier=match.group("identifier").strip(),
                    url=(match.group("url") or "").strip() or None,
                )
            )
        return references
    return []


def _coerce_scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (bool, int, float)):
        return str(value)
    if isinstance(value, Mapping):
        for key in ("value", "name", "key", "id"):
            candidate = _coerce_scalar(value.get(key))
            if candidate:
                return candidate
        return None
    if isinstance(value, list):
        parts = [part for item in value if (part := _coerce_scalar(item))]
        return ", ".join(parts) or None
    return None


def _extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return _extract_doc_nodes(value.get("content"))
    if isinstance(value, list):
        return _extract_doc_nodes(value)
    return str(value)


def _extract_doc_nodes(content: Any) -> str:
    if not isinstance(content, list):
        return ""

    fragments: list[str] = []
    for node in content:
        if not isinstance(node, Mapping):
            continue
        node_type = node.get("type")
        if node_type == "text":
            text = node.get("text")
            if isinstance(text, str):
                fragments.append(text)
            continue

        nested = _extract_doc_nodes(node.get("content"))
        if nested:
            fragments.append(nested)
        if node_type in {"paragraph", "bulletList", "listItem"}:
            fragments.append("\n")

    return "".join(fragments).strip()


def _normalize_severity(value: str | None) -> Severity:
    if value is None:
        return Severity.UNKNOWN
    try:
        return Severity(value.lower())
    except ValueError:
        return Severity.UNKNOWN
