from __future__ import annotations

from execution_accelerator.config import load_runtime_config
from execution_accelerator.graph import bootstrap_ticket_run, load_remediation_state
from execution_accelerator.schemas import WorkflowStatus


def test_bootstrap_ticket_run_persists_checkpointed_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-42",
        runtime_config=config,
        thread_id="sec-42-thread",
    )
    loaded_state = load_remediation_state(
        runtime_config=config,
        thread_id="sec-42-thread",
    )

    assert result.thread_id == "sec-42-thread"
    assert result.checkpoint_path == config.checkpoints_path
    assert result.state.workflow_status == WorkflowStatus.PLANNING_READY
    assert result.state.remediation_plan is not None
    assert config.checkpoints_path.exists()
    assert loaded_state.initial_ticket_id == "SEC-42"
    assert loaded_state.workflow_status == WorkflowStatus.PLANNING_READY
    assert len(loaded_state.audit_events) == 2
