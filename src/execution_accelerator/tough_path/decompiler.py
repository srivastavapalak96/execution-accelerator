"""Step 3a of the tough-path ladder: download + decompile JAR pairs.

Given a Maven coordinate, ``download_artifact`` fetches the JAR from a Maven
repository (Maven Central by default) into a sha256-keyed cache under
``.local/cache/jars/{group}/{artifact}/{version}/{sha256}.jar``.

``decompile_jar`` invokes the CFR decompiler at ``tools/cfr.jar`` (set up by
``make bootstrap-tools``) and writes Java source files into
``.local/cache/decompiled/{coord}/{sha256}/``.

When ``tools/cfr.jar`` is missing, ``decompile_jar`` raises
:class:`DecompilerToolMissing` so the ladder can fall through to the LLM lane
or escalate cleanly. Tests inject a fake ``cfr_jar`` path or short-circuit via
``cfr_invoker`` for hermetic coverage.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx

from execution_accelerator.schemas import DependencyCoordinate

DEFAULT_MAVEN_BASE_URL: Final[str] = "https://repo1.maven.org/maven2"
DEFAULT_CACHE_ROOT: Final[Path] = Path(".local/cache")
DEFAULT_CFR_JAR_PATH: Final[Path] = Path(__file__).resolve().parents[3] / "tools" / "cfr.jar"


class DecompilerError(RuntimeError):
    """Base error for decompile-step failures."""


class DecompilerToolMissing(DecompilerError):
    """Raised when ``tools/cfr.jar`` (or another required CLI) is unavailable."""


class DecompilerDownloadError(DecompilerError):
    """Raised when the JAR could not be fetched from the Maven repository."""


@dataclass(frozen=True)
class DecompiledArtifact:
    """Bundle returned by :func:`decompile_jar`."""

    coordinate: DependencyCoordinate
    jar_path: Path
    jar_sha256: str
    decompiled_dir: Path
    class_count: int


def download_artifact(
    coordinate: DependencyCoordinate,
    *,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    base_url: str = DEFAULT_MAVEN_BASE_URL,
    fetcher: Callable[[str], bytes] | None = None,
) -> tuple[Path, str]:
    """Fetch ``coordinate`` from the Maven repository, cache it, return ``(path, sha256)``.

    ``fetcher`` short-circuits the HTTP call for tests. Default behavior makes
    a real ``httpx.get`` against ``base_url``.
    """

    jars_dir = cache_root / "jars" / coordinate.group_id.replace(".", "/") / coordinate.artifact_id / coordinate.version
    jars_dir.mkdir(parents=True, exist_ok=True)

    # If a previously-cached jar exists, reuse it. We do not redownload because
    # Maven coordinates are immutable.
    existing = sorted(jars_dir.glob("*.jar"))
    if existing:
        cached = existing[0]
        return cached, _hash_file(cached)

    url = build_artifact_url(coordinate, base_url=base_url)
    body = (fetcher or _httpx_fetch)(url)
    if not body:
        raise DecompilerDownloadError(f"Empty body returned for {url}")
    sha256 = hashlib.sha256(body).hexdigest()
    target = jars_dir / f"{sha256}.jar"
    target.write_bytes(body)
    return target, sha256


def decompile_jar(
    coordinate: DependencyCoordinate,
    *,
    jar_path: Path,
    jar_sha256: str,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    cfr_jar: Path | None = None,
    cfr_invoker: Callable[[Sequence[str]], None] | None = None,
) -> DecompiledArtifact:
    """Decompile ``jar_path`` via CFR into the cache directory and return the bundle.

    ``cfr_invoker`` short-circuits the actual CFR subprocess for tests; default
    behavior shells out to ``java -jar tools/cfr.jar``.
    """

    cfr_jar_path = cfr_jar or DEFAULT_CFR_JAR_PATH
    coord_slug = f"{coordinate.group_id}__{coordinate.artifact_id}__{coordinate.version}"
    output_dir = cache_root / "decompiled" / coord_slug / jar_sha256
    if not output_dir.exists():
        if cfr_invoker is None:
            if not cfr_jar_path.exists():
                raise DecompilerToolMissing(
                    f"CFR jar not found at {cfr_jar_path}; run `make bootstrap-tools` to install."
                )
            cfr_invoker = _real_cfr_invoker
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            cfr_invoker(
                [
                    "java",
                    "-jar",
                    str(cfr_jar_path),
                    str(jar_path),
                    "--outputdir",
                    str(output_dir),
                ]
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            shutil.rmtree(output_dir, ignore_errors=True)
            raise DecompilerError(f"CFR failed on {jar_path}: {exc}") from exc

    class_count = sum(1 for _ in output_dir.rglob("*.java"))
    return DecompiledArtifact(
        coordinate=coordinate,
        jar_path=jar_path,
        jar_sha256=jar_sha256,
        decompiled_dir=output_dir,
        class_count=class_count,
    )


def build_artifact_url(coordinate: DependencyCoordinate, *, base_url: str = DEFAULT_MAVEN_BASE_URL) -> str:
    group_path = coordinate.group_id.replace(".", "/")
    return (
        f"{base_url.rstrip('/')}/{group_path}/{coordinate.artifact_id}/"
        f"{coordinate.version}/{coordinate.artifact_id}-{coordinate.version}.jar"
    )


def _httpx_fetch(url: str) -> bytes:
    try:
        response = httpx.get(url, timeout=60.0, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise DecompilerDownloadError(f"HTTP fetch failed for {url}: {exc}") from exc
    return response.content


def _real_cfr_invoker(cmd: Sequence[str]) -> None:
    subprocess.run(list(cmd), check=True, capture_output=True, timeout=300)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
