# Execution Accelerator Status

This file tracks the repository **as implemented today**, not the aspirational end state.

| Area | Status | Notes |
|------|--------|-------|
| LangGraph + SQLite checkpoints | SHIPPED | Persisted runs and checkpoint reload are implemented. |
| Typed schemas and remediation state | SHIPPED | Core workflow models and state exist. |
| Fixture execution mode | SHIPPED | `EA_MODE=fixture` is the default and covered by tests. |
| Live execution mode | PARTIAL | `EA_MODE=live` now covers credential probe, Jira intake, repository inventory/clone, OSV advisory lookup, Maven verification, OpenRewrite-backed POM mutation, live preflight, live validation, and basic live delivery. |
| Jira intake | PARTIAL | Fixture-backed by default; live issue reads work with `config/jira.yaml` plus Jira credentials. |
| Repository inventory + workspace prep | PARTIAL | Fixture-backed by default; live inventory from `config/repositories.yaml`, PR idempotency lookup, per-repo `maven_settings`, per-repo `proxy_jump`, and git clone prep exist. |
| Advisory verification | PARTIAL | Fixture-backed by default; live OSV lookup with local cache now exists. |
| Maven verification | PARTIAL | Fixture-backed by default; live metadata + dependency-tree verification now exists, including direct/transitive classification and risk evaluation. |
| Simple remediation lane | PARTIAL | Fixture-backed default path remains, and live mode now delegates direct upgrades through OpenRewrite-backed mutation. |
| Transitive remediation lane | PARTIAL | Fixture-backed default path remains, and live mode now delegates managed dependency overrides through OpenRewrite-backed mutation. |
| Complex remediation lane | PARTIAL | Analysis/execution scaffold exists, not real migration logic. |
| Validation | PARTIAL | Live preflight resolution now checks the workspace dependency tree and live validation runs `mvn verify` plus Surefire/Failsafe parsing, but security diffing and live rollback remain fixture-backed. |
| Delivery | PARTIAL | Live branch publication and PR creation now exist; Jira completion is currently a comment write, not a full transition workflow. |
| Failure classification | PARTIAL | Phase 0 stub routes failures through classify -> escalate. |
| Retry matrix | PLANNED | Full retry routing is not implemented yet. |
| Policy engine | PARTIAL | A basic policy engine runs after route selection and can block tagged repositories or require approval for complex refactors. |
| Human approval interrupt | PLANNED | Not wired yet. |
| Live PR creation and Jira updates | PARTIAL | PR creation is live; Jira updates currently post completion comments only. |
| Tough-path EOL migrations | PLANNED | No real recipe/decompile/diff/mapping ladder yet. |
| Observability and escalation bundles | PLANNED | Not implemented yet. |
| CI workflow | SHIPPED | GitHub Actions runs ruff, strict mypy, and fixture-mode pytest. |
