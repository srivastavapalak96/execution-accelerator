from __future__ import annotations

import json
from pathlib import Path

from execution_accelerator.config import load_runtime_config
from execution_accelerator.nodes import classify_failure, escalate
from execution_accelerator.schemas import FailureClassification, RemediationStrategy, ValidationCheck, ValidationStatus
from execution_accelerator.state import RemediationState


def test_classify_failure_records_total_attempts() -> None:
    state = RemediationState(
        initial_ticket_id="SEC-123",
        validation_results=[
            {
                "repository": "payments-service",
                "status": ValidationStatus.FAILED,
                "checks": [
                    ValidationCheck(name="compile", status=ValidationStatus.FAILED, details="Compilation failed.")
                ],
                "summary": "Compile failed.",
            }
        ],
    )

    update = classify_failure(state)

    assert update["total_attempts"] == 1
    assert update["failure_classifications"][-1] == FailureClassification.COMPILE_ERROR
    assert update["audit_events"][-1].event_type == "failure.classify"


def test_classify_failure_schedules_retry_for_recoverable_simple_update(monkeypatch) -> None:
    monkeypatch.setenv("EA_MAX_RETRY_ATTEMPTS", "1")
    state = RemediationState(
        initial_ticket_id="SEC-123",
        route_decision={"strategy": RemediationStrategy.SIMPLE_UPDATE, "confidence": 0.93, "reason": "Direct fix."},
        errors=[{"code": "validation_failed", "message": "Compile failed.", "recoverable": True}],
        validation_results=[
            {
                "repository": "payments-service",
                "status": ValidationStatus.FAILED,
                "checks": [
                    ValidationCheck(name="compile", status=ValidationStatus.PASSED, details="Compile passed."),
                    ValidationCheck(name="unit-tests", status=ValidationStatus.FAILED, details="Tests failed."),
                ],
                "summary": "Tests failed.",
            }
        ],
    )

    update = classify_failure(state)

    assert update["retry_count"] == 1
    assert update["retry_decision"].next_node == "remediate_simple"
    assert update["workflow_status"] == "in_progress"


def test_classify_failure_clears_attempt_scoped_state_before_retry(monkeypatch) -> None:
    monkeypatch.setenv("EA_MAX_RETRY_ATTEMPTS", "1")
    state = RemediationState(
        initial_ticket_id="SEC-123",
        route_decision={"strategy": RemediationStrategy.SIMPLE_UPDATE, "confidence": 0.93, "reason": "Direct fix."},
        errors=[{"code": "validation_test_failed", "message": "Tests failed.", "recoverable": True}],
        modified_files=["/tmp/workspace/pom.xml"],
        code_diffs=[
            {
                "file_path": "pom.xml",
                "change_summary": "Bump legacy-json to 1.2.4.",
                "additions": 1,
                "deletions": 1,
            }
        ],
        preflight_resolution={
            "repository": "payments-service",
            "status": "passed",
            "resolved_version": "1.2.4",
            "dependency_kind": "direct",
            "message": "Preflight passed.",
        },
        rollback_plan={
            "repository": "payments-service",
            "status": "applied",
            "reason": "Restored pom.xml",
            "files_to_restore": ["pom.xml"],
        },
        validation_results=[
            {
                "repository": "payments-service",
                "status": ValidationStatus.FAILED,
                "checks": [
                    ValidationCheck(name="compile", status=ValidationStatus.PASSED, details="Compile passed."),
                    ValidationCheck(name="unit-tests", status=ValidationStatus.FAILED, details="Tests failed."),
                ],
                "summary": "Tests failed.",
            }
        ],
    )

    update = classify_failure(state)

    assert update["retry_decision"].next_node == "remediate_simple"
    assert update["rollback_plan"] is None
    assert update["modified_files"] == []
    assert update["code_diffs"] == []
    assert update["preflight_resolution"] is None


def test_classify_failure_escalates_compile_failure_even_with_retry_budget(monkeypatch) -> None:
    monkeypatch.setenv("EA_MAX_RETRY_ATTEMPTS", "2")
    state = RemediationState(
        initial_ticket_id="SEC-124",
        route_decision={"strategy": RemediationStrategy.SIMPLE_UPDATE, "confidence": 0.93, "reason": "Direct fix."},
        errors=[{"code": "validation_failed", "message": "Compile failed.", "recoverable": True}],
        validation_results=[
            {
                "repository": "payments-service",
                "status": ValidationStatus.FAILED,
                "checks": [
                    ValidationCheck(name="compile", status=ValidationStatus.FAILED, details="Compilation failed.")
                ],
                "summary": "Compile failed.",
            }
        ],
    )

    update = classify_failure(state)

    assert update["retry_count"] == 0
    assert update["retry_decision"].next_node == "escalate"
    assert update["workflow_status"] == "failed"


def test_classify_failure_identifies_unresolved_security_scan_as_recipe_noop() -> None:
    state = RemediationState(
        initial_ticket_id="SEC-125",
        route_decision={"strategy": RemediationStrategy.SIMPLE_UPDATE, "confidence": 0.93, "reason": "Direct fix."},
        errors=[{"code": "validation_failed", "message": "Security scan failed.", "recoverable": False}],
        validation_results=[
            {
                "repository": "payments-service",
                "status": ValidationStatus.FAILED,
                "checks": [
                    ValidationCheck(name="compile", status=ValidationStatus.PASSED, details="Compilation passed."),
                    ValidationCheck(
                        name="security-scan",
                        status=ValidationStatus.FAILED,
                        details="org.example:legacy-json still resolves versions 1.2.3; expected only 1.2.4.",
                    ),
                ],
                "summary": "Live validation detected an unresolved vulnerable dependency.",
            }
        ],
    )

    update = classify_failure(state)

    assert update["failure_classifications"][-1] == FailureClassification.RECIPE_NOOP
    assert update["retry_decision"].next_node == "escalate"
    assert update["retry_decision"].reason == "recipe_noop failures are not automatically retried."


def test_classify_failure_identifies_license_scan_failure_as_license_violation() -> None:
    state = RemediationState(
        initial_ticket_id="SEC-126",
        route_decision={"strategy": RemediationStrategy.SIMPLE_UPDATE, "confidence": 0.93, "reason": "Direct fix."},
        errors=[{"code": "validation_license_failed", "message": "License scan failed.", "recoverable": False}],
        validation_results=[
            {
                "repository": "payments-service",
                "status": ValidationStatus.FAILED,
                "checks": [
                    ValidationCheck(name="compile", status=ValidationStatus.PASSED, details="Compilation passed."),
                    ValidationCheck(
                        name="license-scan",
                        status=ValidationStatus.FAILED,
                        details="Disallowed dependency licenses detected for 1 dependencies against denylist [GPL].",
                    ),
                ],
                "summary": "Live validation detected a disallowed or unverifiable dependency license.",
            }
        ],
    )

    update = classify_failure(state)

    assert update["failure_classifications"][-1] == FailureClassification.LICENSE_VIOLATION
    assert update["retry_decision"].next_node == "escalate"
    assert update["retry_decision"].reason == "license_violation failures are not automatically retried."


def test_classify_failure_retries_transient_validation_failures(monkeypatch) -> None:
    monkeypatch.setenv("EA_MAX_RETRY_ATTEMPTS", "1")
    state = RemediationState(
        initial_ticket_id="SEC-126A",
        route_decision={"strategy": RemediationStrategy.SIMPLE_UPDATE, "confidence": 0.93, "reason": "Direct fix."},
        errors=[
            {
                "code": "validation_transient_failed",
                "message": "Live validation could not inspect the remediated dependency tree.",
                "recoverable": True,
            }
        ],
        validation_results=[
            {
                "repository": "payments-service",
                "status": ValidationStatus.FAILED,
                "checks": [
                    ValidationCheck(name="compile", status=ValidationStatus.PASSED, details="Compilation passed."),
                    ValidationCheck(
                        name="security-scan",
                        status=ValidationStatus.FAILED,
                        details=(
                            "Live security rescan could not inspect the Maven dependency tree: "
                            "Timed out fetching dependency metadata from the repository mirror."
                        ),
                    ),
                ],
                "summary": "Live validation could not inspect the remediated dependency tree.",
            }
        ],
    )

    update = classify_failure(state)

    assert update["failure_classifications"][-1] == FailureClassification.NETWORK_TRANSIENT
    assert update["retry_count"] == 1
    assert update["retry_decision"].next_node == "remediate_simple"
    assert (
        update["retry_decision"].reason
        == "Retryable transient validation failure will rerun the active remediation lane."
    )


def test_escalate_records_terminal_audit_event() -> None:
    state = RemediationState(
        initial_ticket_id="SEC-123",
        total_attempts=1,
        failure_classifications=[FailureClassification.UNKNOWN],
    )

    update = escalate(state)

    assert update["workflow_status"] == "failed"
    assert update["audit_events"][-1].event_type == "failure.escalate"


def test_escalate_node_writes_bundle(tmp_path: Path) -> None:
    config = load_runtime_config(repo_root=tmp_path)
    node = __import__("execution_accelerator.nodes", fromlist=["build_escalate_node"]).build_escalate_node(config)
    state = RemediationState(
        initial_ticket_id="SEC-123",
        total_attempts=1,
        failure_classifications=[FailureClassification.COMPILE_ERROR],
        route_decision={"strategy": RemediationStrategy.SIMPLE_UPDATE, "confidence": 0.93, "reason": "Direct fix."},
        approval_history=[
            {
                "stage": "remediation",
                "decision": "approved",
                "reviewer": "security-lead",
                "comments": "Approved after compile-risk review.",
            }
        ],
        modified_files=["/tmp/workspace/pom.xml"],
        errors=[{"code": "validation_failed", "message": "Compile failed.", "recoverable": False}],
        validation_results=[
            {
                "repository": "payments-service",
                "status": ValidationStatus.FAILED,
                "checks": [
                    {
                        "name": "compile",
                        "status": ValidationStatus.FAILED,
                        "details": "Compilation failed.",
                    }
                ],
                "summary": "Compile failed.",
            }
        ],
    )

    update = node(state)

    assert update["workflow_status"] == "failed"
    bundle_path = Path(update["escalation_bundle"].bundle_path)
    assert bundle_path.exists()
    assert update["audit_events"][-1].details["bundle_path"] == str(bundle_path)
    payload = json.loads(bundle_path.read_text())
    assert update["escalation_bundle"].route_strategy == RemediationStrategy.SIMPLE_UPDATE
    assert update["escalation_bundle"].route_reason == "Direct fix."
    assert update["escalation_bundle"].approval_stage == "remediation"
    assert update["escalation_bundle"].approval_reviewer == "security-lead"
    assert update["escalation_bundle"].approval_comments == "Approved after compile-risk review."
    assert update["escalation_bundle"].validation_status == ValidationStatus.FAILED
    assert update["escalation_bundle"].primary_validation_check == "compile"
    assert update["escalation_bundle"].failed_repository is None
    assert update["escalation_bundle"].pending_repos == []
    assert update["escalation_bundle"].completed_repos == []
    assert update["escalation_bundle"].skipped_repos == []
    assert payload["route_strategy"] == RemediationStrategy.SIMPLE_UPDATE
    assert payload["route_reason"] == "Direct fix."
    assert payload["approval_stage"] == "remediation"
    assert payload["approval_reviewer"] == "security-lead"
    assert payload["approval_comments"] == "Approved after compile-risk review."
    assert payload["validation_summary"] == "Compile failed."
    assert payload["primary_validation_check_status"] == ValidationStatus.FAILED
    assert payload["failed_repository"] is None
    assert payload["pending_repos"] == []
    assert payload["completed_repos"] == []
    assert payload["skipped_repos"] == []


def test_escalate_node_persists_complex_plan_context(tmp_path: Path) -> None:
    config = load_runtime_config(repo_root=tmp_path)
    node = __import__("execution_accelerator.nodes", fromlist=["build_escalate_node"]).build_escalate_node(config)
    state = RemediationState(
        initial_ticket_id="SEC-777",
        total_attempts=2,
        failure_classifications=[FailureClassification.TEST_FAILURE],
        route_decision={"strategy": RemediationStrategy.COMPLEX_REFACTOR, "confidence": 0.78, "reason": "Breaking API changes."},
        approval_history=[
            {
                "stage": "delivery",
                "decision": "approved",
                "reviewer": "release-manager",
                "comments": "Approved for publication once validation is green.",
            }
        ],
        errors=[{"code": "validation_failed", "message": "Tests failed.", "recoverable": False}],
        validation_results=[
            {
                "repository": "payments-service",
                "status": ValidationStatus.FAILED,
                "checks": [
                    {
                        "name": "unit-tests",
                        "status": ValidationStatus.FAILED,
                        "details": "2 tests failed.",
                    }
                ],
                "summary": "Tests failed.",
            }
        ],
        code_diffs=[
            {
                "file_path": "src/main/java/com/example/payments/LegacyJsonAdapter.java",
                "change_summary": "Replace removed parser entry point with the builder-backed parser.",
                "additions": 12,
                "deletions": 0,
            }
        ],
        complex_remediation_plan={
            "repository": "payments-service",
            "summary": "Analyze the major-version jump before attempting code changes.",
            "compatibility_diff": {
                "package_name": "org.example:legacy-json",
                "baseline_version": "1.2.3",
                "target_version": "2.0.0",
                "summary": "Major-version upgrade removes legacy parser entry points.",
                "risk": "high",
                "breaking_changes": [
                    {
                        "symbol": "org.example.LegacyParser#parse",
                        "change_type": "removed",
                        "impact": "Call sites must migrate to JsonParserBuilder.",
                        "guidance": "Replace direct parse calls with builder.create().parse(...)",
                    }
                ],
            },
            "migration_tactic": "adapter_shim",
            "target_files": [
                {
                    "file_path": "src/main/java/com/example/payments/LegacyJsonAdapter.java",
                    "change_summary": "Replace removed parser entry point with the builder-backed parser.",
                    "related_symbols": ["org.example.LegacyParser#parse"],
                }
            ],
            "open_questions": ["Should adapter construction move behind a Spring bean factory?"],
        },
    )

    update = node(state)

    bundle = update["escalation_bundle"]
    bundle_path = Path(bundle.bundle_path)
    payload = json.loads(bundle_path.read_text())

    assert bundle.complex_migration_tactic == "adapter_shim"
    assert bundle.code_diff_summaries == ["Replace removed parser entry point with the builder-backed parser."]
    assert bundle.route_strategy == RemediationStrategy.COMPLEX_REFACTOR
    assert bundle.route_reason == "Breaking API changes."
    assert bundle.approval_stage == "delivery"
    assert bundle.approval_reviewer == "release-manager"
    assert bundle.approval_comments == "Approved for publication once validation is green."
    assert bundle.validation_status == ValidationStatus.FAILED
    assert bundle.primary_validation_check == "unit-tests"
    assert bundle.primary_validation_check_status == ValidationStatus.FAILED
    assert bundle.complex_target_files == ["src/main/java/com/example/payments/LegacyJsonAdapter.java"]
    assert bundle.complex_open_questions == ["Should adapter construction move behind a Spring bean factory?"]
    assert payload["code_diff_summaries"] == ["Replace removed parser entry point with the builder-backed parser."]
    assert payload["route_strategy"] == RemediationStrategy.COMPLEX_REFACTOR
    assert payload["route_reason"] == "Breaking API changes."
    assert payload["approval_stage"] == "delivery"
    assert payload["approval_reviewer"] == "release-manager"
    assert payload["approval_comments"] == "Approved for publication once validation is green."
    assert payload["validation_summary"] == "Tests failed."
    assert payload["primary_validation_check"] == "unit-tests"
    assert payload["primary_validation_check_details"] == "2 tests failed."
    assert payload["complex_migration_tactic"] == "adapter_shim"
    assert payload["complex_target_files"] == ["src/main/java/com/example/payments/LegacyJsonAdapter.java"]
    assert payload["complex_open_questions"] == ["Should adapter construction move behind a Spring bean factory?"]


def test_escalate_node_uses_first_failed_validation_check_as_primary(tmp_path: Path) -> None:
    config = load_runtime_config(repo_root=tmp_path)
    node = __import__("execution_accelerator.nodes", fromlist=["build_escalate_node"]).build_escalate_node(config)
    state = RemediationState(
        initial_ticket_id="SEC-888",
        total_attempts=1,
        failure_classifications=[FailureClassification.LICENSE_VIOLATION],
        validation_results=[
            {
                "repository": "payments-service",
                "status": ValidationStatus.FAILED,
                "checks": [
                    {
                        "name": "compile",
                        "status": ValidationStatus.PASSED,
                        "details": "Compilation passed.",
                    },
                    {
                        "name": "license-scan",
                        "status": ValidationStatus.FAILED,
                        "details": "Disallowed GPL dependency detected.",
                    },
                ],
                "summary": "Live validation detected a disallowed or unverifiable dependency license.",
            }
        ],
    )

    update = node(state)

    assert update["escalation_bundle"].primary_validation_check == "license-scan"
    assert update["escalation_bundle"].primary_validation_check_status == ValidationStatus.FAILED
    assert update["escalation_bundle"].primary_validation_check_details == "Disallowed GPL dependency detected."


def test_escalate_node_captures_multi_repo_progress(tmp_path: Path) -> None:
    config = load_runtime_config(repo_root=tmp_path)
    node = __import__("execution_accelerator.nodes", fromlist=["build_escalate_node"]).build_escalate_node(config)
    state = RemediationState(
        initial_ticket_id="SEC-999",
        current_working_repo="ledger-service",
        total_attempts=1,
        failure_classifications=[FailureClassification.TEST_FAILURE],
        completed_repos=["payments-service"],
        pending_repos=["ledger-service"],
        skipped_repos=[{"name": "reporting-service", "reason": "existing_pr:https://example.test/pr/7"}],
        errors=[{"code": "validation_test_failed", "message": "Tests failed.", "recoverable": False, "repository": "ledger-service"}],
        validation_results=[
            {
                "repository": "ledger-service",
                "status": ValidationStatus.FAILED,
                "checks": [
                    {
                        "name": "unit-tests",
                        "status": ValidationStatus.FAILED,
                        "details": "2 tests failed.",
                    }
                ],
                "summary": "Tests failed.",
            }
        ],
    )

    update = node(state)
    bundle = update["escalation_bundle"]
    payload = json.loads(Path(bundle.bundle_path).read_text())

    assert bundle.failed_repository == "ledger-service"
    assert bundle.completed_repos == ["payments-service"]
    assert bundle.pending_repos == ["ledger-service"]
    assert bundle.skipped_repos[0]["name"] == "reporting-service"
    assert bundle.skipped_repos[0]["reason"] == "existing_pr:https://example.test/pr/7"
    assert payload["failed_repository"] == "ledger-service"
    assert payload["completed_repos"] == ["payments-service"]
    assert payload["pending_repos"] == ["ledger-service"]
    assert payload["skipped_repos"] == [{"name": "reporting-service", "reason": "existing_pr:https://example.test/pr/7"}]
