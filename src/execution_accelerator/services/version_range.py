from __future__ import annotations

from dataclasses import dataclass
import re


_SPLIT_PATTERN = re.compile(r"[.\-_\+]")
_TOKEN_PATTERN = re.compile(r"\d+|[a-zA-Z]+")
_QUALIFIER_ORDER = {
    "snapshot": -5,
    "alpha": -4,
    "a": -4,
    "beta": -3,
    "b": -3,
    "milestone": -2,
    "m": -2,
    "rc": -1,
    "cr": -1,
    "": 0,
    "final": 0,
    "ga": 0,
    "release": 0,
    "sp": 1,
}


@dataclass(frozen=True)
class _Bound:
    value: str | None
    inclusive: bool


def compare_versions(left: str, right: str) -> int:
    left_parts = _normalize_parts(left)
    right_parts = _normalize_parts(right)
    max_length = max(len(left_parts), len(right_parts))
    for index in range(max_length):
        left_part = left_parts[index] if index < len(left_parts) else 0
        right_part = right_parts[index] if index < len(right_parts) else 0
        if left_part == right_part:
            continue
        if isinstance(left_part, int) and isinstance(right_part, int):
            return -1 if left_part < right_part else 1
        if isinstance(left_part, int):
            return 1
        if isinstance(right_part, int):
            return -1
        return -1 if left_part < right_part else 1
    return 0


def is_affected(version: str, range_specs: list[str]) -> bool:
    return any(_matches_range(version, range_spec) for range_spec in range_specs)


def is_fix_version(version: str, *, current_version: str, affected_ranges: list[str]) -> bool:
    return compare_versions(version, current_version) > 0 and not is_affected(version, affected_ranges)


def pick_lowest_fix_version(
    versions: list[str],
    *,
    current_version: str,
    affected_ranges: list[str],
) -> str | None:
    ordered_versions = sorted(set(versions), key=_VersionSortKey)
    for candidate in ordered_versions:
        if is_fix_version(candidate, current_version=current_version, affected_ranges=affected_ranges):
            return candidate
    return None


class _VersionSortKey:
    def __init__(self, version: str) -> None:
        self.version = version

    def __lt__(self, other: "_VersionSortKey") -> bool:
        return compare_versions(self.version, other.version) < 0


def _matches_range(version: str, range_spec: str) -> bool:
    spec = range_spec.strip()
    if not spec:
        return False
    if spec[0] not in {"[", "("}:
        return compare_versions(version, spec) == 0

    for segment in _split_union_ranges(spec):
        lower, upper = _parse_segment(segment)
        if _matches_bounds(version, lower=lower, upper=upper):
            return True
    return False


def _split_union_ranges(spec: str) -> list[str]:
    segments: list[str] = []
    depth = 0
    start = 0
    for index, character in enumerate(spec):
        if character in {"[", "("}:
            if depth == 0:
                start = index
            depth += 1
        elif character in {"]", ")"}:
            depth -= 1
            if depth == 0:
                segments.append(spec[start : index + 1])
    return segments or [spec]


def _parse_segment(segment: str) -> tuple[_Bound, _Bound]:
    inclusive_lower = segment.startswith("[")
    inclusive_upper = segment.endswith("]")
    body = segment[1:-1]
    if "," not in body:
        value = body.strip() or None
        exact_bound = _Bound(value=value, inclusive=True)
        return exact_bound, exact_bound
    lower_text, upper_text = body.split(",", 1)
    lower = _Bound(value=lower_text.strip() or None, inclusive=inclusive_lower)
    upper = _Bound(value=upper_text.strip() or None, inclusive=inclusive_upper)
    return lower, upper


def _matches_bounds(version: str, *, lower: _Bound, upper: _Bound) -> bool:
    if lower.value is not None:
        comparison = compare_versions(version, lower.value)
        if comparison < 0 or (comparison == 0 and not lower.inclusive):
            return False
    if upper.value is not None:
        comparison = compare_versions(version, upper.value)
        if comparison > 0 or (comparison == 0 and not upper.inclusive):
            return False
    return True


def _normalize_parts(version: str) -> list[int | str]:
    parts: list[int | str] = []
    for token in _SPLIT_PATTERN.split(version.strip().lower()):
        if not token:
            continue
        for piece in _TOKEN_PATTERN.findall(token):
            if piece.isdigit():
                parts.append(int(piece))
                continue
            parts.append(_QUALIFIER_ORDER.get(piece, piece))
    return parts
