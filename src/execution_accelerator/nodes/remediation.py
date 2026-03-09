"""Day 5 simple remediation and preflight nodes."""

from __future__ import annotations

from pathlib import Path

from execution_accelerator.adapters import PomMutationAdapter, PreflightResolutionAdapter
from execution_accelerator.schemas import (
    AuditEvent,
    DependencyCoordinate,
    PomMutationChange,
    PomMutationKind,
    PomMutationPlan,
    PomSectionTarget,
    RemediationStrategy,
)
from execution_accelerator.state import CodeDiffSummary, RemediationState


def build_remediate_simple_node(pom_adapter: PomMutationAdapter):
    """Create a node that applies the Day 5 simple remediation plan."""

    def remediate_simple(state: RemediationState) -> dict[str, object]:
        assert state.route_decision is not None
        assert state.maven_verification is not None
        assert state.route_decision.strategy == RemediationStrategy.SIMPLE_UPDATE

        repository = state.current_working_repo or state.pending_repos[0]
        workspace = state.repo_map[repository]
        plan = _build_simple_plan(state, repository)

        pom_path = Path(workspace.local_path) / plan.changes[0].file_path
        pom_path.parent.mkdir(parents=True, exist_ok=True)
        pom_path.write_text(pom_adapter.load_fixture_before())
        mutated_xml = pom_adapter.apply_plan(pom_path.read_text(), plan)
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


def build_preflight_validation_node(preflight_adapter: PreflightResolutionAdapter):
    """Create a node that loads the fixture-backed preflight validation result."""

    def preflight_validate(state: RemediationState) -> dict[str, object]:
        assert state.current_working_repo is not None

        preflight_resolution = preflight_adapter.load_result(repository=state.current_working_repo)
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


def _build_diff_summary(plan: PomMutationPlan) -> list[CodeDiffSummary]:
    return [
        CodeDiffSummary(
            file_path=change.file_path,
            change_summary=(
                f"Updated {change.dependency.group_id}:{change.dependency.artifact_id} "
                f"from {change.previous_version} to {change.target_version}."
            ),
            additions=1,
            deletions=1,
        )
        for change in plan.changes
    ]
