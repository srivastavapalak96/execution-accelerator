"""Day 5/6 remediation and preflight nodes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import re

from execution_accelerator.adapters import (
    ComplexRemediationAdapter,
    PomMutationAdapter,
    PreflightResolutionAdapter,
)
from execution_accelerator.schemas import (
    AuditEvent,
    CodeChangeTarget,
    ComplexCodeChangePlan,
    ComplexRemediationPlan,
    DependencyCoordinate,
    PomMutationChange,
    PomMutationKind,
    PomMutationPlan,
    PomSectionTarget,
    RemediationPlan,
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
        migration_tactic, tactic_rationale = complex_adapter.select_migration_tactic(compatibility_diff)
        migration_steps = complex_adapter.build_migration_steps(compatibility_diff)
        complex_plan = ComplexRemediationPlan(
            repository=repository,
            summary=(
                f"Analyze {state.vulnerability_details.package_name} "
                f"from {state.vulnerability_details.installed_version} to {state.maven_verification.target_version} "
                "before attempting code changes."
            ),
            artifact_candidates=artifact_candidates,
            compatibility_diff=compatibility_diff,
            migration_tactic=migration_tactic,
            tactic_rationale=tactic_rationale,
            migration_steps=migration_steps,
        )
        remediation_plan = _refine_complex_remediation_plan(
            state=state,
            complex_plan=complex_plan,
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
                    "migration_tactic": migration_tactic,
                    "migration_step_count": len(migration_steps),
                },
            )
        )

        return {
            "current_working_repo": repository,
            "artifact_candidates": artifact_candidates,
            "compatibility_diff": compatibility_diff,
            "complex_remediation_plan": complex_plan,
            "remediation_plan": remediation_plan,
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

        workspace = state.repo_map.get(state.current_working_repo)
        if workspace is None:
            raise WorkspaceError("workspace context missing; repository intake failed")
        decompiled_artifacts = complex_adapter.load_decompiled_artifacts()
        symbol_mappings = complex_adapter.load_symbol_mappings()
        code_change_plan = complex_adapter.load_code_change_plan()
        complex_plan = state.complex_remediation_plan.model_copy(
            update={
                "target_files": code_change_plan.target_files,
                "symbol_mappings": symbol_mappings,
                "open_questions": code_change_plan.open_questions,
            }
        )
        remediation_plan = _refine_complex_execution_plan(
            state=state,
            complex_plan=complex_plan,
            code_change_plan=code_change_plan,
        )
        modified_files, code_diffs = _materialize_complex_scaffold(
            workspace_path=Path(workspace.local_path),
            complex_plan=complex_plan,
            code_change_plan=code_change_plan,
        )

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
                    "open_question_count": len(code_change_plan.open_questions),
                },
            )
        )

        return {
            "decompiled_artifacts": decompiled_artifacts,
            "symbol_mappings": symbol_mappings,
            "code_change_plan": code_change_plan,
            "complex_remediation_plan": complex_plan,
            "remediation_plan": remediation_plan,
            "modified_files": modified_files,
            "code_diffs": code_diffs,
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


def _refine_complex_remediation_plan(
    *,
    state: RemediationState,
    complex_plan: ComplexRemediationPlan,
) -> RemediationPlan:
    current_plan = state.remediation_plan
    target_repositories = (
        list(current_plan.target_repositories)
        if current_plan is not None
        else list(state.pending_repos or state.repo_map.keys())
    )
    return RemediationPlan(
        strategy=RemediationStrategy.COMPLEX_REFACTOR,
        summary=complex_plan.summary,
        rationale=complex_plan.tactic_rationale,
        target_repositories=target_repositories,
        requires_human_approval=current_plan.requires_human_approval if current_plan is not None else True,
    )


def _refine_complex_execution_plan(
    *,
    state: RemediationState,
    complex_plan: ComplexRemediationPlan,
    code_change_plan: ComplexCodeChangePlan,
) -> RemediationPlan:
    base_plan = _refine_complex_remediation_plan(state=state, complex_plan=complex_plan)
    return base_plan.model_copy(
        update={
            "summary": (
                f"{complex_plan.summary} Prepared deterministic scaffold edits for "
                f"{len(code_change_plan.target_files)} files."
            ),
            "rationale": (
                f"{complex_plan.tactic_rationale} "
                f"Current scaffold covers {len(code_change_plan.target_files)} target files and "
                f"{len(code_change_plan.open_questions)} unresolved questions."
            ),
        }
    )


def _materialize_complex_scaffold(
    *,
    workspace_path: Path,
    complex_plan: ComplexRemediationPlan,
    code_change_plan: ComplexCodeChangePlan,
) -> tuple[list[str], list[CodeDiffSummary]]:
    modified_files: list[str] = []
    code_diffs: list[CodeDiffSummary] = []
    for target in code_change_plan.target_files:
        target_path = _resolve_workspace_file(workspace_path, target.file_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            existing_text = target_path.read_text()
            rendered_text = _append_complex_scaffold_note(
                existing_text=existing_text,
                target=target,
                complex_plan=complex_plan,
            )
            additions = max(rendered_text.count("\n") - existing_text.count("\n"), 0)
        else:
            existing_text = None
            rendered_text = _render_complex_scaffold_file(target=target, complex_plan=complex_plan)
            additions = rendered_text.count("\n")
        target_path.write_text(rendered_text)
        modified_files.append(str(target_path))
        code_diffs.append(
            CodeDiffSummary(
                file_path=target.file_path,
                change_summary=target.change_summary,
                additions=additions,
                deletions=0,
            )
        )
    return modified_files, code_diffs


def _resolve_workspace_file(workspace_path: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise WorkspaceError("complex scaffold target must be relative to the repository workspace")
    resolved = (workspace_path / candidate).resolve()
    try:
        resolved.relative_to(workspace_path.resolve())
    except ValueError as error:
        raise WorkspaceError("complex scaffold target escapes the repository workspace") from error
    return resolved


def _append_complex_scaffold_note(
    *,
    existing_text: str,
    target: CodeChangeTarget,
    complex_plan: ComplexRemediationPlan,
) -> str:
    marker = "Execution Accelerator complex scaffold."
    if marker in existing_text:
        return existing_text
    note = _render_complex_scaffold_note(target=target, complex_plan=complex_plan)
    return existing_text.rstrip() + "\n\n" + note + "\n"


def _render_complex_scaffold_file(
    *,
    target: CodeChangeTarget,
    complex_plan: ComplexRemediationPlan,
) -> str:
    target_path = Path(target.file_path)
    if target_path.suffix == ".java":
        package_line = _build_java_package_line(target_path)
        class_name = _sanitize_java_identifier(target_path.stem)
        lines: list[str] = []
        if package_line is not None:
            lines.append(package_line)
            lines.append("")
        lines.append(f"public final class {class_name} {{")
        for note_line in _render_complex_scaffold_note(
            target=target,
            complex_plan=complex_plan,
        ).splitlines():
            lines.append(f"    {note_line}")
        lines.append("}")
        lines.append("")
        return "\n".join(lines)
    return _render_complex_scaffold_note(target=target, complex_plan=complex_plan) + "\n"


def _render_complex_scaffold_note(
    *,
    target: CodeChangeTarget,
    complex_plan: ComplexRemediationPlan,
) -> str:
    note_lines = [
        "/*",
        " * Execution Accelerator complex scaffold.",
        f" * Change summary: {target.change_summary}",
        f" * Migration tactic: {complex_plan.migration_tactic}",
    ]
    if target.related_symbols:
        note_lines.append(f" * Related symbols: {', '.join(target.related_symbols)}")
    if complex_plan.open_questions:
        note_lines.append(f" * Open questions: {' | '.join(complex_plan.open_questions)}")
    note_lines.append(" */")
    return "\n".join(note_lines)


def _build_java_package_line(target_path: Path) -> str | None:
    parts = target_path.parts
    try:
        java_root = parts.index("java")
    except ValueError:
        return None
    package_parts = parts[java_root + 1 : -1]
    if not package_parts:
        return None
    return f"package {'.'.join(package_parts)};"


def _sanitize_java_identifier(name: str) -> str:
    sanitized = re.sub(r"[^0-9A-Za-z_]", "", name)
    if not sanitized:
        return "ComplexScaffold"
    if sanitized[0].isdigit():
        return f"Complex{sanitized}"
    return sanitized
