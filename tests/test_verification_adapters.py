from __future__ import annotations

from pathlib import Path
import json

import pytest

from execution_accelerator.adapters import (
    AdvisoryVerificationAdapter,
    AdvisoryVerificationMismatchError,
    MavenVerificationAdapter,
    MavenVerificationMismatchError,
    VerificationConfigurationError,
)
from execution_accelerator.config import load_runtime_config
from execution_accelerator.execution import MavenRunner
from execution_accelerator.schemas import (
    AffectedRepository,
    ExecutionMode,
    MavenDependencyKind,
    MavenExecutionPlan,
    Severity,
    VulnerabilityDetails,
    VerificationStatus,
)
from execution_accelerator.services.advisory import OsvAdvisoryService
from execution_accelerator.state import RepositoryWorkspace
from tests.live_support import ResponseSpec, create_live_repo, serve_routes


def build_vulnerability_details() -> VulnerabilityDetails:
    return VulnerabilityDetails(
        package_name="org.example:legacy-json",
        installed_version="1.2.3",
        fixed_version="1.2.4",
        summary="Verification adapter test vulnerability",
        cve_id="CVE-2026-12345",
        severity=Severity.HIGH,
        affected_repositories=[
            AffectedRepository(name="payments-service", manifest_path="pom.xml")
        ],
    )


def test_advisory_verification_adapter_loads_fixture(tmp_path, monkeypatch) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "advisory_verification.json"
    monkeypatch.setenv("EA_ADVISORY_FIXTURE_PATH", str(fixture_path))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = AdvisoryVerificationAdapter.from_runtime_config(config)

    verification = adapter.load_verification(build_vulnerability_details())

    assert verification.status == VerificationStatus.VERIFIED
    assert verification.recommended_fix_version == "1.2.4"


def test_maven_verification_adapter_loads_fixture(tmp_path, monkeypatch) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "maven_verification.json"
    monkeypatch.setenv("EA_MAVEN_VERIFICATION_FIXTURE_PATH", str(fixture_path))
    config = load_runtime_config(repo_root=tmp_path)
    adapter = MavenVerificationAdapter.from_runtime_config(config)

    verification = adapter.load_verification(
        build_vulnerability_details(),
        target_version="1.2.4",
    )

    assert verification.status == VerificationStatus.VERIFIED
    assert verification.target_version == "1.2.4"


def test_advisory_verification_adapter_requires_configuration() -> None:
    adapter = AdvisoryVerificationAdapter()

    with pytest.raises(VerificationConfigurationError):
        adapter.load_verification(build_vulnerability_details())


def test_maven_verification_adapter_rejects_target_mismatch() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "maven_verification.json"
    adapter = MavenVerificationAdapter(fixture_path=fixture_path)

    with pytest.raises(MavenVerificationMismatchError):
        adapter.load_verification(build_vulnerability_details(), target_version="2.0.0")


def test_advisory_verification_adapter_rejects_package_mismatch() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "advisory_verification.json"
    adapter = AdvisoryVerificationAdapter(fixture_path=fixture_path)
    details = build_vulnerability_details().model_copy(update={"package_name": "org.example:other-lib"})

    with pytest.raises(AdvisoryVerificationMismatchError):
        adapter.load_verification(details)


def test_advisory_verification_adapter_live_queries_osv(tmp_path) -> None:
    details = build_vulnerability_details()
    with serve_routes(
        {
            (
                "POST",
                "/v1/query",
            ): ResponseSpec(
                status=200,
                body=json.dumps(
                    {
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
                                "references": [{"type": "ADVISORY", "url": "https://example.test/advisory"}],
                            }
                        ]
                    }
                ).encode(),
            )
        }
    ) as base_url:
        adapter = AdvisoryVerificationAdapter(
            mode=ExecutionMode.LIVE,
            advisory_service=OsvAdvisoryService(api_base_url=base_url, cache_dir=tmp_path / "cache"),
        )

        verification = adapter.load_verification(details)

    assert verification.status == VerificationStatus.VERIFIED
    assert verification.recommended_fix_version == "1.2.4"
    assert verification.cve_id == "CVE-2026-12345"
    assert verification.references[0].url == "https://example.test/advisory"


def test_maven_verification_adapter_live_reads_dependency_tree_and_metadata(tmp_path) -> None:
    repo_path = create_live_repo(
        tmp_path / "repo",
        pom_text=(
            "<project xmlns=\"http://maven.apache.org/POM/4.0.0\">"
            "<modelVersion>4.0.0</modelVersion>"
            "<groupId>org.example</groupId><artifactId>payments-service</artifactId><version>1.0.0</version>"
            "</project>"
        ),
        dependency_tree_output=(
            "[INFO] org.example:payments-service:jar:1.0.0\n"
            "[INFO] +- org.example:legacy-json:jar:1.2.3:compile\n"
        ),
    )
    metadata_path = "/org/example/legacy-json/maven-metadata.xml"
    with serve_routes(
        {
            (
                "GET",
                metadata_path,
            ): ResponseSpec(
                status=200,
                body=(
                    "<metadata><groupId>org.example</groupId><artifactId>legacy-json</artifactId>"
                    "<versioning><latest>1.2.4</latest><release>1.2.4</release>"
                    "<versions><version>1.2.3</version><version>1.2.4</version></versions>"
                    "</versioning></metadata>"
                ).encode(),
                content_type="application/xml",
            )
        }
    ) as base_url:
        adapter = MavenVerificationAdapter(
            mode=ExecutionMode.LIVE,
            maven_runner=MavenRunner(log_dir=tmp_path / "logs", metadata_base_url=base_url),
            eol_packages_path=tmp_path / "eol_packages.yaml",
        )
        verification = adapter.load_verification(
            build_vulnerability_details(),
            target_version="1.2.4",
            repository_workspace=RepositoryWorkspace(
                name="payments-service",
                local_path=str(repo_path),
                clone_url=str(repo_path),
                default_branch="main",
                build_system="maven",
                manifest_path="pom.xml",
            ),
            maven_plan=MavenExecutionPlan(
                repository="payments-service",
                command=["./mvnw"],
                root_pom_path=str(repo_path / "pom.xml"),
                uses_wrapper=True,
            ),
        )

    assert verification.status == VerificationStatus.VERIFIED
    assert verification.dependency_kind == MavenDependencyKind.DIRECT
    assert verification.target_version == "1.2.4"
