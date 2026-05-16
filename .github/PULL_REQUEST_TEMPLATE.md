<!-- Brief summary of the change. Why is it needed? -->

## What changed

-

## Why

<!-- Link the Jira ticket, GitHub issue, or describe the problem this solves. -->

## Verification

- [ ] `make test` (312+ unit tests pass under `EA_MODE=fixture`)
- [ ] `ruff check src tests` clean
- [ ] `mypy --strict src` clean
- [ ] `EA_INTEGRATION=1 pytest tests/integration -q` passes (if the change
      touches `execution/`, `adapters/live/`, or `services/`)
- [ ] Updated `docs/status.md` if a feature changed status (`SHIPPED` /
      `PARTIAL` / `PLANNED`)

## Notes for reviewer

<!-- Anything non-obvious? Trade-offs you considered? Future work this enables? -->
