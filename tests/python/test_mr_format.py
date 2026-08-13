"""Merge request / compare UI helpers."""

from __future__ import annotations

from labdesk_ui.windows.repo_window import _format_mr_row


def test_format_mr_row():
    row = _format_mr_row(
        {
            "iid": 12,
            "title": "Ship Flatpak",
            "state": "opened",
            "source_branch": "feature/fp",
            "target_branch": "main",
        }
    )
    assert row.startswith("!12 ")
    assert "Ship Flatpak" in row
    assert "[opened]" in row
    assert "feature/fp → main" in row
