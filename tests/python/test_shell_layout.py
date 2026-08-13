"""Sidebar/classic shell must not leave click-eating overlays."""

from __future__ import annotations

from labdesk_ui.windows.main_window import MainWindow


def _main(monkeypatch, process_events, shell: str) -> MainWindow:
    monkeypatch.setattr(MainWindow, "refresh_connection_banner", lambda self: None)
    monkeypatch.setattr(MainWindow, "_apply_saved_theme", lambda self: None)
    monkeypatch.setattr(MainWindow, "_saved_ui_shell", lambda self: shell)
    monkeypatch.setattr(MainWindow, "_saved_active_view", lambda self: "projects")
    win = MainWindow()
    process_events()
    return win


def test_sidebar_parks_unused_column_off_mainwindow(qapp, monkeypatch, process_events):
    win = _main(monkeypatch, process_events, "sidebar")
    try:
        # Orphan QMainWindow children cover the central widget and steal clicks.
        assert win._column.parent() is not win
        assert win._column.parent() is win._body
        assert win._column.isHidden()
        assert not win.stack.isHidden()
        assert not win._nav_host.isHidden()
        # Switch classic → sidebar again and ensure no MainWindow overlays accumulate.
        win._apply_shell("classic")
        process_events()
        win._apply_shell("sidebar")
        process_events()
        assert win._column.parent() is not win
        assert win._column.isHidden()
        for child in (win.stack, win._nav_host, win._column):
            assert child.parent() is not win
    finally:
        win.close()
        process_events(20)


def test_classic_shows_column(qapp, monkeypatch, process_events):
    win = _main(monkeypatch, process_events, "classic")
    try:
        assert not win._column.isHidden()
        assert win._column.parent() is win._body
    finally:
        win.close()
        process_events(20)
