from __future__ import annotations

from pathlib import Path

from execution_accelerator.adapters import AdvisoryVerificationAdapter, MavenVerificationAdapter
from execution_accelerator.profiles import detect_maven_execution_plan
from execution_accelerator.nodes import (
    build_detect_maven_profile_node,
    build_verify_advisory_node,
    build_verify_maven_target_node,
    select_route,
)
from execution_accelerator.config import load_runtime_config
from execution_accelerator.schemas import RemediationStrategy, WorkflowStatus
from execution_accelerator.state import RemediationState, RepositoryWorkspace
from tests.conftest import seed_workspace_pom


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


def test_verify_maven_target_node_loads_fixture_data(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    workspace = tmp_path / "workspace"
    seed_workspace_pom(workspace, fixture_dir / "pom_before.xml")
    state = build_state().model_copy(
        update={
            "repo_map": {
                "payments-service": RepositoryWorkspace(
                    name="payments-service",
                    local_path=str(workspace),
                    clone_url="https://example.test/payments-service.git",
                    default_branch="main",
                    build_system="maven",
                    manifest_path="pom.xml",
                )
            },
            "current_working_repo": "payments-service",
            "advisory_verification": AdvisoryVerificationAdapter(
                fixture_path=fixture_dir / "advisory_verification.json"
            ).load_verification(build_state().vulnerability_details),
            "maven_plan": detect_maven_execution_plan(
                RepositoryWorkspace(
                    name="payments-service",
                    local_path=str(workspace),
                    clone_url="https://example.test/payments-service.git",
                    default_branch="main",
                    build_system="maven",
                    manifest_path="pom.xml",
                )
            ),
        }
    )
    node = build_verify_maven_target_node(
        MavenVerificationAdapter(fixture_path=fixture_dir / "maven_verification.json")
    )

    update = node(state)

    assert update["maven_verification"].target_version == "1.2.4"
    assert update["audit_events"][-1].event_type == "verification.maven"


def test_detect_maven_profile_node_sets_current_repo_and_plan(tmp_path, monkeypatch) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    workspace = tmp_path / "workspace" / "payments-service"
    seed_workspace_pom(workspace, fixture_dir / "pom_before.xml")
    (workspace / "mvnw").write_text("#!/bin/sh\n")
    (workspace / "mvnw").chmod(0o755)
    monkeypatch.setenv("EA_MAVEN_SETTINGS", str(tmp_path / "settings.xml"))
    (tmp_path / "settings.xml").write_text("<settings/>")
    config = load_runtime_config(repo_root=tmp_path)
    node = build_detect_maven_profile_node(config)

    update = node(
        RemediationState(
            initial_ticket_id="SEC-123",
            pending_repos=["payments-service"],
            repo_map={
                "payments-service": RepositoryWorkspace(
                    name="payments-service",
                    local_path=str(workspace),
                    clone_url="https://example.test/payments-service.git",
                    default_branch="main",
                    build_system="maven",
                    manifest_path="pom.xml",
                )
            },
        )
    )

    assert update["current_working_repo"] == "payments-service"
    assert update["maven_plan"].uses_wrapper is True
    assert update["audit_events"][-1].event_type == "verification.maven_profile"


def test_detect_maven_profile_node_prefers_repo_specific_maven_settings(tmp_path, monkeypatch) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    workspace = tmp_path / "workspace" / "payments-service"
    seed_workspace_pom(workspace, fixture_dir / "pom_before.xml")
    repo_settings = tmp_path / "repo-settings.xml"
    env_settings = tmp_path / "env-settings.xml"
    repo_settings.write_text("<settings><mirrors /></settings>")
    env_settings.write_text("<settings><servers /></settings>")
    monkeypatch.setenv("EA_MAVEN_SETTINGS", str(env_settings))
    config = load_runtime_config(repo_root=tmp_path)
    node = build_detect_maven_profile_node(config)

    update = node(
        RemediationState(
            initial_ticket_id="SEC-123",
            pending_repos=["payments-service"],
            repo_map={
                "payments-service": RepositoryWorkspace(
                    name="payments-service",
                    local_path=str(workspace),
                    clone_url="https://example.test/payments-service.git",
                    default_branch="main",
                    build_system="maven",
                    manifest_path="pom.xml",
                    maven_settings=str(repo_settings),
                )
            },
        )
    )

    assert update["maven_plan"].settings_xml == str(repo_settings)


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
