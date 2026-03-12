from __future__ import annotations

from pathlib import Path

from execution_accelerator.adapters import AdvisoryVerificationAdapter, MavenVerificationAdapter
from execution_accelerator.nodes import (
    build_verify_advisory_node,
    build_verify_maven_target_node,
    select_route,
)
from execution_accelerator.schemas import RemediationStrategy, WorkflowStatus
from execution_accelerator.state import RemediationState


def build_state() -> RemediationState:
    fixture_dir = Path(__file__).parent / "fixtures"
    vulnerability_details = (
        __import__("execution_accelerator.adapters", fromlist=["JiraAdapter"])
        .JiraAdapter(fixture_path=fixture_dir / "jira_issue.json")
        .load_vulnerability_details("SEC-123")
    )
    return RemediationState(
        initial_ticket_id="SEC-123",
        vulnerability_details=vulnerability_details,
        pending_repos=["payments-service"],
    )


def test_verify_advisory_node_loads_fixture_data() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    node = build_verify_advisory_node(
        AdvisoryVerificationAdapter(fixture_path=fixture_dir / "advisory_verification.json")
    )

    update = node(build_state())

    assert update["advisory_verification"].recommended_fix_version == "1.2.4"
    assert update["audit_events"][-1].event_type == "verification.advisory"


def test_verify_maven_target_node_loads_fixture_data() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    state = build_state().model_copy(
        update={
            "advisory_verification": AdvisoryVerificationAdapter(
                fixture_path=fixture_dir / "advisory_verification.json"
            ).load_verification(build_state().vulnerability_details),
        }
    )
    node = build_verify_maven_target_node(
        MavenVerificationAdapter(fixture_path=fixture_dir / "maven_verification.json")
    )

    update = node(state)

    assert update["maven_verification"].target_version == "1.2.4"
    assert update["audit_events"][-1].event_type == "verification.maven"


def test_select_route_prefers_simple_update_for_low_risk_direct_dependencies() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    state = build_state().model_copy(
        update={
            "advisory_verification": AdvisoryVerificationAdapter(
                fixture_path=fixture_dir / "advisory_verification.json"
            ).load_verification(build_state().vulnerability_details),
            "maven_verification": MavenVerificationAdapter(
                fixture_path=fixture_dir / "maven_verification.json"
            ).load_verification(build_state().vulnerability_details, target_version="1.2.4"),
        }
    )

    update = select_route(state)

    assert update["workflow_status"] == WorkflowStatus.PLANNING_READY
    assert update["route_decision"].strategy == RemediationStrategy.SIMPLE_UPDATE
    assert update["remediation_plan"].strategy == RemediationStrategy.SIMPLE_UPDATE
    assert update["audit_events"][-1].event_type == "verification.route"


def test_select_route_prefers_transitive_override_for_indirect_dependencies() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    state = build_state().model_copy(
        update={
            "advisory_verification": AdvisoryVerificationAdapter(
                fixture_path=fixture_dir / "advisory_verification.json"
            ).load_verification(build_state().vulnerability_details),
            "maven_verification": MavenVerificationAdapter(
                fixture_path=fixture_dir / "maven_verification_transitive.json"
            ).load_verification(build_state().vulnerability_details, target_version="1.2.4"),
        }
    )

    update = select_route(state)

    assert update["workflow_status"] == WorkflowStatus.PLANNING_READY
    assert update["route_decision"].strategy == RemediationStrategy.TRANSITIVE_OVERRIDE
    assert update["remediation_plan"].strategy == RemediationStrategy.TRANSITIVE_OVERRIDE
    assert update["audit_events"][-1].event_type == "verification.route"


def test_select_route_prefers_complex_refactor_for_high_risk_targets() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    state = build_state().model_copy(
        update={
            "advisory_verification": AdvisoryVerificationAdapter(
                fixture_path=fixture_dir / "advisory_verification.json"
            ).load_verification(build_state().vulnerability_details),
            "maven_verification": MavenVerificationAdapter(
                fixture_path=fixture_dir / "maven_verification_complex.json"
            ).load_verification(build_state().vulnerability_details, target_version="2.0.0"),
        }
    )

    update = select_route(state)

    assert update["workflow_status"] == WorkflowStatus.PLANNING_READY
    assert update["route_decision"].strategy == RemediationStrategy.COMPLEX_REFACTOR
    assert update["remediation_plan"].strategy == RemediationStrategy.COMPLEX_REFACTOR
    assert update["route_decision"].requires_human_approval is True
