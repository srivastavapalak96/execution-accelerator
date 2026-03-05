"""Minimal LangGraph bootstrap for the Day 2 foundation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from execution_accelerator.config import RuntimeConfig
from execution_accelerator.nodes import bootstrap_state, prepare_planning_stub
from execution_accelerator.persistence import build_default_thread_id, build_thread_config, sqlite_checkpointer
from execution_accelerator.state import RemediationState


class BootstrapRunResult(BaseModel):
    """Summary returned after bootstrapping a persisted remediation run."""

    thread_id: str
    checkpoint_path: Path
    state: RemediationState


def build_remediation_graph() -> StateGraph:
    """Build the minimal stateful remediation graph."""

    builder = StateGraph(RemediationState)
    builder.add_node("bootstrap_state", bootstrap_state)
    builder.add_node("prepare_planning_stub", prepare_planning_stub)
    builder.add_edge(START, "bootstrap_state")
    builder.add_edge("bootstrap_state", "prepare_planning_stub")
    builder.add_edge("prepare_planning_stub", END)
    return builder


def compile_remediation_graph(*, checkpointer: Any | None = None):
    """Compile the remediation graph, optionally with persistence."""

    return build_remediation_graph().compile(checkpointer=checkpointer, name="execution_accelerator")


def bootstrap_ticket_run(
    ticket_id: str,
    *,
    runtime_config: RuntimeConfig,
    thread_id: str | None = None,
) -> BootstrapRunResult:
    """Bootstrap a persisted remediation thread for a Jira ticket id."""

    resolved_thread_id = thread_id or build_default_thread_id(ticket_id)
    initial_state = RemediationState(initial_ticket_id=ticket_id)

    with sqlite_checkpointer(runtime_config) as checkpointer:
        graph = compile_remediation_graph(checkpointer=checkpointer)
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

    with sqlite_checkpointer(runtime_config) as checkpointer:
        graph = compile_remediation_graph(checkpointer=checkpointer)
        snapshot = graph.get_state(build_thread_config(thread_id))
    return RemediationState.model_validate(snapshot.values)
