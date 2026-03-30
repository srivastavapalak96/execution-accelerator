"""Day 5/6 remediation and preflight nodes."""

from __future__ import annotations

from collections.abc import Callable
import difflib
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
    SymbolMappingEntry,
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
    """Create a node that records the prepared complex-lane analysis plan."""

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
        modified_files, code_diffs = _materialize_complex_scaffold(
            workspace_path=Path(workspace.local_path),
            complex_plan=complex_plan,
            code_change_plan=code_change_plan,
        )
        remediation_plan = _refine_complex_execution_plan(
            state=state,
            complex_plan=complex_plan,
            code_change_plan=code_change_plan,
            executed_file_count=len(code_diffs),
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
                    "executed_file_count": len(code_diffs),
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
    executed_file_count: int,
) -> RemediationPlan:
    base_plan = _refine_complex_remediation_plan(state=state, complex_plan=complex_plan)
    extra_file_count = max(0, executed_file_count - len(code_change_plan.target_files))
    return base_plan.model_copy(
        update={
            "summary": (
                f"{complex_plan.summary} Executed bounded complex migration edits for "
                f"{executed_file_count} files."
            ),
            "rationale": (
                f"{complex_plan.tactic_rationale} "
                f"Current bounded execution covers {len(code_change_plan.target_files)} planned target files, "
                f"{extra_file_count} detected existing source files, and "
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
    planned_targets = {target.file_path: target for target in code_change_plan.target_files}
    for target in code_change_plan.target_files:
        target_path = _resolve_workspace_file(workspace_path, target.file_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            existing_text = target_path.read_text()
            rewritten_text = _apply_complex_symbol_rewrites(
                existing_text=existing_text,
                target=target,
                complex_plan=complex_plan,
            )
            rendered_text = _append_complex_scaffold_note(
                existing_text=rewritten_text,
                target=target,
                complex_plan=complex_plan,
            )
        else:
            existing_text = ""
            rendered_text = _render_complex_scaffold_file(target=target, complex_plan=complex_plan)
        additions, deletions = _summarize_text_diff(existing_text, rendered_text)
        target_path.write_text(rendered_text)
        modified_files.append(str(target_path))
        code_diffs.append(
            CodeDiffSummary(
                file_path=target.file_path,
                change_summary=target.change_summary,
                additions=additions,
                deletions=deletions,
            )
        )
    related_symbols = _collect_complex_related_symbols(complex_plan)
    for source_path in _iter_workspace_java_files(workspace_path):
        relative_path = str(source_path.relative_to(workspace_path))
        if relative_path in planned_targets:
            continue
        existing_text = source_path.read_text()
        synthetic_target = CodeChangeTarget(
            file_path=relative_path,
            change_summary="Apply supported complex migration rewrites for detected legacy API usage.",
            related_symbols=related_symbols,
        )
        rendered_text = _apply_complex_symbol_rewrites(
            existing_text=existing_text,
            target=synthetic_target,
            complex_plan=complex_plan,
        )
        if rendered_text == existing_text:
            continue
        additions, deletions = _summarize_text_diff(existing_text, rendered_text)
        source_path.write_text(rendered_text)
        modified_files.append(str(source_path))
        code_diffs.append(
            CodeDiffSummary(
                file_path=relative_path,
                change_summary=synthetic_target.change_summary,
                additions=additions,
                deletions=deletions,
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


def _apply_complex_symbol_rewrites(
    *,
    existing_text: str,
    target: CodeChangeTarget,
    complex_plan: ComplexRemediationPlan,
) -> str:
    rewritten_text = existing_text
    for constructor_class, factory_call in _iter_complex_constructor_rewrites(
        target=target,
        complex_plan=complex_plan,
    ):
        rewritten_text = _rewrite_java_constructor_calls(
            rewritten_text,
            constructor_class=constructor_class,
            factory_call=factory_call,
        )
    for legacy_call, replacement_call in _iter_complex_symbol_rewrites(
        target=target,
        complex_plan=complex_plan,
    ):
        rewritten_text = rewritten_text.replace(legacy_call, replacement_call)
    for legacy_field, replacement_field in _iter_complex_field_rewrites(
        target=target,
        complex_plan=complex_plan,
    ):
        rewritten_text = _rewrite_java_field_references(
            rewritten_text,
            legacy_field=legacy_field,
            replacement_field=replacement_field,
        )
    for legacy_class, method_name, replacement_call in _iter_complex_static_import_rewrites(
        target=target,
        complex_plan=complex_plan,
    ):
        rewritten_text = _rewrite_java_static_import_calls(
            rewritten_text,
            legacy_class=legacy_class,
            method_name=method_name,
            replacement_call=replacement_call,
        )
    for legacy_class, field_name, replacement_field in _iter_complex_static_import_field_rewrites(
        target=target,
        complex_plan=complex_plan,
    ):
        rewritten_text = _rewrite_java_static_import_fields(
            rewritten_text,
            legacy_class=legacy_class,
            field_name=field_name,
            replacement_field=replacement_field,
        )
    for legacy_reference, replacement_reference in _iter_complex_method_reference_rewrites(
        target=target,
        complex_plan=complex_plan,
    ):
        rewritten_text = rewritten_text.replace(legacy_reference, replacement_reference)
    for legacy_reference, replacement_lambda in _iter_complex_constructor_reference_rewrites(
        target=target,
        complex_plan=complex_plan,
    ):
        rewritten_text = rewritten_text.replace(legacy_reference, replacement_lambda)
    for legacy_class in _iter_complex_import_cleanup_classes(
        target=target,
        complex_plan=complex_plan,
    ):
        rewritten_text = _remove_unused_exact_java_import(
            rewritten_text,
            legacy_class=legacy_class,
        )
    return rewritten_text


def _iter_complex_symbol_rewrites(
    *,
    target: CodeChangeTarget,
    complex_plan: ComplexRemediationPlan,
) -> list[tuple[str, str]]:
    rewrites: list[tuple[str, str]] = []
    related_symbols = set(target.related_symbols)
    for mapping in complex_plan.symbol_mappings:
        if mapping.legacy_symbol not in related_symbols and mapping.replacement_symbol not in related_symbols:
            continue
        replacement_call = _render_java_method_call(mapping.replacement_symbol, qualified=True)
        if replacement_call is None:
            continue
        for qualified in (False, True):
            legacy_call = _render_java_method_call(mapping.legacy_symbol, qualified=qualified)
            if legacy_call is None:
                continue
            rewrite = (legacy_call, replacement_call)
            if rewrite not in rewrites:
                rewrites.append(rewrite)
    return rewrites


def _iter_complex_static_import_rewrites(
    *,
    target: CodeChangeTarget,
    complex_plan: ComplexRemediationPlan,
) -> list[tuple[str, str, str]]:
    rewrites: list[tuple[str, str, str]] = []
    related_symbols = set(target.related_symbols)
    for mapping in complex_plan.symbol_mappings:
        if mapping.legacy_symbol not in related_symbols and mapping.replacement_symbol not in related_symbols:
            continue
        legacy_class = _parse_java_symbol_class(mapping.legacy_symbol)
        method_name = _parse_java_method_name(mapping.legacy_symbol)
        replacement_call = _render_java_method_call(mapping.replacement_symbol, qualified=True)
        if legacy_class is None or method_name is None or replacement_call is None:
            continue
        rewrite = (legacy_class, method_name, replacement_call)
        if rewrite not in rewrites:
            rewrites.append(rewrite)
    return rewrites


def _iter_complex_field_rewrites(
    *,
    target: CodeChangeTarget,
    complex_plan: ComplexRemediationPlan,
) -> list[tuple[str, str]]:
    rewrites: list[tuple[str, str]] = []
    related_symbols = set(target.related_symbols)
    for mapping in complex_plan.symbol_mappings:
        if mapping.legacy_symbol not in related_symbols and mapping.replacement_symbol not in related_symbols:
            continue
        replacement_field = _render_java_field_reference(mapping.replacement_symbol, qualified=True)
        if replacement_field is None:
            continue
        for qualified in (False, True):
            legacy_field = _render_java_field_reference(mapping.legacy_symbol, qualified=qualified)
            if legacy_field is None:
                continue
            rewrite = (legacy_field, replacement_field)
            if rewrite not in rewrites:
                rewrites.append(rewrite)
    return rewrites


def _iter_complex_static_import_field_rewrites(
    *,
    target: CodeChangeTarget,
    complex_plan: ComplexRemediationPlan,
) -> list[tuple[str, str, str]]:
    rewrites: list[tuple[str, str, str]] = []
    related_symbols = set(target.related_symbols)
    for mapping in complex_plan.symbol_mappings:
        if mapping.legacy_symbol not in related_symbols and mapping.replacement_symbol not in related_symbols:
            continue
        legacy_class = _parse_java_symbol_class(mapping.legacy_symbol)
        field_name = _parse_java_field_name(mapping.legacy_symbol)
        replacement_field = _render_java_field_reference(mapping.replacement_symbol, qualified=True)
        if legacy_class is None or field_name is None or replacement_field is None:
            continue
        rewrite = (legacy_class, field_name, replacement_field)
        if rewrite not in rewrites:
            rewrites.append(rewrite)
    return rewrites


def _iter_complex_import_cleanup_classes(
    *,
    target: CodeChangeTarget,
    complex_plan: ComplexRemediationPlan,
) -> list[str]:
    legacy_classes: list[str] = []
    related_symbols = set(target.related_symbols)
    for mapping in complex_plan.symbol_mappings:
        if mapping.legacy_symbol not in related_symbols and mapping.replacement_symbol not in related_symbols:
            continue
        legacy_class = _parse_java_symbol_class(mapping.legacy_symbol)
        if legacy_class is not None and legacy_class not in legacy_classes:
            legacy_classes.append(legacy_class)
    return legacy_classes


def _iter_complex_method_reference_rewrites(
    *,
    target: CodeChangeTarget,
    complex_plan: ComplexRemediationPlan,
) -> list[tuple[str, str]]:
    rewrites: list[tuple[str, str]] = []
    related_symbols = set(target.related_symbols)
    for mapping in complex_plan.symbol_mappings:
        if mapping.legacy_symbol not in related_symbols and mapping.replacement_symbol not in related_symbols:
            continue
        replacement_reference = _render_java_method_reference(mapping.replacement_symbol, qualified=True)
        if replacement_reference is None:
            continue
        for qualified in (False, True):
            legacy_reference = _render_java_method_reference(mapping.legacy_symbol, qualified=qualified)
            if legacy_reference is None:
                continue
            rewrite = (legacy_reference, replacement_reference)
            if rewrite not in rewrites:
                rewrites.append(rewrite)
    return rewrites


def _iter_complex_constructor_rewrites(
    *,
    target: CodeChangeTarget,
    complex_plan: ComplexRemediationPlan,
) -> list[tuple[str, str]]:
    rewrites: list[tuple[str, str]] = []
    related_symbols = set(target.related_symbols)
    for mapping in complex_plan.symbol_mappings:
        if mapping.legacy_symbol not in related_symbols and mapping.replacement_symbol not in related_symbols:
            continue
        constructor_class = _parse_java_constructor_class(mapping.legacy_symbol)
        if constructor_class is None:
            continue
        factory_call = _render_java_factory_call(mapping.replacement_symbol, qualified=True)
        if factory_call is None:
            continue
        rewrite = (constructor_class, factory_call)
        if rewrite not in rewrites:
            rewrites.append(rewrite)
    return rewrites


def _iter_complex_constructor_reference_rewrites(
    *,
    target: CodeChangeTarget,
    complex_plan: ComplexRemediationPlan,
) -> list[tuple[str, str]]:
    rewrites: list[tuple[str, str]] = []
    related_symbols = set(target.related_symbols)
    for mapping in complex_plan.symbol_mappings:
        if mapping.legacy_symbol not in related_symbols and mapping.replacement_symbol not in related_symbols:
            continue
        constructor_class = _parse_java_constructor_class(mapping.legacy_symbol)
        if constructor_class is None:
            continue
        factory_call = _render_java_factory_call(mapping.replacement_symbol, qualified=True)
        if factory_call is None:
            continue
        parameter_types = _parse_java_symbol_parameter_types(mapping.legacy_symbol)
        replacement_lambda = _render_java_constructor_reference_lambda(
            constructor_class=constructor_class,
            factory_call=factory_call,
            parameter_types=parameter_types,
        )
        for qualified in (False, True):
            rendered_class = constructor_class if qualified else constructor_class.rsplit(".", maxsplit=1)[-1]
            rewrite = (f"{rendered_class}::new", replacement_lambda)
            if rewrite not in rewrites:
                rewrites.append(rewrite)
    return rewrites


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
        generated_methods = _render_generated_complex_java_methods(target=target, complex_plan=complex_plan)
        if generated_methods:
            for generated_method in generated_methods:
                for method_line in generated_method.splitlines():
                    lines.append(f"    {method_line}" if method_line else "")
                lines.append("")
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


def _render_java_method_call(symbol: str, *, qualified: bool) -> str | None:
    if "#" not in symbol:
        return None
    class_name, member_expression = symbol.split("#", maxsplit=1)
    if not class_name or not member_expression or "<init>" in member_expression:
        return None
    rendered_class = class_name if qualified else class_name.rsplit(".", maxsplit=1)[-1]
    return f"{rendered_class}.{member_expression}("


def _render_java_method_reference(symbol: str, *, qualified: bool) -> str | None:
    if "#" not in symbol:
        return None
    class_name, member_expression = symbol.split("#", maxsplit=1)
    if not class_name or not member_expression or "<init>" in member_expression:
        return None
    if "." in member_expression:
        qualifier_expression, _, method_name = member_expression.rpartition(".")
        if not qualifier_expression or not method_name:
            return None
        rendered_class = class_name if qualified else class_name.rsplit(".", maxsplit=1)[-1]
        return f"{rendered_class}.{qualifier_expression}::{method_name}"
    rendered_class = class_name if qualified else class_name.rsplit(".", maxsplit=1)[-1]
    return f"{rendered_class}::{member_expression}"


def _render_java_field_reference(symbol: str, *, qualified: bool) -> str | None:
    if "#" not in symbol:
        return None
    class_name, member_expression = symbol.split("#", maxsplit=1)
    if not class_name or not member_expression or "(" in member_expression or "<init>" in member_expression:
        return None
    rendered_class = class_name if qualified else class_name.rsplit(".", maxsplit=1)[-1]
    return f"{rendered_class}.{member_expression}"


def _parse_java_symbol_class(symbol: str) -> str | None:
    if "#" not in symbol:
        return None
    class_name, _ = symbol.split("#", maxsplit=1)
    return class_name or None


def _parse_java_method_name(symbol: str) -> str | None:
    if "#" not in symbol:
        return None
    _, member_expression = symbol.split("#", maxsplit=1)
    if not member_expression or "<init>" in member_expression:
        return None
    method_name = member_expression.rsplit(".", maxsplit=1)[-1].split("(", maxsplit=1)[0]
    return method_name or None


def _parse_java_field_name(symbol: str) -> str | None:
    if "#" not in symbol:
        return None
    _, member_expression = symbol.split("#", maxsplit=1)
    if not member_expression or "(" in member_expression or "<init>" in member_expression:
        return None
    field_name = member_expression.rsplit(".", maxsplit=1)[-1]
    return field_name or None


def _parse_java_constructor_class(symbol: str) -> str | None:
    if "#<init>" in symbol:
        class_name, _, _ = symbol.partition("#<init>")
        return class_name or None
    if ".<init>" in symbol:
        class_name, _, _ = symbol.partition(".<init>")
        return class_name or None
    return None


def _render_java_factory_call(symbol: str, *, qualified: bool) -> str | None:
    if "#" not in symbol:
        return None
    class_name, member_expression = symbol.split("#", maxsplit=1)
    if not class_name or not member_expression or "<init>" in member_expression:
        return None
    method_name = member_expression.split("(", maxsplit=1)[0]
    rendered_class = class_name if qualified else class_name.rsplit(".", maxsplit=1)[-1]
    return f"{rendered_class}.{method_name}"


def _render_java_invocation_expression(symbol: str, *, arguments: list[str], qualified: bool) -> str | None:
    if "#" not in symbol:
        return None
    class_name, member_expression = symbol.split("#", maxsplit=1)
    if not class_name or not member_expression:
        return None
    rendered_class = class_name if qualified else class_name.rsplit(".", maxsplit=1)[-1]
    return f"{rendered_class}.{member_expression}({', '.join(arguments)})"


def _parse_java_symbol_parameter_types(symbol: str) -> list[str]:
    open_paren = symbol.find("(")
    close_paren = symbol.rfind(")")
    if open_paren == -1 or close_paren == -1 or close_paren < open_paren:
        return []
    parameter_text = symbol[open_paren + 1 : close_paren].strip()
    if not parameter_text:
        return []
    return [parameter.strip() for parameter in parameter_text.split(",") if parameter.strip()]


def _render_generated_complex_java_methods(
    *,
    target: CodeChangeTarget,
    complex_plan: ComplexRemediationPlan,
) -> list[str]:
    methods: list[str] = []
    for mapping in complex_plan.symbol_mappings:
        if mapping.legacy_symbol not in target.related_symbols and mapping.replacement_symbol not in target.related_symbols:
            continue
        generated_method = _render_generated_complex_java_method(mapping)
        if generated_method is not None and generated_method not in methods:
            methods.append(generated_method)
    return methods


def _render_generated_complex_java_method(mapping: SymbolMappingEntry) -> str | None:
    constructor_class = _parse_java_constructor_class(mapping.legacy_symbol)
    if constructor_class is not None:
        return _render_generated_constructor_bridge(mapping.legacy_symbol, constructor_class, mapping.replacement_symbol)
    return _render_generated_method_bridge(mapping.legacy_symbol, mapping.replacement_symbol)


def _render_generated_method_bridge(legacy_symbol: str, replacement_symbol: str) -> str | None:
    if "#" not in legacy_symbol:
        return None
    _, member_expression = legacy_symbol.split("#", maxsplit=1)
    method_name = member_expression.split("(", maxsplit=1)[0]
    if not method_name or "<init>" in method_name:
        return None
    parameter_type = "String" if method_name.startswith("parse") else "Object"
    parameter_name = "payload" if parameter_type == "String" else "input"
    replacement_call = _render_java_invocation_expression(
        replacement_symbol,
        arguments=[parameter_name],
        qualified=True,
    )
    if replacement_call is None:
        return None
    return "\n".join(
        [
            f"public Object {method_name}({parameter_type} {parameter_name}) {{",
            f"    return {replacement_call};",
            "}",
        ]
    )


def _render_generated_constructor_bridge(
    legacy_symbol: str,
    constructor_class: str,
    replacement_symbol: str,
) -> str | None:
    factory_call = _render_java_factory_call(replacement_symbol, qualified=True)
    if factory_call is None:
        return None
    parameter_types = _parse_java_symbol_parameter_types(legacy_symbol)
    parameter_names = [_default_java_parameter_name(parameter_type, index) for index, parameter_type in enumerate(parameter_types)]
    signature = ", ".join(
        f"{parameter_type} {parameter_name}" for parameter_type, parameter_name in zip(parameter_types, parameter_names, strict=False)
    )
    wrapped_argument = (
        f"{factory_call}({', '.join(parameter_names)})" if parameter_names else f"{factory_call}()"
    )
    simple_class = constructor_class.rsplit(".", maxsplit=1)[-1]
    return "\n".join(
        [
            f"public {constructor_class} create{simple_class}({signature}) {{",
            f"    return new {constructor_class}({wrapped_argument});",
            "}",
        ]
    )


def _default_java_parameter_name(parameter_type: str, index: int) -> str:
    normalized = parameter_type.strip()
    if normalized == "boolean":
        return "enabled" if index == 0 else f"flag{index}"
    if normalized in {"String", "java.lang.String"}:
        return "value" if index == 0 else f"value{index}"
    return f"arg{index}"


def _collect_complex_related_symbols(complex_plan: ComplexRemediationPlan) -> list[str]:
    symbols: list[str] = []
    for mapping in complex_plan.symbol_mappings:
        if mapping.legacy_symbol not in symbols:
            symbols.append(mapping.legacy_symbol)
        if mapping.replacement_symbol not in symbols:
            symbols.append(mapping.replacement_symbol)
    return symbols


def _iter_workspace_java_files(workspace_path: Path) -> list[Path]:
    ignored_directories = {".git", ".venv", ".mvn", "build", "out", "target"}
    java_files: list[Path] = []
    for source_path in sorted(workspace_path.rglob("*.java")):
        relative_parts = source_path.relative_to(workspace_path).parts
        if any(part in ignored_directories for part in relative_parts):
            continue
        java_files.append(source_path)
    return java_files


def _rewrite_java_constructor_calls(
    text: str,
    *,
    constructor_class: str,
    factory_call: str,
) -> str:
    rewritten_text = text
    for qualified in (False, True):
        rendered_class = constructor_class if qualified else constructor_class.rsplit(".", maxsplit=1)[-1]
        pattern = re.compile(rf"new\s+{re.escape(rendered_class)}\s*\(")
        cursor = 0
        segments: list[str] = []
        for match in pattern.finditer(rewritten_text):
            open_paren_index = match.end() - 1
            close_paren_index = _find_matching_parenthesis(rewritten_text, open_paren_index)
            if close_paren_index is None:
                continue
            arguments = rewritten_text[open_paren_index + 1 : close_paren_index]
            normalized_arguments = arguments.strip()
            if normalized_arguments.startswith(f"{factory_call}("):
                continue
            segments.append(rewritten_text[cursor : open_paren_index + 1])
            wrapped_arguments = f"{factory_call}({normalized_arguments})" if normalized_arguments else f"{factory_call}()"
            segments.append(wrapped_arguments)
            cursor = close_paren_index
        if not segments:
            continue
        segments.append(rewritten_text[cursor:])
        rewritten_text = "".join(segments)
    return rewritten_text


def _render_java_constructor_reference_lambda(
    *,
    constructor_class: str,
    factory_call: str,
    parameter_types: list[str],
) -> str:
    parameter_names = [_default_java_parameter_name(parameter_type, index) for index, parameter_type in enumerate(parameter_types)]
    if not parameter_names:
        return f"() -> new {constructor_class}({factory_call}())"
    parameter_list = parameter_names[0] if len(parameter_names) == 1 else f"({', '.join(parameter_names)})"
    wrapped_argument = f"{factory_call}({', '.join(parameter_names)})"
    return f"{parameter_list} -> new {constructor_class}({wrapped_argument})"


def _rewrite_java_static_import_calls(
    text: str,
    *,
    legacy_class: str,
    method_name: str,
    replacement_call: str,
) -> str:
    exact_import_pattern = re.compile(
        rf"(?m)^[ \t]*import\s+static\s+{re.escape(legacy_class)}\.{re.escape(method_name)}\s*;\s*\n?"
    )
    wildcard_import_pattern = re.compile(
        rf"(?m)^[ \t]*import\s+static\s+{re.escape(legacy_class)}\.\*\s*;\s*$"
    )
    has_exact_import = exact_import_pattern.search(text) is not None
    has_wildcard_import = wildcard_import_pattern.search(text) is not None
    if not has_exact_import and not has_wildcard_import:
        return text

    rewritten_lines: list[str] = []
    changed = False
    for line in text.splitlines(keepends=True):
        if _looks_like_java_method_declaration(line, method_name):
            rewritten_lines.append(line)
            continue
        updated_line = re.sub(
            rf"(?<![\w.]){re.escape(method_name)}\s*\(",
            replacement_call,
            line,
        )
        if updated_line != line:
            changed = True
        rewritten_lines.append(updated_line)

    rewritten_text = "".join(rewritten_lines)
    if changed and has_exact_import:
        rewritten_text = exact_import_pattern.sub("", rewritten_text)
        rewritten_text = re.sub(r"\n{3,}", "\n\n", rewritten_text)
    return rewritten_text


def _rewrite_java_static_import_fields(
    text: str,
    *,
    legacy_class: str,
    field_name: str,
    replacement_field: str,
) -> str:
    exact_import_pattern = re.compile(
        rf"(?m)^[ \t]*import\s+static\s+{re.escape(legacy_class)}\.{re.escape(field_name)}\s*;\s*\n?"
    )
    wildcard_import_pattern = re.compile(
        rf"(?m)^[ \t]*import\s+static\s+{re.escape(legacy_class)}\.\*\s*;\s*$"
    )
    has_exact_import = exact_import_pattern.search(text) is not None
    has_wildcard_import = wildcard_import_pattern.search(text) is not None
    if not has_exact_import and not has_wildcard_import:
        return text

    rewritten_lines: list[str] = []
    changed = False
    for line in text.splitlines(keepends=True):
        if line.strip().startswith(("package ", "import ", "@", "/*", "*", "//")):
            rewritten_lines.append(line)
            continue
        if _looks_like_java_field_declaration(line, field_name):
            rewritten_lines.append(line)
            continue
        updated_line = re.sub(
            rf"(?<![\w.]){re.escape(field_name)}\b",
            replacement_field,
            line,
        )
        if updated_line != line:
            changed = True
        rewritten_lines.append(updated_line)

    rewritten_text = "".join(rewritten_lines)
    if changed and has_exact_import:
        rewritten_text = exact_import_pattern.sub("", rewritten_text)
        rewritten_text = re.sub(r"\n{3,}", "\n\n", rewritten_text)
    return rewritten_text


def _rewrite_java_field_references(text: str, *, legacy_field: str, replacement_field: str) -> str:
    rewritten_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.strip().startswith(("package ", "import ", "@", "/*", "*", "//")):
            rewritten_lines.append(line)
            continue
        rewritten_lines.append(
            re.sub(
                rf"(?<![\w.]){re.escape(legacy_field)}\b",
                replacement_field,
                line,
            )
        )
    return "".join(rewritten_lines)


def _looks_like_java_method_declaration(line: str, method_name: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith(("package ", "import ", "@", "/*", "*", "//")):
        return False
    first_token_match = re.match(r"^\s*([A-Za-z_]\w*)", line)
    if first_token_match is not None and first_token_match.group(1) in {
        "return",
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "throw",
        "new",
    }:
        return False
    return (
        re.match(
            rf"^\s*(?:public|private|protected|static|final|abstract|synchronized|native|default|\w[\w<>\[\],.?]*)[\w\s<>\[\],.?]*\b{re.escape(method_name)}\s*\(",
            line,
        )
        is not None
    )


def _looks_like_java_field_declaration(line: str, field_name: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith(("package ", "import ", "@", "/*", "*", "//")):
        return False
    first_token_match = re.match(r"^\s*([A-Za-z_]\w*)", line)
    if first_token_match is not None and first_token_match.group(1) in {
        "return",
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "throw",
        "new",
    }:
        return False
    return (
        re.match(
            rf"^\s*(?:public|private|protected|static|final|abstract|transient|volatile|\w[\w<>\[\],.?]*)[\w\s<>\[\],.?]*\b{re.escape(field_name)}\b\s*(?:=|;)",
            line,
        )
        is not None
    )


def _remove_unused_exact_java_import(text: str, *, legacy_class: str) -> str:
    import_pattern = re.compile(
        rf"(?m)^[ \t]*import\s+{re.escape(legacy_class)}\s*;\s*\n?"
    )
    if import_pattern.search(text) is None:
        return text
    stripped_text = import_pattern.sub("", text)
    simple_name = legacy_class.rsplit(".", maxsplit=1)[-1]
    if re.search(rf"(?<![\w.]){re.escape(simple_name)}\b", stripped_text) is not None:
        return text
    return re.sub(r"\n{3,}", "\n\n", stripped_text)


def _find_matching_parenthesis(text: str, open_paren_index: int) -> int | None:
    depth = 0
    for index in range(open_paren_index, len(text)):
        current = text[index]
        if current == "(":
            depth += 1
        elif current == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _summarize_text_diff(previous_text: str, updated_text: str) -> tuple[int, int]:
    additions = 0
    deletions = 0
    for line in difflib.ndiff(previous_text.splitlines(), updated_text.splitlines()):
        if line.startswith("+ "):
            additions += 1
        elif line.startswith("- "):
            deletions += 1
    return additions, deletions
