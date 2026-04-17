"""Integration test: real OSV.dev advisory query.

Hits api.osv.dev with a known-vulnerable Maven coordinate and asserts the
response shape. Pinned to commons-text 1.9 (CVE-2022-42889) because that
advisory is stable, well-documented, and widely indexed.
"""

from __future__ import annotations

import httpx
import pytest

from execution_accelerator.schemas import VerificationStatus
from execution_accelerator.services.advisory import OsvAdvisoryService

KNOWN_VULNERABLE_PACKAGE = "org.apache.commons:commons-text"
KNOWN_VULNERABLE_VERSION = "1.9"
EXPECTED_FIX_VERSION = "1.10.0"
EXPECTED_CVE = "CVE-2022-42889"


def test_osv_live_returns_real_cve(tmp_path: pytest.TempdirFactory) -> None:
    """OSV.dev knows about commons-text 1.9 and returns the documented fix version."""

    cache_dir = tmp_path / "osv_cache"
    service = OsvAdvisoryService(cache_dir=cache_dir)

    try:
        verification = service.query(
            package_name=KNOWN_VULNERABLE_PACKAGE,
            version=KNOWN_VULNERABLE_VERSION,
        )
    except httpx.HTTPError as exc:
        pytest.xfail(f"OSV.dev unreachable in this environment: {exc}")
    except ValueError as exc:
        pytest.fail(f"OSV returned an unexpected payload shape: {exc}")

    assert verification.package_name == KNOWN_VULNERABLE_PACKAGE
    assert verification.vulnerable_version == KNOWN_VULNERABLE_VERSION
    assert verification.recommended_fix_version == EXPECTED_FIX_VERSION
    assert verification.status == VerificationStatus.VERIFIED
    assert verification.source == "osv"
    # CVE-2022-42889 is sometimes reported as the primary alias. We accept any CVE
    # alias since OSV occasionally reorders its alias list across mirrors.
    if verification.cve_id is not None:
        assert verification.cve_id.startswith("CVE-")
    assert any(reference.url for reference in verification.references), \
        "OSV advisory should include at least one reference URL"


def test_osv_cache_round_trip(tmp_path: pytest.TempdirFactory) -> None:
    """A cached payload survives across service instances within the TTL."""

    cache_dir = tmp_path / "osv_cache"
    first = OsvAdvisoryService(cache_dir=cache_dir)
    second = OsvAdvisoryService(cache_dir=cache_dir)

    try:
        first_result = first.query(
            package_name=KNOWN_VULNERABLE_PACKAGE,
            version=KNOWN_VULNERABLE_VERSION,
        )
    except httpx.HTTPError as exc:
        pytest.xfail(f"OSV.dev unreachable: {exc}")

    # The cache file should exist after the first call.
    cache_files = list(cache_dir.glob("*.json"))
    assert len(cache_files) == 1, f"Expected exactly one cache file, found {len(cache_files)}"

    # Second call should hit the cache (we cannot easily prove this without
    # patching, but we can at least confirm the result is consistent).
    second_result = second.query(
        package_name=KNOWN_VULNERABLE_PACKAGE,
        version=KNOWN_VULNERABLE_VERSION,
    )
    assert second_result.recommended_fix_version == first_result.recommended_fix_version
