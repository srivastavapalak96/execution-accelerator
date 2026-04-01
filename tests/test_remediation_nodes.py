from __future__ import annotations

import json
from pathlib import Path

import pytest

from execution_accelerator.adapters import (
    AdvisoryVerificationAdapter,
    ComplexRemediationAdapter,
    JiraAdapter,
    MavenVerificationAdapter,
    PomMutationAdapter,
    PreflightResolutionAdapter,
    RepositoryInventoryAdapter,
)
from execution_accelerator.nodes import (
    build_check_repository_idempotency_node,
    build_execute_complex_scaffold_node,
    build_load_repository_context_node,
    build_preflight_validation_node,
    build_prepare_complex_remediation_node,
    build_remediate_simple_node,
    build_remediate_transitive_node,
)
from execution_accelerator.nodes.remediation import WorkspaceError
from execution_accelerator.nodes.verification import select_route
from execution_accelerator.schemas import (
    DependencyCoordinate,
    ExecutionMode,
    MavenDependencyKind,
    MavenExecutionPlan,
    ValidationStatus,
)
from execution_accelerator.state import RemediationState
from tests.conftest import seed_workspace_pom


def build_state(tmp_path: Path, *, transitive: bool = False, complex_refactor: bool = False) -> RemediationState:
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
    repo_context_update = build_check_repository_idempotency_node(
        RepositoryInventoryAdapter(
            fixture_path=fixture_dir / "repository_inventory.json",
            workspace_root=tmp_path / "workspace",
        )
    )(
        RemediationState(
            initial_ticket_id="SEC-123",
            vulnerability_details=vulnerability_details,
            targets=repo_update["targets"],
        )
    )
    state = RemediationState(
        initial_ticket_id="SEC-123",
        vulnerability_details=vulnerability_details,
        targets=repo_update["targets"],
        repo_map=repo_context_update["repo_map"],
        pending_repos=repo_context_update["pending_repos"],
        advisory_verification=AdvisoryVerificationAdapter(
            fixture_path=fixture_dir / "advisory_verification.json"
        ).load_verification(vulnerability_details),
        maven_verification=MavenVerificationAdapter(
            fixture_path=(
                fixture_dir / "maven_verification_complex.json"
                if complex_refactor
                else (
                fixture_dir / "maven_verification_transitive.json"
                if transitive
                else fixture_dir / "maven_verification.json"
                )
            )
        ).load_verification(
            vulnerability_details,
            target_version="2.0.0" if complex_refactor else "1.2.4",
        ),
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
    workspace = Path(state.repo_map["payments-service"].local_path)
    seed_workspace_pom(workspace, fixture_dir / "pom_before.xml")

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
    workspace = Path(state.repo_map["payments-service"].local_path)
    seed_workspace_pom(workspace, fixture_dir / "pom_transitive_before.xml")

    update = node(state)

    assert update["current_working_repo"] == "payments-service"
    assert update["pom_mutation_plan"].strategy == "transitive_override"
    assert update["pom_mutation_plan"].changes[0].target_section == "dependency_management"
    assert Path(update["modified_files"][0]).read_text().count("1.2.4") == 1
    assert update["code_diffs"][0].change_summary.startswith("Added dependencyManagement override")
    assert update["audit_events"][-1].event_type == "remediation.transitive_override"


def test_remediate_simple_node_uses_openrewrite_in_live_mode(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    state = build_state(tmp_path)
    workspace = Path(state.repo_map["payments-service"].local_path)
    seed_workspace_pom(workspace, fixture_dir / "pom_before.xml")
    calls: list[tuple[str, dict[str, str] | None]] = []

    class StubOpenRewriteRunner:
        def apply_recipe(
            self,
            cwd: Path,
            *,
            recipe_name: str,
            execution_plan: MavenExecutionPlan | None = None,
            recipe_options: dict[str, str] | None = None,
        ) -> None:
            calls.append((recipe_name, recipe_options))
            pom_path = cwd / "pom.xml"
            pom_path.write_text(pom_path.read_text().replace("1.2.3", "1.2.4"))

    node = build_remediate_simple_node(
        PomMutationAdapter(
            mode=ExecutionMode.LIVE,
            openrewrite_runner=StubOpenRewriteRunner(),  # type: ignore[arg-type]
        )
    )

    update = node(
        state.model_copy(
            update={
                "maven_plan": MavenExecutionPlan(
                    repository="payments-service",
                    command=["./mvnw"],
                    root_pom_path=str(workspace / "pom.xml"),
                    uses_wrapper=True,
                )
            }
        )
    )

    assert calls[0][0] == "org.openrewrite.java.dependencies.UpgradeDependencyVersion"
    assert calls[0][1] == {
        "groupId": "org.example",
        "artifactId": "legacy-json",
        "newVersion": "1.2.4",
    }
    assert Path(update["modified_files"][0]).read_text().count("1.2.4") == 1


def test_remediate_transitive_node_uses_openrewrite_in_live_mode(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    state = build_state(tmp_path, transitive=True)
    workspace = Path(state.repo_map["payments-service"].local_path)
    seed_workspace_pom(workspace, fixture_dir / "pom_transitive_before.xml")
    calls: list[tuple[str, dict[str, str] | None]] = []

    class StubOpenRewriteRunner:
        def apply_recipe(
            self,
            cwd: Path,
            *,
            recipe_name: str,
            execution_plan: MavenExecutionPlan | None = None,
            recipe_options: dict[str, str] | None = None,
        ) -> None:
            calls.append((recipe_name, recipe_options))
            pom_path = cwd / "pom.xml"
            pom_path.write_text(
                pom_path.read_text().replace(
                    "</project>",
                    (
                        "<dependencyManagement><dependencies><dependency>"
                        "<groupId>org.example</groupId><artifactId>legacy-json</artifactId>"
                        "<version>1.2.4</version></dependency></dependencies></dependencyManagement></project>"
                    ),
                )
            )

    node = build_remediate_transitive_node(
        PomMutationAdapter(
            mode=ExecutionMode.LIVE,
            openrewrite_runner=StubOpenRewriteRunner(),  # type: ignore[arg-type]
        )
    )

    update = node(
        state.model_copy(
            update={
                "maven_plan": MavenExecutionPlan(
                    repository="payments-service",
                    command=["./mvnw"],
                    root_pom_path=str(workspace / "pom.xml"),
                    uses_wrapper=True,
                )
            }
        )
    )

    assert calls[0][0] == "org.openrewrite.maven.AddManagedDependency"
    assert calls[0][1] == {
        "groupId": "org.example",
        "artifactId": "legacy-json",
        "version": "1.2.4",
    }
    assert Path(update["modified_files"][0]).read_text().count("1.2.4") == 1


def test_remediation_nodes_require_workspace_pom(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    node = build_remediate_simple_node(
        PomMutationAdapter(
            fixture_before_path=fixture_dir / "pom_before.xml",
            fixture_after_path=fixture_dir / "pom_after.xml",
        )
    )
    state = build_state(tmp_path)

    with pytest.raises(WorkspaceError, match="workspace pom missing; clone failed"):
        node(state)


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


def test_preflight_validation_node_uses_live_dependency_tree(tmp_path) -> None:
    state = build_state(tmp_path)

    class StubMavenRunner:
        def dependency_tree(
            self,
            cwd: Path,
            *,
            settings_xml: Path | None = None,
            jdk_home: Path | None = None,
        ) -> list[object]:
            return [
                __import__("execution_accelerator.execution", fromlist=["DependencyTreeEntry"]).DependencyTreeEntry(
                    coordinate=DependencyCoordinate(
                        group_id="org.example",
                        artifact_id="legacy-json",
                        version="1.2.4",
                    ),
                    packaging="jar",
                    scope="compile",
                    direct=True,
                )
            ]

    node = build_preflight_validation_node(
        PreflightResolutionAdapter(
            mode=ExecutionMode.LIVE,
            maven_runner=StubMavenRunner(),  # type: ignore[arg-type]
        )
    )

    update = node(
        state.model_copy(
            update={
                "current_working_repo": "payments-service",
                "maven_plan": MavenExecutionPlan(
                    repository="payments-service",
                    command=["./mvnw"],
                    root_pom_path=str(Path(state.repo_map["payments-service"].local_path) / "pom.xml"),
                    uses_wrapper=True,
                ),
            }
        )
    )

    assert update["preflight_resolution"].status == ValidationStatus.PASSED
    assert update["preflight_resolution"].resolved_version == "1.2.4"
    assert update["preflight_resolution"].dependency_kind == MavenDependencyKind.DIRECT


def test_prepare_complex_remediation_node_records_analysis_placeholders(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    node = build_prepare_complex_remediation_node(
        ComplexRemediationAdapter(
            artifact_fixture_path=fixture_dir / "complex_artifacts.json",
            compatibility_diff_fixture_path=fixture_dir / "compatibility_diff.json",
        )
    )
    state = build_state(tmp_path, complex_refactor=True)

    update = node(state)

    assert update["current_working_repo"] == "payments-service"
    assert len(update["artifact_candidates"]) == 2
    assert update["compatibility_diff"].risk == "high"
    assert update["complex_remediation_plan"].strategy == "complex_refactor"
    assert update["complex_remediation_plan"].migration_tactic == "adapter_shim"
    assert len(update["complex_remediation_plan"].migration_steps) == 2
    assert update["remediation_plan"].summary.startswith("Analyze org.example:legacy-json from 1.2.3 to 2.0.0")
    assert "compatibility adapter" in update["remediation_plan"].rationale
    assert update["audit_events"][-1].event_type == "remediation.complex_prepare"


def test_execute_complex_scaffold_node_records_decompile_and_change_plan(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    adapter = ComplexRemediationAdapter(
        artifact_fixture_path=fixture_dir / "complex_artifacts.json",
        compatibility_diff_fixture_path=fixture_dir / "compatibility_diff.json",
        decompiled_artifact_fixture_path=fixture_dir / "decompiled_artifacts.json",
        symbol_mapping_fixture_path=fixture_dir / "symbol_mappings.json",
        code_change_plan_fixture_path=fixture_dir / "code_change_plan.json",
    )
    prepare_node = build_prepare_complex_remediation_node(adapter)
    scaffold_node = build_execute_complex_scaffold_node(adapter)
    base_state = build_state(tmp_path, complex_refactor=True)
    prepared_state = base_state.model_copy(update=prepare_node(base_state))

    update = scaffold_node(prepared_state)

    assert len(update["decompiled_artifacts"]) == 2
    assert len(update["symbol_mappings"]) == 2
    assert update["code_change_plan"].target_files[0].file_path.endswith("LegacyJsonAdapter.java")
    assert update["complex_remediation_plan"].target_files[0].file_path.endswith("LegacyJsonAdapter.java")
    assert update["complex_remediation_plan"].symbol_mappings[0].legacy_symbol == "org.example.LegacyParser#parse"
    assert update["complex_remediation_plan"].open_questions[0].startswith("Should adapter construction")
    assert len(update["modified_files"]) == 2
    adapter_path = Path(update["modified_files"][0])
    serializer_path = Path(update["modified_files"][1])
    assert adapter_path.read_text().startswith("package com.example.payments;")
    assert "public Object parse(String payload) {" in adapter_path.read_text()
    assert "return org.example.JsonParserBuilder.create().parse(payload);" in adapter_path.read_text()
    assert "public org.example.LegacySerializer createLegacySerializer(boolean enabled) {" in serializer_path.read_text()
    assert (
        "return new org.example.LegacySerializer(org.example.SerializationConfigFactory.create(enabled));"
        in serializer_path.read_text()
    )
    assert update["code_diffs"][0].file_path.endswith("LegacyJsonAdapter.java")
    assert update["remediation_plan"].summary.endswith("Executed bounded complex migration edits for 2 files.")
    assert "2 planned target files, 0 detected existing source files, and 2 unresolved questions" in update["remediation_plan"].rationale
    assert update["audit_events"][-1].event_type == "remediation.complex_scaffold"


def test_execute_complex_scaffold_node_rewrites_existing_java_symbols(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    adapter = ComplexRemediationAdapter(
        artifact_fixture_path=fixture_dir / "complex_artifacts.json",
        compatibility_diff_fixture_path=fixture_dir / "compatibility_diff.json",
        decompiled_artifact_fixture_path=fixture_dir / "decompiled_artifacts.json",
        symbol_mapping_fixture_path=fixture_dir / "symbol_mappings.json",
        code_change_plan_fixture_path=fixture_dir / "code_change_plan.json",
    )
    prepare_node = build_prepare_complex_remediation_node(adapter)
    scaffold_node = build_execute_complex_scaffold_node(adapter)
    base_state = build_state(tmp_path, complex_refactor=True)
    prepared_state = base_state.model_copy(update=prepare_node(base_state))
    existing_target = (
        Path(prepared_state.repo_map["payments-service"].local_path)
        / "src/main/java/com/example/payments/LegacyJsonAdapter.java"
    )
    existing_target.parent.mkdir(parents=True, exist_ok=True)
    existing_target.write_text(
        "\n".join(
            [
                "package com.example.payments;",
                "",
                "public final class LegacyJsonAdapter {",
                "    String parse(String payload) {",
                "        return LegacyParser.parse(payload);",
                "    }",
                "}",
                "",
            ]
        )
    )

    update = scaffold_node(prepared_state)

    rendered_text = existing_target.read_text()
    assert "LegacyParser.parse(payload)" not in rendered_text
    assert "org.example.JsonParserBuilder.create().parse(payload)" in rendered_text
    assert "Execution Accelerator complex scaffold." in rendered_text
    assert update["code_diffs"][0].additions >= 1
    assert update["code_diffs"][0].deletions >= 1


def test_execute_complex_scaffold_node_removes_obsolete_exact_java_imports(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    adapter = ComplexRemediationAdapter(
        artifact_fixture_path=fixture_dir / "complex_artifacts.json",
        compatibility_diff_fixture_path=fixture_dir / "compatibility_diff.json",
        decompiled_artifact_fixture_path=fixture_dir / "decompiled_artifacts.json",
        symbol_mapping_fixture_path=fixture_dir / "symbol_mappings.json",
        code_change_plan_fixture_path=fixture_dir / "code_change_plan.json",
    )
    prepare_node = build_prepare_complex_remediation_node(adapter)
    scaffold_node = build_execute_complex_scaffold_node(adapter)
    base_state = build_state(tmp_path, complex_refactor=True)
    prepared_state = base_state.model_copy(update=prepare_node(base_state))
    existing_target = (
        Path(prepared_state.repo_map["payments-service"].local_path)
        / "src/main/java/com/example/payments/LegacyJsonAdapter.java"
    )
    existing_target.parent.mkdir(parents=True, exist_ok=True)
    existing_target.write_text(
        "\n".join(
            [
                "package com.example.payments;",
                "",
                "import org.example.LegacyParser;",
                "",
                "public final class LegacyJsonAdapter {",
                "    String parsePayload(String payload) {",
                "        return LegacyParser.parse(payload);",
                "    }",
                "}",
                "",
            ]
        )
    )

    update = scaffold_node(prepared_state)

    rendered_text = existing_target.read_text()
    assert "import org.example.LegacyParser;" not in rendered_text
    assert "LegacyParser.parse(payload)" not in rendered_text
    assert "org.example.JsonParserBuilder.create().parse(payload)" in rendered_text
    adapter_diff = next(diff for diff in update["code_diffs"] if diff.file_path.endswith("LegacyJsonAdapter.java"))
    assert adapter_diff.additions >= 1
    assert adapter_diff.deletions >= 1


def test_execute_complex_scaffold_node_preserves_still_used_exact_java_imports(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    adapter = ComplexRemediationAdapter(
        artifact_fixture_path=fixture_dir / "complex_artifacts.json",
        compatibility_diff_fixture_path=fixture_dir / "compatibility_diff.json",
        decompiled_artifact_fixture_path=fixture_dir / "decompiled_artifacts.json",
        symbol_mapping_fixture_path=fixture_dir / "symbol_mappings.json",
        code_change_plan_fixture_path=fixture_dir / "code_change_plan.json",
    )
    prepare_node = build_prepare_complex_remediation_node(adapter)
    scaffold_node = build_execute_complex_scaffold_node(adapter)
    base_state = build_state(tmp_path, complex_refactor=True)
    prepared_state = base_state.model_copy(update=prepare_node(base_state))
    existing_target = (
        Path(prepared_state.repo_map["payments-service"].local_path)
        / "src/main/java/com/example/payments/LegacyJsonAdapter.java"
    )
    existing_target.parent.mkdir(parents=True, exist_ok=True)
    existing_target.write_text(
        "\n".join(
            [
                "package com.example.payments;",
                "",
                "import org.example.LegacyParser;",
                "",
                "public final class LegacyJsonAdapter {",
                "    LegacyParser currentParser() {",
                "        return null;",
                "    }",
                "",
                "    String parsePayload(String payload) {",
                "        return LegacyParser.parse(payload);",
                "    }",
                "}",
                "",
            ]
        )
    )

    scaffold_node(prepared_state)

    rendered_text = existing_target.read_text()
    assert "import org.example.LegacyParser;" in rendered_text
    assert "LegacyParser currentParser()" in rendered_text
    assert "org.example.JsonParserBuilder.create().parse(payload)" in rendered_text


def test_execute_complex_scaffold_node_rewrites_java_method_references(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    adapter = ComplexRemediationAdapter(
        artifact_fixture_path=fixture_dir / "complex_artifacts.json",
        compatibility_diff_fixture_path=fixture_dir / "compatibility_diff.json",
        decompiled_artifact_fixture_path=fixture_dir / "decompiled_artifacts.json",
        symbol_mapping_fixture_path=fixture_dir / "symbol_mappings.json",
        code_change_plan_fixture_path=fixture_dir / "code_change_plan.json",
    )
    prepare_node = build_prepare_complex_remediation_node(adapter)
    scaffold_node = build_execute_complex_scaffold_node(adapter)
    base_state = build_state(tmp_path, complex_refactor=True)
    prepared_state = base_state.model_copy(update=prepare_node(base_state))
    existing_target = (
        Path(prepared_state.repo_map["payments-service"].local_path)
        / "src/main/java/com/example/payments/LegacyJsonAdapter.java"
    )
    existing_target.parent.mkdir(parents=True, exist_ok=True)
    existing_target.write_text(
        "\n".join(
            [
                "package com.example.payments;",
                "",
                "public final class LegacyJsonAdapter {",
                "    Object parser() {",
                "        return LegacyParser::parse;",
                "    }",
                "}",
                "",
            ]
        )
    )

    update = scaffold_node(prepared_state)

    rendered_text = existing_target.read_text()
    assert "LegacyParser::parse" not in rendered_text
    assert "org.example.JsonParserBuilder.create()::parse" in rendered_text
    assert "Execution Accelerator complex scaffold." in rendered_text
    adapter_diff = next(diff for diff in update["code_diffs"] if diff.file_path.endswith("LegacyJsonAdapter.java"))
    assert adapter_diff.additions >= 1
    assert adapter_diff.deletions >= 1


def test_execute_complex_scaffold_node_rewrites_static_imported_java_calls(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    adapter = ComplexRemediationAdapter(
        artifact_fixture_path=fixture_dir / "complex_artifacts.json",
        compatibility_diff_fixture_path=fixture_dir / "compatibility_diff.json",
        decompiled_artifact_fixture_path=fixture_dir / "decompiled_artifacts.json",
        symbol_mapping_fixture_path=fixture_dir / "symbol_mappings.json",
        code_change_plan_fixture_path=fixture_dir / "code_change_plan.json",
    )
    prepare_node = build_prepare_complex_remediation_node(adapter)
    scaffold_node = build_execute_complex_scaffold_node(adapter)
    base_state = build_state(tmp_path, complex_refactor=True)
    prepared_state = base_state.model_copy(update=prepare_node(base_state))
    existing_target = (
        Path(prepared_state.repo_map["payments-service"].local_path)
        / "src/main/java/com/example/payments/LegacyJsonAdapter.java"
    )
    existing_target.parent.mkdir(parents=True, exist_ok=True)
    existing_target.write_text(
        "\n".join(
            [
                "package com.example.payments;",
                "",
                "import static org.example.LegacyParser.parse;",
                "",
                "public final class LegacyJsonAdapter {",
                "    String parsePayload(String payload) {",
                "        return parse(payload);",
                "    }",
                "}",
                "",
            ]
        )
    )

    update = scaffold_node(prepared_state)

    rendered_text = existing_target.read_text()
    assert "import static org.example.LegacyParser.parse;" not in rendered_text
    assert "return parse(payload);" not in rendered_text
    assert "return org.example.JsonParserBuilder.create().parse(payload);" in rendered_text
    assert "Execution Accelerator complex scaffold." in rendered_text
    adapter_diff = next(diff for diff in update["code_diffs"] if diff.file_path.endswith("LegacyJsonAdapter.java"))
    assert adapter_diff.additions >= 1
    assert adapter_diff.deletions >= 1


def test_execute_complex_scaffold_node_rewrites_existing_java_constructor_symbols(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    adapter = ComplexRemediationAdapter(
        artifact_fixture_path=fixture_dir / "complex_artifacts.json",
        compatibility_diff_fixture_path=fixture_dir / "compatibility_diff.json",
        decompiled_artifact_fixture_path=fixture_dir / "decompiled_artifacts.json",
        symbol_mapping_fixture_path=fixture_dir / "symbol_mappings.json",
        code_change_plan_fixture_path=fixture_dir / "code_change_plan.json",
    )
    prepare_node = build_prepare_complex_remediation_node(adapter)
    scaffold_node = build_execute_complex_scaffold_node(adapter)
    base_state = build_state(tmp_path, complex_refactor=True)
    prepared_state = base_state.model_copy(update=prepare_node(base_state))
    existing_target = (
        Path(prepared_state.repo_map["payments-service"].local_path)
        / "src/main/java/com/example/payments/LegacySerializerConfig.java"
    )
    existing_target.parent.mkdir(parents=True, exist_ok=True)
    existing_target.write_text(
        "\n".join(
            [
                "package com.example.payments;",
                "",
                "public final class LegacySerializerConfig {",
                "    Object createSerializer() {",
                "        return new LegacySerializer(true);",
                "    }",
                "}",
                "",
            ]
        )
    )

    update = scaffold_node(prepared_state)

    rendered_text = existing_target.read_text()
    assert "new LegacySerializer(true)" not in rendered_text
    assert "new LegacySerializer(org.example.SerializationConfigFactory.create(true))" in rendered_text
    assert "Execution Accelerator complex scaffold." in rendered_text
    serializer_diff = next(diff for diff in update["code_diffs"] if diff.file_path.endswith("LegacySerializerConfig.java"))
    assert serializer_diff.additions >= 1
    assert serializer_diff.deletions >= 1


def test_execute_complex_scaffold_node_rewrites_java_constructor_references(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    adapter = ComplexRemediationAdapter(
        artifact_fixture_path=fixture_dir / "complex_artifacts.json",
        compatibility_diff_fixture_path=fixture_dir / "compatibility_diff.json",
        decompiled_artifact_fixture_path=fixture_dir / "decompiled_artifacts.json",
        symbol_mapping_fixture_path=fixture_dir / "symbol_mappings.json",
        code_change_plan_fixture_path=fixture_dir / "code_change_plan.json",
    )
    prepare_node = build_prepare_complex_remediation_node(adapter)
    scaffold_node = build_execute_complex_scaffold_node(adapter)
    base_state = build_state(tmp_path, complex_refactor=True)
    prepared_state = base_state.model_copy(update=prepare_node(base_state))
    existing_target = (
        Path(prepared_state.repo_map["payments-service"].local_path)
        / "src/main/java/com/example/payments/LegacySerializerConfig.java"
    )
    existing_target.parent.mkdir(parents=True, exist_ok=True)
    existing_target.write_text(
        "\n".join(
            [
                "package com.example.payments;",
                "",
                "public final class LegacySerializerConfig {",
                "    Object serializerFactory() {",
                "        return LegacySerializer::new;",
                "    }",
                "}",
                "",
            ]
        )
    )

    update = scaffold_node(prepared_state)

    rendered_text = existing_target.read_text()
    assert "LegacySerializer::new" not in rendered_text
    assert "enabled -> new org.example.LegacySerializer(org.example.SerializationConfigFactory.create(enabled))" in rendered_text
    assert "Execution Accelerator complex scaffold." in rendered_text
    serializer_diff = next(diff for diff in update["code_diffs"] if diff.file_path.endswith("LegacySerializerConfig.java"))
    assert serializer_diff.additions >= 1
    assert serializer_diff.deletions >= 1


def test_execute_complex_scaffold_node_rewrites_detected_unplanned_java_sources(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    adapter = ComplexRemediationAdapter(
        artifact_fixture_path=fixture_dir / "complex_artifacts.json",
        compatibility_diff_fixture_path=fixture_dir / "compatibility_diff.json",
        decompiled_artifact_fixture_path=fixture_dir / "decompiled_artifacts.json",
        symbol_mapping_fixture_path=fixture_dir / "symbol_mappings.json",
        code_change_plan_fixture_path=fixture_dir / "code_change_plan.json",
    )
    prepare_node = build_prepare_complex_remediation_node(adapter)
    scaffold_node = build_execute_complex_scaffold_node(adapter)
    base_state = build_state(tmp_path, complex_refactor=True)
    prepared_state = base_state.model_copy(update=prepare_node(base_state))
    existing_target = (
        Path(prepared_state.repo_map["payments-service"].local_path)
        / "src/main/java/com/example/payments/LegacyJsonConsumer.java"
    )
    existing_target.parent.mkdir(parents=True, exist_ok=True)
    existing_target.write_text(
        "\n".join(
            [
                "package com.example.payments;",
                "",
                "public final class LegacyJsonConsumer {",
                "    String parse(String payload) {",
                "        return LegacyParser.parse(payload);",
                "    }",
                "}",
                "",
            ]
        )
    )

    update = scaffold_node(prepared_state)

    rendered_text = existing_target.read_text()
    assert "LegacyParser.parse(payload)" not in rendered_text
    assert "org.example.JsonParserBuilder.create().parse(payload)" in rendered_text
    assert "Execution Accelerator complex scaffold." not in rendered_text
    extra_diff = next(diff for diff in update["code_diffs"] if diff.file_path.endswith("LegacyJsonConsumer.java"))
    assert extra_diff.change_summary == "Apply supported complex migration rewrites for detected legacy API usage."
    assert update["remediation_plan"].summary.endswith("Executed bounded complex migration edits for 3 files.")


def test_execute_complex_scaffold_node_rewrites_wildcard_static_imported_calls_in_detected_sources(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    adapter = ComplexRemediationAdapter(
        artifact_fixture_path=fixture_dir / "complex_artifacts.json",
        compatibility_diff_fixture_path=fixture_dir / "compatibility_diff.json",
        decompiled_artifact_fixture_path=fixture_dir / "decompiled_artifacts.json",
        symbol_mapping_fixture_path=fixture_dir / "symbol_mappings.json",
        code_change_plan_fixture_path=fixture_dir / "code_change_plan.json",
    )
    prepare_node = build_prepare_complex_remediation_node(adapter)
    scaffold_node = build_execute_complex_scaffold_node(adapter)
    base_state = build_state(tmp_path, complex_refactor=True)
    prepared_state = base_state.model_copy(update=prepare_node(base_state))
    existing_target = (
        Path(prepared_state.repo_map["payments-service"].local_path)
        / "src/main/java/com/example/payments/LegacyJsonConsumer.java"
    )
    existing_target.parent.mkdir(parents=True, exist_ok=True)
    existing_target.write_text(
        "\n".join(
            [
                "package com.example.payments;",
                "",
                "import static org.example.LegacyParser.*;",
                "",
                "public final class LegacyJsonConsumer {",
                "    String parsePayload(String payload) {",
                "        return parse(payload);",
                "    }",
                "}",
                "",
            ]
        )
    )

    update = scaffold_node(prepared_state)

    rendered_text = existing_target.read_text()
    assert "import static org.example.LegacyParser.*;" in rendered_text
    assert "return parse(payload);" not in rendered_text
    assert "return org.example.JsonParserBuilder.create().parse(payload);" in rendered_text
    assert "Execution Accelerator complex scaffold." not in rendered_text
    extra_diff = next(diff for diff in update["code_diffs"] if diff.file_path.endswith("LegacyJsonConsumer.java"))
    assert extra_diff.change_summary == "Apply supported complex migration rewrites for detected legacy API usage."


def test_execute_complex_scaffold_node_rewrites_detected_java_static_fields_and_cleans_imports(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    symbol_mappings = json.loads((fixture_dir / "symbol_mappings.json").read_text())
    symbol_mappings["symbol_mappings"].append(
        {
            "legacy_symbol": "org.example.LegacyParser#DEFAULT_MODE",
            "replacement_symbol": "org.example.JsonParserDefaults#STRICT_MODE",
            "confidence": 0.88,
            "rationale": "The legacy default parser mode constant moved to JsonParserDefaults.",
        }
    )
    symbol_mapping_path = tmp_path / "symbol_mappings_with_field.json"
    symbol_mapping_path.write_text(json.dumps(symbol_mappings))
    adapter = ComplexRemediationAdapter(
        artifact_fixture_path=fixture_dir / "complex_artifacts.json",
        compatibility_diff_fixture_path=fixture_dir / "compatibility_diff.json",
        decompiled_artifact_fixture_path=fixture_dir / "decompiled_artifacts.json",
        symbol_mapping_fixture_path=symbol_mapping_path,
        code_change_plan_fixture_path=fixture_dir / "code_change_plan.json",
    )
    prepare_node = build_prepare_complex_remediation_node(adapter)
    scaffold_node = build_execute_complex_scaffold_node(adapter)
    base_state = build_state(tmp_path, complex_refactor=True)
    prepared_state = base_state.model_copy(update=prepare_node(base_state))
    existing_target = (
        Path(prepared_state.repo_map["payments-service"].local_path)
        / "src/main/java/com/example/payments/LegacyJsonConsumer.java"
    )
    existing_target.parent.mkdir(parents=True, exist_ok=True)
    existing_target.write_text(
        "\n".join(
            [
                "package com.example.payments;",
                "",
                "import org.example.LegacyParser;",
                "",
                "public final class LegacyJsonConsumer {",
                "    Object defaultMode() {",
                "        return LegacyParser.DEFAULT_MODE;",
                "    }",
                "}",
                "",
            ]
        )
    )

    update = scaffold_node(prepared_state)

    rendered_text = existing_target.read_text()
    assert "import org.example.LegacyParser;" not in rendered_text
    assert "LegacyParser.DEFAULT_MODE" not in rendered_text
    assert "org.example.JsonParserDefaults.STRICT_MODE" in rendered_text
    assert "Execution Accelerator complex scaffold." not in rendered_text
    extra_diff = next(diff for diff in update["code_diffs"] if diff.file_path.endswith("LegacyJsonConsumer.java"))
    assert extra_diff.change_summary == "Apply supported complex migration rewrites for detected legacy API usage."


def test_execute_complex_scaffold_node_rewrites_exact_static_imported_java_fields(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    symbol_mappings = json.loads((fixture_dir / "symbol_mappings.json").read_text())
    symbol_mappings["symbol_mappings"].append(
        {
            "legacy_symbol": "org.example.LegacyParser#DEFAULT_MODE",
            "replacement_symbol": "org.example.JsonParserDefaults#STRICT_MODE",
            "confidence": 0.88,
            "rationale": "The legacy default parser mode constant moved to JsonParserDefaults.",
        }
    )
    symbol_mapping_path = tmp_path / "symbol_mappings_with_static_field.json"
    symbol_mapping_path.write_text(json.dumps(symbol_mappings))
    adapter = ComplexRemediationAdapter(
        artifact_fixture_path=fixture_dir / "complex_artifacts.json",
        compatibility_diff_fixture_path=fixture_dir / "compatibility_diff.json",
        decompiled_artifact_fixture_path=fixture_dir / "decompiled_artifacts.json",
        symbol_mapping_fixture_path=symbol_mapping_path,
        code_change_plan_fixture_path=fixture_dir / "code_change_plan.json",
    )
    prepare_node = build_prepare_complex_remediation_node(adapter)
    scaffold_node = build_execute_complex_scaffold_node(adapter)
    base_state = build_state(tmp_path, complex_refactor=True)
    prepared_state = base_state.model_copy(update=prepare_node(base_state))
    existing_target = (
        Path(prepared_state.repo_map["payments-service"].local_path)
        / "src/main/java/com/example/payments/LegacyJsonConsumer.java"
    )
    existing_target.parent.mkdir(parents=True, exist_ok=True)
    existing_target.write_text(
        "\n".join(
            [
                "package com.example.payments;",
                "",
                "import static org.example.LegacyParser.DEFAULT_MODE;",
                "",
                "public final class LegacyJsonConsumer {",
                "    Object defaultMode() {",
                "        return DEFAULT_MODE;",
                "    }",
                "}",
                "",
            ]
        )
    )

    update = scaffold_node(prepared_state)

    rendered_text = existing_target.read_text()
    assert "import static org.example.LegacyParser.DEFAULT_MODE;" not in rendered_text
    assert "return DEFAULT_MODE;" not in rendered_text
    assert "return org.example.JsonParserDefaults.STRICT_MODE;" in rendered_text
    assert "Execution Accelerator complex scaffold." not in rendered_text
    extra_diff = next(diff for diff in update["code_diffs"] if diff.file_path.endswith("LegacyJsonConsumer.java"))
    assert extra_diff.change_summary == "Apply supported complex migration rewrites for detected legacy API usage."
