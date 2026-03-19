from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from execution_accelerator.schemas import PolicyDecision, RemediationStrategy
from execution_accelerator.state import RemediationState


@dataclass(frozen=True)
class PolicyConfig:
    draft_pr_only: bool = True
    complex_refactor_requires_human_approval: bool = True
    transitive_override_requires_human_approval: bool = False
    approval_required_tags: tuple[str, ...] = ()
    blocked_tags: tuple[str, ...] = ()


@dataclass
class PolicyEngine:
    """Evaluate a minimal remediation policy from config/policy.yaml."""

    config_path: Path

    def evaluate(self, state: RemediationState) -> PolicyDecision:
        config = self.load_config()
        target_tags = _current_target_tags(state)
        blocked_tags = sorted(tag for tag in target_tags if tag in config.blocked_tags)
        if blocked_tags:
            return PolicyDecision(
                allowed=False,
                requires_human_approval=True,
                blocked_reason=f"Policy blocked remediation for repository tags: {', '.join(blocked_tags)}",
            )

        requires_human_approval = state.requires_human_approval
        approval_reasons = _collect_approval_reasons(state, config, target_tags=target_tags)
        if approval_reasons:
            requires_human_approval = True

        return PolicyDecision(
            allowed=True,
            requires_human_approval=requires_human_approval,
            approval_reason="; ".join(dict.fromkeys(approval_reasons)) or None,
            blocked_reason=None,
        )

    def load_config(self) -> PolicyConfig:
        if not self.config_path.exists():
            return PolicyConfig()
        loaded = yaml.safe_load(self.config_path.read_text()) or {}
        if not isinstance(loaded, dict):
            return PolicyConfig()
        blocked_tags = tuple(
            tag
            for tag in loaded.get("blocked_tags", [])
            if isinstance(tag, str) and tag.strip()
        )
        approval_required_tags = tuple(
            tag
            for tag in loaded.get("approval_required_tags", [])
            if isinstance(tag, str) and tag.strip()
        )
        return PolicyConfig(
            draft_pr_only=bool(loaded.get("draft_pr_only", True)),
            complex_refactor_requires_human_approval=bool(
                loaded.get("complex_refactor_requires_human_approval", True)
            ),
            transitive_override_requires_human_approval=bool(
                loaded.get("transitive_override_requires_human_approval", False)
            ),
            approval_required_tags=approval_required_tags,
            blocked_tags=blocked_tags,
        )


def _current_target_tags(state: RemediationState) -> set[str]:
    if state.current_working_repo and state.current_working_repo in state.repo_map:
        return set(state.repo_map[state.current_working_repo].tags)
    if state.targets and state.current_target_index < len(state.targets):
        return set(state.targets[state.current_target_index].tags)
    return set()


def _policy_requires_route_approval(state: RemediationState, config: PolicyConfig) -> bool:
    if state.route_decision is None:
        return False
    if (
        state.route_decision.strategy == RemediationStrategy.COMPLEX_REFACTOR
        and config.complex_refactor_requires_human_approval
    ):
        return True
    return (
        state.route_decision.strategy == RemediationStrategy.TRANSITIVE_OVERRIDE
        and config.transitive_override_requires_human_approval
    )


def _collect_approval_reasons(
    state: RemediationState, config: PolicyConfig, *, target_tags: set[str]
) -> list[str]:
    reasons: list[str] = []
    if state.route_decision is not None:
        if state.route_decision.requires_human_approval:
            reasons.append(f"Route requires approval: {state.route_decision.reason}")
        if (
            state.route_decision.strategy == RemediationStrategy.COMPLEX_REFACTOR
            and config.complex_refactor_requires_human_approval
        ):
            reasons.append("Policy requires approval for complex_refactor remediation.")
        if (
            state.route_decision.strategy == RemediationStrategy.TRANSITIVE_OVERRIDE
            and config.transitive_override_requires_human_approval
        ):
            reasons.append("Policy requires approval for transitive_override remediation.")
    tagged_reasons = sorted(tag for tag in target_tags if tag in config.approval_required_tags)
    if tagged_reasons:
        reasons.append(f"Repository tags require approval: {', '.join(tagged_reasons)}")
    return reasons
