"""Structured-output helper around :mod:`execution_accelerator.llm.client`.

Every node that wants structured-output Pydantic results from an LLM goes
through :func:`structured_call`. It provides:

* prompt redaction for hosted providers (refuses to send if a credential shape
  remains after redaction),
* a single bounded retry on Pydantic validation failure,
* per-ticket call and token budget enforcement (default 20 calls / 100k tokens),
* an audit trail via :class:`LlmCallRecord` appended to ``state.llm_calls``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import TypeVar

import pydantic

from execution_accelerator.schemas import LlmCallRecord
from execution_accelerator.state import RemediationState

from .budget import LlmBudgetExceeded, PromptHasSensitiveData
from .client import LlmClient
from .redact import redact_prompt


T = TypeVar("T", bound=pydantic.BaseModel)

DEFAULT_MAX_CALLS_PER_TICKET = 20
DEFAULT_MAX_TOKENS_PER_TICKET = 100_000


@dataclass
class StructuredCallResult:
    """Bundle returned by :func:`structured_call`."""

    parsed: pydantic.BaseModel
    record: LlmCallRecord
    redacted_prompt: str


def structured_call(
    *,
    client: LlmClient,
    state: RemediationState,
    prompt: str,
    schema: type[T],
    prompt_name: str,
    extra_secrets: tuple[str, ...] = (),
    strict_redaction: bool | None = None,
) -> tuple[T, LlmCallRecord]:
    """Make a structured-output LLM call subject to redaction, budget, and validation guards.

    Returns the parsed Pydantic model plus the audit record. The caller is
    expected to append the record to ``state.llm_calls`` (we do not mutate the
    state here — the caller knows whether the surrounding node should commit
    state changes).
    """

    _enforce_call_budget(state)

    redacted, matched = redact_prompt(prompt, extra_secrets=extra_secrets)
    if _should_block_on_match(client, matched, strict_redaction):
        raise PromptHasSensitiveData(pattern_name=matched[0])

    schema_hint = _schema_hint(schema)
    raw_text, token_count = client.invoke_json(prompt=redacted, schema_hint=schema_hint)

    parsed = _parse_or_retry(client, redacted, schema, raw_text, schema_hint=schema_hint)

    record = LlmCallRecord(
        provider=client.provider,
        model=client.model,
        prompt_name=prompt_name,
        token_count=token_count,
    )

    _enforce_token_budget(state, additional=token_count)
    return parsed, record


def _parse_or_retry(
    client: LlmClient,
    redacted_prompt: str,
    schema: type[T],
    first_text: str,
    *,
    schema_hint: str,
) -> T:
    try:
        return schema.model_validate(json.loads(first_text))
    except (json.JSONDecodeError, pydantic.ValidationError):
        # One retry with a stricter schema reminder appended to the prompt.
        retry_prompt = (
            redacted_prompt
            + "\n\nReturn STRICTLY valid JSON matching the schema below.\n"
            + schema_hint
        )
        retry_text, _retry_tokens = client.invoke_json(prompt=retry_prompt, schema_hint=schema_hint)
        return schema.model_validate(json.loads(retry_text))


def _enforce_call_budget(state: RemediationState) -> None:
    limit = int(os.getenv("EA_MAX_LLM_CALLS_PER_TICKET", str(DEFAULT_MAX_CALLS_PER_TICKET)))
    used = len(state.llm_calls)
    if used >= limit:
        raise LlmBudgetExceeded(kind="calls", used=used, limit=limit)


def _enforce_token_budget(state: RemediationState, *, additional: int) -> None:
    limit = int(os.getenv("EA_MAX_LLM_TOKENS_PER_TICKET", str(DEFAULT_MAX_TOKENS_PER_TICKET)))
    if state.llm_tokens_used + additional > limit:
        raise LlmBudgetExceeded(
            kind="tokens",
            used=state.llm_tokens_used + additional,
            limit=limit,
        )


def _should_block_on_match(client: LlmClient, matched: tuple[str, ...], strict: bool | None) -> bool:
    if not matched:
        return False
    if strict is True:
        return True
    if strict is False:
        return False
    # Default policy: block hosted providers, allow Ollama (local + private).
    return client.provider != "ollama" and client.provider != "stub"


def _schema_hint(schema: type[T]) -> str:
    """Render a one-line JSON schema hint suitable for inclusion in a retry prompt."""

    return json.dumps(schema.model_json_schema(), separators=(",", ":"))
