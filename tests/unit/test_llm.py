"""Unit tests for execution_accelerator.llm.{client,structured,redact,budget}."""

from __future__ import annotations

import json

import pydantic
import pytest

from execution_accelerator.llm.budget import LlmBudgetExceeded, PromptHasSensitiveData
from execution_accelerator.llm.client import (
    LlmClientError,
    StubLlmClient,
    build_llm_client,
    estimate_tokens,
    stub_responder_for,
)
from execution_accelerator.llm.redact import REDACTION_TOKEN, redact_prompt
from execution_accelerator.llm.structured import structured_call
from execution_accelerator.schemas import LlmCallRecord
from execution_accelerator.state import RemediationState


class _FakeStructuredOutput(pydantic.BaseModel):
    ok: bool
    message: str


def _state() -> RemediationState:
    return RemediationState(initial_ticket_id="SEC-LLM-1")


# --- redaction ----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected_match",
    [
        ("token=ghp_abcd1234abcd1234abcd1234abcd1234abcd12", "github_token_classic"),
        ("Authorization: Bearer abc.def.ghi", "bearer_token"),
        ("AKIAABCDEFGHIJKLMNOP", "aws_access_key"),
        ("xoxb-1234567890-abcdefghij", "slack_token"),
        ("<password>secret-pw</password>", "settings_xml_password"),
        ("https://user:pa55@example.com/repo.git", "basic_auth_url"),
    ],
)
def test_redact_prompt_replaces_known_credential_shapes(raw: str, expected_match: str) -> None:
    redacted, matched = redact_prompt(raw)
    assert REDACTION_TOKEN in redacted
    assert expected_match in matched


def test_redact_prompt_replaces_caller_supplied_secrets_first() -> None:
    secret = "MY-CUSTOM-SECRET-VALUE"
    redacted, matched = redact_prompt(
        f"prompt with {secret} and Bearer literal-token-here",
        extra_secrets=(secret,),
    )
    assert secret not in redacted
    assert "literal-token-here" not in redacted
    assert "bearer_token" in matched


def test_redact_prompt_returns_clean_when_nothing_matches() -> None:
    redacted, matched = redact_prompt("This is a completely benign prompt.")
    assert redacted == "This is a completely benign prompt."
    assert matched == ()


# --- client builder -----------------------------------------------------------


def test_build_llm_client_stub_short_circuit() -> None:
    client = build_llm_client(stub_responder=stub_responder_for({"ok": True, "message": "hi"}))
    assert isinstance(client, StubLlmClient)
    text, tokens = client.invoke_json(prompt="anything")
    assert json.loads(text) == {"ok": True, "message": "hi"}
    assert tokens > 0


def test_build_llm_client_ollama_default_env() -> None:
    client = build_llm_client(env={}, stub_responder=None)
    assert client.provider == "ollama"
    assert client.model == "llama3.1:8b"


def test_build_llm_client_rejects_hosted_providers_until_wired() -> None:
    with pytest.raises(LlmClientError, match="not yet implemented"):
        build_llm_client(env={"EA_LLM_PROVIDER": "anthropic"})


def test_build_llm_client_rejects_unknown_provider() -> None:
    with pytest.raises(LlmClientError, match="Unknown EA_LLM_PROVIDER"):
        build_llm_client(env={"EA_LLM_PROVIDER": "totally-bogus"})


def test_estimate_tokens_returns_at_least_one() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 16) == 4


# --- structured_call ----------------------------------------------------------


def test_structured_call_parses_first_response() -> None:
    client = StubLlmClient(
        provider="stub",
        model="m",
        responder=stub_responder_for({"ok": True, "message": "hello"}),
    )
    parsed, record = structured_call(
        client=client,
        state=_state(),
        prompt="probe",
        schema=_FakeStructuredOutput,
        prompt_name="probe",
    )
    assert parsed.ok is True
    assert parsed.message == "hello"
    assert record.provider == "stub"
    assert record.prompt_name == "probe"
    assert record.token_count > 0


def test_structured_call_retries_once_on_invalid_json() -> None:
    calls: list[str] = []

    def responder(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return "this is not valid JSON"
        return json.dumps({"ok": True, "message": "second-try"})

    client = StubLlmClient(provider="stub", model="m", responder=responder)
    parsed, _record = structured_call(
        client=client,
        state=_state(),
        prompt="probe",
        schema=_FakeStructuredOutput,
        prompt_name="probe",
    )
    assert parsed.message == "second-try"
    assert len(calls) == 2
    # The retry prompt should include a schema hint.
    assert "STRICTLY valid JSON" in calls[1]


def test_structured_call_reraises_after_two_failures() -> None:
    client = StubLlmClient(
        provider="stub",
        model="m",
        responder=stub_responder_for({"wrong_field": "x"}),
    )
    with pytest.raises(pydantic.ValidationError):
        structured_call(
            client=client,
            state=_state(),
            prompt="probe",
            schema=_FakeStructuredOutput,
            prompt_name="probe",
        )


def test_structured_call_blocks_hosted_provider_when_sensitive_data_present() -> None:
    # We cannot construct a real hosted client, but we can fake one by spoofing
    # the .provider attribute on a StubLlmClient.
    client = StubLlmClient(
        provider="anthropic",
        model="hosted-test",
        responder=stub_responder_for({"ok": True, "message": "x"}),
    )
    with pytest.raises(PromptHasSensitiveData):
        structured_call(
            client=client,
            state=_state(),
            prompt="please use Bearer abc.def.ghi to fetch the data",
            schema=_FakeStructuredOutput,
            prompt_name="probe",
        )


def test_structured_call_allows_ollama_with_sensitive_data() -> None:
    client = StubLlmClient(
        provider="ollama",
        model="llama3.1:8b",
        responder=stub_responder_for({"ok": True, "message": "local"}),
    )
    # Should not raise: local Ollama is treated as private by default.
    parsed, _record = structured_call(
        client=client,
        state=_state(),
        prompt="please use Bearer abc.def.ghi to fetch the data",
        schema=_FakeStructuredOutput,
        prompt_name="probe",
    )
    assert parsed.ok is True


def test_structured_call_strict_redaction_blocks_even_local() -> None:
    client = StubLlmClient(
        provider="ollama",
        model="m",
        responder=stub_responder_for({"ok": True, "message": "x"}),
    )
    with pytest.raises(PromptHasSensitiveData):
        structured_call(
            client=client,
            state=_state(),
            prompt="Bearer abc.def.ghi",
            schema=_FakeStructuredOutput,
            prompt_name="probe",
            strict_redaction=True,
        )


def test_structured_call_enforces_call_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EA_MAX_LLM_CALLS_PER_TICKET", "2")
    client = StubLlmClient(
        provider="stub",
        model="m",
        responder=stub_responder_for({"ok": True, "message": "x"}),
    )
    state = _state()
    state.llm_calls.extend(
        LlmCallRecord(provider="stub", model="m", prompt_name="prior", token_count=10)
        for _ in range(2)
    )
    with pytest.raises(LlmBudgetExceeded, match="calls"):
        structured_call(
            client=client,
            state=state,
            prompt="probe",
            schema=_FakeStructuredOutput,
            prompt_name="probe",
        )


def test_structured_call_enforces_token_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EA_MAX_LLM_TOKENS_PER_TICKET", "5")
    # Stub responder returning a long string so the estimate exceeds 5 tokens.
    client = StubLlmClient(
        provider="stub",
        model="m",
        responder=lambda _p: json.dumps({"ok": True, "message": "x" * 2000}),
    )
    state = _state()
    with pytest.raises(LlmBudgetExceeded, match="tokens"):
        structured_call(
            client=client,
            state=state,
            prompt="probe " * 200,
            schema=_FakeStructuredOutput,
            prompt_name="probe",
        )
