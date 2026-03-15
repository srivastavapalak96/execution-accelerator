"""Day 5/6 remediation and preflight nodes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from execution_accelerator.adapters import (
    ComplexRemediationAdapter,
    PomMutationAdapter,
    PreflightResolutionAdapter,
)
from execution_accelerator.schemas import (
    AuditEvent,
    ComplexRemediationPlan,
    DependencyCoordinate,
    PomMutationChange,
    PomMutationKind,
    PomMutationPlan,
    PomSectionTarget,
    RemediationStrategy,
)
from execution_accelerator.state import CodeDiffSummary, RemediationState


class WorkspaceError(RuntimeError):
    """Raised when the expected workspace manifest is missing."""


def build_remediate_simple_node(
    pom_adapter: PomMutationAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that applies the Day 5 simple remediation plan."""

    def remediate_simple(state: RemediationState) -> dict[str, object]:
        assert state.route_decision is not None
        assert state.maven_verification is not None
        assert state.route_decision.strategy == RemediationStrategy.SIMPLE_UPDATE

        repository = state.current_working_repo or state.pending_repos[0]
        workspace = state.repo_map[repository]
        plan = _build_simple_plan(state, repository)

        pom_path = Path(workspace.local_path) / plan.changes[0].file_path
        if not pom_path.exists():
            raise WorkspaceError("workspace pom missing; clone failed")
        mutated_xml = pom_adapter.apply_plan(
            pom_path.read_text(),
            plan,
            workspace_path=Path(workspace.local_path),
            execution_plan=state.maven_plan,
        )
        pom_path.write_text(mutated_xml)

        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="remediation.simple_apply",
                message=f"Applied simple pom remediation for {repository}.",
                details={
                    "repository": repository,
                    "file_path": plan.changes[0].file_path,
                    "target_version": plan.changes[0].target_version,
                },
            )
        )

        return {
            "current_working_repo": repository,
            "pom_mutation_plan": plan,
            "modified_files": [str(pom_path)],
            "code_diffs": _build_diff_summary(plan),
            "audit_events": audit_events,
        }

    return remediate_simple


def build_remediate_transitive_node(
    pom_adapter: PomMutationAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that applies the Day 6 transitive override remediation plan."""

    def remediate_transitive(state: RemediationState) -> dict[str, object]:
        assert state.route_decision is not None
        assert state.maven_verification is not None
        assert state.route_decision.strategy == RemediationStrategy.TRANSITIVE_OVERRIDE

        repository = state.current_working_repo or state.pending_repos[0]
        workspace = state.repo_map[repository]
        plan = _build_transitive_plan(state, repository)

        pom_path = Path(workspace.local_path) / plan.changes[0].file_path
        if not pom_path.exists():
            raise WorkspaceError("workspace pom missing; clone failed")
        mutated_xml = pom_adapter.apply_plan(
            pom_path.read_text(),
            plan,
            workspace_path=Path(workspace.local_path),
            execution_plan=state.maven_plan,
        )
        pom_path.write_text(mutated_xml)

        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="remediation.transitive_override",
                message=f"Applied transitive override remediation for {repository}.",
                details={
                    "repository": repository,
                    "file_path": plan.changes[0].file_path,
                    "target_version": plan.changes[0].target_version,
                    "target_section": plan.changes[0].target_section,
                },
            )
        )

        return {
            "current_working_repo": repository,
            "pom_mutation_plan": plan,
            "modified_files": [str(pom_path)],
            "code_diffs": _build_diff_summary(plan),
            "audit_events": audit_events,
        }

    return remediate_transitive


def build_preflight_validation_node(
    preflight_adapter: PreflightResolutionAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that loads the fixture-backed preflight validation result."""

    def preflight_validate(state: RemediationState) -> dict[str, object]:
        assert state.current_working_repo is not None

        workspace = state.repo_map.get(state.current_working_repo)
        preflight_resolution = preflight_adapter.load_result(
            repository=state.current_working_repo,
            workspace_path=Path(workspace.local_path) if workspace is not None else None,
            vulnerability_details=state.vulnerability_details,
            maven_verification=state.maven_verification,
            execution_plan=state.maven_plan,
        )
        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="remediation.preflight",
                message=f"Completed preflight validation for {state.current_working_repo}.",
                details={
                    "repository": state.current_working_repo,
                    "status": preflight_resolution.status,
                    "resolved_version": preflight_resolution.resolved_version,
                },
            )
        )

        return {
            "preflight_resolution": preflight_resolution,
            "audit_events": audit_events,
        }

    return preflight_validate


def build_prepare_complex_remediation_node(
    complex_adapter: ComplexRemediationAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that records the Day 7 complex-lane analysis placeholders."""

    def prepare_complex_remediation(state: RemediationState) -> dict[str, object]:
        assert state.route_decision is not None
        assert state.maven_verification is not None
        assert state.vulnerability_details is not None
        assert state.route_decision.strategy == RemediationStrategy.COMPLEX_REFACTOR

        repository = state.current_working_repo or state.pending_repos[0]
        artifact_candidates = complex_adapter.load_artifact_candidates()
        compatibility_diff = complex_adapter.load_compatibility_diff()
        complex_plan = ComplexRemediationPlan(
            repository=repository,
            summary=(
                f"Analyze {state.vulnerability_details.package_name} "
                f"from {state.vulnerability_details.installed_version} to {state.maven_verification.target_version} "
                "before attempting code changes."
            ),
            artifact_candidates=artifact_candidates,
            compatibility_diff=compatibility_diff,
        )

        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="remediation.complex_prepare",
                message=f"Prepared complex remediation analysis for {repository}.",
                details={
                    "repository": repository,
                    "candidate_count": len(artifact_candidates),
                    "breaking_change_count": len(compatibility_diff.breaking_changes),
                },
            )
        )

        return {
            "current_working_repo": repository,
            "artifact_candidates": artifact_candidates,
            "compatibility_diff": compatibility_diff,
            "complex_remediation_plan": complex_plan,
            "audit_events": audit_events,
        }

    return prepare_complex_remediation


def build_execute_complex_scaffold_node(
    complex_adapter: ComplexRemediationAdapter,
) -> Callable[[RemediationState], dict[str, object]]:
    """Create a node that expands the Day 8 complex analysis into an execution scaffold."""

    def execute_complex_scaffold(state: RemediationState) -> dict[str, object]:
        assert state.route_decision is not None
        assert state.route_decision.strategy == RemediationStrategy.COMPLEX_REFACTOR
        assert state.current_working_repo is not None
        assert state.complex_remediation_plan is not None

        decompiled_artifacts = complex_adapter.load_decompiled_artifacts()
        symbol_mappings = complex_adapter.load_symbol_mappings()
        code_change_plan = complex_adapter.load_code_change_plan()

        audit_events = list(state.audit_events)
        audit_events.append(
            AuditEvent(
                event_type="remediation.complex_scaffold",
                message=f"Built complex execution scaffold for {state.current_working_repo}.",
                details={
                    "repository": state.current_working_repo,
                    "decompiled_artifact_count": len(decompiled_artifacts),
                    "symbol_mapping_count": len(symbol_mappings),
                    "planned_file_count": len(code_change_plan.target_files),
                },
            )
        )

        return {
            "decompiled_artifacts": decompiled_artifacts,
            "symbol_mappings": symbol_mappings,
            "code_change_plan": code_change_plan,
            "audit_events": audit_events,
        }

    return execute_complex_scaffold


def _build_simple_plan(state: RemediationState, repository: str) -> PomMutationPlan:
    assert state.vulnerability_details is not None
    assert state.maven_verification is not None

    current_repo = state.repo_map[repository]
    file_path = current_repo.manifest_path or "pom.xml"
    dependency = DependencyCoordinate(
        group_id=state.vulnerability_details.package_name.split(":", maxsplit=1)[0],
        artifact_id=state.vulnerability_details.package_name.split(":", maxsplit=1)[1],
        version=state.maven_verification.target_version,
    )

    return PomMutationPlan(
        repository=repository,
        strategy=RemediationStrategy.SIMPLE_UPDATE,
        summary=f"Bump {state.vulnerability_details.package_name} to {state.maven_verification.target_version}.",
        changes=[
            PomMutationChange(
                file_path=file_path,
                dependency=dependency,
                mutation_kind=PomMutationKind.DIRECT_VERSION_BUMP,
                target_section=PomSectionTarget.PROJECT_DEPENDENCIES,
                previous_version=state.vulnerability_details.installed_version,
                target_version=state.maven_verification.target_version,
                xml_path_hint="./dependencies/dependency/version",
            )
        ],
    )


def _build_transitive_plan(state: RemediationState, repository: str) -> PomMutationPlan:
    assert state.vulnerability_details is not None
    assert state.maven_verification is not None

    current_repo = state.repo_map[repository]
    file_path = current_repo.manifest_path or "pom.xml"
    dependency = DependencyCoordinate(
        group_id=state.vulnerability_details.package_name.split(":", maxsplit=1)[0],
        artifact_id=state.vulnerability_details.package_name.split(":", maxsplit=1)[1],
        version=state.maven_verification.target_version,
    )

    return PomMutationPlan(
        repository=repository,
        strategy=RemediationStrategy.TRANSITIVE_OVERRIDE,
        summary=(
            f"Add a dependencyManagement override for {state.vulnerability_details.package_name} "
            f"at {state.maven_verification.target_version}."
        ),
        changes=[
            PomMutationChange(
                file_path=file_path,
                dependency=dependency,
                mutation_kind=PomMutationKind.DEPENDENCY_MANAGEMENT_OVERRIDE,
                target_section=PomSectionTarget.DEPENDENCY_MANAGEMENT,
                previous_version=state.vulnerability_details.installed_version,
                target_version=state.maven_verification.target_version,
                xml_path_hint="./dependencyManagement/dependencies/dependency/version",
            )
        ],
    )


def _build_diff_summary(plan: PomMutationPlan) -> list[CodeDiffSummary]:
    return [
        CodeDiffSummary(
            file_path=change.file_path,
            change_summary=_build_change_summary(change),
            additions=1,
            deletions=1,
        )
        for change in plan.changes
    ]


def _build_change_summary(change: PomMutationChange) -> str:
    if change.target_section == PomSectionTarget.DEPENDENCY_MANAGEMENT:
        return (
            f"Added dependencyManagement override for "
            f"{change.dependency.group_id}:{change.dependency.artifact_id} "
            f"at {change.target_version}."
        )

    return (
        f"Updated {change.dependency.group_id}:{change.dependency.artifact_id} "
        f"from {change.previous_version} to {change.target_version}."
    )
