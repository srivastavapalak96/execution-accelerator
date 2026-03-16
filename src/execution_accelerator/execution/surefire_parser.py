from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as DefusedET


@dataclass(frozen=True)
class SurefireSuiteResult:
    """One parsed Surefire or Failsafe testsuite summary."""

    name: str
    tests: int
    failures: int
    errors: int
    skipped: int


@dataclass(frozen=True)
class SurefireReportSummary:
    """Aggregate summary over one or more Surefire report files."""

    suites: tuple[SurefireSuiteResult, ...]
    total_tests: int
    total_failures: int
    total_errors: int
    total_skipped: int

    @property
    def passed(self) -> bool:
        return self.total_failures == 0 and self.total_errors == 0


def parse_surefire_report(xml_text: str) -> SurefireReportSummary:
    root = DefusedET.fromstring(xml_text)
    suite_elements = _suite_elements(root)
    suites = tuple(_parse_suite(element) for element in suite_elements)
    return SurefireReportSummary(
        suites=suites,
        total_tests=sum(suite.tests for suite in suites),
        total_failures=sum(suite.failures for suite in suites),
        total_errors=sum(suite.errors for suite in suites),
        total_skipped=sum(suite.skipped for suite in suites),
    )


def parse_surefire_reports(reports_dir: Path) -> SurefireReportSummary:
    suites: list[SurefireSuiteResult] = []
    for report_path in sorted(Path(reports_dir).glob("TEST-*.xml")):
        summary = parse_surefire_report(report_path.read_text())
        suites.extend(summary.suites)
    return SurefireReportSummary(
        suites=tuple(suites),
        total_tests=sum(suite.tests for suite in suites),
        total_failures=sum(suite.failures for suite in suites),
        total_errors=sum(suite.errors for suite in suites),
        total_skipped=sum(suite.skipped for suite in suites),
    )


def _suite_elements(root: Any) -> list[Any]:
    if root.tag == "testsuite":
        return [root]
    if root.tag == "testsuites":
        return list(root.findall("testsuite"))
    raise ValueError(f"Unsupported surefire root element: {root.tag}")


def _parse_suite(element: Any) -> SurefireSuiteResult:
    return SurefireSuiteResult(
        name=_string_attr(element, "name") or "unnamed",
        tests=_int_attr(element, "tests"),
        failures=_int_attr(element, "failures"),
        errors=_int_attr(element, "errors"),
        skipped=_int_attr(element, "skipped"),
    )


def _string_attr(element: Any, name: str) -> str | None:
    value = element.attrib.get(name)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _int_attr(element: Any, name: str) -> int:
    value = _string_attr(element, name)
    if value is None:
        return 0
    return int(value)
