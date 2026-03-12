# Execution Accelerator Status

This file tracks the repository **as implemented today**, not the aspirational end state.

| Area | Status | Notes |
|------|--------|-------|
| LangGraph + SQLite checkpoints | SHIPPED | Persisted runs and checkpoint reload are implemented. |
| Typed schemas and remediation state | SHIPPED | Core workflow models and state exist. |
| Fixture execution mode | SHIPPED | `EA_MODE=fixture` is the default and covered by tests. |
| Live execution mode | PLANNED | `EA_MODE=live` is explicit but currently raises `NotImplementedError` in adapters. |
| Jira intake | PARTIAL | Fixture-backed only. |
| Repository inventory + workspace prep | PARTIAL | Fixture-backed only; no live clone yet. |
| Advisory verification | PARTIAL | Fixture-backed only. |
| Maven verification | PARTIAL | Fixture-backed only. |
| Simple remediation lane | PARTIAL | Fixture-backed mutation flow exists. |
| Transitive remediation lane | PARTIAL | Fixture-backed override flow exists. |
| Complex remediation lane | PARTIAL | Analysis/execution scaffold exists, not real migration logic. |
| Validation | PARTIAL | Fixture-backed validation and rollback scaffolding exists. |
| Delivery | PARTIAL | Fixture-backed branch/PR/Jira completion exists. |
| Failure classification | PARTIAL | Phase 0 stub routes failures through classify -> escalate. |
| Retry matrix | PLANNED | Full retry routing is not implemented yet. |
| Policy engine | PLANNED | No real policy evaluation yet. |
| Human approval interrupt | PLANNED | Not wired yet. |
| Live PR creation and Jira updates | PLANNED | Delivery is still fixture-backed. |
| Tough-path EOL migrations | PLANNED | No real recipe/decompile/diff/mapping ladder yet. |
| Observability and escalation bundles | PLANNED | Not implemented yet. |
| CI workflow | PLANNED | Baseline CI not yet added. |
