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


class ExecutionMode(StrEnum):
    """Top-level execution mode for fixture-backed versus live integrations."""

    FIXTURE = "fixture"
    LIVE = "live"


class ValidationStatus(StrEnum):
    """Status for validation checks and repo-level validation."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RollbackStatus(StrEnum):
    """Status of rollback work after validation failure."""

    PENDING = "pending"
    APPLIED = "applied"
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


class ApprovalStage(StrEnum):
    """Named approval checkpoints in the workflow."""

    REMEDIATION = "remediation"
    DELIVERY = "delivery"


class FailureClassification(StrEnum):
    """Normalized failure classes for retry and escalation routing."""

    NETWORK_TRANSIENT = "network_transient"
    COMPILE_ERROR = "compile_error"
    TEST_FAILURE = "test_failure"
    POLICY_BLOCK = "policy_block"
    RECIPE_NOOP = "recipe_noop"
    LLM_SCHEMA_INVALID = "llm_schema_invalid"
    LLM_PATCH_UNCOMPILABLE = "llm_patch_uncompilable"
    IDEMPOTENT_HIT = "idempotent_hit"
    UNKNOWN = "unknown"


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
    maven_settings: str | None = None
    proxy_jump: str | None = None
    owner: str | None = None
    tags: list[str] = Field(default_factory=list)


class RepositoryInventoryPayload(BaseSchemaModel):
    """Local inventory fixture used by the Day 3 repository intake flow."""

    repositories: list[RepositoryInventoryRecord] = Field(default_factory=list)


class RemediationTarget(BaseSchemaModel):
    """One remediation unit for a repository/package/version combination."""

    ticket_id: str = Field(min_length=1)
    repository_name: str = Field(min_length=1)
    package_name: str = Field(min_length=1)
    installed_version: str = Field(min_length=1)
    target_version: str | None = None
    clone_url: str = Field(min_length=1)
    default_branch: str = "main"
    build_system: str = "maven"
    manifest_path: str = Field(min_length=1)
    maven_settings: str | None = None
    proxy_jump: str | None = None
    owner: str | None = None
    tags: list[str] = Field(default_factory=list)


class MavenExecutionPlan(BaseSchemaModel):
    """Detected Maven execution settings for a cloned repository workspace."""

    repository: str = Field(min_length=1)
    command: list[str] = Field(default_factory=list)
    root_pom_path: str = Field(min_length=1)
    uses_wrapper: bool = False
    modules: list[str] = Field(default_factory=list)
    profiles: list[str] = Field(default_factory=list)
    settings_xml: str | None = None
    java_home: str | None = None


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


class DependencyCoordinate(BaseSchemaModel):
    """Maven dependency coordinate used in simple remediation planning."""

    group_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class ArtifactCandidate(BaseSchemaModel):
    """Candidate artifact considered during complex remediation planning."""

    coordinate: DependencyCoordinate
    source: str = Field(min_length=1)
    packaging: str = "jar"
    rationale: str = Field(min_length=1)


class CompatibilityChangeType(StrEnum):
    """Kinds of compatibility changes observed between artifact versions."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    DEPRECATED = "deprecated"


class ComplexMigrationTactic(StrEnum):
    """Primary tactic chosen for the complex remediation lane."""

    ADAPTER_SHIM = "adapter_shim"
    FACTORY_INTRODUCTION = "factory_introduction"
    TARGETED_SYMBOL_REWRITE = "targeted_symbol_rewrite"


class CompatibilityDiffEntry(BaseSchemaModel):
    """One compatibility finding for the complex remediation lane."""

    symbol: str = Field(min_length=1)
    change_type: CompatibilityChangeType = CompatibilityChangeType.MODIFIED
    impact: str = Field(min_length=1)
    guidance: str | None = None


class CompatibilityDiffResult(BaseSchemaModel):
    """Placeholder compatibility diff summary between current and target artifacts."""

    package_name: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    target_version: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    risk: CompatibilityRisk = CompatibilityRisk.HIGH
    breaking_changes: list[CompatibilityDiffEntry] = Field(default_factory=list)


class DecompiledArtifactSummary(BaseSchemaModel):
    """Placeholder output from fetching and decompiling one candidate artifact."""

    coordinate: DependencyCoordinate
    source_path: str = Field(min_length=1)
    package_count: int = Field(ge=0)
    symbol_count: int = Field(ge=0)
    notes: str = Field(min_length=1)


class SymbolMappingEntry(BaseSchemaModel):
    """Mapping between a legacy symbol and its target replacement."""

    legacy_symbol: str = Field(min_length=1)
    replacement_symbol: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)


class CodeChangeTarget(BaseSchemaModel):
    """One file-level change target derived from complex remediation analysis."""

    file_path: str = Field(min_length=1)
    change_summary: str = Field(min_length=1)
    related_symbols: list[str] = Field(default_factory=list)


class PomMutationKind(StrEnum):
    """Kinds of pom mutations supported by the Day 5 simple remediation flow."""

    DIRECT_VERSION_BUMP = "direct_version_bump"
    DEPENDENCY_MANAGEMENT_OVERRIDE = "dependency_management_override"


class PomSectionTarget(StrEnum):
    """Pom section targeted by a mutation change."""

    PROJECT_DEPENDENCIES = "project_dependencies"
    DEPENDENCY_MANAGEMENT = "dependency_management"


class PomMutationChange(BaseSchemaModel):
    """One mutation to apply to a pom file."""

    file_path: str = Field(min_length=1)
    dependency: DependencyCoordinate
    mutation_kind: PomMutationKind = PomMutationKind.DIRECT_VERSION_BUMP
    target_section: PomSectionTarget = PomSectionTarget.PROJECT_DEPENDENCIES
    previous_version: str = Field(min_length=1)
    target_version: str = Field(min_length=1)
    xml_path_hint: str = Field(min_length=1)


class PomMutationPlan(BaseSchemaModel):
    """Planned simple remediation changes for one repository."""

    repository: str = Field(min_length=1)
    strategy: RemediationStrategy = RemediationStrategy.SIMPLE_UPDATE
    changes: list[PomMutationChange] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class PreflightResolutionResult(BaseSchemaModel):
    """Result of validating the mutated pom configuration before full remediation."""

    repository: str = Field(min_length=1)
    status: ValidationStatus = ValidationStatus.PENDING
    resolved_version: str = Field(min_length=1)
    dependency_kind: MavenDependencyKind = MavenDependencyKind.DIRECT
    message: str = Field(min_length=1)


class ComplexRemediationPlan(BaseSchemaModel):
    """Planned Day 7 complex-remediation analysis for one repository."""

    repository: str = Field(min_length=1)
    strategy: RemediationStrategy = RemediationStrategy.COMPLEX_REFACTOR
    summary: str = Field(min_length=1)
    artifact_candidates: list[ArtifactCandidate] = Field(default_factory=list)
    compatibility_diff: CompatibilityDiffResult
    migration_tactic: ComplexMigrationTactic = ComplexMigrationTactic.TARGETED_SYMBOL_REWRITE
    tactic_rationale: str = Field(
        default="Breaking changes are narrow enough to handle with direct symbol replacements in affected files.",
        min_length=1,
    )
    migration_steps: list[str] = Field(default_factory=list)
    target_files: list[CodeChangeTarget] = Field(default_factory=list)
    symbol_mappings: list[SymbolMappingEntry] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    requires_code_changes: bool = True


class ComplexCodeChangePlan(BaseSchemaModel):
    """Structured code-change planning placeholder for the complex remediation lane."""

    repository: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    target_files: list[CodeChangeTarget] = Field(default_factory=list)
    symbol_mappings: list[SymbolMappingEntry] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class RollbackPlan(BaseSchemaModel):
    """Placeholder rollback plan emitted after validation failure."""

    repository: str = Field(min_length=1)
    status: RollbackStatus = RollbackStatus.PENDING
    reason: str = Field(min_length=1)
    files_to_restore: list[str] = Field(default_factory=list)


class BranchPublicationResult(BaseSchemaModel):
    """Placeholder branch/commit publication metadata for a completed remediation."""

    repository: str = Field(min_length=1)
    branch_name: str = Field(min_length=1)
    commit_sha: str = Field(min_length=1)
    commit_message: str = Field(min_length=1)
    pushed: bool = True


class PullRequestSummary(BaseSchemaModel):
    """Placeholder pull request metadata emitted after publication."""

    repository: str = Field(min_length=1)
    number: int = Field(ge=1)
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: str = Field(min_length=1)


class JiraCompletionResult(BaseSchemaModel):
    """Placeholder Jira completion metadata for a finished remediation."""

    ticket_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    comment: str = Field(min_length=1)


class RemediationPlan(BaseSchemaModel):
    """Planner output that guides the next stages of execution."""

    strategy: RemediationStrategy = RemediationStrategy.UNKNOWN
    summary: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    target_repositories: list[str] = Field(default_factory=list)
    requires_human_approval: bool = False


class RetryDecision(BaseSchemaModel):
    """Decision produced by the retry classifier."""

    classification: FailureClassification = FailureClassification.UNKNOWN
    next_node: str = Field(min_length=1)
    max_attempts: int = Field(ge=0)
    reason: str = Field(min_length=1)


class PolicyDecision(BaseSchemaModel):
    """Policy evaluation result for one remediation target."""

    allowed: bool = True
    requires_human_approval: bool = False
    requires_delivery_approval: bool = False
    approval_reason: str | None = None
    blocked_reason: str | None = None


class ApprovalRecord(BaseSchemaModel):
    """One persisted human approval decision."""

    stage: ApprovalStage = ApprovalStage.REMEDIATION
    decision: ApprovalDecision = ApprovalDecision.PENDING
    reviewer: str | None = None
    comments: str | None = None


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


class EscalationBundle(BaseSchemaModel):
    """Persisted escalation artifact produced for terminal failures."""

    bundle_path: str = Field(min_length=1)
    failure_classification: FailureClassification = FailureClassification.UNKNOWN
    error_codes: list[str] = Field(default_factory=list)
    modified_files: list[str] = Field(default_factory=list)
    code_diff_summaries: list[str] = Field(default_factory=list)
    complex_migration_tactic: ComplexMigrationTactic | None = None
    complex_target_files: list[str] = Field(default_factory=list)
    complex_open_questions: list[str] = Field(default_factory=list)
    log_files: list[str] = Field(default_factory=list)
    audit_event_count: int = Field(default=0, ge=0)


class LlmCallRecord(BaseSchemaModel):
    """Minimal audit payload for an LLM call."""

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_name: str = Field(min_length=1)
    token_count: int = Field(default=0, ge=0)


class HumanFeedback(BaseSchemaModel):
    """Human review feedback captured during interrupt/resume flows."""

    decision: ApprovalDecision = ApprovalDecision.PENDING
    reviewer: str | None = None
    comments: str | None = None
