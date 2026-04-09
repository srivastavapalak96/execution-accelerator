# ADR 0001: LLM scope is bounded and deterministic-first

## Status

Accepted

## Context

Execution Accelerator is primarily a deterministic remediation workflow:

- Jira intake, repository preparation, advisory lookup, Maven verification, simple remediation, transitive remediation, validation, rollback, delivery, and escalation are all deterministic today.
- The complex lane performs bounded deterministic Java rewrites, but broader tough-path and repair behavior is still incomplete.
- A clear, written boundary is required so the codebase, docs, and roadmap converge on a single target instead of drifting between "fully automated" and "deterministic only".

This ADR documents what an LLM is and is not used for in this project.

## Decision

Execution Accelerator stays **deterministic-first**. An LLM is consulted only where deterministic remediation is likely to fail or become ambiguous:

1. tough-path symbol-mapping rationale when deterministic similarity confidence is low
2. bounded repair attempts for compile/test failures
3. last-resort patch generation inside strict file/line/attempt limits

An LLM is explicitly **out of scope** for:

1. Jira intake and parsing
2. repository discovery and preparation
3. advisory verification
4. Maven verification and route selection
5. simple direct-version bumps
6. standard transitive overrides

## Consequences

- High-level docs describe the system as **LangGraph-orchestrated, deterministic-first, with bounded LLM fallback for tough-path and repair work**.
- The remaining roadmap retains Tier C1/C2/C3.
- Current implementation status stays honest: the repo is not yet shipping those bounded LLM capabilities.
- Future LLM work must include prompt redaction, per-ticket call/token budgets, structured outputs, and explicit retry/error handling.

## Follow-up work

1. Keep `README.md`, `docs/vision.md`, and `docs/status.md` aligned with this scope.
2. Land the retry/default and invariant-error credibility blockers before starting the larger LLM/tough-path packages.
3. Add the bounded LLM wrapper only after the live deterministic path is safer by default.
