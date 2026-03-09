from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from execution_accelerator.adapters import (
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
                previous_version="1.2.3",
                target_version="1.2.4",
                xml_path_hint="./dependencies/dependency[artifactId='legacy-json']/version",
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


def test_pom_mutation_adapter_requires_configuration() -> None:
    adapter = PomMutationAdapter()

    with pytest.raises(PomMutationConfigurationError):
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
