"""Typed remediation state for the LangGraph workflow."""

from __future__ import annotations

from pydantic import Field

from execution_accelerator.schemas import (
    ApprovalDecision,
    AdvisoryVerification,
    ArtifactCandidate,
    AuditEvent,
    BaseSchemaModel,
    BranchPublicationResult,
    ComplexCodeChangePlan,
    CompatibilityDiffResult,
    ComplexRemediationPlan,
    DecompiledArtifactSummary,
    EscalationBundle,
    FailureClassification,
    JiraCompletionResult,
    LlmCallRecord,
    MavenVerification,
    HumanFeedback,
    PolicyDecision,
    PomMutationPlan,
    PreflightResolutionResult,
    MavenExecutionPlan,
    RemediationPlan,
    RemediationRouteDecision,
    RepositoryValidationResult,
    RollbackPlan,
    PullRequestSummary,
    SymbolMappingEntry,
    RemediationTarget,
    VulnerabilityDetails,
    WorkflowStatus,
)


class RepositoryWorkspace(BaseSchemaModel):
    """Repository-specific execution context tracked in workflow state."""

    name: str = Field(min_length=1)
    local_path: str = Field(min_length=1)
    clone_url: str | None = None
    default_branch: str = "main"
    build_system: str = "maven"
    manifest_path: str | None = None
    maven_settings: str | None = None
    proxy_jump: str | None = None
    owner: str | None = None
    tags: list[str] = Field(default_factory=list)


class SkippedRepository(BaseSchemaModel):
    """Repository skipped during remediation with an explicit reason."""

    name: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class CodeDiffSummary(BaseSchemaModel):
    """Lightweight diff metadata produced by remediation steps."""

    file_path: str = Field(min_length=1)
    change_summary: str = Field(min_length=1)
    additions: int = Field(default=0, ge=0)
    deletions: int = Field(default=0, ge=0)


class WorkflowError(BaseSchemaModel):
    """Structured workflow error captured for retry and audit behavior."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    recoverable: bool = False
    repository: str | None = None


class RemediationState(BaseSchemaModel):
    """End-to-end workflow state persisted by LangGraph checkpoints."""

    initial_ticket_id: str = Field(min_length=1)
    workflow_status: WorkflowStatus = WorkflowStatus.PENDING
    vulnerability_details: VulnerabilityDetails | None = None
    advisory_verification: AdvisoryVerification | None = None
    maven_verification: MavenVerification | None = None
    route_decision: RemediationRouteDecision | None = None
    pom_mutation_plan: PomMutationPlan | None = None
    preflight_resolution: PreflightResolutionResult | None = None
    artifact_candidates: list[ArtifactCandidate] = Field(default_factory=list)
    compatibility_diff: CompatibilityDiffResult | None = None
    complex_remediation_plan: ComplexRemediationPlan | None = None
    decompiled_artifacts: list[DecompiledArtifactSummary] = Field(default_factory=list)
    symbol_mappings: list[SymbolMappingEntry] = Field(default_factory=list)
    code_change_plan: ComplexCodeChangePlan | None = None
    maven_plan: MavenExecutionPlan | None = None
    targets: list[RemediationTarget] = Field(default_factory=list)
    current_target_index: int = Field(default=0, ge=0)
    repo_map: dict[str, RepositoryWorkspace] = Field(default_factory=dict)
    pending_repos: list[str] = Field(default_factory=list)
    current_working_repo: str | None = None
    completed_repos: list[str] = Field(default_factory=list)
    skipped_repos: list[SkippedRepository] = Field(default_factory=list)
    remediation_plan: RemediationPlan | None = None
    modified_files: list[str] = Field(default_factory=list)
    code_diffs: list[CodeDiffSummary] = Field(default_factory=list)
    validation_results: list[RepositoryValidationResult] = Field(default_factory=list)
    rollback_plan: RollbackPlan | None = None
    branch_publication: BranchPublicationResult | None = None
    pull_request_summary: PullRequestSummary | None = None
    jira_completion: JiraCompletionResult | None = None
    total_attempts: int = Field(default=0, ge=0)
    failure_classifications: list[FailureClassification] = Field(default_factory=list)
    policy_decisions: list[PolicyDecision] = Field(default_factory=list)
    llm_calls: list[LlmCallRecord] = Field(default_factory=list)
    llm_tokens_used: int = Field(default=0, ge=0)
    errors: list[WorkflowError] = Field(default_factory=list)
    retry_count: int = Field(default=0, ge=0)
    requires_human_approval: bool = False
    human_feedback: HumanFeedback | None = None
    escalation_bundle: EscalationBundle | None = None
    audit_events: list[AuditEvent] = Field(default_factory=list)

    @property
    def human_approval_decision(self) -> ApprovalDecision:
        """Return the current approval decision, defaulting to pending."""

        if self.human_feedback is None:
            return ApprovalDecision.PENDING
        return self.human_feedback.decision
