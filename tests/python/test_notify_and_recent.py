"""Slice H notify chip + recent-repos helpers."""

from __future__ import annotations

from labdesk_ui.windows.repo_window import RepoWindow


def test_update_notify_chip_pipeline_and_mr(qapp):
    win = RepoWindow.__new__(RepoWindow)
    win.notify_chip = type("L", (), {"setText": lambda self, t: setattr(self, "text", t)})()
    win._last_mr_updated = "2020-01-01T00:00:00Z"

    RepoWindow._update_notify_chip(
        win,
        [{"updated_at": "2026-01-01T00:00:00Z"}],
        {"status": "failed", "ref": "main"},
    )
    text = win.notify_chip.text
    assert "Pipeline failed" in text
    assert "MR/PR list updated" in text


def test_update_notify_chip_quiet_when_clean(qapp):
    win = RepoWindow.__new__(RepoWindow)
    win.notify_chip = type("L", (), {"setText": lambda self, t: setattr(self, "text", t)})()
    win._last_mr_updated = None
    RepoWindow._update_notify_chip(win, [], {"status": "success", "ref": "main"})
    assert win.notify_chip.text == ""
