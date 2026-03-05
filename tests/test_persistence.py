from __future__ import annotations

from execution_accelerator.config import load_runtime_config
from execution_accelerator.persistence import build_default_thread_id, ensure_runtime_directories


def test_build_default_thread_id_normalizes_ticket_id() -> None:
    assert build_default_thread_id("SEC-123 / Maven Upgrade") == "ticket-sec-123-maven-upgrade"


def test_ensure_runtime_directories_creates_local_layout(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    config = load_runtime_config(repo_root=tmp_path)

    ensure_runtime_directories(config)

    assert config.data_dir.is_dir()
    assert config.workspace_dir.is_dir()
    assert config.logs_dir.is_dir()
    assert config.checkpoints_path.parent.is_dir()
