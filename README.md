# Execution Accelerator

Execution Accelerator is a **local, checkpointed remediation workflow prototype** for Maven vulnerability tickets.

Today, this repository is best understood as a **partially live remediation prototype with a still-incomplete live delivery path**:

- LangGraph orchestration is real
- SQLite checkpoint persistence is real
- workflow schemas/state are real
- live Jira intake, repository preparation, OSV advisory lookup, Maven profile detection, and Maven verification are real
- bounded retry routing for retryable test failures, live remediation, live validation, basic live delivery, and failure escalation bundles now exist
- the complex lane now persists a concrete migration tactic plus concrete file/symbol targets and open questions, and it now materializes deterministic scaffolded file changes before validation, but tougher tough-path behavior is still incomplete

If you want the long-term target, read **`docs/vision.md`**.  
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
6. live or fixture-backed validation, including a post-remediation dependency-tree rescan in live mode
7. fixture-backed or live git-backed rollback-on-failure, including cleanup of untracked remediation files in live mode
8. fixture-backed delivery metadata on success, plus live branch publication / PR creation / Jira completion comments and optional done transitions; delivery-approved complex runs can now publish ready PRs instead of remaining draft-only, GitHub PR-create conflicts can recover the existing open PR instead of failing delivery, Jira done-transition conflicts can recover when the issue is already in the target status, and PR bodies now publish workflow context instead of a placeholder sentence
9. fixture-backed or live failure escalation summaries, including persisted escalation bundle paths in run output and richer complex-plan context for tough-path failures
10. persisted approval pauses for complex refactors, transitive overrides, and approval-tagged repositories, plus an optional second delivery approval gate for complex publication
11. complex-refactor planning and scaffold execution that now persist a primary migration tactic, actionable migration steps, concrete file/symbol targets, and unresolved execution questions derived from compatibility analysis, and materialize deterministic scaffolded file changes before validation
12. CLI summaries that surface skipped repositories and raw skip reasons such as existing open remediation PRs
13. CLI summaries that surface the latest terminal workflow error for failed or blocked runs

The default mode is:

```bash
EA_MODE=fixture
```

`EA_MODE=live` is now explicit. Intake, verification, remediation, validation, rollback, bounded retry routing for retryable test failures, escalation bundles, a basic delivery path, and persisted approval pause/resume are real enough to exercise a live run, including policy-driven approval for transitive overrides, tagged repositories, and optional second-stage complex delivery approval; the complex lane also persists a concrete migration tactic, actionable migration steps, concrete file/symbol targets, and unresolved execution questions, and now materializes deterministic scaffolded file changes before validation, but tougher remediation lanes are still incomplete.

## Current limitations

This repository does **not** yet perform:

- full Jira completion workflow handling beyond a configured done transition
- full compile/test/license validation coverage
- richer retry policies beyond the current bounded test-failure remediation re-run
- richer policy enforcement beyond the current route/tag and complex-delivery approval rules
- real tough-path/EOL migrations beyond the current tactic-and-checklist complex scaffold
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
