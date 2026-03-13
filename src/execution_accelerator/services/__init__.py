"""Domain services for live verification and remediation decisions."""

from .version_range import compare_versions, is_affected, is_fix_version, pick_lowest_fix_version

__all__ = [
    "compare_versions",
    "is_affected",
    "is_fix_version",
    "pick_lowest_fix_version",
]
