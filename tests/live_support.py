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
def serve_routes(routes: dict[tuple[str, str], ResponseSpec]) -> Iterator[str]:
    requests: list[tuple[str, str, bytes]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._serve("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._serve("POST")

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
) -> Path:
    repo_path.mkdir(parents=True, exist_ok=True)
    (repo_path / "pom.xml").write_text(pom_text)
    mvnw = repo_path / "mvnw"
    mvnw.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"dependency:tree\" ]; then\n"
        f"  cat <<'EOF'\n{dependency_tree_output}\nEOF\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1\" = \"help:effective-pom\" ]; then\n"
        "  cat pom.xml\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1\" = \"verify\" ]; then\n"
        "  echo \"[INFO] BUILD SUCCESS\"\n"
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
