from __future__ import annotations

from pathlib import Path

from execution_accelerator.execution import parse_surefire_report, parse_surefire_reports


def test_parse_surefire_report_parses_single_testsuite() -> None:
    summary = parse_surefire_report(
        """
        <testsuite name="com.example.LegacyJsonTest" tests="5" failures="1" errors="0" skipped="1">
        </testsuite>
        """
    )

    assert len(summary.suites) == 1
    assert summary.suites[0].name == "com.example.LegacyJsonTest"
    assert summary.total_tests == 5
    assert summary.total_failures == 1
    assert summary.total_skipped == 1
    assert summary.passed is False


def test_parse_surefire_report_parses_testsuites_root() -> None:
    summary = parse_surefire_report(
        """
        <testsuites>
          <testsuite name="A" tests="2" failures="0" errors="0" skipped="0" />
          <testsuite name="B" tests="3" failures="0" errors="1" skipped="0" />
        </testsuites>
        """
    )

    assert len(summary.suites) == 2
    assert summary.total_tests == 5
    assert summary.total_errors == 1
    assert summary.passed is False


def test_parse_surefire_reports_aggregates_report_directory(tmp_path: Path) -> None:
    reports_dir = tmp_path / "surefire-reports"
    reports_dir.mkdir()
    (reports_dir / "TEST-a.xml").write_text('<testsuite name="A" tests="2" failures="0" errors="0" skipped="0" />')
    (reports_dir / "TEST-b.xml").write_text('<testsuite name="B" tests="3" failures="0" errors="0" skipped="1" />')
    (reports_dir / "ignored.xml").write_text('<testsuite name="ignored" tests="99" failures="0" errors="0" skipped="0" />')

    summary = parse_surefire_reports(reports_dir)

    assert [suite.name for suite in summary.suites] == ["A", "B"]
    assert summary.total_tests == 5
    assert summary.total_skipped == 1
    assert summary.passed is True
