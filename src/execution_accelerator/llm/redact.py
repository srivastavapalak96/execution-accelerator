"""Prompt redaction for hosted LLM providers.

When ``EA_LLM_PROVIDER`` is anything other than ``ollama`` (which runs locally),
prompts go to a hosted endpoint and any credential-shaped substring becomes a
data-leak risk. ``redact_prompt`` replaces known shapes with ``[REDACTED]`` and
returns ``(redacted_text, matched_pattern_names)`` so the caller can refuse to
send when a strict mode is required.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

REDACTION_TOKEN = "[REDACTED]"

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("github_token_classic", re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}")),
    ("github_token_legacy", re.compile(r"\b[a-f0-9]{40}\b")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._\-+/]+=*", re.IGNORECASE)),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"xox[bpoars]-[A-Za-z0-9-]{10,}")),
    ("settings_xml_password", re.compile(r"<password>[^<]+</password>", re.IGNORECASE)),
    ("basic_auth_url", re.compile(r"https?://[^/\s:]+:[^@/\s]+@")),
)


def redact_prompt(
    prompt: str,
    *,
    extra_secrets: Iterable[str] = (),
) -> tuple[str, tuple[str, ...]]:
    """Return ``(redacted_prompt, matched_pattern_names)`` for the given prompt.

    Caller-supplied ``extra_secrets`` (e.g., literal token values from
    ``Credentials``) are replaced first so they cannot survive in any prefix
    that a regex might miss.
    """

    redacted = prompt
    for secret in sorted({s for s in extra_secrets if s}, key=len, reverse=True):
        redacted = redacted.replace(secret, REDACTION_TOKEN)

    matched: list[str] = []
    for name, pattern in _PATTERNS:
        if pattern.search(redacted):
            matched.append(name)
            redacted = pattern.sub(REDACTION_TOKEN, redacted)
    return redacted, tuple(matched)
