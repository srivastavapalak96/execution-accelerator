"""Unit tests for execution_accelerator.tough_path.decompiler."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

import pytest

from execution_accelerator.schemas import DependencyCoordinate
from execution_accelerator.tough_path.decompiler import (
    DecompilerDownloadError,
    DecompilerToolMissing,
    build_artifact_url,
    decompile_jar,
    download_artifact,
)


def _coordinate() -> DependencyCoordinate:
    return DependencyCoordinate(
        group_id="org.apache.commons",
        artifact_id="commons-text",
        version="1.9",
    )


def test_build_artifact_url_uses_group_path() -> None:
    url = build_artifact_url(_coordinate())
    assert url == (
        "https://repo1.maven.org/maven2/org/apache/commons/commons-text/1.9/"
        "commons-text-1.9.jar"
    )


def test_download_artifact_caches_and_returns_sha(tmp_path: Path) -> None:
    body = b"PK\x03\x04 fake jar bytes"

    def fetcher(_url: str) -> bytes:
        return body

    cache = tmp_path / "cache"
    path, sha = download_artifact(_coordinate(), cache_root=cache, fetcher=fetcher)
    assert path.exists()
    assert path.read_bytes() == body
    assert sha == hashlib.sha256(body).hexdigest()


def test_download_artifact_reuses_cached_jar_without_calling_fetcher(tmp_path: Path) -> None:
    body = b"existing-bytes"
    coord = _coordinate()
    cache = tmp_path / "cache"
    target = cache / "jars" / "org/apache/commons" / "commons-text" / "1.9"
    target.mkdir(parents=True)
    sha = hashlib.sha256(body).hexdigest()
    (target / f"{sha}.jar").write_bytes(body)

    fetcher_calls: list[str] = []

    def fetcher(url: str) -> bytes:
        fetcher_calls.append(url)
        return b""

    path, returned_sha = download_artifact(coord, cache_root=cache, fetcher=fetcher)
    assert path.read_bytes() == body
    assert returned_sha == sha
    assert fetcher_calls == [], "Fetcher must not be invoked when a cached jar exists"


def test_download_artifact_raises_on_empty_body(tmp_path: Path) -> None:
    def fetcher(_url: str) -> bytes:
        return b""

    with pytest.raises(DecompilerDownloadError, match="Empty body"):
        download_artifact(_coordinate(), cache_root=tmp_path, fetcher=fetcher)


def test_decompile_jar_invokes_cfr_and_counts_classes(tmp_path: Path) -> None:
    coord = _coordinate()
    jar_path = tmp_path / "fake.jar"
    jar_path.write_bytes(b"jar")
    sha = "abc123"

    captured: list[Sequence[str]] = []

    def cfr_invoker(cmd: Sequence[str]) -> None:
        captured.append(cmd)
        # Simulate CFR by writing two .java files into the output dir.
        out_index = list(cmd).index("--outputdir")
        outdir = Path(cmd[out_index + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "A.java").write_text("class A {}\n")
        (outdir / "B.java").write_text("class B {}\n")

    result = decompile_jar(
        coord,
        jar_path=jar_path,
        jar_sha256=sha,
        cache_root=tmp_path / "cache",
        cfr_invoker=cfr_invoker,
        cfr_jar=tmp_path / "stub.jar",
    )

    assert result.class_count == 2
    assert result.decompiled_dir.is_dir()
    assert any(str(jar_path) in str(arg) for arg in captured[0])


def test_decompile_jar_short_circuits_when_output_already_exists(tmp_path: Path) -> None:
    coord = _coordinate()
    jar_path = tmp_path / "fake.jar"
    jar_path.write_bytes(b"jar")
    sha = "deadbeef"
    output_dir = (
        tmp_path / "cache" / "decompiled"
        / f"{coord.group_id}__{coord.artifact_id}__{coord.version}" / sha
    )
    output_dir.mkdir(parents=True)
    (output_dir / "Existing.java").write_text("class Existing {}\n")

    invocations = 0

    def cfr_invoker(_cmd: Sequence[str]) -> None:
        nonlocal invocations
        invocations += 1

    result = decompile_jar(
        coord,
        jar_path=jar_path,
        jar_sha256=sha,
        cache_root=tmp_path / "cache",
        cfr_invoker=cfr_invoker,
    )

    assert invocations == 0, "Should not re-invoke CFR when cached output exists"
    assert result.class_count == 1


def test_decompile_jar_raises_when_cfr_missing(tmp_path: Path) -> None:
    coord = _coordinate()
    jar_path = tmp_path / "fake.jar"
    jar_path.write_bytes(b"jar")

    with pytest.raises(DecompilerToolMissing, match="CFR jar not found"):
        decompile_jar(
            coord,
            jar_path=jar_path,
            jar_sha256="x",
            cache_root=tmp_path / "cache",
            cfr_jar=tmp_path / "does-not-exist.jar",
            cfr_invoker=None,
        )
