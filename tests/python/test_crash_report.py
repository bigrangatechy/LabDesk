"""Crash reporting helpers (LD-SYS-001)."""

from __future__ import annotations

from labdesk_ui.utils import crash_report


def test_write_crash_log_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(crash_report, "logs_dir", lambda: tmp_path)
    path = crash_report.write_crash_log("test", "Traceback (most recent call last):\n  boom\n")
    assert path.name == "last-crash.log"
    text = path.read_text(encoding="utf-8")
    assert "LabDesk test" in text
    assert "boom" in text


def test_format_exception_report_includes_type():
    try:
        raise RuntimeError("example failure")
    except RuntimeError as exc:
        report = crash_report.format_exception_report(type(exc), exc, exc.__traceback__)
    assert "RuntimeError" in report
    assert "example failure" in report


def test_install_crash_reporting_idempotent(qapp):
    crash_report._INSTALLED = False
    crash_report.install_crash_reporting()
    crash_report.install_crash_reporting()
    assert crash_report._INSTALLED is True
