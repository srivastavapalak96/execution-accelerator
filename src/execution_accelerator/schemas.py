"""Typed workflow schemas shared across graph nodes and adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class Severity(StrEnum):
    """Normalized vulnerability severity."""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RemediationStrategy(StrEnum):
    """Routing lanes for the remediation workflow."""

    UNKNOWN = "unknown"
    SIMPLE_UPDATE = "simple_update"
    TRANSITIVE_OVERRIDE = "transitive_override"
    COMPLEX_REFACTOR = "complex_refactor"


class WorkflowStatus(StrEnum):
    """Top-level workflow progress markers."""

    PENDING = "pending"
    BOOTSTRAPPED = "bootstrapped"
    PLANNING_READY = "planning_ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationStatus(StrEnum):
    """Status for validation checks and repo-level validation."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class VerificationStatus(StrEnum):
    """Status for advisory and Maven verification steps."""

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ApprovalDecision(StrEnum):
    """Possible human review outcomes."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class BaseSchemaModel(BaseModel):
    """Common model configuration for workflow schemas."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AuditEvent(BaseSchemaModel):
    """Append-only audit event emitted during workflow execution."""

    event_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    details: dict[str, Any] = Field(default_factory=dict)


class VulnerabilityReference(BaseSchemaModel):
    """External reference tied to a vulnerability or remediation record."""

    source: str = Field(min_length=1)
    identifier: str = Field(min_length=1)
    url: str | None = None


class AffectedRepository(BaseSchemaModel):
    """Repository linked to a vulnerability."""

    name: str = Field(min_length=1)
    clone_url: str | None = None
    default_branch: str = "main"
    build_system: str = "maven"
    manifest_path: str | None = None


class VulnerabilityDetails(BaseSchemaModel):
    """Normalized vulnerability metadata used by the remediation workflow."""

    package_name: str = Field(min_length=1)
    installed_version: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    cve_id: str | None = None
    fixed_version: str | None = None
    severity: Severity = Severity.UNKNOWN
    affected_repositories: list[AffectedRepository] = Field(default_factory=list)
    references: list[VulnerabilityReference] = Field(default_factory=list)


class JiraIssuePayload(BaseSchemaModel):
    """Normalized Jira payload used for local Day 3 intake."""

    ticket_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    description: str | None = None
    package_name: str = Field(min_length=1)
    installed_version: str = Field(min_length=1)
    fixed_version: str | None = None
    severity: Severity = Severity.UNKNOWN
    affected_repositories: list[AffectedRepository] = Field(default_factory=list)
    references: list[VulnerabilityReference] = Field(default_factory=list)


class RepositoryInventoryRecord(BaseSchemaModel):
    """Repository metadata discovered during intake and clone preparation."""

    name: str = Field(min_length=1)
    clone_url: str = Field(min_length=1)
    default_branch: str = "main"
    build_system: str = "maven"
    manifest_path: str = Field(min_length=1)
    owner: str | None = None
    tags: list[str] = Field(default_factory=list)


class RepositoryInventoryPayload(BaseSchemaModel):
    """Local inventory fixture used by the Day 3 repository intake flow."""

    repositories: list[RepositoryInventoryRecord] = Field(default_factory=list)


class MavenDependencyKind(StrEnum):
    """Whether the vulnerable dependency is direct or transitive."""

    DIRECT = "direct"
    TRANSITIVE = "transitive"


class CompatibilityRisk(StrEnum):
    """Compatibility risk level for a proposed remediation target."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AdvisoryVerification(BaseSchemaModel):
    """Normalized advisory verification result for a vulnerable package."""

    package_name: str = Field(min_length=1)
    vulnerable_version: str = Field(min_length=1)
    recommended_fix_version: str = Field(min_length=1)
    status: VerificationStatus = VerificationStatus.PENDING
    source: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    cve_id: str | None = None
    severity: Severity = Severity.UNKNOWN
    references: list[VulnerabilityReference] = Field(default_factory=list)


class MavenVerification(BaseSchemaModel):
    """Result of verifying a remediation target against Maven-style metadata."""

    package_name: str = Field(min_length=1)
    current_version: str = Field(min_length=1)
    target_version: str = Field(min_length=1)
    dependency_kind: MavenDependencyKind = MavenDependencyKind.DIRECT
    status: VerificationStatus = VerificationStatus.PENDING
    compatibility_risk: CompatibilityRisk = CompatibilityRisk.LOW
    resolver_note: str = Field(min_length=1)


class RemediationRouteDecision(BaseSchemaModel):
    """Routing decision produced after advisory and Maven verification."""

    strategy: RemediationStrategy = RemediationStrategy.UNKNOWN
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_approval: bool = False


class RemediationPlan(BaseSchemaModel):
    """Planner output that guides the next stages of execution."""

    strategy: RemediationStrategy = RemediationStrategy.UNKNOWN
    summary: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    target_repositories: list[str] = Field(default_factory=list)
    requires_human_approval: bool = False


class ValidationCheck(BaseSchemaModel):
    """Single validation step executed against a repository."""

    name: str = Field(min_length=1)
    status: ValidationStatus = ValidationStatus.PENDING
    details: str | None = None


class RepositoryValidationResult(BaseSchemaModel):
    """Aggregated validation result for one repository."""

    repository: str = Field(min_length=1)
    status: ValidationStatus = ValidationStatus.PENDING
    checks: list[ValidationCheck] = Field(default_factory=list)
    summary: str | None = None


class HumanFeedback(BaseSchemaModel):
    """Human review feedback captured during interrupt/resume flows."""

    decision: ApprovalDecision = ApprovalDecision.PENDING
    reviewer: str | None = None
    comments: str | None = None
