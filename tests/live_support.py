from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import threading


@dataclass(frozen=True)
class ResponseSpec:
    status: int
    body: bytes
    content_type: str = "application/json"


@contextmanager
def serve_routes(
    routes: dict[tuple[str, str], ResponseSpec],
    *,
    requests_log: list[tuple[str, str, bytes]] | None = None,
) -> Iterator[str]:
    requests = requests_log if requests_log is not None else []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._serve("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._serve("POST")

        def do_PATCH(self) -> None:  # noqa: N802
            self._serve("PATCH")

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def _serve(self, method: str) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            requests.append((method, self.path, body))
            route_key = (method, self.path)
            if route_key not in routes:
                route_key = (method, self.path.split("?", 1)[0])
            response = routes.get(route_key, ResponseSpec(status=404, body=b"{}"))
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            self.wfile.write(response.body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def create_live_repo(
    repo_path: Path,
    *,
    pom_text: str,
    dependency_tree_output: str,
    dynamic_legacy_json_version: bool = False,
    surefire_report_xml: str | None = None,
    verify_exit_code: int = 0,
    simulate_openrewrite: bool = False,
) -> Path:
    repo_path.mkdir(parents=True, exist_ok=True)
    (repo_path / "pom.xml").write_text(pom_text)
    mvnw = repo_path / "mvnw"
    dependency_tree_body = (
        "  version=$(python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "import re\n"
        "pom = Path('pom.xml').read_text()\n"
        "match = re.search(r'<artifactId>legacy-json</artifactId>\\s*<version>([^<]+)</version>', pom)\n"
        "print(match.group(1) if match else '1.2.3')\n"
        "PY\n"
        ")\n"
        "  printf '[INFO] org.example:payments-service:jar:1.0.0\\n'\n"
        "  printf '[INFO] +- org.example:legacy-json:jar:%s:compile\\n' \"$version\"\n"
        if dynamic_legacy_json_version
        else f"  cat <<'EOF'\n{dependency_tree_output}\nEOF\n"
    )
    if surefire_report_xml is not None:
        verify_body = (
            "  mkdir -p target/surefire-reports\n"
            "  cat <<'EOF' > target/surefire-reports/TEST-demo.xml\n"
            f"{surefire_report_xml}\n"
            "EOF\n"
        )
    else:
        verify_body = ""
    verify_body += (
        "  echo \"[ERROR] BUILD FAILURE\" >&2\n"
        f"  exit {verify_exit_code}\n"
        if verify_exit_code
        else "  echo \"[INFO] BUILD SUCCESS\"\n  exit 0\n"
    )
    openrewrite_body = (
        "if [ \"$1\" = \"org.openrewrite.maven:rewrite-maven-plugin:run\" ] || "
        "[ \"$1\" = \"org.openrewrite.maven:rewrite-maven-plugin:dryRun\" ]; then\n"
        "  target_version=\"\"\n"
        "  for arg in \"$@\"; do\n"
        "    case \"$arg\" in\n"
        "      -Drewrite.newVersion=*) target_version=\"${arg#*=}\" ;;\n"
        "      -Drewrite.version=*) target_version=\"${arg#*=}\" ;;\n"
        "    esac\n"
        "  done\n"
        "  if [ \"$1\" = \"org.openrewrite.maven:rewrite-maven-plugin:run\" ] && [ -n \"$target_version\" ]; then\n"
        "    EA_REWRITE_TARGET=\"$target_version\" python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "import os\n"
        "import re\n"
        "target = os.environ['EA_REWRITE_TARGET']\n"
        "pom_path = Path('pom.xml')\n"
        "pom_text = pom_path.read_text()\n"
        "updated = re.sub(\n"
        "    r'(<artifactId>legacy-json</artifactId>\\s*<version>)([^<]+)(</version>)',\n"
        "    rf'\\g<1>{target}\\g<3>',\n"
        "    pom_text,\n"
        "    count=1,\n"
        ")\n"
        "pom_path.write_text(updated)\n"
        "PY\n"
        "  fi\n"
        "  echo \"[INFO] Rewrite complete\"\n"
        "  exit 0\n"
        "fi\n"
        if simulate_openrewrite
        else ""
    )
    mvnw.write_text(
        "#!/bin/sh\n"
        f"{openrewrite_body}"
        "if [ \"$1\" = \"dependency:tree\" ]; then\n"
        f"{dependency_tree_body}"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1\" = \"help:effective-pom\" ]; then\n"
        "  cat pom.xml\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1\" = \"verify\" ]; then\n"
        f"{verify_body}"
        "  exit 0\n"
        "fi\n"
        "echo \"[INFO] OK\"\n"
    )
    mvnw.chmod(0o755)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "pom.xml", "mvnw"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)
    return repo_path


def create_live_remote_repo(
    root_dir: Path,
    *,
    pom_text: str,
    dependency_tree_output: str,
    dynamic_legacy_json_version: bool = False,
    surefire_report_xml: str | None = None,
    verify_exit_code: int = 0,
    simulate_openrewrite: bool = False,
) -> Path:
    working_repo = create_live_repo(
        root_dir / "source-repo",
        pom_text=pom_text,
        dependency_tree_output=dependency_tree_output,
        dynamic_legacy_json_version=dynamic_legacy_json_version,
        surefire_report_xml=surefire_report_xml,
        verify_exit_code=verify_exit_code,
        simulate_openrewrite=simulate_openrewrite,
    )
    remote_repo = root_dir / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote_repo)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote_repo)], cwd=working_repo, check=True, capture_output=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=working_repo, check=True, capture_output=True)
    return remote_repo
