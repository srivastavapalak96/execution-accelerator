# Execution Accelerator

Execution Accelerator is a **local, checkpointed remediation workflow prototype** for Maven vulnerability tickets.

Today, this repository is best understood as a **partially live remediation prototype with a still-incomplete live delivery path**:

- LangGraph orchestration is real
- SQLite checkpoint persistence is real
- workflow schemas/state are real
- live Jira intake, repository preparation, OSV advisory lookup, Maven profile detection, and Maven verification are real
- live remediation, live validation, and basic live delivery now exist
- approval/retry flows and tough-path behavior are still incomplete

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
6. live or fixture-backed validation
7. fixture-backed or live git-backed rollback-on-failure
8. fixture-backed delivery metadata on success, plus live branch publication / PR creation / Jira comment writes

The default mode is:

```bash
EA_MODE=fixture
```

`EA_MODE=live` is now explicit. Intake, verification, remediation, validation, rollback, and a basic delivery path are real enough to exercise a live run, but Jira transition workflows and tougher remediation lanes are still incomplete.

## Current limitations

This repository does **not** yet perform:

- full Jira completion transitions
- full compile/test/security/license validation coverage
- real retry matrix behavior
- richer policy enforcement and approval routing
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
