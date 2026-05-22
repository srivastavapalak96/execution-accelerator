"""LLM client abstraction.

Three concrete clients are supported:

* ``ollama``  -- local default; talks to ``http://localhost:11434`` via httpx.
* ``anthropic`` -- hosted; requires ``langchain-anthropic`` extra.
* ``openai`` -- hosted; requires ``langchain-openai`` extra.

A fourth ``stub`` client backs all unit tests under ``EA_MODE=fixture`` so the
graph + repair nodes can be exercised without a network or a model server.

The provider is chosen by ``EA_LLM_PROVIDER`` (default ``ollama``); the model
tag by ``EA_LLM_MODEL`` (default ``llama3.1:8b``); the Ollama endpoint by
``EA_OLLAMA_BASE_URL``. ``EA_LLM_TIMEOUT_SEC`` caps every call (default 120s).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, Protocol

import httpx

DEFAULT_PROVIDER: Final[str] = "ollama"
DEFAULT_MODEL: Final[str] = "llama3.1:8b"
DEFAULT_OLLAMA_BASE_URL: Final[str] = "http://localhost:11434"
DEFAULT_TIMEOUT_SEC: Final[float] = 120.0


class LlmClientError(RuntimeError):
    """Base error for LLM client failures."""


class LlmClient(Protocol):
    """Protocol every concrete LLM client implements."""

    provider: str
    model: str

    def invoke_json(self, *, prompt: str, schema_hint: str | None = None) -> tuple[str, int]:
        """Return ``(raw_text, approx_token_count)`` from a structured-output prompt.

        ``raw_text`` is expected to be a JSON document parseable into a Pydantic schema
        by the caller; ``approx_token_count`` is the model's reported usage if the
        provider exposes it, otherwise a length-based estimate.
        """
        ...


@dataclass
class StubLlmClient:
    """Deterministic stub used in fixture mode and unit tests.

    The stub does not contact any model. Tests that need predictable structured
    output supply a ``responder`` callable that maps prompts to JSON text.
    """

    provider: str
    model: str
    responder: Callable[[str], str]

    def invoke_json(self, *, prompt: str, schema_hint: str | None = None) -> tuple[str, int]:
        text = self.responder(prompt)
        # Token estimate: rough 4 chars per token, matching common defaults.
        return text, max(1, (len(prompt) + len(text)) // 4)


@dataclass
class OllamaLlmClient:
    """Live Ollama client. Talks to the configured endpoint via httpx."""

    provider: str
    model: str
    base_url: str = DEFAULT_OLLAMA_BASE_URL
    timeout: float = DEFAULT_TIMEOUT_SEC

    def invoke_json(self, *, prompt: str, schema_hint: str | None = None) -> tuple[str, int]:
        url = f"{self.base_url.rstrip('/')}/api/generate"
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0,
            },
        }
        try:
            response = httpx.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LlmClientError(f"Ollama request to {url} failed: {exc}") from exc
        body = response.json()
        text = _string_field(body, "response")
        if text is None:
            raise LlmClientError(f"Ollama response missing 'response' field: keys={list(body)}")
        # Ollama exposes prompt+completion token counts as 'prompt_eval_count' and 'eval_count'.
        token_count = int(body.get("prompt_eval_count") or 0) + int(body.get("eval_count") or 0)
        if token_count == 0:
            token_count = max(1, (len(prompt) + len(text)) // 4)
        return text, token_count


def _string_field(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def build_llm_client(
    *,
    env: Mapping[str, str] | None = None,
    stub_responder: Callable[[str], str] | None = None,
) -> LlmClient:
    """Construct a concrete LLM client per environment configuration.

    ``stub_responder`` short-circuits to a ``StubLlmClient`` for unit tests; if
    not provided, the env-driven path is used. Hosted providers (``anthropic``,
    ``openai``) raise ``LlmClientError`` until their extras are wired -- this is
    intentional, callers should fall back to Ollama or run with the stub.
    """

    resolved_env = env if env is not None else os.environ
    provider = resolved_env.get("EA_LLM_PROVIDER", DEFAULT_PROVIDER).lower()
    model = resolved_env.get("EA_LLM_MODEL", DEFAULT_MODEL)
    timeout = float(resolved_env.get("EA_LLM_TIMEOUT_SEC", DEFAULT_TIMEOUT_SEC))

    if stub_responder is not None:
        return StubLlmClient(provider="stub", model=model, responder=stub_responder)

    if provider == "ollama":
        base_url = resolved_env.get("EA_OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
        return OllamaLlmClient(provider="ollama", model=model, base_url=base_url, timeout=timeout)

    if provider in {"anthropic", "openai"}:
        # The hosted providers are intentionally not wired in this build -- see
        # ADR-0001. When they are, replace this branch with a real client.
        raise LlmClientError(
            f"Hosted LLM provider '{provider}' is not yet implemented; "
            "use EA_LLM_PROVIDER=ollama or pass a stub_responder."
        )

    raise LlmClientError(f"Unknown EA_LLM_PROVIDER: {provider!r}")


def estimate_tokens(text: str) -> int:
    """Rough char-count token estimate, used as a fallback when the provider doesn't report usage."""

    return max(1, len(text) // 4)


# Re-exported for convenience by callers building stubs in tests.
def stub_responder_for(payload: Mapping[str, Any]) -> Callable[[str], str]:
    """Return a responder that always emits ``json.dumps(payload)`` regardless of prompt."""

    serialized = json.dumps(payload)

    def responder(_prompt: str) -> str:
        return serialized

    return responder
