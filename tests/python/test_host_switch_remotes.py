"""Regression: host switch (domain ↔ LAN) must retarget matching clone remotes."""

from __future__ import annotations

from labdesk_ui.windows.main_window import MainWindow


def test_after_account_switch_reports_retarget_count(qapp, monkeypatch):
    """UI must surface how many origins were rewritten after a host change."""
    notes: list[str] = []

    win = MainWindow.__new__(MainWindow)
    win._view_widgets = {}
    win._repo_windows = []
    win.set_detail = lambda text: notes.append(text)
    win.refresh_connection_banner = lambda: None
    win._prune_repo_windows_silent = lambda: None

    MainWindow._after_account_switch(
        win,
        {"retargeted": 3, "base_url": "http://192.168.0.214:8929"},
    )

    assert notes
    assert "3" in notes[0]
    assert "192.168.0.214" in notes[0]


def test_after_account_switch_no_retarget_message(qapp):
    notes: list[str] = []
    win = MainWindow.__new__(MainWindow)
    win._view_widgets = {}
    win._repo_windows = []
    win.set_detail = lambda text: notes.append(text)
    win.refresh_connection_banner = lambda: None
    win._prune_repo_windows_silent = lambda: None

    MainWindow._after_account_switch(
        win,
        {"retargeted": 0, "base_url": "https://gitlab.example.com"},
    )
    assert notes == ["Active host: https://gitlab.example.com"]
