"""Bounded LLM client used for tough-path symbol rationale and compile/test repair.

Per ADR-0001 the LLM is deterministic-first: wrapped, audited, budget-capped, and
redacted before every call. Default provider is local Ollama; hosted Anthropic /
OpenAI providers can be selected via ``EA_LLM_PROVIDER``.
"""

from .budget import LlmBudgetExceeded, PromptHasSensitiveData
from .client import LlmClient, LlmClientError, build_llm_client
from .redact import redact_prompt
from .structured import StructuredCallResult, structured_call

__all__ = [
    "LlmBudgetExceeded",
    "LlmClient",
    "LlmClientError",
    "PromptHasSensitiveData",
    "StructuredCallResult",
    "build_llm_client",
    "redact_prompt",
    "structured_call",
]
