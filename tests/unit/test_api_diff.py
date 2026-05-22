"""Unit tests for execution_accelerator.tough_path.api_diff."""

from __future__ import annotations

from pathlib import Path

from execution_accelerator.schemas import CompatibilityChangeType
from execution_accelerator.tough_path.api_diff import (
    PublicApi,
    PublicSymbol,
    diff_public_apis,
    extract_public_api,
)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_extract_public_api_picks_up_class_method_and_field(tmp_path: Path) -> None:
    _write(
        tmp_path / "org" / "example" / "Greeter.java",
        """
package org.example;

public final class Greeter {
    public static final String DEFAULT_GREETING = "Hello";
    public String greet(String name) {
        return DEFAULT_GREETING;
    }
}
""".strip(),
    )

    api = extract_public_api(tmp_path)
    assert "org.example.Greeter" in api.by_fqn
    assert "org.example.Greeter#DEFAULT_GREETING" in api.by_fqn
    assert "org.example.Greeter#greet(String name)" in api.by_fqn
    method = api.by_fqn["org.example.Greeter#greet(String name)"]
    assert method.kind == "method"
    assert "greet" in method.signature


def test_extract_public_api_skips_private_and_package_private(tmp_path: Path) -> None:
    _write(
        tmp_path / "org" / "example" / "Hidden.java",
        """
package org.example;

class PackagePrivate {}

public final class Hidden {
    private String secret;
    public String visible;
}
""".strip(),
    )

    api = extract_public_api(tmp_path)
    assert "org.example.Hidden" in api.by_fqn
    assert "org.example.PackagePrivate" not in api.by_fqn
    assert "org.example.Hidden#secret" not in api.by_fqn
    assert "org.example.Hidden#visible" in api.by_fqn


def test_diff_public_apis_classifies_removed_added_and_changed(tmp_path: Path) -> None:
    old = PublicApi(
        by_fqn={
            "org.example.Greeter": PublicSymbol(
                fqn="org.example.Greeter", kind="class", signature="public final class Greeter"
            ),
            "org.example.Greeter#oldMethod()": PublicSymbol(
                fqn="org.example.Greeter#oldMethod()",
                kind="method",
                signature="public void oldMethod()",
            ),
            "org.example.Greeter#greet(String name)": PublicSymbol(
                fqn="org.example.Greeter#greet(String name)",
                kind="method",
                signature="public String greet(String name)",
            ),
        }
    )
    new = PublicApi(
        by_fqn={
            "org.example.Greeter": PublicSymbol(
                fqn="org.example.Greeter", kind="class", signature="public final class Greeter"
            ),
            "org.example.Greeter#greet(String name)": PublicSymbol(
                fqn="org.example.Greeter#greet(String name)",
                kind="method",
                signature="public String greet(java.lang.String name)",  # signature drift
            ),
            "org.example.Greeter#newMethod()": PublicSymbol(
                fqn="org.example.Greeter#newMethod()",
                kind="method",
                signature="public void newMethod()",
            ),
        }
    )

    diff = diff_public_apis(old, new)
    removed_fqns = {sym.fqn for sym in diff.removed}
    added_fqns = {sym.fqn for sym in diff.added}
    changed_old_fqns = {old.fqn for old, _new in diff.changed}

    assert removed_fqns == {"org.example.Greeter#oldMethod()"}
    assert added_fqns == {"org.example.Greeter#newMethod()"}
    assert changed_old_fqns == {"org.example.Greeter#greet(String name)"}


def test_compatibility_diff_renders_to_schema_entries() -> None:
    old = PublicApi(
        by_fqn={
            "X": PublicSymbol(fqn="X", kind="class", signature="public class X"),
        }
    )
    new = PublicApi(
        by_fqn={
            "Y": PublicSymbol(fqn="Y", kind="class", signature="public class Y"),
        }
    )
    diff = diff_public_apis(old, new)
    entries = diff.to_diff_entries()
    types = {entry.change_type for entry in entries}
    # Removed X, added Y.
    assert CompatibilityChangeType.REMOVED in types
    assert CompatibilityChangeType.ADDED in types
