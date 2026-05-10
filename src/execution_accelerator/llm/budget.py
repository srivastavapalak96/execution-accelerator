"""Exception types for LLM budget and safety guards."""

from __future__ import annotations


class LlmBudgetExceeded(RuntimeError):
    """Raised when a per-ticket LLM call or token budget is exhausted."""

    def __init__(self, *, kind: str, used: int, limit: int) -> None:
        self.kind = kind
        self.used = used
        self.limit = limit
        super().__init__(
            f"LLM {kind} budget exceeded: {used} > {limit} for this ticket."
        )


class PromptHasSensitiveData(RuntimeError):
    """Raised when a prompt destined for a hosted LLM still contains a credential shape after redaction."""

    def __init__(self, *, pattern_name: str) -> None:
        self.pattern_name = pattern_name
        super().__init__(
            f"Prompt still matches credential pattern '{pattern_name}' after redaction; refusing to send."
        )
