from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from execution_accelerator.schemas import MavenExecutionPlan
from execution_accelerator.state import RepositoryWorkspace


_MAVEN_NAMESPACE = {"m": "http://maven.apache.org/POM/4.0.0"}


def detect_maven_execution_plan(
    workspace: RepositoryWorkspace,
    *,
    settings_xml: Path | None = None,
    java_home: Path | None = None,
) -> MavenExecutionPlan:
    """Detect the primary Maven invocation settings for a cloned repository."""

    workspace_path = Path(workspace.local_path)
    root_pom = workspace_path / (workspace.manifest_path or "pom.xml")
    uses_wrapper = (workspace_path / "mvnw").exists()
    command = ["./mvnw"] if uses_wrapper else ["mvn"]
    modules = _read_maven_values(root_pom, ".//m:modules/m:module")
    profiles = _read_maven_values(root_pom, ".//m:profiles/m:profile/m:id")
    return MavenExecutionPlan(
        repository=workspace.name,
        command=command,
        root_pom_path=str(root_pom),
        uses_wrapper=uses_wrapper,
        modules=modules,
        profiles=profiles,
        settings_xml=str(settings_xml) if settings_xml is not None else None,
        java_home=str(java_home) if java_home is not None else None,
    )


def _read_maven_values(root_pom: Path, query: str) -> list[str]:
    if not root_pom.exists():
        return []
    root = ET.fromstring(root_pom.read_text())
    values: list[str] = []
    for element in root.findall(query, _MAVEN_NAMESPACE):
        if element.text:
            stripped = element.text.strip()
            if stripped:
                values.append(stripped)
    return values
