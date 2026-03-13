from __future__ import annotations

from execution_accelerator.services import compare_versions, is_affected, is_fix_version, pick_lowest_fix_version


def test_compare_versions_handles_numeric_and_qualifier_cases() -> None:
    cases = [
        ("1.2.3", "1.2.3", 0),
        ("1.2.3", "1.2.4", -1),
        ("1.2.10", "1.2.2", 1),
        ("2.0.0", "1.9.9", 1),
        ("1.0.0-alpha", "1.0.0-beta", -1),
        ("1.0.0-rc1", "1.0.0", -1),
        ("1.0.0", "1.0.0-sp1", -1),
        ("1.0.0-final", "1.0.0", 0),
        ("1.0.0", "1.0", 0),
        ("1.0.1", "1.0", 1),
    ]

    for left, right, expected in cases:
        result = compare_versions(left, right)
        assert result == expected


def test_is_affected_supports_exact_open_closed_and_union_ranges() -> None:
    cases = [
        ("1.2.3", ["1.2.3"], True),
        ("1.2.4", ["1.2.3"], False),
        ("1.2.3", ["[1.2.0,1.2.3]"], True),
        ("1.2.4", ["[1.2.0,1.2.3]"], False),
        ("1.2.3", ["[1.2.0,1.2.4)"], True),
        ("1.2.4", ["[1.2.0,1.2.4)"], False),
        ("1.1.9", ["(,1.2.0)"], True),
        ("1.2.0", ["(,1.2.0)"], False),
        ("2.0.0", ["[2.0.0,)"], True),
        ("1.9.9", ["[2.0.0,)"], False),
        ("1.0.5", ["(,1.0.0],[1.0.5,)"], True),
        ("1.0.3", ["(,1.0.0],[1.0.5,)"], False),
    ]

    for version, specs, expected in cases:
        assert is_affected(version, specs) is expected


def test_is_fix_version_and_pick_lowest_fix_version() -> None:
    affected_ranges = ["[1.0.0,1.2.4)"]
    versions = [
        "0.9.9",
        "1.0.0",
        "1.1.0",
        "1.2.3",
        "1.2.4",
        "1.2.5",
        "2.0.0",
    ]

    cases = [
        ("0.9.9", False),
        ("1.0.0", False),
        ("1.2.3", False),
        ("1.2.4", True),
        ("1.2.5", True),
        ("2.0.0", True),
    ]
    for version, expected in cases:
        assert is_fix_version(version, current_version="1.2.3", affected_ranges=affected_ranges) is expected

    assert pick_lowest_fix_version(
        versions,
        current_version="1.2.3",
        affected_ranges=affected_ranges,
    ) == "1.2.4"


def test_pick_lowest_fix_version_returns_none_when_no_fix_exists() -> None:
    assert (
        pick_lowest_fix_version(
            ["1.0.0", "1.0.1", "1.0.2"],
            current_version="1.0.0",
            affected_ranges=["[1.0.0,)"],
        )
        is None
    )
