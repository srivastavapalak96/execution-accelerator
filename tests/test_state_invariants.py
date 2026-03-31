from __future__ import annotations

from execution_accelerator.config import load_runtime_config
from execution_accelerator.graph import bootstrap_ticket_run
from execution_accelerator.state import RemediationState, StateInvariantViolation, require_state_field


def test_require_state_field_raises_explicit_invariant_violation() -> None:
    try:
        require_state_field(
            None,
            source="test_node",
            field_name="current_working_repo",
            message="Current working repo is required.",
        )
    except StateInvariantViolation as violation:
        assert violation.source == "test_node"
        assert violation.field_name == "current_working_repo"
        assert violation.workflow_error.code == "state_invariant_violated"
        assert violation.workflow_error.message == "Current working repo is required."
    else:
        raise AssertionError("Expected StateInvariantViolation to be raised.")


def test_bootstrap_ticket_run_escalates_state_invariant_violation(monkeypatch, tmp_path) -> None:
    def broken_bootstrap(state: RemediationState) -> dict[str, object]:
        require_state_field(
            None,
            source="bootstrap_state",
            field_name="vulnerability_details",
            message="Broken bootstrap invariant.",
        )
        return {}

    monkeypatch.setattr("execution_accelerator.graph.builder.bootstrap_state", broken_bootstrap)
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-9999",
        runtime_config=config,
        thread_id="sec-9999-invariant",
    )

    assert result.state.workflow_status == "failed"
    assert result.state.errors[-1].code == "state_invariant_violated"
    assert result.state.errors[-1].message == "Broken bootstrap invariant."
    assert result.state.escalation_bundle is not None
    assert result.state.audit_events[-2].event_type == "state.invariant"
    assert result.state.audit_events[-1].event_type == "failure.escalate"
