# Status

A scan-friendly view of what's implemented today.

| Capability | Status |
|---|---|
| **Orchestration** | |
| LangGraph state machine + SQLite checkpointing | Shipped |
| Pydantic-typed `RemediationState` end-to-end | Shipped |
| Two-stage human-approval interrupts | Shipped |
| Multi-repository iteration | Shipped |
| **Intake & verification** | |
| Live Jira REST v3 intake (with `config/jira.yaml`) | Shipped |
| `git clone` with bastion `proxy_jump` + `ssh_key` | Shipped |
| Idempotency (open + recently-closed PR search) | Shipped |
| Maven profile detection (JDK / reactor / parent / BOM) | Shipped |
| OSV advisory verification with 24h cache | Shipped |
| Maven Central metadata + `dependency:tree` analysis | Shipped |
| Maven version-range evaluator | Shipped |
| **Remediation** | |
| Simple direct-version bump via OpenRewrite | Shipped |
| Transitive `dependencyManagement` override | Shipped |
| Complex Java rewrites (methods / constructors / refs / static fields) | Shipped |
| Tough-path: OpenRewrite recipe matcher | Shipped |
| Tough-path: CFR decompiler with sha256-keyed cache | Shipped |
| Tough-path: public-API diff (removed / added / changed) | Shipped |
| Tough-path: similarity-based symbol mapper with LLM-confidence cap | Shipped |
| **Validation** | |
| `mvn verify` + Surefire/Failsafe parsing | Shipped |
| OSV rescan via version-range evaluation | Shipped |
| License diff with allow/deny lists | Shipped |
| Real `git restore` + untracked cleanup on failure | Shipped |
| **Delivery** | |
| `git push` + GitHub PR + Jira comment + Jira transition | Shipped |
| PR-conflict recovery (re-bind to existing open PR) | Shipped |
| Optional GPG-signed commits (`EA_GPG_SIGNING_KEY`) | Shipped |
| Post-push rollback primitives (`delete_remote_branch`, `close_pull_request`) | Shipped |
| **AI integration** | |
| Pluggable LLM client (Ollama default; Anthropic/OpenAI hooks) | Shipped |
| Prompt redaction for hosted providers | Shipped |
| Per-ticket call + token budgets | Shipped |
| LLM-staged repair proposals for compile + test failures | Shipped |
| **Failure handling** | |
| Classified retry matrix (network / compile / test / recipe / policy) | Shipped |
| `WorkflowError` invariant guards (no `assert` in `nodes/`) | Shipped |
| JSON escalation bundles for terminal failures | Shipped |
| Bounded total-attempt ceiling (`EA_MAX_TOTAL_ATTEMPTS`) | Shipped |
| **Policy** | |
| YAML-driven CVSS / tag / license rules (`config/policy.yaml`) | Shipped |
| Approval-required tags + complex-refactor approval gate | Shipped |
| Draft-PR policy enforcement | Shipped |
| **Observability** | |
| Per-run audit JSONL (`.local/logs/audit-{thread_id}.jsonl`) | Shipped |
| Per-run metrics CSV (`.local/data/metrics.csv`) | Shipped |
| Operator CLI: `--status`, `--abort`, `--probe-llm` | Shipped |
| **Tests** | |
| 312 unit tests (`EA_MODE=fixture`) | Shipped |
| 8 integration tests (real OSV / `mvn` / `git`, gated on `EA_INTEGRATION=1`) | Shipped |
| `ruff check src tests` clean | Shipped |
| `mypy --strict src` clean across 63 source files | Shipped |
| GitHub Actions on every push/PR + nightly integration job | Shipped |

## Next milestones

- Compose the existing nodes into LangGraph subgraphs (`subgraphs/`) for isolation testing and clearer architecture diagrams.
- Wire the staged `RepairProposal`s into the classified-retry matrix (graph composition lands with the subgraph refactor).
- Phase the post-push rollback primitives onto the failure path (also lands with subgraph composition).
- Three-target validation suite for the tough-path ladder: `commons-lang 2.x → 3.x` (exit gate), `joda-time → java.time` (stretch), `junit 4 → 5` (stretch).
