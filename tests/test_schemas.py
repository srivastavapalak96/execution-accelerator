from __future__ import annotations

from execution_accelerator.schemas import (
    AffectedRepository,
    RemediationPlan,
    RemediationStrategy,
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
                manifest_path="pom.xml",
            )
        ],
    )

    assert details.severity == Severity.HIGH
    assert details.affected_repositories[0].name == "payments-service"
    assert details.affected_repositories[0].build_system == "maven"


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
