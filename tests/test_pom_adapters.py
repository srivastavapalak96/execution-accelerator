from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from execution_accelerator.adapters import (
    FixtureOnlyError,
    PomMutationAdapter,
    PomMutationConfigurationError,
    PomMutationTargetError,
    PreflightResolutionAdapter,
)
from execution_accelerator.config import load_runtime_config
from execution_accelerator.schemas import (
    DependencyCoordinate,
    PomMutationChange,
    PomMutationPlan,
    PomMutationKind,
    PomSectionTarget,
    ValidationStatus,
)


def build_plan() -> PomMutationPlan:
    return PomMutationPlan(
        repository="payments-service",
        summary="Bump the vulnerable dependency to the verified fix version.",
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


def build_transitive_plan() -> PomMutationPlan:
    return PomMutationPlan(
        repository="payments-service",
        summary="Add a dependencyManagement override for the transitive vulnerable dependency.",
        changes=[
            PomMutationChange(
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
                xml_path_hint="./dependencyManagement/dependencies/dependency[artifactId='legacy-json']/version",
            )
        ],
    )


def test_pom_mutation_adapter_applies_simple_version_bump(tmp_path, monkeypatch) -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    monkeypatch.setenv("EA_POM_FIXTURE_BEFORE_PATH", str(fixture_dir / "pom_before.xml"))
    monkeypatch.setenv("EA_POM_FIXTURE_AFTER_PATH", str(fixture_dir / "pom_after.xml"))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = PomMutationAdapter.from_runtime_config(config)

    result = adapter.apply_plan(adapter.load_fixture_before(), build_plan())
    version = ET.fromstring(result).find(
        ".//{http://maven.apache.org/POM/4.0.0}dependency/{http://maven.apache.org/POM/4.0.0}version"
    )

    assert version is not None
    assert version.text == "1.2.4"


def test_pom_mutation_adapter_adds_dependency_management_override() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    adapter = PomMutationAdapter(
        fixture_before_path=fixture_dir / "pom_transitive_before.xml",
        fixture_after_path=fixture_dir / "pom_transitive_after.xml",
    )

    result = adapter.apply_plan(adapter.load_fixture_before(), build_transitive_plan())
    root = ET.fromstring(result)
    version = root.find(
        ".//{http://maven.apache.org/POM/4.0.0}dependencyManagement/"
        "{http://maven.apache.org/POM/4.0.0}dependencies/"
        "{http://maven.apache.org/POM/4.0.0}dependency/"
        "{http://maven.apache.org/POM/4.0.0}version"
    )

    assert version is not None
    assert version.text == "1.2.4"


def test_pom_mutation_adapter_requires_configuration() -> None:
    adapter = PomMutationAdapter()

    with pytest.raises(PomMutationConfigurationError):
        adapter.load_fixture_before()


def test_pom_mutation_fixture_helpers_reject_live_mode() -> None:
    adapter = PomMutationAdapter(mode="live")

    with pytest.raises(FixtureOnlyError, match="EA_MODE=fixture"):
        adapter.load_fixture_before()


def test_pom_mutation_adapter_rejects_missing_dependency() -> None:
    adapter = PomMutationAdapter()
    missing_plan = build_plan().model_copy(
        update={
            "changes": [
                build_plan().changes[0].model_copy(
                    update={
                        "dependency": DependencyCoordinate(
                            group_id="org.example",
                            artifact_id="missing-artifact",
                            version="1.2.4",
                        )
                    }
                )
            ]
        }
    )

    with pytest.raises(PomMutationTargetError):
        adapter.apply_plan(Path(__file__).parent.joinpath("fixtures", "pom_before.xml").read_text(), missing_plan)


def test_preflight_resolution_adapter_loads_fixture(tmp_path, monkeypatch) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "preflight_resolution.json"
    monkeypatch.setenv("EA_PREFLIGHT_RESOLUTION_FIXTURE_PATH", str(fixture_path))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = PreflightResolutionAdapter.from_runtime_config(config)

    result = adapter.load_result(repository="payments-service")

    assert result.status == ValidationStatus.PASSED
    assert result.resolved_version == "1.2.4"


def test_preflight_resolution_adapter_loads_transitive_fixture() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "preflight_resolution_transitive.json"
    adapter = PreflightResolutionAdapter(fixture_path=fixture_path)

    result = adapter.load_result(repository="payments-service")

    assert result.status == ValidationStatus.PASSED
    assert result.dependency_kind == "transitive"
