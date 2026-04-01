"""Stateful remediation graph composition."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from execution_accelerator.adapters import (
    AdvisoryVerificationAdapter,
    ComplexRemediationAdapter,
    DeliveryAdapter,
    JiraAdapter,
    MavenVerificationAdapter,
    PomMutationAdapter,
    PreflightResolutionAdapter,
    RepositoryInventoryAdapter,
    ValidationAdapter,
)
from execution_accelerator.config import RuntimeConfig
from execution_accelerator.nodes import (
    bootstrap_state,
    build_apply_policy_node,
    build_check_repository_idempotency_node,
    build_prepare_delivery_approval_node,
    build_review_approval_node,
    build_escalate_node,
    classify_failure,
    build_detect_maven_profile_node,
    build_execute_complex_scaffold_node,
    build_ingest_and_parse_jira_node,
    build_load_repository_context_node,
    build_preflight_validation_node,
    build_prepare_complex_remediation_node,
    build_publish_remediation_node,
    build_probe_credentials_node,
    build_remediate_simple_node,
    build_remediate_transitive_node,
    build_skip_publish_for_dry_run_node,
    build_handle_validation_failure_node,
    build_validate_remediation_node,
    build_verify_advisory_node,
    build_verify_maven_target_node,
    select_route,
)
from execution_accelerator.policy import PolicyEngine
from execution_accelerator.persistence import build_default_thread_id, build_thread_config, sqlite_checkpointer
from execution_accelerator.schemas import ApprovalStage, HumanFeedback, RemediationStrategy, WorkflowStatus
from execution_accelerator.state import (
    RemediationState,
    StateInvariantViolation,
    build_state_invariant_update,
    require_state_field,
)


_REMEDIATION_APPROVAL_REVIEW_NODE = "review_remediation_approval"
_PREPARE_DELIVERY_APPROVAL_NODE = "prepare_delivery_approval"
_DELIVERY_APPROVAL_REVIEW_NODE = "review_delivery_approval"


class BootstrapRunResult(BaseModel):
    """Summary returned after bootstrapping a persisted remediation run."""

    thread_id: str
    checkpoint_path: Path
    state: RemediationState


def build_remediation_graph(
    *,
    runtime_config: RuntimeConfig,
    jira_adapter: JiraAdapter,
    repository_inventory_adapter: RepositoryInventoryAdapter,
    advisory_verification_adapter: AdvisoryVerificationAdapter,
    maven_verification_adapter: MavenVerificationAdapter,
    complex_remediation_adapter: ComplexRemediationAdapter,
    pom_mutation_adapter: PomMutationAdapter,
    preflight_resolution_adapter: PreflightResolutionAdapter,
    validation_adapter: ValidationAdapter,
    delivery_adapter: DeliveryAdapter,
) -> Any:
    """Build the Day 10 stateful remediation graph."""

    builder = StateGraph(RemediationState)
    post_validation_selector = _build_post_validation_selector(dry_run=runtime_config.dry_run)
    builder.add_node("bootstrap_state", bootstrap_state)
    builder.add_node("probe_credentials", cast(Any, build_probe_credentials_node(runtime_config)))
    builder.add_node("ingest_and_parse_jira", cast(Any, build_ingest_and_parse_jira_node(jira_adapter)))
    builder.add_node(
        "load_repository_context",
        cast(Any, build_load_repository_context_node(repository_inventory_adapter)),
    )
    builder.add_node(
        "check_repository_idempotency",
        cast(Any, build_check_repository_idempotency_node(repository_inventory_adapter)),
    )
    builder.add_node("detect_maven_profile", cast(Any, build_detect_maven_profile_node(runtime_config)))
    builder.add_node(
        "verify_advisory",
        cast(Any, build_verify_advisory_node(advisory_verification_adapter)),
    )
    builder.add_node(
        "verify_maven_target",
        cast(Any, build_verify_maven_target_node(maven_verification_adapter)),
    )
    builder.add_node("select_route", select_route)
    builder.add_node(
        "apply_policy",
        cast(Any, build_apply_policy_node(PolicyEngine(config_path=runtime_config.repo_root / "config" / "policy.yaml"))),
    )
    builder.add_node(
        _REMEDIATION_APPROVAL_REVIEW_NODE,
        cast(Any, build_review_approval_node(ApprovalStage.REMEDIATION)),
    )
    builder.add_node(
        _PREPARE_DELIVERY_APPROVAL_NODE,
        cast(Any, build_prepare_delivery_approval_node()),
    )
    builder.add_node(
        _DELIVERY_APPROVAL_REVIEW_NODE,
        cast(Any, build_review_approval_node(ApprovalStage.DELIVERY)),
    )
    builder.add_node(
        "prepare_complex_remediation",
        cast(Any, build_prepare_complex_remediation_node(complex_remediation_adapter)),
    )
    builder.add_node(
        "execute_complex_scaffold",
        cast(Any, build_execute_complex_scaffold_node(complex_remediation_adapter)),
    )
    builder.add_node("remediate_simple", cast(Any, build_remediate_simple_node(pom_mutation_adapter)))
    builder.add_node("remediate_transitive", cast(Any, build_remediate_transitive_node(pom_mutation_adapter)))
    builder.add_node(
        "preflight_validate",
        cast(Any, build_preflight_validation_node(preflight_resolution_adapter)),
    )
    builder.add_node("validate_remediation", cast(Any, build_validate_remediation_node(validation_adapter)))
    builder.add_node(
        "handle_validation_failure",
        cast(Any, build_handle_validation_failure_node(validation_adapter)),
    )
    builder.add_node("classify_failure", cast(Any, classify_failure))
    builder.add_node("escalate", cast(Any, build_escalate_node(runtime_config)))
    builder.add_node("skip_publish_for_dry_run", cast(Any, build_skip_publish_for_dry_run_node(runtime_config)))
    builder.add_node("publish_remediation", cast(Any, build_publish_remediation_node(delivery_adapter)))
    builder.add_edge(START, "bootstrap_state")
    builder.add_edge("bootstrap_state", "probe_credentials")
    builder.add_edge("probe_credentials", "ingest_and_parse_jira")
    builder.add_edge("ingest_and_parse_jira", "load_repository_context")
    builder.add_edge("load_repository_context", "check_repository_idempotency")
    builder.add_conditional_edges(
        "check_repository_idempotency",
        _select_post_idempotency_node,
        {
            "detect_maven_profile": "detect_maven_profile",
            END: END,
        },
    )
    builder.add_edge("detect_maven_profile", "verify_advisory")
    builder.add_edge("verify_advisory", "verify_maven_target")
    builder.add_edge("verify_maven_target", "select_route")
    builder.add_edge("select_route", "apply_policy")
    builder.add_conditional_edges(
        "apply_policy",
        _select_post_policy_node,
        {
            _REMEDIATION_APPROVAL_REVIEW_NODE: _REMEDIATION_APPROVAL_REVIEW_NODE,
            "prepare_complex_remediation": "prepare_complex_remediation",
            "remediate_simple": "remediate_simple",
            "remediate_transitive": "remediate_transitive",
            END: END,
        },
    )
    builder.add_conditional_edges(
        _REMEDIATION_APPROVAL_REVIEW_NODE,
        _select_post_approval_node,
        {
            "classify_failure": "classify_failure",
            "prepare_complex_remediation": "prepare_complex_remediation",
            "remediate_simple": "remediate_simple",
            "remediate_transitive": "remediate_transitive",
            END: END,
        },
    )
    builder.add_edge("prepare_complex_remediation", "execute_complex_scaffold")
    builder.add_edge("execute_complex_scaffold", "validate_remediation")
    builder.add_edge("remediate_simple", "preflight_validate")
    builder.add_edge("remediate_transitive", "preflight_validate")
    builder.add_edge("preflight_validate", "validate_remediation")
    builder.add_conditional_edges(
        "validate_remediation",
        post_validation_selector,
        {
            "handle_validation_failure": "handle_validation_failure",
            _PREPARE_DELIVERY_APPROVAL_NODE: _PREPARE_DELIVERY_APPROVAL_NODE,
            "skip_publish_for_dry_run": "skip_publish_for_dry_run",
            "publish_remediation": "publish_remediation",
        },
    )
    builder.add_edge(_PREPARE_DELIVERY_APPROVAL_NODE, _DELIVERY_APPROVAL_REVIEW_NODE)
    builder.add_conditional_edges(
        _DELIVERY_APPROVAL_REVIEW_NODE,
        _select_post_delivery_approval_node,
        {
            "classify_failure": "classify_failure",
            "publish_remediation": "publish_remediation",
            END: END,
        },
    )
    builder.add_conditional_edges(
        "publish_remediation",
        _select_post_delivery_node,
        {
            "classify_failure": "classify_failure",
            "detect_maven_profile": "detect_maven_profile",
            END: END,
        },
    )
    builder.add_conditional_edges(
        "skip_publish_for_dry_run",
        _select_post_delivery_node,
        {
            "detect_maven_profile": "detect_maven_profile",
            END: END,
        },
    )
    builder.add_edge("handle_validation_failure", "classify_failure")
    builder.add_conditional_edges(
        "classify_failure",
        _select_failure_node,
        {
            "execute_complex_scaffold": "execute_complex_scaffold",
            "escalate": "escalate",
            "publish_remediation": "publish_remediation",
            "remediate_simple": "remediate_simple",
            "remediate_transitive": "remediate_transitive",
        },
    )
    builder.add_edge("escalate", END)
    return builder


def compile_remediation_graph(
    *,
    runtime_config: RuntimeConfig,
    jira_adapter: JiraAdapter,
    repository_inventory_adapter: RepositoryInventoryAdapter,
    advisory_verification_adapter: AdvisoryVerificationAdapter,
    maven_verification_adapter: MavenVerificationAdapter,
    complex_remediation_adapter: ComplexRemediationAdapter,
    pom_mutation_adapter: PomMutationAdapter,
    preflight_resolution_adapter: PreflightResolutionAdapter,
    validation_adapter: ValidationAdapter,
    delivery_adapter: DeliveryAdapter,
    checkpointer: Any | None = None,
) -> Any:
    """Compile the remediation graph, optionally with persistence."""

    return build_remediation_graph(
        runtime_config=runtime_config,
        jira_adapter=jira_adapter,
        repository_inventory_adapter=repository_inventory_adapter,
        advisory_verification_adapter=advisory_verification_adapter,
        maven_verification_adapter=maven_verification_adapter,
        complex_remediation_adapter=complex_remediation_adapter,
        pom_mutation_adapter=pom_mutation_adapter,
        preflight_resolution_adapter=preflight_resolution_adapter,
        validation_adapter=validation_adapter,
        delivery_adapter=delivery_adapter,
    ).compile(checkpointer=checkpointer, name="execution_accelerator")


def bootstrap_ticket_run(
    ticket_id: str,
    *,
    runtime_config: RuntimeConfig,
    thread_id: str | None = None,
) -> BootstrapRunResult:
    """Bootstrap a persisted remediation thread for a Jira ticket id."""

    resolved_thread_id = thread_id or build_default_thread_id(ticket_id)
    initial_state = RemediationState(initial_ticket_id=ticket_id)
    jira_adapter = JiraAdapter.from_runtime_config(runtime_config)
    repository_inventory_adapter = RepositoryInventoryAdapter.from_runtime_config(runtime_config)
    advisory_verification_adapter = AdvisoryVerificationAdapter.from_runtime_config(runtime_config)
    maven_verification_adapter = MavenVerificationAdapter.from_runtime_config(runtime_config)
    complex_remediation_adapter = ComplexRemediationAdapter.from_runtime_config(runtime_config)
    pom_mutation_adapter = PomMutationAdapter.from_runtime_config(runtime_config)
    preflight_resolution_adapter = PreflightResolutionAdapter.from_runtime_config(runtime_config)
    validation_adapter = ValidationAdapter.from_runtime_config(runtime_config)
    delivery_adapter = DeliveryAdapter.from_runtime_config(runtime_config)

    with sqlite_checkpointer(runtime_config) as checkpointer:
        graph = compile_remediation_graph(
            runtime_config=runtime_config,
            jira_adapter=jira_adapter,
            repository_inventory_adapter=repository_inventory_adapter,
            advisory_verification_adapter=advisory_verification_adapter,
            maven_verification_adapter=maven_verification_adapter,
            complex_remediation_adapter=complex_remediation_adapter,
            pom_mutation_adapter=pom_mutation_adapter,
            preflight_resolution_adapter=preflight_resolution_adapter,
            validation_adapter=validation_adapter,
            delivery_adapter=delivery_adapter,
            checkpointer=checkpointer,
        )
        config = build_thread_config(resolved_thread_id)
        try:
            result = graph.invoke(
                initial_state.model_dump(mode="python"),
                config=config,
                interrupt_before=[_REMEDIATION_APPROVAL_REVIEW_NODE, _DELIVERY_APPROVAL_REVIEW_NODE],
            )
            state = RemediationState.model_validate(result)
        except StateInvariantViolation as violation:
            state = _persist_invariant_failure(
                graph=graph,
                config=config,
                runtime_config=runtime_config,
                fallback_state=initial_state,
                violation=violation,
            )

    return BootstrapRunResult(
        thread_id=resolved_thread_id,
        checkpoint_path=runtime_config.checkpoints_path,
        state=state,
    )


def load_remediation_state(*, runtime_config: RuntimeConfig, thread_id: str) -> RemediationState:
    """Load the latest checkpointed remediation state for a thread."""

    jira_adapter = JiraAdapter.from_runtime_config(runtime_config)
    repository_inventory_adapter = RepositoryInventoryAdapter.from_runtime_config(runtime_config)
    advisory_verification_adapter = AdvisoryVerificationAdapter.from_runtime_config(runtime_config)
    maven_verification_adapter = MavenVerificationAdapter.from_runtime_config(runtime_config)
    complex_remediation_adapter = ComplexRemediationAdapter.from_runtime_config(runtime_config)
    pom_mutation_adapter = PomMutationAdapter.from_runtime_config(runtime_config)
    preflight_resolution_adapter = PreflightResolutionAdapter.from_runtime_config(runtime_config)
    validation_adapter = ValidationAdapter.from_runtime_config(runtime_config)
    delivery_adapter = DeliveryAdapter.from_runtime_config(runtime_config)
    with sqlite_checkpointer(runtime_config) as checkpointer:
        graph = compile_remediation_graph(
            runtime_config=runtime_config,
            jira_adapter=jira_adapter,
            repository_inventory_adapter=repository_inventory_adapter,
            advisory_verification_adapter=advisory_verification_adapter,
            maven_verification_adapter=maven_verification_adapter,
            complex_remediation_adapter=complex_remediation_adapter,
            pom_mutation_adapter=pom_mutation_adapter,
            preflight_resolution_adapter=preflight_resolution_adapter,
            validation_adapter=validation_adapter,
            delivery_adapter=delivery_adapter,
            checkpointer=checkpointer,
        )
        snapshot = graph.get_state(build_thread_config(thread_id))
    return RemediationState.model_validate(snapshot.values)


def resume_ticket_run(
    *, runtime_config: RuntimeConfig, thread_id: str, human_feedback: HumanFeedback | None = None
) -> BootstrapRunResult:
    """Resume a persisted thread when possible, or rehydrate its latest state."""

    jira_adapter = JiraAdapter.from_runtime_config(runtime_config)
    repository_inventory_adapter = RepositoryInventoryAdapter.from_runtime_config(runtime_config)
    advisory_verification_adapter = AdvisoryVerificationAdapter.from_runtime_config(runtime_config)
    maven_verification_adapter = MavenVerificationAdapter.from_runtime_config(runtime_config)
    complex_remediation_adapter = ComplexRemediationAdapter.from_runtime_config(runtime_config)
    pom_mutation_adapter = PomMutationAdapter.from_runtime_config(runtime_config)
    preflight_resolution_adapter = PreflightResolutionAdapter.from_runtime_config(runtime_config)
    validation_adapter = ValidationAdapter.from_runtime_config(runtime_config)
    delivery_adapter = DeliveryAdapter.from_runtime_config(runtime_config)
    config = build_thread_config(thread_id)
    with sqlite_checkpointer(runtime_config) as checkpointer:
        graph = compile_remediation_graph(
            runtime_config=runtime_config,
            jira_adapter=jira_adapter,
            repository_inventory_adapter=repository_inventory_adapter,
            advisory_verification_adapter=advisory_verification_adapter,
            maven_verification_adapter=maven_verification_adapter,
            complex_remediation_adapter=complex_remediation_adapter,
            pom_mutation_adapter=pom_mutation_adapter,
            preflight_resolution_adapter=preflight_resolution_adapter,
            validation_adapter=validation_adapter,
            delivery_adapter=delivery_adapter,
            checkpointer=checkpointer,
        )
        if human_feedback is not None:
            snapshot = graph.get_state(config)
            current_state = RemediationState.model_validate(snapshot.values)
            approval_stage = (
                ApprovalStage.DELIVERY
                if current_state.pending_approval_stage == ApprovalStage.DELIVERY
                else ApprovalStage.REMEDIATION
            )
            approval_node = (
                _DELIVERY_APPROVAL_REVIEW_NODE
                if approval_stage == ApprovalStage.DELIVERY
                else _REMEDIATION_APPROVAL_REVIEW_NODE
            )
            review_update = build_review_approval_node(approval_stage)(
                current_state.model_copy(update={"human_feedback": human_feedback})
            )
            review_update["human_feedback"] = human_feedback.model_dump(mode="python")
            graph.update_state(
                config,
                review_update,
                as_node=approval_node,
            )
            try:
                state = RemediationState.model_validate(graph.invoke(None, config=config))
            except StateInvariantViolation as violation:
                state = _persist_invariant_failure(
                    graph=graph,
                    config=config,
                    runtime_config=runtime_config,
                    fallback_state=current_state,
                    violation=violation,
                )
        else:
            state = RemediationState.model_validate(graph.get_state(config).values)
    return BootstrapRunResult(thread_id=thread_id, checkpoint_path=runtime_config.checkpoints_path, state=state)


def _select_remediation_node(state: RemediationState) -> str:
    route_decision = require_state_field(
        state.route_decision,
        source="_select_remediation_node",
        field_name="route_decision",
        message="Remediation routing requires a selected remediation route.",
        repository=state.current_working_repo,
    )

    if route_decision.strategy == RemediationStrategy.SIMPLE_UPDATE:
        return "remediate_simple"
    if route_decision.strategy == RemediationStrategy.TRANSITIVE_OVERRIDE:
        return "remediate_transitive"
    if route_decision.strategy == RemediationStrategy.COMPLEX_REFACTOR:
        return "prepare_complex_remediation"
    return END


def _select_post_idempotency_node(state: RemediationState) -> str:
    return "detect_maven_profile" if state.pending_repos else END


def _select_post_policy_node(state: RemediationState) -> str:
    if state.policy_decisions and not state.policy_decisions[-1].allowed:
        return END
    if state.requires_human_approval:
        return _REMEDIATION_APPROVAL_REVIEW_NODE
    return _select_remediation_node(state)


def _select_post_approval_node(state: RemediationState) -> str:
    if state.human_approval_decision == "approved":
        return _select_remediation_node(state)
    if state.human_approval_decision == "rejected":
        return "classify_failure"
    return END


def _build_post_validation_selector(*, dry_run: bool) -> Callable[[RemediationState], str]:
    def select_post_validation_node(state: RemediationState) -> str:
        require_state_field(
            state.validation_results[-1] if state.validation_results else None,
            source="_build_post_validation_selector",
            field_name="validation_results",
            message="Post-validation routing requires at least one validation result.",
            repository=state.current_working_repo,
        )

        if state.validation_results[-1].status == "failed":
            return "handle_validation_failure"
        if dry_run:
            return "skip_publish_for_dry_run"
        if state.requires_delivery_approval and not _has_approved_stage(state, ApprovalStage.DELIVERY):
            return _PREPARE_DELIVERY_APPROVAL_NODE
        return "publish_remediation"

    return select_post_validation_node


def _select_failure_node(state: RemediationState) -> str:
    if state.retry_decision is not None:
        return state.retry_decision.next_node
    return "escalate"


def _select_post_delivery_approval_node(state: RemediationState) -> str:
    if state.human_approval_decision == "approved":
        return "publish_remediation"
    if state.human_approval_decision == "rejected":
        return "classify_failure"
    return END


def _select_post_delivery_node(state: RemediationState) -> str:
    if state.workflow_status == WorkflowStatus.FAILED and state.errors:
        return "classify_failure"
    if state.pending_repos:
        return "detect_maven_profile"
    return END


def _has_approved_stage(state: RemediationState, stage: ApprovalStage) -> bool:
    return any(record.stage == stage and record.decision == "approved" for record in state.approval_history)


def _persist_invariant_failure(
    *,
    graph: Any,
    config: Any,
    runtime_config: RuntimeConfig,
    fallback_state: RemediationState,
    violation: StateInvariantViolation,
) -> RemediationState:
    current_state = fallback_state
    try:
        snapshot = graph.get_state(config)
        if getattr(snapshot, "values", None):
            current_state = RemediationState.model_validate(snapshot.values)
    except Exception:
        current_state = fallback_state

    invariant_update = build_state_invariant_update(current_state, violation=violation)
    failed_state = current_state.model_copy(update=invariant_update)
    escalation_update = build_escalate_node(runtime_config)(failed_state)
    graph.update_state(config, {**invariant_update, **escalation_update}, as_node="escalate")
    return RemediationState.model_validate(graph.get_state(config).values)
