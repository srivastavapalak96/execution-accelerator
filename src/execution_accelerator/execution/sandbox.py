from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import shlex
import subprocess
from typing import Mapping, Sequence


REDACTION_TOKEN = "[REDACTED]"
_GITHUB_TOKEN_PATTERN = re.compile(r"gh[pousr]_[A-Za-z0-9_]+")
_BEARER_TOKEN_PATTERN = re.compile(r"Bearer\s+[^\s\"']+")


@dataclass(frozen=True)
class CommandResult:
    """Normalized subprocess result with a persisted log location."""

    command: tuple[str, ...]
    cwd: Path
    returncode: int
    stdout: str
    stderr: str
    log_path: Path
    timed_out: bool = False


class CommandTimeoutError(TimeoutError):
    """Raised when a command exceeds its configured timeout."""

    def __init__(self, timeout: float, result: CommandResult) -> None:
        self.timeout = timeout
        self.result = result
        super().__init__(f"command timed out after {timeout:g}s: {shlex.join(result.command)}")


def redact(text: str, secrets: Sequence[str] | None = None) -> str:
    """Redact explicit secrets and common token shapes from logs."""

    redacted = text
    for secret in sorted({secret for secret in secrets or () if secret}, key=len, reverse=True):
        redacted = redacted.replace(secret, REDACTION_TOKEN)
    redacted = _GITHUB_TOKEN_PATTERN.sub(REDACTION_TOKEN, redacted)
    redacted = _BEARER_TOKEN_PATTERN.sub(f"Bearer {REDACTION_TOKEN}", redacted)
    return redacted


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run_command(
    cmd: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    env: Mapping[str, str] | None,
    log_path: Path,
    secrets: Sequence[str] | None = None,
) -> CommandResult:
    """Run a command, redact sensitive output, and persist a local log."""

    resolved_cwd = Path(cwd).resolve()
    resolved_log_path = Path(log_path).resolve()
    resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
    merged_env = os.environ.copy()
    if env is not None:
        merged_env.update(env)

    try:
        completed = subprocess.run(
            list(cmd),
            cwd=resolved_cwd,
            env=merged_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        timeout_result = CommandResult(
            command=tuple(cmd),
            cwd=resolved_cwd,
            returncode=-1,
            stdout=redact(_coerce_output(exc.stdout), secrets),
            stderr=redact(_coerce_output(exc.stderr), secrets),
            log_path=resolved_log_path,
            timed_out=True,
        )
        _write_log(timeout_result, secrets=secrets, timeout=timeout)
        raise CommandTimeoutError(timeout, timeout_result) from exc

    result = CommandResult(
        command=tuple(cmd),
        cwd=resolved_cwd,
        returncode=completed.returncode,
        stdout=redact(completed.stdout, secrets),
        stderr=redact(completed.stderr, secrets),
        log_path=resolved_log_path,
    )
    _write_log(result, secrets=secrets)
    return result


def _write_log(
    result: CommandResult,
    *,
    secrets: Sequence[str] | None = None,
    timeout: float | None = None,
) -> None:
    sections = [
        f"command: {redact(shlex.join(result.command), secrets)}",
        f"cwd: {result.cwd}",
        f"returncode: {result.returncode}",
    ]
    if result.timed_out and timeout is not None:
        sections.append(f"timed_out_after_seconds: {timeout:g}")
    sections.extend(
        [
            "--- stdout ---",
            result.stdout,
            "--- stderr ---",
            result.stderr,
        ]
    )
    result.log_path.write_text("\n".join(sections).rstrip() + "\n")
