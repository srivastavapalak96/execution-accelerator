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
| Complex remediation lane | PARTIAL | Analysis/execution scaffold exists, and the persisted complex plan now records a primary migration tactic derived from compatibility analysis, but real migration execution logic is still missing. |
| Validation | PARTIAL | Live preflight resolution now checks the workspace dependency tree, live validation runs `mvn verify`, parses Surefire/Failsafe results, rescans the dependency tree for the remediated version, and can trigger git-backed rollback on failure. |
| Delivery | PARTIAL | Live branch publication and PR creation now exist; Jira completion can post a comment and optionally fire a configured done transition, but richer workflow handling is still missing. |
| Failure classification | PARTIAL | Failures route through classify -> rollback -> escalate, and failed runs now persist escalation bundle metadata. |
| Retry matrix | PARTIAL | Retryable test failures can now re-run the active remediation lane within a bounded retry budget before escalating; compile failures still escalate immediately and richer retry policies are still missing. |
| Policy engine | PARTIAL | A basic policy engine runs after route selection, can block tagged repositories, can require approval for complex refactors, transitive overrides, and approval-tagged repositories, and now drives draft PR publication policy. |
| Human approval interrupt | PARTIAL | Approval-required runs now pause before remediation, persist approval state, surface approval reasons in CLI summaries, and can resume after explicit approve/reject input. |
| Live PR creation and Jira updates | PARTIAL | PR creation is live; Jira updates can post completion comments and optionally apply a configured done transition. |
| Tough-path EOL migrations | PLANNED | No real recipe/decompile/diff/mapping ladder yet. |
| Observability and escalation bundles | PARTIAL | Failed runs now write JSON escalation bundles under `data/escalations/` and surface the bundle path in CLI summaries; broader observability hardening is still missing. |
| CI workflow | SHIPPED | GitHub Actions runs ruff, strict mypy, and fixture-mode pytest. |
