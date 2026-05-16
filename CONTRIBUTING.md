# Contributing

Thanks for considering a contribution.

## Development setup

```bash
git clone https://github.com/srivastavapalak96/execution-accelerator.git
cd execution-accelerator
python3 -m venv .venv && source .venv/bin/activate
make install
make test
```

## Project conventions

- **Fixture mode is the default.** All tests pass under `EA_MODE=fixture`. Live
  mode (`EA_MODE=live`) requires real credentials and is exercised separately
  via `tests/integration/` (gated by `EA_INTEGRATION=1`).
- **Schemas first.** New fields go on Pydantic models in `schemas.py` or
  `state.py`; never let untyped dicts cross node boundaries.
- **Adapters dispatch on mode.** New external systems get an adapter class with
  `from_runtime_config()` plus a fixture/live branch.
- **Subprocesses go through `execution/sandbox.py::run_command`.** That's where
  log redaction lives; bypassing it risks leaking credentials into local logs.
- **LLM calls go through `llm/structured.py::structured_call`.** That's where
  prompt redaction, retries, and per-ticket call/token budgets live.
- **No `assert` in `nodes/`.** Use `state.require_state_field()` or raise
  `WorkflowError(code="state_invariant_violated", recoverable=False)` so
  failures route through the escalate path with an audit trail.

## Quality gates

Before opening a PR:

```bash
make test               # 312 unit tests
ruff check src tests
mypy --strict src       # 63 source files clean
```

If the change touches live wrappers (`execution/`, `adapters/live/`, `services/`):

```bash
EA_INTEGRATION=1 pytest tests/integration -q
```

## Commit messages

Imperative mood, lowercase scope where applicable:

- `fix: short description`
- `tests: cover X behaviour`
- `docs: align Y with Z`
- `llm: pluggable client`
- `tough-path: recipe matcher`

One logical change per commit. Tests for a feature go in the commit immediately
after the feature, not bundled together.
