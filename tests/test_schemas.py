from __future__ import annotations

import json
from pathlib import Path

from execution_accelerator.schemas import (
    AffectedRepository,
    AdvisoryVerification,
    CompatibilityRisk,
    DependencyCoordinate,
    JiraIssuePayload,
    MavenDependencyKind,
    MavenVerification,
    PomMutationChange,
    PomMutationKind,
    PomMutationPlan,
    PomSectionTarget,
    PreflightResolutionResult,
    RemediationPlan,
    RemediationRouteDecision,
    RemediationStrategy,
    RepositoryInventoryPayload,
    Severity,
    ValidationCheck,
    ValidationStatus,
    VulnerabilityDetails,
)


def test_vulnerability_details_preserves_nested_repository_metadata() -> None:
    details = VulnerabilityDetails(
        package_name="org.example:legacy-lib",
        installed_version="1.2.3",
        fixed_version="1.2.4",
        summary="Example CVE details",
        severity=Severity.HIGH,
        affected_repositories=[
            AffectedRepository(
                name="payments-service",
                clone_url="https://github.com/example/payments-service.git",
                manifest_path="pom.xml",
            )
        ],
    )

    assert details.severity == Severity.HIGH
    assert details.affected_repositories[0].name == "payments-service"
    assert details.affected_repositories[0].build_system == "maven"
    assert details.affected_repositories[0].clone_url == "https://github.com/example/payments-service.git"


def test_remediation_plan_defaults_to_unknown_strategy() -> None:
    plan = RemediationPlan(
        summary="Awaiting routing",
        rationale="The planner has not selected a remediation lane yet.",
    )

    assert plan.strategy == RemediationStrategy.UNKNOWN
    assert plan.requires_human_approval is False


def test_validation_check_defaults_to_pending() -> None:
    check = ValidationCheck(name="compile")

    assert check.status == ValidationStatus.PENDING


def test_jira_issue_fixture_parses_into_typed_payload() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "jira_issue.json"
    payload = JiraIssuePayload.model_validate(json.loads(fixture_path.read_text()))

    assert payload.ticket_id == "SEC-123"
    assert payload.package_name == "org.example:legacy-json"
    assert payload.severity == Severity.HIGH
    assert payload.affected_repositories[0].clone_url == "https://github.com/example/payments-service.git"


def test_repository_inventory_fixture_parses_into_typed_payload() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "repository_inventory.json"
    payload = RepositoryInventoryPayload.model_validate(json.loads(fixture_path.read_text()))

    assert len(payload.repositories) == 2
    assert payload.repositories[0].owner == "payments-platform"
    assert payload.repositories[1].manifest_path == "ledger-app/pom.xml"


def test_advisory_verification_fixture_parses_into_typed_payload() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "advisory_verification.json"
    payload = AdvisoryVerification.model_validate(json.loads(fixture_path.read_text()))

    assert payload.package_name == "org.example:legacy-json"
    assert payload.recommended_fix_version == "1.2.4"
    assert payload.severity == Severity.HIGH


def test_maven_verification_fixture_parses_into_typed_payload() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "maven_verification.json"
    payload = MavenVerification.model_validate(json.loads(fixture_path.read_text()))

    assert payload.target_version == "1.2.4"
    assert payload.dependency_kind == MavenDependencyKind.DIRECT
    assert payload.compatibility_risk == CompatibilityRisk.LOW


def test_route_decision_captures_routing_confidence() -> None:
    decision = RemediationRouteDecision(
        strategy=RemediationStrategy.SIMPLE_UPDATE,
        reason="Verified fix is available and dependency remains on the direct simple lane.",
        confidence=0.92,
    )

    assert decision.strategy == RemediationStrategy.SIMPLE_UPDATE
    assert decision.requires_human_approval is False


def test_pom_mutation_plan_captures_simple_update_change() -> None:
    plan = PomMutationPlan(
        repository="payments-service",
        summary="Directly bump the vulnerable dependency to the verified target version.",
        changes=[
            PomMutationChange(
                file_path="pom.xml",
                dependency=DependencyCoordinate(
                    group_id="org.example",
                    artifact_id="legacy-json",
                    version="1.2.4",
                ),
                mutation_kind=PomMutationKind.DIRECT_VERSION_BUMP,
                target_section=PomSectionTarget.PROJECT_DEPENDENCIES,
                previous_version="1.2.3",
                target_version="1.2.4",
                xml_path_hint="./dependencies/dependency[artifactId='legacy-json']/version",
            )
        ],
    )

    assert plan.strategy == RemediationStrategy.SIMPLE_UPDATE
    assert plan.changes[0].target_version == "1.2.4"


def test_pom_mutation_change_can_target_dependency_management() -> None:
    change = PomMutationChange(
        file_path="pom.xml",
        dependency=DependencyCoordinate(
            group_id="org.example",
            artifact_id="legacy-json",
            version="1.2.4",
        ),
        mutation_kind=PomMutationKind.DEPENDENCY_MANAGEMENT_OVERRIDE,
        target_section=PomSectionTarget.DEPENDENCY_MANAGEMENT,
        previous_version="1.2.3",
        target_version="1.2.4",
        xml_path_hint="./dependencyManagement/dependencies/dependency/version",
    )

    assert change.target_section == PomSectionTarget.DEPENDENCY_MANAGEMENT


def test_preflight_resolution_fixture_parses_into_typed_payload() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "preflight_resolution.json"
    payload = PreflightResolutionResult.model_validate(json.loads(fixture_path.read_text()))

    assert payload.repository == "payments-service"
    assert payload.resolved_version == "1.2.4"
    assert payload.dependency_kind == MavenDependencyKind.DIRECT
