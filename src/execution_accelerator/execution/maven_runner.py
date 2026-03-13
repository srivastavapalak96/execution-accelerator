from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
from typing import Final
from typing import Any

from defusedxml import ElementTree as DefusedET
import httpx

from execution_accelerator.schemas import DependencyCoordinate

from .sandbox import CommandResult, run_command


_DEFAULT_MAVEN_TIMEOUT: Final[float] = 600.0
_DEPENDENCY_LINE_PATTERN = re.compile(
    r"^(?:\[INFO\]\s*)?(?P<prefix>(?:\|  |   )*)(?P<branch>\+-|\\-)\s+"
    r"(?P<group>[^:]+):(?P<artifact>[^:]+):(?P<packaging>[^:]+):(?P<version>[^:]+)(?::(?P<scope>[^\s:]+))?"
)


@dataclass(frozen=True)
class DependencyTreeEntry:
    """One parsed dependency tree entry."""

    coordinate: DependencyCoordinate
    packaging: str
    scope: str | None
    direct: bool


@dataclass(frozen=True)
class MavenMetadata:
    """Normalized Maven metadata contents."""

    coordinate: DependencyCoordinate
    versions: tuple[str, ...]
    latest: str | None = None
    release: str | None = None


class MavenCommandError(RuntimeError):
    """Raised when a Maven subprocess exits unsuccessfully."""

    def __init__(self, action: str, result: CommandResult) -> None:
        self.action = action
        self.result = result
        super().__init__(f"maven {action} failed with exit code {result.returncode}")


@dataclass
class MavenRunner:
    """Thin wrapper around mvn or ./mvnw with metadata helpers."""

    log_dir: Path
    metadata_base_url: str = "https://repo1.maven.org/maven2"
    timeout: float = _DEFAULT_MAVEN_TIMEOUT
    settings_xml: Path | None = None
    java_home: Path | None = None

    def run(
        self,
        cwd: Path,
        args: list[str],
        *,
        settings_xml: Path | None = None,
        jdk_home: Path | None = None,
        action: str = "run",
    ) -> CommandResult:
        command = [self._resolve_maven_executable(cwd), *self._build_common_args(settings_xml=settings_xml), *args]
        result = run_command(
            command,
            cwd=Path(cwd).resolve(),
            timeout=self.timeout,
            env=self._build_env(jdk_home=jdk_home),
            log_path=Path(self.log_dir).resolve() / f"maven-{action}.log",
        )
        if result.returncode != 0:
            raise MavenCommandError(action, result)
        return result

    def dependency_tree(
        self,
        cwd: Path,
        *,
        settings_xml: Path | None = None,
        jdk_home: Path | None = None,
    ) -> list[DependencyTreeEntry]:
        result = self.run(
            cwd,
            ["dependency:tree"],
            settings_xml=settings_xml,
            jdk_home=jdk_home,
            action="dependency-tree",
        )
        return parse_dependency_tree(result.stdout)

    def effective_pom(
        self,
        cwd: Path,
        *,
        settings_xml: Path | None = None,
        jdk_home: Path | None = None,
    ) -> str:
        result = self.run(
            cwd,
            ["help:effective-pom", "-DforceStdout"],
            settings_xml=settings_xml,
            jdk_home=jdk_home,
            action="effective-pom",
        )
        return result.stdout

    def verify(
        self,
        cwd: Path,
        *,
        settings_xml: Path | None = None,
        jdk_home: Path | None = None,
    ) -> CommandResult:
        return self.run(
            cwd,
            ["verify"],
            settings_xml=settings_xml,
            jdk_home=jdk_home,
            action="verify",
        )

    def fetch_metadata(
        self,
        coordinate: DependencyCoordinate,
        *,
        base_url: str | None = None,
    ) -> MavenMetadata:
        metadata_url = build_metadata_url(coordinate, base_url=base_url or self.metadata_base_url)
        response = httpx.get(metadata_url, timeout=30.0)
        response.raise_for_status()
        return parse_maven_metadata(response.text, coordinate=coordinate)

    def _resolve_maven_executable(self, cwd: Path) -> str:
        wrapper = Path(cwd).resolve() / "mvnw"
        if wrapper.exists():
            return str(wrapper)
        return "mvn"

    def _build_common_args(self, *, settings_xml: Path | None) -> list[str]:
        resolved_settings = settings_xml or self.settings_xml
        if resolved_settings is None:
            return []
        return ["-s", str(Path(resolved_settings).resolve())]

    def _build_env(self, *, jdk_home: Path | None) -> dict[str, str] | None:
        resolved_java_home = jdk_home or self.java_home
        if resolved_java_home is None:
            return None
        env = os.environ.copy()
        env["JAVA_HOME"] = str(Path(resolved_java_home).resolve())
        return env


def build_metadata_url(coordinate: DependencyCoordinate, *, base_url: str) -> str:
    group_path = coordinate.group_id.replace(".", "/")
    return (
        f"{base_url.rstrip('/')}/{group_path}/{coordinate.artifact_id}/maven-metadata.xml"
    )


def parse_dependency_tree(output: str) -> list[DependencyTreeEntry]:
    entries: list[DependencyTreeEntry] = []
    for raw_line in output.splitlines():
        line = raw_line.strip("\n")
        match = _DEPENDENCY_LINE_PATTERN.match(line)
        if match is None:
            continue
        prefix = match.group("prefix")
        depth = len(prefix) // 3
        entries.append(
            DependencyTreeEntry(
                coordinate=DependencyCoordinate(
                    group_id=match.group("group"),
                    artifact_id=match.group("artifact"),
                    version=match.group("version"),
                ),
                packaging=match.group("packaging"),
                scope=match.group("scope"),
                direct=depth == 0,
            )
        )
    return entries


def parse_maven_metadata(xml_text: str, *, coordinate: DependencyCoordinate) -> MavenMetadata:
    root = DefusedET.fromstring(xml_text)
    versions = tuple(
        element.text.strip()
        for element in root.findall("./versioning/versions/version")
        if element.text and element.text.strip()
    )
    latest = _find_optional_text(root, "./versioning/latest")
    release = _find_optional_text(root, "./versioning/release")
    return MavenMetadata(
        coordinate=coordinate,
        versions=versions,
        latest=latest,
        release=release,
    )


def _find_optional_text(root: Any, path: str) -> str | None:
    element = root.find(path)
    if element is None or element.text is None:
        return None
    stripped = element.text.strip()
    return stripped or None
