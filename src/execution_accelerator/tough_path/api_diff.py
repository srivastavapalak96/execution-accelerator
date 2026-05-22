"""Step 3b of the tough-path ladder: extract public APIs and diff old vs new.

We do not invoke ``javap`` directly here -- instead we walk the decompiled
``*.java`` output produced by :mod:`decompiler` and extract public class /
method / field signatures with a small line-based parser. This trades a
tiny amount of fidelity (we don't see private bridge methods, package-private
helpers etc.) for the ability to run without an extra JDK round-trip.

The output is a :class:`CompatibilityDiff` describing which symbols were
removed in the new version, which were added, and which had their signature
changed. That feeds the symbol mapper (step 3c).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from execution_accelerator.schemas import CompatibilityChangeType, CompatibilityDiffEntry


_CLASS_DECLARATION = re.compile(
    r"^\s*public\s+(?:(?:final|abstract|static)\s+)*"
    r"(?P<kind>class|interface|enum|@interface)\s+"
    r"(?P<name>[A-Za-z_][\w$]*)"
)
_METHOD_DECLARATION = re.compile(
    r"^\s*public\s+"
    r"(?:(?:static|final|synchronized|native|abstract|default)\s+)*"
    r"(?:<[^>]+>\s+)?"
    r"(?P<return_type>[\w.<>\[\],\s?]+?)\s+"
    r"(?P<name>[A-Za-z_][\w$]*)\s*"
    r"\((?P<params>[^)]*)\)"
)
_FIELD_DECLARATION = re.compile(
    r"^\s*public\s+"
    r"(?:(?:static|final)\s+)*"
    r"(?P<type>[\w.<>\[\],\s?]+?)\s+"
    r"(?P<name>[A-Za-z_][\w$]*)\s*[=;]"
)


@dataclass(frozen=True)
class PublicSymbol:
    """One public API element extracted from a decompiled source tree."""

    fqn: str
    kind: str  # "class" | "method" | "field"
    signature: str

    @property
    def normalized_signature(self) -> str:
        """A whitespace-normalized signature for cross-version equality."""

        return re.sub(r"\s+", " ", self.signature).strip()


@dataclass
class PublicApi:
    """All public symbols extracted from a decompiled artifact."""

    by_fqn: dict[str, PublicSymbol] = field(default_factory=dict)


@dataclass
class CompatibilityDiff:
    """Removed / added / changed public symbols between two artifacts."""

    removed: list[PublicSymbol] = field(default_factory=list)
    added: list[PublicSymbol] = field(default_factory=list)
    changed: list[tuple[PublicSymbol, PublicSymbol]] = field(default_factory=list)

    def to_diff_entries(self) -> list[CompatibilityDiffEntry]:
        """Render as the existing ``CompatibilityDiffEntry`` schema for state persistence."""

        entries: list[CompatibilityDiffEntry] = []
        for sym in self.removed:
            entries.append(
                CompatibilityDiffEntry(
                    symbol=sym.fqn,
                    change_type=CompatibilityChangeType.REMOVED,
                    impact=f"Removed in target version: {sym.normalized_signature}",
                )
            )
        for old_sym, new_sym in self.changed:
            entries.append(
                CompatibilityDiffEntry(
                    symbol=old_sym.fqn,
                    change_type=CompatibilityChangeType.MODIFIED,
                    impact=(
                        f"Signature changed from `{old_sym.normalized_signature}` "
                        f"to `{new_sym.normalized_signature}`."
                    ),
                )
            )
        for sym in self.added:
            entries.append(
                CompatibilityDiffEntry(
                    symbol=sym.fqn,
                    change_type=CompatibilityChangeType.ADDED,
                    impact=f"Added in target version: {sym.normalized_signature}",
                )
            )
        return entries


def extract_public_api(decompiled_dir: Path) -> PublicApi:
    """Walk ``decompiled_dir/**/*.java`` and return all public classes/methods/fields."""

    api = PublicApi()
    for source_path in sorted(decompiled_dir.rglob("*.java")):
        package = _package_for(source_path, root=decompiled_dir)
        current_class: str | None = None
        for line in source_path.read_text(errors="replace").splitlines():
            stripped = line.strip()
            class_match = _CLASS_DECLARATION.match(line)
            if class_match:
                current_class = (
                    f"{package}.{class_match['name']}" if package else class_match["name"]
                )
                api.by_fqn[current_class] = PublicSymbol(
                    fqn=current_class,
                    kind=class_match["kind"],
                    signature=stripped.rstrip("{").strip(),
                )
                continue
            if current_class is None:
                continue
            method_match = _METHOD_DECLARATION.match(line)
            if method_match and "(" in line:
                method_fqn = f"{current_class}#{method_match['name']}({method_match['params'].strip()})"
                api.by_fqn[method_fqn] = PublicSymbol(
                    fqn=method_fqn,
                    kind="method",
                    signature=stripped.rstrip("{").rstrip(";").strip(),
                )
                continue
            field_match = _FIELD_DECLARATION.match(line)
            if field_match:
                field_fqn = f"{current_class}#{field_match['name']}"
                api.by_fqn[field_fqn] = PublicSymbol(
                    fqn=field_fqn,
                    kind="field",
                    signature=stripped.rstrip(";").strip(),
                )
    return api


def diff_public_apis(old: PublicApi, new: PublicApi) -> CompatibilityDiff:
    """Compute removed/added/changed symbols between two public APIs."""

    diff = CompatibilityDiff()
    for fqn, old_symbol in old.by_fqn.items():
        new_symbol = new.by_fqn.get(fqn)
        if new_symbol is None:
            diff.removed.append(old_symbol)
            continue
        if old_symbol.normalized_signature != new_symbol.normalized_signature:
            diff.changed.append((old_symbol, new_symbol))
    for fqn, new_symbol in new.by_fqn.items():
        if fqn not in old.by_fqn:
            diff.added.append(new_symbol)
    return diff


def _package_for(source_path: Path, *, root: Path) -> str:
    """Best-effort package name inferred from the directory structure under ``root``.

    CFR's output mirrors the package directory layout, so the package can be
    derived directly from the relative path; the alternative would be parsing
    the ``package x.y.z;`` line, which is also fine but slightly more work.
    """

    relative = source_path.relative_to(root)
    parts = relative.with_suffix("").parts
    if len(parts) <= 1:
        return ""
    return ".".join(parts[:-1])
