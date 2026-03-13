from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any
import re

import httpx

from execution_accelerator.schemas import AdvisoryVerification, Severity, VerificationStatus, VulnerabilityReference


_CACHE_SAFE_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass
class OsvAdvisoryService:
    """Query OSV for Maven advisories with a small on-disk cache."""

    api_base_url: str = "https://api.osv.dev"
    cache_dir: Path | None = None
    cache_ttl_seconds: int = 24 * 60 * 60

    def query(
        self,
        *,
        package_name: str,
        version: str,
        severity: Severity = Severity.UNKNOWN,
        fixed_version_hint: str | None = None,
    ) -> AdvisoryVerification:
        payload = self._load_cached_payload(package_name=package_name, version=version)
        if payload is None:
            payload = self._fetch_payload(package_name=package_name, version=version)
            self._write_cached_payload(package_name=package_name, version=version, payload=payload)
        return parse_osv_response(
            payload,
            package_name=package_name,
            version=version,
            default_severity=severity,
            fixed_version_hint=fixed_version_hint,
        )

    def _fetch_payload(self, *, package_name: str, version: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self.api_base_url.rstrip('/')}/v1/query",
            json={
                "package": {
                    "name": package_name,
                    "ecosystem": "Maven",
                },
                "version": version,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected OSV response type: {type(payload).__name__}")
        return payload

    def _load_cached_payload(self, *, package_name: str, version: str) -> dict[str, Any] | None:
        if self.cache_dir is None:
            return None
        cache_path = self._build_cache_path(package_name=package_name, version=version)
        if not cache_path.exists():
            return None
        age = time.time() - cache_path.stat().st_mtime
        if age > self.cache_ttl_seconds:
            return None
        loaded = json.loads(cache_path.read_text())
        return loaded if isinstance(loaded, dict) else None

    def _write_cached_payload(self, *, package_name: str, version: str, payload: dict[str, Any]) -> None:
        if self.cache_dir is None:
            return
        cache_path = self._build_cache_path(package_name=package_name, version=version)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def _build_cache_path(self, *, package_name: str, version: str) -> Path:
        assert self.cache_dir is not None
        safe_package = _CACHE_SAFE_PATTERN.sub("_", package_name)
        safe_version = _CACHE_SAFE_PATTERN.sub("_", version)
        return Path(self.cache_dir) / f"{safe_package}-{safe_version}.json"


def parse_osv_response(
    payload: dict[str, Any],
    *,
    package_name: str,
    version: str,
    default_severity: Severity,
    fixed_version_hint: str | None,
) -> AdvisoryVerification:
    vulnerabilities = payload.get("vulns")
    if not isinstance(vulnerabilities, list) or not vulnerabilities:
        raise ValueError(f"No OSV advisory found for {package_name}@{version}")

    vulnerability = vulnerabilities[0]
    if not isinstance(vulnerability, dict):
        raise ValueError(f"Unexpected OSV vulnerability type: {type(vulnerability).__name__}")

    recommended_fix_version = _extract_fixed_version(vulnerability) or fixed_version_hint
    if not recommended_fix_version:
        raise ValueError(f"OSV advisory for {package_name}@{version} did not expose a fixed version")

    references = _extract_references(vulnerability)
    cve_id = next((alias for alias in _aliases(vulnerability) if alias.startswith("CVE-")), None)
    return AdvisoryVerification(
        package_name=package_name,
        vulnerable_version=version,
        recommended_fix_version=recommended_fix_version,
        status=VerificationStatus.VERIFIED,
        source="osv",
        summary=_string_field(vulnerability.get("summary")) or f"OSV verified fix for {package_name}",
        cve_id=cve_id,
        severity=_extract_severity(vulnerability, default=default_severity),
        references=references,
    )


def _extract_fixed_version(vulnerability: dict[str, Any]) -> str | None:
    affected = vulnerability.get("affected")
    if not isinstance(affected, list):
        return None
    for item in affected:
        if not isinstance(item, dict):
            continue
        ranges = item.get("ranges")
        if not isinstance(ranges, list):
            continue
        for range_item in ranges:
            if not isinstance(range_item, dict):
                continue
            events = range_item.get("events")
            if not isinstance(events, list):
                continue
            for event in events:
                if not isinstance(event, dict):
                    continue
                fixed = _string_field(event.get("fixed"))
                if fixed:
                    return fixed
    return None


def _extract_references(vulnerability: dict[str, Any]) -> list[VulnerabilityReference]:
    raw_references = vulnerability.get("references")
    if not isinstance(raw_references, list):
        return []
    references: list[VulnerabilityReference] = []
    for item in raw_references:
        if not isinstance(item, dict):
            continue
        url = _string_field(item.get("url"))
        if not url:
            continue
        reference_type = _string_field(item.get("type")) or "reference"
        references.append(
            VulnerabilityReference(
                source=reference_type.lower(),
                identifier=url,
                url=url,
            )
        )
    return references


def _extract_severity(vulnerability: dict[str, Any], *, default: Severity) -> Severity:
    database_specific = vulnerability.get("database_specific")
    if isinstance(database_specific, dict):
        severity = _string_field(database_specific.get("severity"))
        if severity:
            return _normalize_severity(severity)
    return default


def _aliases(vulnerability: dict[str, Any]) -> list[str]:
    aliases = vulnerability.get("aliases")
    if not isinstance(aliases, list):
        return []
    return [alias for alias in aliases if isinstance(alias, str)]


def _string_field(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _normalize_severity(value: str) -> Severity:
    try:
        return Severity(value.lower())
    except ValueError:
        return Severity.UNKNOWN
