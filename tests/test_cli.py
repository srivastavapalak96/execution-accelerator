from __future__ import annotations

from execution_accelerator.cli.main import main


def test_main_prints_version(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["execution-accelerator", "--version"])

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "0.1.0"


def test_main_prints_config(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr("sys.argv", ["execution-accelerator", "--show-config"])
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "repo_root=" in captured.out
    assert f"data_dir={tmp_path / 'data'}" in captured.out
    assert f"workspace_dir={tmp_path / 'workspace'}" in captured.out
    assert f"logs_dir={tmp_path / 'logs'}" in captured.out
