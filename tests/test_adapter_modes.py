from __future__ import annotations

from pathlib import Path

import pytest

from execution_accelerator.adapters import (
    AdvisoryVerificationAdapter,
    ComplexRemediationAdapter,
    DeliveryAdapter,
    JiraAdapter,
    MavenVerificationAdapter,
    PomMutationAdapter,
    PreflightResolutionAdapter,
    RepositoryInventoryAdapter,
    ValidationAdapter,
)
from execution_accelerator.schemas import AffectedRepository, ExecutionMode, Severity, VulnerabilityDetails


def build_vulnerability_details() -> VulnerabilityDetails:
    return VulnerabilityDetails(
        package_name="org.example:legacy-json",
        installed_version="1.2.3",
        fixed_version="1.2.4",
        summary="Execution mode test vulnerability",
        severity=Severity.HIGH,
        affected_repositories=[AffectedRepository(name="payments-service", manifest_path="pom.xml")],
    )


def test_live_mode_adapters_fail_fast_until_implemented(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    details = build_vulnerability_details()

    live_calls = [
        lambda: JiraAdapter(fixture_path=fixture_dir / "jira_issue.json", mode=ExecutionMode.LIVE).load_issue(
            "SEC-123"
        ),
        lambda: RepositoryInventoryAdapter(
            fixture_path=fixture_dir / "repository_inventory.json",
            workspace_root=tmp_path / "workspace",
            mode=ExecutionMode.LIVE,
        ).load_inventory(),
        lambda: AdvisoryVerificationAdapter(
            fixture_path=fixture_dir / "advisory_verification.json",
            mode=ExecutionMode.LIVE,
        ).load_verification(details),
        lambda: MavenVerificationAdapter(
            fixture_path=fixture_dir / "maven_verification.json",
            mode=ExecutionMode.LIVE,
        ).load_verification(details, target_version="1.2.4"),
        lambda: PomMutationAdapter(
            fixture_before_path=fixture_dir / "pom_before.xml",
            mode=ExecutionMode.LIVE,
        ).load_fixture_before(),
        lambda: PreflightResolutionAdapter(
            fixture_path=fixture_dir / "preflight_resolution.json",
            mode=ExecutionMode.LIVE,
        ).load_result(repository="payments-service"),
        lambda: ComplexRemediationAdapter(
            artifact_fixture_path=fixture_dir / "complex_artifacts.json",
            mode=ExecutionMode.LIVE,
        ).load_artifact_candidates(),
        lambda: ValidationAdapter(
            validation_result_fixture_path=fixture_dir / "validation_result.json",
            rollback_fixture_path=fixture_dir / "rollback_plan.json",
            mode=ExecutionMode.LIVE,
        ).load_validation_result(repository="payments-service"),
        lambda: DeliveryAdapter(
            branch_publication_fixture_path=fixture_dir / "branch_publication.json",
            pull_request_fixture_path=fixture_dir / "pull_request.json",
            jira_completion_fixture_path=fixture_dir / "jira_completion.json",
            mode=ExecutionMode.LIVE,
        ).load_branch_publication(repository="payments-service"),
    ]

    for live_call in live_calls:
        with pytest.raises(NotImplementedError, match="EA_MODE=live"):
            live_call()
