from __future__ import annotations

from pathlib import Path

from execution_accelerator.adapters import (
    AdvisoryVerificationAdapter,
    JiraAdapter,
    MavenVerificationAdapter,
    PomMutationAdapter,
    PreflightResolutionAdapter,
    RepositoryInventoryAdapter,
)
from execution_accelerator.nodes import (
    build_load_repository_context_node,
    build_preflight_validation_node,
    build_remediate_simple_node,
    build_remediate_transitive_node,
)
from execution_accelerator.nodes.verification import select_route
from execution_accelerator.state import RemediationState


def build_state(tmp_path: Path, *, transitive: bool = False) -> RemediationState:
    fixture_dir = Path(__file__).parent / "fixtures"
    vulnerability_details = JiraAdapter(
        fixture_path=fixture_dir / "jira_issue.json"
    ).load_vulnerability_details("SEC-123")
    repo_update = build_load_repository_context_node(
        RepositoryInventoryAdapter(
            fixture_path=fixture_dir / "repository_inventory.json",
            workspace_root=tmp_path / "workspace",
        )
    )(RemediationState(initial_ticket_id="SEC-123", vulnerability_details=vulnerability_details))
    state = RemediationState(
        initial_ticket_id="SEC-123",
        vulnerability_details=vulnerability_details,
        repo_map=repo_update["repo_map"],
        pending_repos=repo_update["pending_repos"],
        advisory_verification=AdvisoryVerificationAdapter(
            fixture_path=fixture_dir / "advisory_verification.json"
        ).load_verification(vulnerability_details),
        maven_verification=MavenVerificationAdapter(
            fixture_path=(
                fixture_dir / "maven_verification_transitive.json"
                if transitive
                else fixture_dir / "maven_verification.json"
            )
        ).load_verification(vulnerability_details, target_version="1.2.4"),
    )
    route_update = select_route(state)
    return state.model_copy(update=route_update)


def test_remediate_simple_node_applies_pom_change(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    node = build_remediate_simple_node(
        PomMutationAdapter(
            fixture_before_path=fixture_dir / "pom_before.xml",
            fixture_after_path=fixture_dir / "pom_after.xml",
        )
    )
    state = build_state(tmp_path)

    update = node(state)

    assert update["current_working_repo"] == "payments-service"
    assert update["pom_mutation_plan"].changes[0].target_version == "1.2.4"
    assert Path(update["modified_files"][0]).read_text().count("1.2.4") == 1
    assert update["code_diffs"][0].change_summary.startswith("Updated org.example:legacy-json")
    assert update["audit_events"][-1].event_type == "remediation.simple_apply"


def test_remediate_transitive_node_applies_dependency_management_override(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    node = build_remediate_transitive_node(
        PomMutationAdapter(
            fixture_before_path=fixture_dir / "pom_transitive_before.xml",
            fixture_after_path=fixture_dir / "pom_transitive_after.xml",
        )
    )
    state = build_state(tmp_path, transitive=True)

    update = node(state)

    assert update["current_working_repo"] == "payments-service"
    assert update["pom_mutation_plan"].strategy == "transitive_override"
    assert update["pom_mutation_plan"].changes[0].target_section == "dependency_management"
    assert Path(update["modified_files"][0]).read_text().count("1.2.4") == 1
    assert update["code_diffs"][0].change_summary.startswith("Added dependencyManagement override")
    assert update["audit_events"][-1].event_type == "remediation.transitive_override"


def test_preflight_validation_node_loads_fixture_result() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    node = build_preflight_validation_node(
        PreflightResolutionAdapter(fixture_path=fixture_dir / "preflight_resolution.json")
    )
    state = RemediationState(
        initial_ticket_id="SEC-123",
        current_working_repo="payments-service",
    )

    update = node(state)

    assert update["preflight_resolution"].resolved_version == "1.2.4"
    assert update["audit_events"][-1].event_type == "remediation.preflight"
