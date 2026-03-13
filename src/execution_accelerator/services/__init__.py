"""Domain services for live verification and remediation decisions."""

from .advisory import OsvAdvisoryService, parse_osv_response
from .version_range import compare_versions, is_affected, is_fix_version, pick_lowest_fix_version

__all__ = [
    "OsvAdvisoryService",
    "compare_versions",
    "is_affected",
    "is_fix_version",
    "parse_osv_response",
    "pick_lowest_fix_version",
]
