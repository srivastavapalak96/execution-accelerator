from __future__ import annotations

from pathlib import Path
import sys

import pytest

from execution_accelerator.execution import CommandTimeoutError, redact, run_command


def test_redact_masks_explicit_secrets_and_common_token_patterns() -> None:
    text = "token=super-secret ghp_1234567890abcdef1234 Authorization: Bearer abc.def.ghi"

    redacted = redact(text, secrets=["super-secret"])

    assert "super-secret" not in redacted
    assert "ghp_1234567890abcdef1234" not in redacted
    assert "Bearer abc.def.ghi" not in redacted
    assert redacted.count("[REDACTED]") == 3


def test_run_command_writes_redacted_output_to_result_and_log(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "command.log"

    result = run_command(
        [
            sys.executable,
            "-c",
            (
                "import os, sys; "
                "print(f'stdout={os.environ[\"TOKEN\"]}'); "
                "print(f'stderr={os.environ[\"TOKEN\"]}', file=sys.stderr)"
            ),
        ],
        cwd=tmp_path,
        timeout=5,
        env={"TOKEN": "super-secret"},
        log_path=log_path,
        secrets=["super-secret"],
    )

    log_text = log_path.read_text()

    assert result.returncode == 0
    assert "super-secret" not in result.stdout
    assert "super-secret" not in result.stderr
    assert "[REDACTED]" in result.stdout
    assert "[REDACTED]" in result.stderr
    assert "super-secret" not in log_text
    assert "[REDACTED]" in log_text


def test_run_command_raises_timeout_with_redacted_partial_output(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "timeout.log"

    with pytest.raises(CommandTimeoutError) as exc_info:
        run_command(
            [
                sys.executable,
                "-c",
                (
                    "import sys, time; "
                    "print('before timeout'); "
                    "print('Bearer timeout-secret'); "
                    "sys.stdout.flush(); "
                    "time.sleep(1)"
                ),
            ],
            cwd=tmp_path,
            timeout=0.1,
            env=None,
            log_path=log_path,
            secrets=["timeout-secret"],
        )

    error = exc_info.value
    log_text = log_path.read_text()

    assert error.result.timed_out is True
    assert "before timeout" in error.result.stdout
    assert "timeout-secret" not in error.result.stdout
    assert "timeout-secret" not in log_text
    assert "timed_out_after_seconds: 0.1" in log_text
