# Execution Accelerator

Execution Accelerator is a **local, checkpointed remediation workflow prototype** for Maven vulnerability tickets.

Today, this repository is best understood as a **partially live remediation prototype with a still-incomplete live delivery path**. The long-term target remains **deterministic-first with bounded LLM fallback only for tough-path and repair work**:

- LangGraph orchestration is real
- SQLite checkpoint persistence is real
- workflow schemas/state are real
- live Jira intake, repository preparation, OSV advisory lookup, Maven profile detection, and Maven verification are real
- bounded retry routing for retryable test failures, transient dependency-inspection validation failures, and transient delivery failures, live remediation, live validation, basic live delivery, and failure escalation bundles now exist
- the complex lane now persists a concrete migration tactic plus concrete file/symbol targets and open questions, and it now executes bounded real Java migration work before validation by rewriting supported method/constructor calls, references, static-imported legacy calls, static field/constant references, and obsolete exact imports, generating executable helper shims for missing target files, and scanning existing Java sources for detected legacy API usage, but broader tough-path behavior is still incomplete

If you want the long-term target, read **`docs/vision.md`** and **`docs/adr/0001-ai-scope.md`**.  
If you want the truth about what works right now, read **`docs/status.md`**.

## What works today

The current repo can run a persisted local flow for:

1. Jira intake from fixtures, plus live Jira reads
2. repository workspace preparation from fixtures, plus live inventory/clone primitives
3. advisory verification from fixtures or live OSV
4. Maven profile detection plus Maven metadata/dependency-tree verification in live mode
5. route selection across:
   - simple update
   - transitive override
   - complex refactor scaffold
6. live or fixture-backed validation, including a post-remediation dependency-tree rescan in live mode and a dependency license scan with optional denylist or allowlist enforcement
7. fixture-backed or live git-backed rollback-on-failure, including cleanup of untracked remediation files in live mode
8. fixture-backed delivery metadata on success, plus live branch publication / PR creation / Jira completion comments and optional done transitions; delivery-approved complex runs can now publish ready PRs instead of remaining draft-only, GitHub PR-create conflicts can recover the existing open PR and refresh stale title/body metadata instead of failing delivery, transient publish-time delivery failures now become structured workflow errors and can retry `publish_remediation` without republishing already-created branch/PR state, Jira done-transition conflicts can recover when the issue is already in the target status, Jira done transitions can now also be resolved live by target status name when a transition ID is not preconfigured, both PR bodies and Jira comments now publish workflow, route, approval, approval-comment, remediation-plan context, and multi-repo progress instead of placeholder text, and successful runs now continue across all pending affected repositories instead of stopping after the first one
9. fixture-backed or live failure escalation summaries, including persisted escalation bundle paths in run output, route rationale, approval provenance, code-diff summaries, validation context, richer complex-plan context for tough-path failures, multi-repo progress context such as the failed repository plus completed/pending/skipped repositories, and partial delivery context such as already-published branch/PR state when publication fails mid-flight
10. persisted approval pauses for complex refactors, transitive overrides, and approval-tagged repositories, plus an optional second delivery approval gate for complex publication
11. complex-refactor planning and bounded execution that now persist a primary migration tactic, actionable migration steps, concrete file/symbol targets, and unresolved execution questions derived from compatibility analysis, and execute supported Java method/constructor rewrites, static-import rewrites, static field/constant rewrites, exact-import cleanup, and generated helper shims before validation
12. CLI summaries that surface skipped repositories and raw skip reasons such as existing or recently closed remediation PRs, plus route rationale, changed-file counts, aggregate diff totals, the first failing validation check when validation breaks, and primary change summaries
13. retry scheduling that now clears stale rollback/preflight/diff state before rerunning a remediation lane, successful validation clears stale rollback/retry directives from the current run snapshot, transient dependency-tree or license-metadata inspection failures can now rerun within the same bounded retry budget, transient delivery failures can rerun `publish_remediation` while preserving already-published branch/PR state, completed runs now clear stale terminal failure markers after a successful retry so operator summaries do not still report recovered errors, and the canonical retry budget is now `EA_MAX_RETRIES` with a default of `3` while `EA_MAX_RETRY_ATTEMPTS` remains a compatibility alias
14. CLI summaries that surface the latest terminal workflow error for failed or blocked runs and now show remediation plan summary/rationale directly
15. workflow nodes and graph routing helpers now surface missing required state as explicit `state_invariant_violated` workflow failures with escalation bundles instead of raw assertion crashes
16. Complex scaffold execution that can deterministically rewrite supported Java method-call and constructor migration sites in existing files before appending operator-facing scaffold notes

The default mode is:

```bash
EA_MODE=fixture
```

`EA_MODE=live` is now explicit. Intake, verification, remediation, validation, rollback, bounded retry routing for retryable test failures, transient dependency-inspection validation failures, and transient delivery failures, escalation bundles, a basic delivery path, and persisted approval pause/resume are real enough to exercise a live run, including policy-driven approval for transitive overrides, tagged repositories, and optional second-stage complex delivery approval; the complex lane also persists a concrete migration tactic, actionable migration steps, concrete file/symbol targets, and unresolved execution questions, and now materializes deterministic scaffolded file changes before validation, but tougher remediation lanes are still incomplete. Retry behavior now defaults on via `EA_MAX_RETRIES=3` unless explicitly overridden, startup probing now checks live Jira/GitHub write access before work begins, and live mode no longer silently inherits fixture-path defaults or dead fixture guards in the live-capable adapters.

## Current limitations

This repository does **not** yet perform:

- fuller Jira completion workflow handling beyond the current done-transition-by-id or done-transition-by-status support
- richer license-policy handling beyond the current dependency license scan and optional denylist/allowlist enforcement
- richer retry policies beyond the current bounded test-failure, transient-validation, and transient-delivery re-runs
- richer policy enforcement beyond the current route/tag and complex-delivery approval rules
- broad tough-path/EOL migrations beyond the current bounded Java rewrite/helper generation support
- broader observability hardening beyond the escalation bundle artifact

## Quickstart

Create a virtual environment, install dependencies, and run the fixture suite:

```bash
python3 -m venv .venv
. .venv/bin/activate
make install
make test
```

Show resolved runtime configuration:

```bash
python -m execution_accelerator --show-config
```

Bootstrap a fixture-backed ticket run:

```bash
python -m execution_accelerator --bootstrap-ticket SEC-123 --thread-id sec-123-dev
```

Bootstrap a dry-run that stops before delivery side effects:

```bash
python -m execution_accelerator --bootstrap-ticket SEC-123 --dry-run --keep-workspace
```

Inspect persisted state:

```bash
python -m execution_accelerator --show-thread-state sec-123-dev
```

Rehydrate a persisted thread with the resume flow:

```bash
python -m execution_accelerator --resume sec-123-dev
```

## Development notes

- The canonical phased implementation plan lives outside the repo and should be followed in order.
- Phase 0 currently focuses on:
  - removing dangerous fixture behavior from production code
  - making fixture vs live mode explicit
  - wiring retry/escalation honestly
  - documenting the real implementation boundary

## Repository layout

Important source areas:

- `src/execution_accelerator/schemas.py` — typed workflow models
- `src/execution_accelerator/state.py` — persisted remediation state
- `src/execution_accelerator/graph/builder.py` — main graph composition
- `src/execution_accelerator/nodes/` — graph nodes
- `src/execution_accelerator/adapters/` — fixture adapters plus live intake/verification implementations
- `src/execution_accelerator/services/` — OSV and version-range services
- `src/execution_accelerator/profiles/` — Maven profile detection helpers
- `tests/` — fixture suite plus live verification integration coverage

## Validation

Primary local validation:

```bash
make test
```

Focused smoke-style commands still exist for manual inspection, but they should not be confused with live end-to-end remediation.
