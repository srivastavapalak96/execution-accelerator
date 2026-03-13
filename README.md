# Execution Accelerator

Execution Accelerator is a **local, checkpointed remediation workflow prototype** for Maven vulnerability tickets.

Today, this repository is best understood as a **mostly fixture-backed implementation scaffold**:

- LangGraph orchestration is real
- SQLite checkpoint persistence is real
- workflow schemas/state are real
- remediation, validation, delivery, and tough-path behavior are still mostly **fixture-backed placeholders**
- live Jira reads now have a real adapter path; the rest of the workflow is still largely fixture-backed

If you want the long-term target, read **`docs/vision.md`**.  
If you want the truth about what works right now, read **`docs/status.md`**.

## What works today

The current repo can run a persisted local flow for:

1. Jira intake from fixtures, plus partial live Jira reads
2. repository workspace preparation from fixtures, plus live inventory/clone primitives
3. advisory + Maven verification from fixtures
4. route selection across:
   - simple update
   - transitive override
   - complex refactor scaffold
5. fixture-backed validation
6. fixture-backed rollback-on-failure
7. fixture-backed delivery metadata on success

The default mode is:

```bash
EA_MODE=fixture
```

`EA_MODE=live` is now explicit. Jira issue reads are partially implemented; the remaining live adapters are still mostly unimplemented.

## Current limitations

This repository does **not** yet perform:

- live Jira writes
- fully wired live repository remediation end to end
- live PR creation
- live OSV + Maven verification
- live compile/test/security validation
- real retry matrix behavior
- real policy enforcement
- real tough-path/EOL migrations

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
- `src/execution_accelerator/adapters/` — fixture adapters and live-mode stubs
- `tests/` — fixture-backed test suite

## Validation

Primary local validation:

```bash
make test
```

Focused smoke-style commands still exist for manual inspection, but they should not be confused with live end-to-end remediation.
