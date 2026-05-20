# ADR 0001: LLM scope is bounded and deterministic-first

## Status

Accepted.

## Context

Most of Execution Accelerator is deterministic. Jira intake, repository
preparation, OSV/Maven verification, simple/transitive remediation, validation,
rollback, and delivery all run without an LLM. The question this ADR answers
is which steps, if any, may call an LLM.

## Decision

The LLM is consulted only where deterministic remediation is likely to fail or
become ambiguous:

1. tough-path symbol-mapping rationale when deterministic similarity is low,
2. compile- and test-failure repair proposals inside strict per-patch limits,
3. last-resort patch generation when JavaParser-style structural edits cannot
   express the change.

The LLM is explicitly out of scope for Jira intake and parsing, repository
discovery, advisory verification, Maven verification and route selection, and
both simple and transitive remediation lanes.

## Consequences

- High-level docs describe the system as LangGraph-orchestrated and
  deterministic-first, with bounded LLM fallback for tough-path and repair
  work.
- Every LLM call goes through one wrapper that enforces prompt redaction,
  per-ticket call and token budgets, structured Pydantic output, and a single
  bounded retry on validation failure.
- The final stored confidence on any LLM-enriched symbol mapping is
  `min(deterministic, llm)` so the LLM cannot inflate trust beyond what the
  similarity scoring justifies.
- Hosted providers (Anthropic, OpenAI) are pluggable via `EA_LLM_PROVIDER` but
  refuse to send a prompt if any credential-shaped substring survives
  redaction.
