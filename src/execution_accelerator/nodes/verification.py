"""Day 4 verification and routing nodes."""

from __future__ import annotations

from collections.abc import Callable

from execution_accelerator.adapters import AdvisoryVerificationAdapter, MavenVerificationAdapter
from execution_accelerator.schemas import (
    AuditEvent,
    CompatibilityRisk,
    MavenDependencyKind,
    RemediationPlan,
    RemediationRouteDecision,
    RemediationStrategy,
    VerificationStatus,
    WorkflowStatus,
)
from execution_accelerator.state import RemediationState


def build_verify_advisory_node(
    advisory_adapter: AdvisoryVerificationAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that verifies the recommended remediation target from advisory data."""

    def verify_advisory(state: RemediationState) -> dict[str, object]:
        assert state.vulnerability_details is not None

        advisory_verification = advisory_adapter.load_verification(state.vulnerability_details)
        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="verification.advisory",
                message=f"Verified advisory remediation target for {state.initial_ticket_id}.",
                details={
                    "ticket_id": state.initial_ticket_id,
                    "package_name": advisory_verification.package_name,
                    "target_version": advisory_verification.recommended_fix_version,
                    "status": advisory_verification.status,
                },
            )
        )

        return {
            "advisory_verification": advisory_verification,
            "audit_events": audit_events,
        }

    return verify_advisory


def build_verify_maven_target_node(
    maven_adapter: MavenVerificationAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that verifies the selected target version against Maven metadata."""

    def verify_maven_target(state: RemediationState) -> dict[str, object]:
        assert state.vulnerability_details is not None
        assert state.advisory_verification is not None

        maven_verification = maven_adapter.load_verification(
            state.vulnerability_details,
            target_version=state.advisory_verification.recommended_fix_version,
        )
        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="verification.maven",
                message=f"Verified Maven remediation target for {state.initial_ticket_id}.",
                details={
                    "ticket_id": state.initial_ticket_id,
                    "target_version": maven_verification.target_version,
                    "dependency_kind": maven_verification.dependency_kind,
                    "compatibility_risk": maven_verification.compatibility_risk,
                },
            )
        )

        return {
            "maven_verification": maven_verification,
            "audit_events": audit_events,
        }

    return verify_maven_target


def select_route(state: RemediationState) -> dict[str, object]:
    """Select the initial remediation lane from verified advisory and Maven metadata."""

    assert state.advisory_verification is not None
    assert state.maven_verification is not None

    route_decision = _build_route_decision(state)
    target_repositories = list(state.pending_repos or state.repo_map.keys())
    remediation_plan = RemediationPlan(
        strategy=route_decision.strategy,
        summary=f"Route {state.initial_ticket_id} into the {route_decision.strategy} lane.",
        rationale=route_decision.reason,
        target_repositories=target_repositories,
        requires_human_approval=route_decision.requires_human_approval,
    )

    audit_events = list(state.audit_events)
    audit_events.append(
        AuditEvent(
            event_type="verification.route",
            message=f"Selected remediation route for {state.initial_ticket_id}.",
            details={
                "ticket_id": state.initial_ticket_id,
                "strategy": route_decision.strategy,
                "confidence": route_decision.confidence,
                "requires_human_approval": route_decision.requires_human_approval,
            },
        )
    )

    return {
        "workflow_status": WorkflowStatus.PLANNING_READY,
        "route_decision": route_decision,
        "remediation_plan": remediation_plan,
        "requires_human_approval": route_decision.requires_human_approval,
        "audit_events": audit_events,
    }


def _build_route_decision(state: RemediationState) -> RemediationRouteDecision:
    advisory = state.advisory_verification
    maven = state.maven_verification
    assert advisory is not None
    assert maven is not None

    if (
        advisory.status != VerificationStatus.VERIFIED
        or maven.status != VerificationStatus.VERIFIED
    ):
        return RemediationRouteDecision(
            strategy=RemediationStrategy.UNKNOWN,
            reason="Verification did not produce a trusted remediation target.",
            confidence=0.2,
            requires_human_approval=True,
        )

    if maven.compatibility_risk == CompatibilityRisk.HIGH:
        return RemediationRouteDecision(
            strategy=RemediationStrategy.COMPLEX_REFACTOR,
            reason="Verified target introduces high compatibility risk and needs the complex remediation lane.",
            confidence=0.78,
            requires_human_approval=True,
        )

    if maven.dependency_kind == MavenDependencyKind.TRANSITIVE:
        return RemediationRouteDecision(
            strategy=RemediationStrategy.TRANSITIVE_OVERRIDE,
            reason="Verified target is transitive, so remediation should start with an override strategy.",
            confidence=0.88,
        )

    return RemediationRouteDecision(
        strategy=RemediationStrategy.SIMPLE_UPDATE,
        reason="Verified target is direct, available, and low-risk, so the simple update lane is appropriate.",
        confidence=0.93,
    )
