# Execution Accelerator Vision

Execution Accelerator aims to become a **Jira-driven remediation system** that can:

- ingest a vulnerability ticket
- identify the affected repositories and manifests
- verify a safe target version
- choose the right remediation lane
- apply the fix
- validate it
- publish a branch and PR
- update Jira with the outcome

## Target remediation lanes

1. **Simple update**
   - direct dependency bumps
   - safe `pom.xml` edits

2. **Transitive override**
   - dependencyManagement overrides
   - BOM-aware transitive fixes

3. **Complex migration**
   - EOL or breaking-change upgrades
   - jar fetch and decompile
   - compatibility diffing
   - symbol mapping
   - deterministic or bounded agentic code updates

AI scope is intentionally narrow: deterministic paths stay primary, and bounded LLM fallback is reserved for tough-path ambiguity and repair flows. See **`docs/adr/0001-ai-scope.md`**.

## Operating principles

1. **End-to-end first**
2. **Deterministic before agentic**
3. **Validation gates delivery**
4. **Retry and escalation must be explicit**
5. **Human approval is a fallback, not the steady state**

## End-state workflow

`Jira intake -> repository clone -> advisory verification -> Maven verification -> route -> remediation subgraph -> validation -> publish PR -> Jira completion`

The repository is **not at this end state yet**. See `docs/status.md` for the current implementation boundary.
