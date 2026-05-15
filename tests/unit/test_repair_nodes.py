"""Unit tests for execution_accelerator.nodes.repair."""

from __future__ import annotations

import json

import pydantic
import pytest

from execution_accelerator.llm.client import StubLlmClient, stub_responder_for
from execution_accelerator.nodes.repair import (
    MAX_FILES_PER_PATCH,
    MAX_LINES_PER_PATCH,
    RepairBudgetExceeded,
    build_repair_compile_node,
    build_repair_tests_node,
)
from execution_accelerator.schemas import FailureClassification
from execution_accelerator.state import RemediationState, RepositoryWorkspace, WorkflowError


def _state_with_compile_failure() -> RemediationState:
    state = RemediationState(initial_ticket_id="SEC-RPR-1")
    state.current_working_repo = "payments-service"
    state.repo_map["payments-service"] = RepositoryWorkspace(
        name="payments-service",
        local_path="/tmp/workspace",
    )
    state.errors.append(
        WorkflowError(
            code="compile_failed",
            message="App.java:42: error: cannot find symbol StringSubstitutor",
            recoverable=True,
            repository="payments-service",
        )
    )
    state.relevant_repair_inputs = [
        ("src/main/java/App.java", "package x; public class App {}"),
    ]
    return state


def _stub_responder(diff: str, files: list[str], rationale: str = "minimal fix") -> "callable":
    return stub_responder_for(
        {
            "rationale": rationale,
            "unified_diff": diff,
            "affected_files": files,
        }
    )


def test_repair_compile_writes_proposal_and_audit_event() -> None:
    diff = (
        "--- a/src/main/java/App.java\n"
        "+++ b/src/main/java/App.java\n"
        "@@ -1 +1 @@\n"
        "-import old.Pkg;\n"
        "+import new.Pkg;\n"
    )
    client = StubLlmClient(
        provider="stub",
        model="m",
        responder=_stub_responder(diff, ["src/main/java/App.java"]),
    )
    node = build_repair_compile_node(client)
    state = _state_with_compile_failure()

    result = node(state)

    assert "repair_proposals" in result
    assert len(result["repair_proposals"]) == 1
    proposal = result["repair_proposals"][0]
    assert proposal.failure_classification == FailureClassification.COMPILE_ERROR
    # BaseSchemaModel strips trailing whitespace; compare on rstripped form.
    assert proposal.unified_diff == diff.rstrip()
    assert proposal.attempt_index == 1
    assert "src/main/java/App.java" in proposal.affected_files
    # Audit event recorded.
    audit_events = result["audit_events"]
    assert audit_events[-1].event_type.startswith("repair.")
    assert audit_events[-1].details["attempt_index"] == 1
    # LLM accounting updated.
    assert len(result["llm_calls"]) == 1
    assert result["llm_tokens_used"] >= 1


def test_repair_tests_uses_test_failure_classification() -> None:
    diff = (
        "--- a/src/test/java/AppTest.java\n"
        "+++ b/src/test/java/AppTest.java\n"
        "@@ -1 +1 @@\n"
        "-assertEquals(1, foo());\n"
        "+assertEquals(2, foo());\n"
    )
    client = StubLlmClient(
        provider="stub",
        model="m",
        responder=_stub_responder(diff, ["src/test/java/AppTest.java"]),
    )
    node = build_repair_tests_node(client)
    state = _state_with_compile_failure()

    result = node(state)

    proposal = result["repair_proposals"][0]
    assert proposal.failure_classification == FailureClassification.TEST_FAILURE


def test_repair_node_increments_attempt_index_across_runs() -> None:
    diff = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n"
    client = StubLlmClient(
        provider="stub",
        model="m",
        responder=_stub_responder(diff, ["x"]),
    )
    node = build_repair_compile_node(client)
    state = _state_with_compile_failure()

    first_result = node(state)
    state.repair_proposals = first_result["repair_proposals"]
    state.llm_calls = first_result["llm_calls"]
    state.audit_events = first_result["audit_events"]
    state.llm_tokens_used = first_result["llm_tokens_used"]

    second_result = node(state)
    assert second_result["repair_proposals"][-1].attempt_index == 2


def test_repair_node_rejects_too_many_files() -> None:
    files = [f"src/F{i}.java" for i in range(MAX_FILES_PER_PATCH + 1)]
    diff = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"
    client = StubLlmClient(
        provider="stub",
        model="m",
        responder=_stub_responder(diff, files),
    )
    node = build_repair_compile_node(client)

    with pytest.raises(RepairBudgetExceeded, match="files"):
        node(_state_with_compile_failure())


def test_repair_node_rejects_too_many_diff_lines() -> None:
    body = "\n".join(["+added line"] * (MAX_LINES_PER_PATCH + 1))
    diff = f"--- a/x\n+++ b/x\n@@ -1 +1 @@\n{body}\n"
    client = StubLlmClient(
        provider="stub",
        model="m",
        responder=_stub_responder(diff, ["x"]),
    )
    node = build_repair_compile_node(client)

    with pytest.raises(RepairBudgetExceeded, match="lines"):
        node(_state_with_compile_failure())


def test_repair_node_propagates_validation_error_when_response_missing_field() -> None:
    bad_responder = stub_responder_for({"rationale": "but no diff"})
    client = StubLlmClient(provider="stub", model="m", responder=bad_responder)
    node = build_repair_compile_node(client)

    with pytest.raises(pydantic.ValidationError):
        node(_state_with_compile_failure())


def test_repair_node_supports_custom_prompt_loader() -> None:
    captured_prompts: list[str] = []

    def responder(prompt: str) -> str:
        captured_prompts.append(prompt)
        return json.dumps(
            {
                "rationale": "ok",
                "unified_diff": "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
                "affected_files": ["x"],
            }
        )

    client = StubLlmClient(provider="stub", model="m", responder=responder)
    node = build_repair_compile_node(
        client,
        prompt_loader=lambda: "CUSTOM PROMPT {failure_classification}: {error_excerpt}\n{file_excerpts}",
    )
    node(_state_with_compile_failure())

    assert any(prompt.startswith("CUSTOM PROMPT compile_error") for prompt in captured_prompts)
