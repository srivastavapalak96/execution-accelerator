"""Stateful remediation graph composition."""

from __future__ import annotations

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
    classify_failure,
    build_execute_complex_scaffold_node,
    build_ingest_and_parse_jira_node,
    build_load_repository_context_node,
    build_preflight_validation_node,
    build_prepare_complex_remediation_node,
    build_publish_remediation_node,
    build_remediate_simple_node,
    build_remediate_transitive_node,
    build_handle_validation_failure_node,
    build_validate_remediation_node,
    build_verify_advisory_node,
    build_verify_maven_target_node,
    escalate,
    select_route,
)
from execution_accelerator.persistence import build_default_thread_id, build_thread_config, sqlite_checkpointer
from execution_accelerator.schemas import RemediationStrategy
from execution_accelerator.state import RemediationState


class BootstrapRunResult(BaseModel):
    """Summary returned after bootstrapping a persisted remediation run."""

    thread_id: str
    checkpoint_path: Path
    state: RemediationState


def build_remediation_graph(
    *,
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
    builder.add_node("bootstrap_state", bootstrap_state)
    builder.add_node("ingest_and_parse_jira", cast(Any, build_ingest_and_parse_jira_node(jira_adapter)))
    builder.add_node(
        "load_repository_context",
        cast(Any, build_load_repository_context_node(repository_inventory_adapter)),
    )
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
    builder.add_node("escalate", cast(Any, escalate))
    builder.add_node("publish_remediation", cast(Any, build_publish_remediation_node(delivery_adapter)))
    builder.add_edge(START, "bootstrap_state")
    builder.add_edge("bootstrap_state", "ingest_and_parse_jira")
    builder.add_edge("ingest_and_parse_jira", "load_repository_context")
    builder.add_edge("load_repository_context", "verify_advisory")
    builder.add_edge("verify_advisory", "verify_maven_target")
    builder.add_edge("verify_maven_target", "select_route")
    builder.add_conditional_edges(
        "select_route",
        _select_remediation_node,
        {
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
        _select_post_validation_node,
        {
            "handle_validation_failure": "handle_validation_failure",
            "publish_remediation": "publish_remediation",
        },
    )
    builder.add_edge("publish_remediation", END)
    builder.add_edge("handle_validation_failure", "classify_failure")
    builder.add_conditional_edges(
        "classify_failure",
        _select_failure_node,
        {
            "escalate": "escalate",
        },
    )
    builder.add_edge("escalate", END)
    return builder


def compile_remediation_graph(
    *,
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
        result = graph.invoke(
            initial_state.model_dump(mode="python"),
            config=build_thread_config(resolved_thread_id),
        )

    return BootstrapRunResult(
        thread_id=resolved_thread_id,
        checkpoint_path=runtime_config.checkpoints_path,
        state=RemediationState.model_validate(result),
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


def _select_remediation_node(state: RemediationState) -> str:
    assert state.route_decision is not None

    if state.route_decision.strategy == RemediationStrategy.SIMPLE_UPDATE:
        return "remediate_simple"
    if state.route_decision.strategy == RemediationStrategy.TRANSITIVE_OVERRIDE:
        return "remediate_transitive"
    if state.route_decision.strategy == RemediationStrategy.COMPLEX_REFACTOR:
        return "prepare_complex_remediation"
    return END


def _select_post_validation_node(state: RemediationState) -> str:
    assert state.validation_results

    if state.validation_results[-1].status == "failed":
        return "handle_validation_failure"
    return "publish_remediation"


def _select_failure_node(state: RemediationState) -> str:
    return "escalate"
