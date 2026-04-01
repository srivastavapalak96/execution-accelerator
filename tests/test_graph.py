from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import json
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
from execution_accelerator.config import load_runtime_config
from execution_accelerator.graph import bootstrap_ticket_run, compile_remediation_graph, load_remediation_state, resume_ticket_run
from execution_accelerator.persistence import build_thread_config
from execution_accelerator.schemas import (
    ApprovalDecision,
    HumanFeedback,
    PreflightResolutionResult,
    RepositoryValidationResult,
    RollbackPlan,
    ValidationStatus,
    WorkflowStatus,
)
from tests.conftest import seed_bootstrap_workspace_pom
from tests.live_support import ResponseSpec, create_live_remote_repo, create_live_repo, serve_routes


def _configure_runtime(monkeypatch, tmp_path, *, transitive: bool = False, complex_refactor: bool = False) -> None:
    fixtures_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv("EA_DRY_RUN", "0")
    monkeypatch.setenv("EA_KEEP_WORKSPACE", "0")
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(fixtures_dir / "jira_issue.json"))
    monkeypatch.setenv(
        "EA_REPOSITORY_INVENTORY_FIXTURE_PATH",
        str(fixtures_dir / "repository_inventory.json"),
    )
    monkeypatch.setenv(
        "EA_ADVISORY_FIXTURE_PATH",
        str(
            fixtures_dir
            / ("advisory_verification_complex.json" if complex_refactor else "advisory_verification.json")
        ),
    )
    monkeypatch.setenv(
        "EA_MAVEN_VERIFICATION_FIXTURE_PATH",
        str(
            fixtures_dir
            / (
                "maven_verification_complex.json"
                if complex_refactor
                else ("maven_verification_transitive.json" if transitive else "maven_verification.json")
            )
        ),
    )
    monkeypatch.setenv(
        "EA_POM_FIXTURE_BEFORE_PATH",
        str(fixtures_dir / ("pom_transitive_before.xml" if transitive else "pom_before.xml")),
    )
    monkeypatch.setenv(
        "EA_POM_FIXTURE_AFTER_PATH",
        str(fixtures_dir / ("pom_transitive_after.xml" if transitive else "pom_after.xml")),
    )
    monkeypatch.setenv(
        "EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH",
        str(
            fixtures_dir
            / ("preflight_resolution_transitive.json" if transitive else "preflight_resolution.json")
        ),
    )
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixtures_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixtures_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixtures_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixtures_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixtures_dir / "code_change_plan.json"))
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixtures_dir / "validation_result.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixtures_dir / "rollback_plan.json"))
    monkeypatch.setenv("EA_BRANCH_PUBLICATION_FIXTURE_PATH", str(fixtures_dir / "branch_publication.json"))
    monkeypatch.setenv("EA_PULL_REQUEST_FIXTURE_PATH", str(fixtures_dir / "pull_request.json"))
    monkeypatch.setenv("EA_JIRA_COMPLETION_FIXTURE_PATH", str(fixtures_dir / "jira_completion.json"))


def test_bootstrap_ticket_run_persists_checkpointed_state(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-42",
        repository_name="payments-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_before.xml",
    )
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-42",
        runtime_config=config,
        thread_id="sec-42-thread",
    )
    loaded_state = load_remediation_state(
        runtime_config=config,
        thread_id="sec-42-thread",
    )

    assert result.thread_id == "sec-42-thread"
    assert result.checkpoint_path == config.checkpoints_path
    assert result.state.workflow_status == WorkflowStatus.COMPLETED
    assert result.state.vulnerability_details is not None
    assert result.state.vulnerability_details.package_name == "org.example:legacy-json"
    assert result.state.advisory_verification is not None
    assert result.state.advisory_verification.recommended_fix_version == "1.2.4"
    assert result.state.maven_verification is not None
    assert result.state.maven_verification.target_version == "1.2.4"
    assert result.state.route_decision is not None
    assert result.state.route_decision.strategy == "simple_update"
    assert result.state.remediation_plan is not None
    assert result.state.remediation_plan.strategy == "simple_update"
    assert result.state.pom_mutation_plan is not None
    assert result.state.pom_mutation_plan.changes[0].target_version == "1.2.4"
    assert result.state.preflight_resolution is not None
    assert result.state.preflight_resolution.resolved_version == "1.2.4"
    assert result.state.current_working_repo == "payments-service"
    assert len(result.state.modified_files) == 1
    assert result.state.pending_repos == []
    assert result.state.completed_repos == ["payments-service"]
    assert result.state.repo_map["payments-service"].owner == "payments-platform"
    assert config.checkpoints_path.exists()
    assert loaded_state.initial_ticket_id == "SEC-42"
    assert loaded_state.workflow_status == WorkflowStatus.COMPLETED
    assert len(result.state.targets) == 1
    assert result.state.current_target_index == 0
    assert len(loaded_state.audit_events) == 14
    assert Path(loaded_state.repo_map["payments-service"].local_path).is_dir()
    assert (
        Path(loaded_state.repo_map["payments-service"].local_path) / ".execution-accelerator-repo.json"
    ).exists()
    assert Path(loaded_state.modified_files[0]).exists()
    assert result.state.validation_results[-1].status == "passed"
    assert result.state.branch_publication is not None
    assert result.state.pull_request_summary is not None
    assert result.state.jira_completion is not None


def test_bootstrap_ticket_run_persists_transitive_override_state(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path, transitive=True)
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-420",
        repository_name="payments-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_transitive_before.xml",
    )
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-420",
        runtime_config=config,
        thread_id="sec-420-thread",
    )
    loaded_state = load_remediation_state(
        runtime_config=config,
        thread_id="sec-420-thread",
    )

    assert result.thread_id == "sec-420-thread"
    assert result.state.route_decision is not None
    assert result.state.route_decision.strategy == "transitive_override"
    assert result.state.remediation_plan is not None
    assert result.state.remediation_plan.strategy == "transitive_override"
    assert result.state.pom_mutation_plan is not None
    assert result.state.pom_mutation_plan.changes[0].target_section == "dependency_management"
    assert result.state.preflight_resolution is not None
    assert result.state.preflight_resolution.dependency_kind == "transitive"
    assert len(result.state.targets) == 1
    assert len(result.state.audit_events) == 14
    mutated_root = ET.fromstring(Path(result.state.modified_files[0]).read_text())
    version = mutated_root.find(
        ".//{http://maven.apache.org/POM/4.0.0}dependencyManagement/"
        "{http://maven.apache.org/POM/4.0.0}dependencies/"
        "{http://maven.apache.org/POM/4.0.0}dependency/"
        "{http://maven.apache.org/POM/4.0.0}version"
    )
    assert version is not None
    assert version.text == "1.2.4"
    assert loaded_state.route_decision is not None
    assert loaded_state.route_decision.strategy == "transitive_override"
    assert loaded_state.validation_results[-1].status == "passed"
    assert loaded_state.workflow_status == WorkflowStatus.COMPLETED
    assert loaded_state.completed_repos == ["payments-service"]


def test_bootstrap_ticket_run_processes_multiple_repositories(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    multi_repo_jira_path = tmp_path / "fixtures" / "jira_issue_multi.json"
    multi_repo_jira_path.parent.mkdir(parents=True, exist_ok=True)
    multi_repo_jira_path.write_text(
        json.dumps(
            {
                "ticket_id": "SEC-222",
                "summary": "Upgrade vulnerable JSON dependency",
                "description": "Two repositories require the same remediation.",
                "package_name": "org.example:legacy-json",
                "installed_version": "1.2.3",
                "fixed_version": "1.2.4",
                "severity": "high",
                "affected_repositories": [
                    {
                        "name": "payments-service",
                        "clone_url": "https://github.com/example/payments-service.git",
                        "default_branch": "main",
                        "build_system": "maven",
                        "manifest_path": "pom.xml",
                    },
                    {
                        "name": "ledger-service",
                        "clone_url": "https://github.com/example/ledger-service.git",
                        "default_branch": "main",
                        "build_system": "maven",
                        "manifest_path": "ledger-app/pom.xml",
                    },
                ],
                "references": [
                    {
                        "source": "cve",
                        "identifier": "CVE-2026-12345",
                        "url": "https://example.com/advisories/CVE-2026-12345",
                    }
                ],
            }
        )
    )
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(multi_repo_jira_path))
    monkeypatch.setattr(
        "execution_accelerator.adapters.pom.PreflightResolutionAdapter.load_result",
        lambda self, **kwargs: PreflightResolutionResult(
            repository=kwargs["repository"],
            status=ValidationStatus.PASSED,
            resolved_version="1.2.4",
            dependency_kind="direct",
            message="Preflight passed.",
        ),
    )
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-222",
        repository_name="payments-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_before.xml",
    )
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-222",
        repository_name="ledger-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_before.xml",
        manifest_path="ledger-app/pom.xml",
    )
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-222",
        runtime_config=config,
        thread_id="sec-222-thread",
    )

    assert result.state.workflow_status == WorkflowStatus.COMPLETED
    assert result.state.pending_repos == []
    assert result.state.completed_repos == ["payments-service", "ledger-service"]
    assert result.state.current_target_index == 1
    assert result.state.current_working_repo == "ledger-service"
    assert result.state.branch_publication is not None
    assert result.state.pull_request_summary is not None
    assert result.state.jira_completion is not None
    assert result.state.modified_files[0].endswith("ledger-service/ledger-app/pom.xml")


def test_bootstrap_ticket_run_captures_multi_repo_failure_context(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("EA_MAX_RETRIES", "0")
    multi_repo_jira_path = tmp_path / "fixtures" / "jira_issue_multi.json"
    multi_repo_jira_path.parent.mkdir(parents=True, exist_ok=True)
    multi_repo_jira_path.write_text(
        json.dumps(
            {
                "ticket_id": "SEC-223",
                "summary": "Upgrade vulnerable JSON dependency",
                "description": "Second repository fails validation.",
                "package_name": "org.example:legacy-json",
                "installed_version": "1.2.3",
                "fixed_version": "1.2.4",
                "severity": "high",
                "affected_repositories": [
                    {
                        "name": "payments-service",
                        "clone_url": "https://github.com/example/payments-service.git",
                        "default_branch": "main",
                        "build_system": "maven",
                        "manifest_path": "pom.xml",
                    },
                    {
                        "name": "ledger-service",
                        "clone_url": "https://github.com/example/ledger-service.git",
                        "default_branch": "main",
                        "build_system": "maven",
                        "manifest_path": "ledger-app/pom.xml",
                    },
                ],
                "references": [
                    {
                        "source": "cve",
                        "identifier": "CVE-2026-12345",
                        "url": "https://example.com/advisories/CVE-2026-12345",
                    }
                ],
            }
        )
    )
    monkeypatch.setenv("EA_JIRA_FIXTURE_PATH", str(multi_repo_jira_path))
    monkeypatch.setattr(
        "execution_accelerator.adapters.pom.PreflightResolutionAdapter.load_result",
        lambda self, **kwargs: PreflightResolutionResult(
            repository=kwargs["repository"],
            status=ValidationStatus.PASSED,
            resolved_version="1.2.4",
            dependency_kind="direct",
            message="Preflight passed.",
        ),
    )

    def fake_validation_result(self, **kwargs):
        repository = kwargs["repository"]
        if repository == "payments-service":
            return RepositoryValidationResult(
                repository=repository,
                status=ValidationStatus.PASSED,
                checks=[{"name": "compile", "status": ValidationStatus.PASSED, "details": "Compile passed."}],
                summary="Validation passed.",
            )
        return RepositoryValidationResult(
            repository=repository,
            status=ValidationStatus.FAILED,
            checks=[{"name": "unit-tests", "status": ValidationStatus.FAILED, "details": "2 tests failed."}],
            summary="Tests failed.",
        )

    def fake_rollback_plan(self, **kwargs):
        return RollbackPlan(
            repository=kwargs["repository"],
            status="applied",
            reason="Restored workspace after validation failure.",
            files_to_restore=["ledger-app/pom.xml"],
        )

    monkeypatch.setattr("execution_accelerator.adapters.validation.ValidationAdapter.load_validation_result", fake_validation_result)
    monkeypatch.setattr("execution_accelerator.adapters.validation.ValidationAdapter.load_rollback_plan", fake_rollback_plan)

    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-223",
        repository_name="payments-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_before.xml",
    )
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-223",
        repository_name="ledger-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_before.xml",
        manifest_path="ledger-app/pom.xml",
    )
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-223",
        runtime_config=config,
        thread_id="sec-223-thread",
    )

    assert result.state.workflow_status == WorkflowStatus.FAILED
    assert result.state.escalation_bundle is not None
    assert result.state.escalation_bundle.failed_repository == "ledger-service"
    assert result.state.escalation_bundle.completed_repos == ["payments-service"]
    assert result.state.escalation_bundle.pending_repos == ["ledger-service"]
    assert result.state.errors[-1].repository == "ledger-service"


def test_bootstrap_ticket_run_pauses_transitive_override_when_policy_requires_approval(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path, transitive=True)
    policy_dir = tmp_path / "config"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "policy.yaml").write_text("transitive_override_requires_human_approval: true\n")
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-421",
        repository_name="payments-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_transitive_before.xml",
    )
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-421",
        runtime_config=config,
        thread_id="sec-421-thread",
    )
    loaded_state = load_remediation_state(
        runtime_config=config,
        thread_id="sec-421-thread",
    )

    assert result.state.route_decision is not None
    assert result.state.route_decision.strategy == "transitive_override"
    assert result.state.requires_human_approval is True
    assert result.state.workflow_status == WorkflowStatus.PENDING
    assert result.state.preflight_resolution is None
    assert result.state.validation_results == []
    assert result.state.policy_decisions[-1].approval_reason == (
        "Policy requires approval for transitive_override remediation."
    )
    assert loaded_state.workflow_status == WorkflowStatus.PENDING
    assert loaded_state.policy_decisions[-1].approval_reason == (
        "Policy requires approval for transitive_override remediation."
    )


def test_resume_ticket_run_advances_transitive_override_after_policy_approval(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path, transitive=True)
    policy_dir = tmp_path / "config"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "policy.yaml").write_text("transitive_override_requires_human_approval: true\n")
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-421",
        repository_name="payments-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_transitive_before.xml",
    )
    config = load_runtime_config(repo_root=tmp_path)

    bootstrap_ticket_run(
        "SEC-421",
        runtime_config=config,
        thread_id="sec-421-thread",
    )
    result = resume_ticket_run(
        runtime_config=config,
        thread_id="sec-421-thread",
        human_feedback=HumanFeedback(
            decision=ApprovalDecision.APPROVED,
            reviewer="security-lead",
            comments="Transitive override approved.",
        ),
    )

    assert result.state.workflow_status == WorkflowStatus.COMPLETED
    assert result.state.preflight_resolution is not None
    assert result.state.validation_results[-1].status == "passed"
    assert result.state.pull_request_summary is not None

def test_bootstrap_ticket_run_persists_complex_refactor_state(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path, complex_refactor=True)
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-777",
        runtime_config=config,
        thread_id="sec-777-thread",
    )
    loaded_state = load_remediation_state(
        runtime_config=config,
        thread_id="sec-777-thread",
    )

    assert result.state.route_decision is not None
    assert result.state.route_decision.strategy == "complex_refactor"
    assert result.state.requires_human_approval is True
    assert result.state.human_feedback is None
    assert result.state.complex_remediation_plan is None
    assert result.state.preflight_resolution is None
    assert result.state.pom_mutation_plan is None
    assert result.state.validation_results == []
    assert result.state.workflow_status == WorkflowStatus.PENDING
    assert result.state.completed_repos == []
    assert result.state.pending_repos == ["payments-service"]
    assert len(result.state.targets) == 1
    assert loaded_state.requires_human_approval is True
    assert loaded_state.workflow_status == WorkflowStatus.PENDING
    assert loaded_state.pull_request_summary is None
    assert loaded_state.jira_completion is None


def test_resume_ticket_run_advances_complex_refactor_after_approval(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path, complex_refactor=True)
    config = load_runtime_config(repo_root=tmp_path)

    bootstrap_ticket_run(
        "SEC-777",
        runtime_config=config,
        thread_id="sec-777-thread",
    )
    result = resume_ticket_run(
        runtime_config=config,
        thread_id="sec-777-thread",
        human_feedback=HumanFeedback(
            decision=ApprovalDecision.APPROVED,
            reviewer="security-lead",
            comments="Approved for automation.",
        ),
    )
    loaded_state = load_remediation_state(
        runtime_config=config,
        thread_id="sec-777-thread",
    )

    assert result.state.route_decision is not None
    assert result.state.route_decision.strategy == "complex_refactor"
    assert result.state.remediation_plan is not None
    assert result.state.remediation_plan.strategy == "complex_refactor"
    assert result.state.complex_remediation_plan is not None
    assert len(result.state.complex_remediation_plan.artifact_candidates) == 2
    assert result.state.complex_remediation_plan.migration_tactic == "adapter_shim"
    assert len(result.state.complex_remediation_plan.migration_steps) == 2
    assert result.state.complex_remediation_plan.target_files[0].file_path.endswith("LegacyJsonAdapter.java")
    assert result.state.complex_remediation_plan.symbol_mappings[0].legacy_symbol == "org.example.LegacyParser#parse"
    assert result.state.complex_remediation_plan.open_questions[0].startswith("Should adapter construction")
    assert len(result.state.modified_files) == 2
    assert result.state.code_diffs[0].file_path.endswith("LegacyJsonAdapter.java")
    assert result.state.compatibility_diff is not None
    assert result.state.compatibility_diff.risk == "high"
    assert len(result.state.decompiled_artifacts) == 2
    assert len(result.state.symbol_mappings) == 2
    assert result.state.code_change_plan is not None
    assert len(result.state.code_change_plan.target_files) == 2
    assert result.state.preflight_resolution is None
    assert result.state.pom_mutation_plan is None
    assert len(result.state.validation_results) == 1
    assert result.state.validation_results[-1].status == "passed"
    assert result.state.remediation_plan is not None
    assert result.state.remediation_plan.summary.endswith("Executed bounded complex migration edits for 2 files.")
    assert result.state.workflow_status == WorkflowStatus.COMPLETED
    assert result.state.completed_repos == ["payments-service"]
    assert result.state.pending_repos == []
    assert len(result.state.targets) == 1
    assert loaded_state.complex_remediation_plan is not None
    assert loaded_state.complex_remediation_plan.compatibility_diff.target_version == "2.0.0"
    assert loaded_state.complex_remediation_plan.migration_tactic == "adapter_shim"
    assert len(loaded_state.complex_remediation_plan.migration_steps) == 2
    assert loaded_state.complex_remediation_plan.target_files[0].file_path.endswith("LegacyJsonAdapter.java")
    assert loaded_state.complex_remediation_plan.symbol_mappings[0].legacy_symbol == "org.example.LegacyParser#parse"
    assert loaded_state.complex_remediation_plan.open_questions[0].startswith("Should adapter construction")
    assert len(loaded_state.modified_files) == 2
    assert loaded_state.remediation_plan is not None
    assert loaded_state.remediation_plan.summary.endswith("Executed bounded complex migration edits for 2 files.")
    assert loaded_state.code_change_plan is not None
    assert loaded_state.code_change_plan.target_files[0].file_path.endswith("LegacyJsonAdapter.java")
    assert loaded_state.workflow_status == WorkflowStatus.COMPLETED
    assert loaded_state.pull_request_summary is not None
    assert loaded_state.jira_completion is not None


def test_resume_ticket_run_pauses_complex_refactor_for_delivery_approval(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path, complex_refactor=True)
    policy_dir = tmp_path / "config"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "policy.yaml").write_text(
        "\n".join(
            [
                "draft_pr_only: true",
                "complex_refactor_requires_human_approval: true",
                "complex_refactor_requires_delivery_approval: true",
                "blocked_tags: []",
            ]
        )
        + "\n"
    )
    config = load_runtime_config(repo_root=tmp_path)

    bootstrap_ticket_run(
        "SEC-778",
        runtime_config=config,
        thread_id="sec-778-thread",
    )
    result = resume_ticket_run(
        runtime_config=config,
        thread_id="sec-778-thread",
        human_feedback=HumanFeedback(
            decision=ApprovalDecision.APPROVED,
            reviewer="security-lead",
            comments="Approved for remediation.",
        ),
    )
    loaded_state = load_remediation_state(
        runtime_config=config,
        thread_id="sec-778-thread",
    )

    assert result.state.workflow_status == WorkflowStatus.PENDING
    assert result.state.pending_approval_stage == "delivery"
    assert result.state.pending_approval_reason == (
        "Policy requires approval before publishing complex remediation results."
    )
    assert len(result.state.validation_results) == 1
    assert result.state.validation_results[-1].status == "passed"
    assert result.state.pull_request_summary is None
    assert loaded_state.pending_approval_stage == "delivery"
    assert loaded_state.pull_request_summary is None


def test_resume_ticket_run_completes_delivery_after_second_approval(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path, complex_refactor=True)
    policy_dir = tmp_path / "config"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "policy.yaml").write_text(
        "\n".join(
            [
                "draft_pr_only: true",
                "complex_refactor_requires_human_approval: true",
                "complex_refactor_requires_delivery_approval: true",
                "blocked_tags: []",
            ]
        )
        + "\n"
    )
    config = load_runtime_config(repo_root=tmp_path)

    bootstrap_ticket_run(
        "SEC-778",
        runtime_config=config,
        thread_id="sec-778-thread",
    )
    resume_ticket_run(
        runtime_config=config,
        thread_id="sec-778-thread",
        human_feedback=HumanFeedback(
            decision=ApprovalDecision.APPROVED,
            reviewer="security-lead",
            comments="Approved for remediation.",
        ),
    )
    result = resume_ticket_run(
        runtime_config=config,
        thread_id="sec-778-thread",
        human_feedback=HumanFeedback(
            decision=ApprovalDecision.APPROVED,
            reviewer="release-manager",
            comments="Approved for publication.",
        ),
    )

    assert result.state.workflow_status == WorkflowStatus.COMPLETED
    assert result.state.pull_request_summary is not None
    assert result.state.jira_completion is not None
    assert result.state.pending_approval_stage is None
    assert len(result.state.approval_history) == 2


def test_bootstrap_ticket_run_records_failure_and_rollback_state(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "EA_VALIDATION_RESULT_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "validation_result_failure.json"),
    )
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-500",
        repository_name="payments-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_before.xml",
    )
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-500",
        runtime_config=config,
        thread_id="sec-500-thread",
    )
    loaded_state = load_remediation_state(
        runtime_config=config,
        thread_id="sec-500-thread",
    )

    assert result.state.workflow_status == WorkflowStatus.FAILED
    assert result.state.validation_results[-1].status == "failed"
    assert result.state.rollback_plan is not None
    assert result.state.rollback_plan.status == "applied"
    assert result.state.escalation_bundle is not None
    assert result.state.total_attempts == 1
    assert result.state.retry_count == 0
    assert result.state.retry_decision is not None
    assert result.state.retry_decision.next_node == "escalate"
    assert result.state.failure_classifications[-1] == "compile_error"
    assert result.state.errors[-1].code == "validation_compile_failed"
    assert len(result.state.targets) == 1
    assert len(result.state.audit_events) == 16
    assert Path(result.state.escalation_bundle.bundle_path).exists()
    assert loaded_state.escalation_bundle is not None
    assert loaded_state.escalation_bundle.bundle_path == result.state.escalation_bundle.bundle_path


def test_bootstrap_ticket_run_retries_once_before_escalating(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("EA_MAX_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv(
        "EA_VALIDATION_RESULT_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "validation_result_test_failure.json"),
    )
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-501",
        repository_name="payments-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_before.xml",
    )
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-501",
        runtime_config=config,
        thread_id="sec-501-thread",
    )

    assert result.state.workflow_status == WorkflowStatus.FAILED
    assert result.state.retry_count == 1
    assert result.state.retry_decision is not None
    assert result.state.retry_decision.next_node == "escalate"
    assert result.state.total_attempts == 2
    assert len(result.state.validation_results) == 2
    assert result.state.failure_classifications == ["test_failure", "test_failure"]
    assert result.state.escalation_bundle is not None


def test_bootstrap_ticket_run_retries_transient_validation_failure_before_escalating(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("EA_MAX_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv(
        "EA_VALIDATION_RESULT_FIXTURE_PATH",
        str(Path(__file__).parent / "fixtures" / "validation_result_transient_failure.json"),
    )
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-502",
        repository_name="payments-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_before.xml",
    )
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-502",
        runtime_config=config,
        thread_id="sec-502-thread",
    )

    assert result.state.workflow_status == WorkflowStatus.FAILED
    assert result.state.retry_count == 1
    assert result.state.retry_decision is not None
    assert result.state.retry_decision.next_node == "escalate"
    assert result.state.total_attempts == 2
    assert len(result.state.validation_results) == 2
    assert result.state.failure_classifications == ["network_transient", "network_transient"]
    assert result.state.escalation_bundle is not None


def test_bootstrap_ticket_run_retries_transient_delivery_failure_before_succeeding(tmp_path, monkeypatch) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("EA_MAX_RETRY_ATTEMPTS", "1")
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-503",
        repository_name="payments-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_before.xml",
    )
    attempts = {"jira_completion": 0}
    original_load_jira_completion = DeliveryAdapter.load_jira_completion

    def flaky_jira_completion(self, **kwargs):
        attempts["jira_completion"] += 1
        if attempts["jira_completion"] == 1:
            raise __import__("httpx").ConnectError("jira gateway timeout")
        return original_load_jira_completion(self, **kwargs)

    monkeypatch.setattr(DeliveryAdapter, "load_jira_completion", flaky_jira_completion)
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-503",
        runtime_config=config,
        thread_id="sec-503-thread",
    )

    assert result.state.workflow_status == WorkflowStatus.COMPLETED
    assert result.state.retry_count == 1
    assert result.state.total_attempts == 1
    assert result.state.failure_classifications == []
    assert result.state.errors == []
    assert result.state.retry_decision is None
    assert result.state.branch_publication is not None
    assert result.state.pull_request_summary is not None
    assert result.state.jira_completion is not None
    assert attempts["jira_completion"] == 2


def test_bootstrap_ticket_run_escalates_transient_delivery_failure_with_partial_delivery_context(
    tmp_path, monkeypatch
) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("EA_MAX_RETRY_ATTEMPTS", "1")
    seed_bootstrap_workspace_pom(
        tmp_path / "workspace",
        ticket_id="SEC-504",
        repository_name="payments-service",
        fixture_path=Path(__file__).parent / "fixtures" / "pom_before.xml",
    )

    def broken_jira_completion(self, **kwargs):
        raise __import__("httpx").ConnectError("jira gateway timeout")

    monkeypatch.setattr(DeliveryAdapter, "load_jira_completion", broken_jira_completion)
    config = load_runtime_config(repo_root=tmp_path)

    result = bootstrap_ticket_run(
        "SEC-504",
        runtime_config=config,
        thread_id="sec-504-thread",
    )

    assert result.state.workflow_status == WorkflowStatus.FAILED
    assert result.state.retry_count == 1
    assert result.state.total_attempts == 2
    assert result.state.failure_classifications == ["network_transient", "network_transient"]
    assert result.state.branch_publication is not None
    assert result.state.pull_request_summary is not None
    assert result.state.jira_completion is None
    assert result.state.escalation_bundle is not None
    assert result.state.escalation_bundle.branch_publication is not None
    assert result.state.escalation_bundle.pull_request_summary is not None
    assert result.state.escalation_bundle.jira_completion is None
    assert result.state.escalation_bundle.branch_publication.branch_name == result.state.branch_publication.branch_name
    assert result.state.escalation_bundle.pull_request_summary.number == result.state.pull_request_summary.number


def test_live_flow_runs_through_delivery_with_live_integrations(tmp_path, monkeypatch) -> None:
    fixtures_dir = Path(__file__).parent / "fixtures"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    remote_repo = create_live_remote_repo(
        tmp_path / "origin-repo",
        pom_text=(
            "<project xmlns=\"http://maven.apache.org/POM/4.0.0\">"
            "<modelVersion>4.0.0</modelVersion>"
            "<groupId>org.example</groupId><artifactId>payments-service</artifactId><version>1.0.0</version>"
            "<dependencies><dependency><groupId>org.example</groupId><artifactId>legacy-json</artifactId>"
            "<version>1.2.3</version></dependency></dependencies>"
            "</project>"
        ),
        dependency_tree_output=(
            "[INFO] org.example:payments-service:jar:1.0.0\n"
            "[INFO] +- org.example:legacy-json:jar:1.2.3:compile\n"
        ),
        dynamic_legacy_json_version=True,
        surefire_report_xml='<testsuite name="demo" tests="2" failures="0" errors="0" skipped="0" />',
        simulate_openrewrite=True,
    )
    (config_dir / "jira.yaml").write_text("project_key: SEC\n")
    (config_dir / "repositories.yaml").write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "name": "payments-service",
                        "clone_url": str(remote_repo),
                        "default_branch": "main",
                        "build_system": "maven",
                        "manifest_path": "pom.xml",
                        "owner": "payments-platform",
                    }
                ]
            }
        )
    )
    monkeypatch.setenv("EA_MODE", "live")
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv("EA_DRY_RUN", "0")
    monkeypatch.setenv("EA_KEEP_WORKSPACE", "1")
    monkeypatch.setenv("EA_JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_JIRA_TOKEN", "jira-token")
    monkeypatch.setenv("EA_JIRA_PROBE_TICKET", "SEC-900")
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("GITHUB_OWNER", "payments-platform")
    monkeypatch.setenv("EA_GIT_USER_NAME", "Execution Bot")
    monkeypatch.setenv("EA_GIT_USER_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_POM_FIXTURE_BEFORE_PATH", str(fixtures_dir / "pom_before.xml"))
    monkeypatch.setenv("EA_POM_FIXTURE_AFTER_PATH", str(fixtures_dir / "pom_after.xml"))
    monkeypatch.setenv("EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH", str(fixtures_dir / "preflight_resolution.json"))
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixtures_dir / "validation_result.json"))
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixtures_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixtures_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixtures_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixtures_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixtures_dir / "code_change_plan.json"))
    monkeypatch.setenv("EA_ROLLBACK_FIXTURE_PATH", str(fixtures_dir / "rollback_plan.json"))

    issue_response = {
        "key": "SEC-900",
        "fields": {
            "summary": "Upgrade legacy-json",
            "description": (
                "Package: org.example:legacy-json\n"
                "Installed Version: 1.2.3\n"
                "Fixed Version: 1.2.4\n"
                "Severity: high\n"
                "Repository: payments-service\n"
                "CVE: CVE-2026-12345\n"
            ),
        },
    }
    osv_response = {
        "vulns": [
            {
                "id": "OSV-2026-1",
                "summary": "legacy-json vulnerable before 1.2.4",
                "aliases": ["CVE-2026-12345"],
                "database_specific": {"severity": "high"},
                "affected": [
                    {
                        "package": {"name": "org.example:legacy-json", "ecosystem": "Maven"},
                        "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "1.2.4"}]}],
                    }
                ],
            }
        ]
    }
    with serve_routes(
        {
            ("GET", "/rest/api/3/myself"): ResponseSpec(status=200, body=b"{}"),
            ("GET", "/rest/api/3/issue/SEC-900/transitions"): ResponseSpec(status=200, body=b'{"transitions": []}'),
            ("GET", "/user"): ResponseSpec(status=200, body=b"{}"),
            (
                "GET",
                "/repos/payments-platform/payments-service",
            ): ResponseSpec(status=200, body=b'{"permissions": {"push": true}}'),
            ("GET", "/rest/api/3/issue/SEC-900"): ResponseSpec(status=200, body=json.dumps(issue_response).encode()),
            ("GET", "/search/issues"): ResponseSpec(
                status=200,
                body=b'{\"items\": []}',
            ),
            ("POST", "/v1/query"): ResponseSpec(status=200, body=json.dumps(osv_response).encode()),
            (
                "GET",
                "/org/example/legacy-json/maven-metadata.xml",
            ): ResponseSpec(
                status=200,
                body=(
                    "<metadata><groupId>org.example</groupId><artifactId>legacy-json</artifactId>"
                    "<versioning><latest>1.2.4</latest><release>1.2.4</release>"
                    "<versions><version>1.2.3</version><version>1.2.4</version></versions>"
                    "</versioning></metadata>"
                ).encode(),
                content_type="application/xml",
            ),
            (
                "POST",
                "/repos/payments-platform/payments-service/pulls",
            ): ResponseSpec(
                status=201,
                body=(
                    b'{"number": 42, "html_url": "https://example.test/pr/42", '
                    b'"title": "SEC-900: remediate org.example:legacy-json", "state": "open"}'
                ),
            ),
            ("POST", "/rest/api/3/issue/SEC-900/comment"): ResponseSpec(status=201, body=b'{"id":"10001"}'),
        }
    ) as base_url:
        monkeypatch.setenv("EA_JIRA_BASE_URL", base_url)
        monkeypatch.setenv("EA_GITHUB_API_BASE", base_url)
        monkeypatch.setenv("EA_OSV_API_BASE", base_url)
        monkeypatch.setenv("EA_MAVEN_METADATA_BASE", base_url)
        config = load_runtime_config(repo_root=tmp_path)
        graph = compile_remediation_graph(
            runtime_config=config,
            jira_adapter=JiraAdapter.from_runtime_config(config),
            repository_inventory_adapter=RepositoryInventoryAdapter.from_runtime_config(config),
            advisory_verification_adapter=AdvisoryVerificationAdapter.from_runtime_config(config),
            maven_verification_adapter=MavenVerificationAdapter.from_runtime_config(config),
            complex_remediation_adapter=ComplexRemediationAdapter.from_runtime_config(config),
            pom_mutation_adapter=PomMutationAdapter.from_runtime_config(config),
            preflight_resolution_adapter=PreflightResolutionAdapter.from_runtime_config(config),
            validation_adapter=ValidationAdapter.from_runtime_config(config),
            delivery_adapter=DeliveryAdapter.from_runtime_config(config),
            checkpointer=None,
        )

        result = graph.invoke(
            {"initial_ticket_id": "SEC-900"},
            config=build_thread_config("live-sec-900"),
        )

    assert result["workflow_status"] == WorkflowStatus.COMPLETED
    assert result["advisory_verification"].source == "osv"
    assert result["maven_verification"].dependency_kind == "direct"
    assert result["maven_plan"].uses_wrapper is True
    assert result["validation_results"][-1].status == "passed"
    assert result["branch_publication"].branch_name == "sec-900-remediate-org-example-legacy-json"
    assert result["pull_request_summary"].number == 42
    assert result["jira_completion"].status == "commented"


def test_live_flow_runs_through_rollback_after_validation_failure(tmp_path, monkeypatch) -> None:
    fixtures_dir = Path(__file__).parent / "fixtures"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    repo_path = create_live_repo(
        tmp_path / "origin-repo",
        pom_text=(
            "<project xmlns=\"http://maven.apache.org/POM/4.0.0\">"
            "<modelVersion>4.0.0</modelVersion>"
            "<groupId>org.example</groupId><artifactId>payments-service</artifactId><version>1.0.0</version>"
            "<dependencies><dependency><groupId>org.example</groupId><artifactId>legacy-json</artifactId>"
            "<version>1.2.3</version></dependency></dependencies>"
            "</project>"
        ),
        dependency_tree_output=(
            "[INFO] org.example:payments-service:jar:1.0.0\n"
            "[INFO] +- org.example:legacy-json:jar:1.2.3:compile\n"
        ),
        dynamic_legacy_json_version=True,
        verify_exit_code=1,
        simulate_openrewrite=True,
    )
    (config_dir / "jira.yaml").write_text("project_key: SEC\n")
    (config_dir / "repositories.yaml").write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "name": "payments-service",
                        "clone_url": str(repo_path),
                        "default_branch": "main",
                        "build_system": "maven",
                        "manifest_path": "pom.xml",
                        "owner": "payments-platform",
                    }
                ]
            }
        )
    )
    monkeypatch.setenv("EA_MODE", "live")
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EA_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("EA_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("EA_CHECKPOINTS_PATH", str(tmp_path / "state" / "checkpoints.sqlite"))
    monkeypatch.setenv("EA_DRY_RUN", "0")
    monkeypatch.setenv("EA_KEEP_WORKSPACE", "1")
    monkeypatch.setenv("EA_JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_JIRA_TOKEN", "jira-token")
    monkeypatch.setenv("EA_JIRA_PROBE_TICKET", "SEC-901")
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("GITHUB_OWNER", "payments-platform")
    monkeypatch.setenv("EA_GIT_USER_NAME", "Execution Bot")
    monkeypatch.setenv("EA_GIT_USER_EMAIL", "bot@example.com")
    monkeypatch.setenv("EA_POM_FIXTURE_BEFORE_PATH", str(fixtures_dir / "pom_before.xml"))
    monkeypatch.setenv("EA_POM_FIXTURE_AFTER_PATH", str(fixtures_dir / "pom_after.xml"))
    monkeypatch.setenv("EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH", str(fixtures_dir / "preflight_resolution.json"))
    monkeypatch.setenv("EA_VALIDATION_RESULT_FIXTURE_PATH", str(fixtures_dir / "validation_result.json"))
    monkeypatch.setenv("EA_COMPLEX_ARTIFACT_FIXTURE_PATH", str(fixtures_dir / "complex_artifacts.json"))
    monkeypatch.setenv("EA_COMPATIBILITY_DIFF_FIXTURE_PATH", str(fixtures_dir / "compatibility_diff.json"))
    monkeypatch.setenv("EA_DECOMPILED_ARTIFACT_FIXTURE_PATH", str(fixtures_dir / "decompiled_artifacts.json"))
    monkeypatch.setenv("EA_SYMBOL_MAPPING_FIXTURE_PATH", str(fixtures_dir / "symbol_mappings.json"))
    monkeypatch.setenv("EA_CODE_CHANGE_PLAN_FIXTURE_PATH", str(fixtures_dir / "code_change_plan.json"))

    issue_response = {
        "key": "SEC-901",
        "fields": {
            "summary": "Upgrade legacy-json",
            "description": (
                "Package: org.example:legacy-json\n"
                "Installed Version: 1.2.3\n"
                "Fixed Version: 1.2.4\n"
                "Severity: high\n"
                "Repository: payments-service\n"
                "CVE: CVE-2026-12345\n"
            ),
        },
    }
    osv_response = {
        "vulns": [
            {
                "id": "OSV-2026-1",
                "summary": "legacy-json vulnerable before 1.2.4",
                "aliases": ["CVE-2026-12345"],
                "database_specific": {"severity": "high"},
                "affected": [
                    {
                        "package": {"name": "org.example:legacy-json", "ecosystem": "Maven"},
                        "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "1.2.4"}]}],
                    }
                ],
            }
        ]
    }
    with serve_routes(
        {
            ("GET", "/rest/api/3/myself"): ResponseSpec(status=200, body=b"{}"),
            ("GET", "/rest/api/3/issue/SEC-901/transitions"): ResponseSpec(status=200, body=b'{"transitions": []}'),
            ("GET", "/user"): ResponseSpec(status=200, body=b"{}"),
            (
                "GET",
                "/repos/payments-platform/payments-service",
            ): ResponseSpec(status=200, body=b'{"permissions": {"push": true}}'),
            ("GET", "/rest/api/3/issue/SEC-901"): ResponseSpec(status=200, body=json.dumps(issue_response).encode()),
            ("GET", "/search/issues"): ResponseSpec(status=200, body=b'{\"items\": []}'),
            ("POST", "/v1/query"): ResponseSpec(status=200, body=json.dumps(osv_response).encode()),
            (
                "GET",
                "/org/example/legacy-json/maven-metadata.xml",
            ): ResponseSpec(
                status=200,
                body=(
                    "<metadata><groupId>org.example</groupId><artifactId>legacy-json</artifactId>"
                    "<versioning><latest>1.2.4</latest><release>1.2.4</release>"
                    "<versions><version>1.2.3</version><version>1.2.4</version></versions>"
                    "</versioning></metadata>"
                ).encode(),
                content_type="application/xml",
            ),
        }
    ) as base_url:
        monkeypatch.setenv("EA_JIRA_BASE_URL", base_url)
        monkeypatch.setenv("EA_GITHUB_API_BASE", base_url)
        monkeypatch.setenv("EA_OSV_API_BASE", base_url)
        monkeypatch.setenv("EA_MAVEN_METADATA_BASE", base_url)
        config = load_runtime_config(repo_root=tmp_path)
        graph = compile_remediation_graph(
            runtime_config=config,
            jira_adapter=JiraAdapter.from_runtime_config(config),
            repository_inventory_adapter=RepositoryInventoryAdapter.from_runtime_config(config),
            advisory_verification_adapter=AdvisoryVerificationAdapter.from_runtime_config(config),
            maven_verification_adapter=MavenVerificationAdapter.from_runtime_config(config),
            complex_remediation_adapter=ComplexRemediationAdapter.from_runtime_config(config),
            pom_mutation_adapter=PomMutationAdapter.from_runtime_config(config),
            preflight_resolution_adapter=PreflightResolutionAdapter.from_runtime_config(config),
            validation_adapter=ValidationAdapter.from_runtime_config(config),
            delivery_adapter=DeliveryAdapter.from_runtime_config(config),
            checkpointer=None,
        )

        result = graph.invoke(
            {"initial_ticket_id": "SEC-901"},
            config=build_thread_config("live-sec-901"),
        )

    assert result["workflow_status"] == WorkflowStatus.FAILED
    assert result["rollback_plan"].status == "applied"
    assert Path(result["modified_files"][0]).read_text().count("1.2.3") == 1
    assert result.get("pull_request_summary") is None
