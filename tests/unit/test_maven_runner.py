from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import http.server
import os
import socketserver
import threading
from collections.abc import Iterator

from execution_accelerator.execution import MavenRunner, parse_dependency_tree, parse_maven_metadata
from execution_accelerator.schemas import DependencyCoordinate


def test_parse_dependency_tree_marks_direct_and_transitive_entries() -> None:
    output = "\n".join(
        [
            "[INFO] com.example:demo:jar:1.0.0",
            "[INFO] +- org.example:legacy-json:jar:1.2.3:compile",
            "[INFO] |  \\- org.slf4j:slf4j-api:jar:2.0.11:compile",
            "[INFO] \\- junit:junit:jar:4.13.2:test",
        ]
    )

    entries = parse_dependency_tree(output)

    assert len(entries) == 3
    assert entries[0].coordinate.group_id == "org.example"
    assert entries[0].direct is True
    assert entries[1].coordinate.artifact_id == "slf4j-api"
    assert entries[1].direct is False
    assert entries[2].scope == "test"


def test_parse_maven_metadata_extracts_versions() -> None:
    metadata = parse_maven_metadata(
        """
        <metadata>
          <groupId>org.example</groupId>
          <artifactId>legacy-json</artifactId>
          <versioning>
            <latest>1.2.5</latest>
            <release>1.2.4</release>
            <versions>
              <version>1.2.3</version>
              <version>1.2.4</version>
              <version>1.2.5</version>
            </versions>
          </versioning>
        </metadata>
        """,
        coordinate=DependencyCoordinate(group_id="org.example", artifact_id="legacy-json", version="1.2.3"),
    )

    assert metadata.latest == "1.2.5"
    assert metadata.release == "1.2.4"
    assert metadata.versions == ("1.2.3", "1.2.4", "1.2.5")


def test_maven_runner_uses_wrapper_for_dependency_tree_and_verify(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    wrapper = repo_dir / "mvnw"
    wrapper.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                'case "$*" in',
                '  *"dependency:tree"*)',
                "    cat <<'EOF'",
                "[INFO] com.example:demo:jar:1.0.0",
                "[INFO] +- org.example:legacy-json:jar:1.2.3:compile",
                "EOF",
                "    ;;",
                '  *"help:effective-pom"*)',
                "    cat pom.xml",
                "    ;;",
                '  *"verify"*)',
                "    echo BUILD SUCCESS",
                "    ;;",
                "esac",
            ]
        )
        + "\n"
    )
    wrapper.chmod(0o755)
    (repo_dir / "pom.xml").write_text("<project/>\n")
    runner = MavenRunner(log_dir=tmp_path / "logs")

    tree = runner.dependency_tree(repo_dir)
    effective_pom = runner.effective_pom(repo_dir)
    verify_result = runner.verify(repo_dir)

    assert len(tree) == 1
    assert tree[0].coordinate.artifact_id == "legacy-json"
    assert effective_pom.strip() == "<project/>"
    assert "BUILD SUCCESS" in verify_result.stdout


def test_maven_runner_fetches_metadata_from_http_server(tmp_path: Path) -> None:
    metadata_root = tmp_path / "repo"
    metadata_file = metadata_root / "org" / "example" / "legacy-json" / "maven-metadata.xml"
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    metadata_file.write_text(
        """
        <metadata>
          <versioning>
            <latest>1.2.5</latest>
            <release>1.2.4</release>
            <versions>
              <version>1.2.3</version>
              <version>1.2.4</version>
              <version>1.2.5</version>
            </versions>
          </versioning>
        </metadata>
        """
    )
    coordinate = DependencyCoordinate(group_id="org.example", artifact_id="legacy-json", version="1.2.3")

    with serve_directory(metadata_root) as base_url:
        metadata = MavenRunner(log_dir=tmp_path / "logs", metadata_base_url=base_url).fetch_metadata(coordinate)

    assert metadata.coordinate.artifact_id == "legacy-json"
    assert metadata.release == "1.2.4"
    assert metadata.versions[-1] == "1.2.5"


@contextmanager
def serve_directory(directory: Path) -> Iterator[str]:
    previous_cwd = Path.cwd()
    os.chdir(directory)
    try:
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

        with socketserver.TCPServer(("127.0.0.1", 0), QuietHandler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}"
            finally:
                server.shutdown()
                thread.join()
    finally:
        os.chdir(previous_cwd)
