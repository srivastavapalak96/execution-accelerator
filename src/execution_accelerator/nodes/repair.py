"""LLM-assisted repair nodes for compile and test failures.

When ``classify_failure`` reports ``compile_error`` or ``test_failure`` with
retry budget remaining, the graph routes through ``repair_compile`` or
``repair_tests`` before the next validation attempt. Both stage a
``RepairProposal`` on state; the validation adapter applies it under
``git apply --check`` and ``mvn compile``.

Per-patch size limits live here (10 files, 500 changed lines).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

import pydantic

from execution_accelerator.llm.client import LlmClient
from execution_accelerator.llm.structured import structured_call
from execution_accelerator.schemas import (
    AuditEvent,
    FailureClassification,
    RepairProposal,
)
from execution_accelerator.state import RemediationState

MAX_FILES_PER_PATCH = 10
MAX_LINES_PER_PATCH = 500


class RepairBudgetExceeded(RuntimeError):
    """Raised when an LLM-generated patch exceeds the per-patch size limits."""

    def __init__(self, *, kind: str, observed: int, limit: int) -> None:
        self.kind = kind
        self.observed = observed
        self.limit = limit
        super().__init__(
            f"Repair patch exceeded {kind} limit: {observed} > {limit}"
        )


class _LlmPatchProposal(pydantic.BaseModel):
    """Schema enforced on the LLM's structured response."""

    rationale: str = pydantic.Field(min_length=1, max_length=2000)
    unified_diff: str = pydantic.Field(min_length=1)
    affected_files: list[str] = pydantic.Field(default_factory=list)


@dataclass
class RepairContext:
    """Bundle of inputs feeding a single repair attempt."""

    failure_classification: FailureClassification
    workspace_path: str
    error_excerpt: str
    relevant_files: tuple[tuple[str, str], ...]  # (relative_path, contents)


def build_repair_compile_node(
    client: LlmClient,
    *,
    prompt_loader: Callable[[], str] | None = None,
) -> Callable[[RemediationState], dict[str, object]]:
    """Construct the ``repair_compile`` node bound to ``client``."""

    return _build_repair_node(
        client=client,
        prompt_name="repair_compile",
        default_prompt=_DEFAULT_COMPILE_PROMPT,
        prompt_loader=prompt_loader,
        failure_class=FailureClassification.COMPILE_ERROR,
    )


def build_repair_tests_node(
    client: LlmClient,
    *,
    prompt_loader: Callable[[], str] | None = None,
) -> Callable[[RemediationState], dict[str, object]]:
    """Construct the ``repair_tests`` node bound to ``client``."""

    return _build_repair_node(
        client=client,
        prompt_name="repair_tests",
        default_prompt=_DEFAULT_TEST_PROMPT,
        prompt_loader=prompt_loader,
        failure_class=FailureClassification.TEST_FAILURE,
    )


def _build_repair_node(
    *,
    client: LlmClient,
    prompt_name: str,
    default_prompt: str,
    prompt_loader: Callable[[], str] | None,
    failure_class: FailureClassification,
) -> Callable[[RemediationState], dict[str, object]]:
    def repair(state: RemediationState) -> dict[str, object]:
        context = _context_from_state(state, failure_class=failure_class)
        prompt_template = prompt_loader() if prompt_loader is not None else default_prompt
        prompt = _render_prompt(prompt_template, context=context)

        proposal_model, record = structured_call(
            client=client,
            state=state,
            prompt=prompt,
            schema=_LlmPatchProposal,
            prompt_name=prompt_name,
        )
        _enforce_patch_limits(proposal_model)

        repair_proposal = RepairProposal(
            failure_classification=failure_class,
            rationale=proposal_model.rationale,
            unified_diff=proposal_model.unified_diff,
            affected_files=tuple(proposal_model.affected_files),
            attempt_index=len(state.repair_proposals) + 1,
        )

        return {
            "llm_calls": _appended(state.llm_calls, record),
            "llm_tokens_used": state.llm_tokens_used + record.token_count,
            "repair_proposals": _appended(state.repair_proposals, repair_proposal),
            "audit_events": _appended(
                state.audit_events,
                AuditEvent(
                    event_type=f"repair.{failure_class}",
                    message=f"Generated repair proposal for {failure_class}.",
                    details={
                        "affected_files": list(proposal_model.affected_files),
                        "diff_lines": _count_diff_lines(proposal_model.unified_diff),
                        "attempt_index": repair_proposal.attempt_index,
                    },
                ),
            ),
        }

    return repair


def _context_from_state(
    state: RemediationState,
    *,
    failure_class: FailureClassification,
) -> RepairContext:
    """Pull the most relevant info out of state for the LLM prompt."""

    workspace_path = ""
    if state.current_working_repo is not None:
        workspace = state.repo_map.get(state.current_working_repo)
        if workspace is not None:
            workspace_path = workspace.local_path

    error_excerpt = ""
    if state.errors:
        error_excerpt = state.errors[-1].message[:4000]

    return RepairContext(
        failure_classification=failure_class,
        workspace_path=workspace_path,
        error_excerpt=error_excerpt,
        relevant_files=tuple(state.relevant_repair_inputs),
    )


def _render_prompt(template: str, *, context: RepairContext) -> str:
    file_excerpts = "\n\n".join(
        f"--- {path} ---\n{contents}" for path, contents in context.relevant_files
    ) or "(no source files attached)"
    return template.format(
        failure_classification=context.failure_classification,
        workspace_path=context.workspace_path,
        error_excerpt=context.error_excerpt or "(no error message captured)",
        file_excerpts=file_excerpts,
    )


def _enforce_patch_limits(proposal: _LlmPatchProposal) -> None:
    file_count = len(proposal.affected_files)
    if file_count > MAX_FILES_PER_PATCH:
        raise RepairBudgetExceeded(kind="files", observed=file_count, limit=MAX_FILES_PER_PATCH)
    line_count = _count_diff_lines(proposal.unified_diff)
    if line_count > MAX_LINES_PER_PATCH:
        raise RepairBudgetExceeded(kind="lines", observed=line_count, limit=MAX_LINES_PER_PATCH)


def _count_diff_lines(unified_diff: str) -> int:
    """Count added + removed lines in a unified diff. Headers don't count."""

    count = 0
    for line in unified_diff.splitlines():
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            count += 1
    return count


_T = TypeVar("_T")


def _appended(values: Sequence[_T], record: _T) -> list[_T]:
    new_list = list(values)
    new_list.append(record)
    return new_list


_DEFAULT_COMPILE_PROMPT = """You are an expert Java engineer fixing a compile failure during automated remediation.

Failure classification: {failure_classification}
Workspace: {workspace_path}

Compiler output (truncated):
{error_excerpt}

Relevant source files:
{file_excerpts}

Return STRICT JSON matching the following schema:
{{
  "rationale": "string explaining the minimal change",
  "unified_diff": "git-applyable unified diff",
  "affected_files": ["repo/relative/path.java", ...]
}}
Constraints:
- Modify at most 10 files; the diff must be at most 500 changed lines.
- Do NOT introduce new dependencies, new imports of packages not present, or unrelated refactors.
- The diff must be directly applicable with `git apply --check`.
"""


_DEFAULT_TEST_PROMPT = """You are an expert Java engineer fixing a failing test during automated remediation.

Failure classification: {failure_classification}
Workspace: {workspace_path}

Test failure output (truncated):
{error_excerpt}

Relevant test and source files:
{file_excerpts}

Return STRICT JSON matching the following schema:
{{
  "rationale": "string explaining the minimal change",
  "unified_diff": "git-applyable unified diff",
  "affected_files": ["repo/relative/path.java", ...]
}}
Constraints:
- Modify at most 10 files; the diff must be at most 500 changed lines.
- Prefer fixing the production code over weakening the assertion.
- The diff must be directly applicable with `git apply --check`.
"""
