# ADR 0001: AI scope is bounded and deterministic-first

## Status

Accepted

## Context

Execution Accelerator was originally framed around AI-assisted remediation, but the current repository is still primarily a deterministic workflow:

- Jira intake, repository preparation, advisory lookup, Maven verification, simple remediation, transitive remediation, validation, rollback, delivery, and escalation are deterministic today.
- The complex lane already performs bounded deterministic Java rewrites, but broader tough-path and repair behavior is still incomplete.
- The new backlog review identified this as the highest-leverage decision because it changes the size and shape of the remaining roadmap.

We need a documented answer to what "AI" means in this project so the repo is honest and the next implementation slices converge on one target.

## Decision

Execution Accelerator will keep an **AI-assisted** framing, but only in a **bounded, deterministic-first** way.

AI is in scope only where deterministic remediation is likely to fail or become too ambiguous:

1. tough-path symbol-mapping rationale when deterministic confidence is low
2. bounded repair attempts for compile/test failures
3. last-resort patch generation inside strict file/line/attempt limits

AI is explicitly **out of scope** for:

1. Jira intake and parsing
2. repository discovery and preparation
3. advisory verification
4. Maven verification and route selection
5. simple direct-version bumps
6. standard transitive overrides

## Consequences

- High-level docs should describe the system as **LangGraph-orchestrated, deterministic-first, with bounded LLM fallback for tough-path and repair work**.
- The remaining roadmap should keep Tier C1/C2/C3, not delete them.
- Current implementation status remains honest: the repo is not yet shipping those bounded LLM capabilities.
- Future LLM work must include redaction, budgeting, structured outputs, and explicit retry/error handling.

## Follow-up work

1. Keep README, `docs/vision.md`, and `docs/status.md` aligned with this scope.
2. Implement the retry/default and invariant-error credibility blockers before starting the larger LLM/tough-path packages.
3. Add the bounded LLM wrapper only after the live deterministic path is safer by default.
