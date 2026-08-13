"""Regression: reopen repo after close must not touch a deleted Qt wrapper."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from shiboken6 import delete as shiboken_delete
from shiboken6 import isValid

from labdesk_ui.windows.main_window import MainWindow
from labdesk_ui.windows.repo_window import RepoWindow


@pytest.fixture
def main(qapp, monkeypatch, process_events):
    # Avoid network / theme / async banner during construction.
    monkeypatch.setattr(MainWindow, "refresh_connection_banner", lambda self: None)
    monkeypatch.setattr(MainWindow, "_apply_saved_theme", lambda self: None)
    monkeypatch.setattr(MainWindow, "_saved_ui_shell", lambda self: "classic")
    monkeypatch.setattr(MainWindow, "_saved_active_view", lambda self: "projects")
    monkeypatch.setattr(RepoWindow, "refresh", lambda self: None)
    monkeypatch.setattr(RepoWindow, "set_network_available", lambda self, *_a, **_k: None)

    win = MainWindow()
    process_events()
    yield win
    try:
        for repo in list(getattr(win, "_repo_windows", []) or []):
            try:
                if isValid(repo):
                    repo.close()
            except RuntimeError:
                pass
        win.close()
    except RuntimeError:
        pass
    process_events(20)


def _force_dead_repo(path: str, monkeypatch, process_events) -> RepoWindow:
    """Build a RepoWindow then destroy the C++ object, keeping the Python wrapper."""
    monkeypatch.setattr(RepoWindow, "refresh", lambda self: None)
    repo = RepoWindow(path, title="t", parent=None)
    repo.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    repo.show()
    process_events()
    assert MainWindow._repo_window_alive(repo) is True
    # Guaranteed invalid wrapper (close+deleteLater timing is flaky under offscreen).
    shiboken_delete(repo)
    process_events(5)
    assert isValid(repo) is False
    return repo


def test_repo_path_readable_after_delete_but_alive_is_false(
    qapp, tmp_path, process_events, monkeypatch
):
    """Documents the trap the old prune used: repo_path survives C++ delete."""
    path = tmp_path / "repo"
    path.mkdir()
    resolved = str(path.resolve())
    repo = _force_dead_repo(resolved, monkeypatch, process_events)

    # Trap: pure-Python attribute still works.
    assert repo.repo_path == resolved
    # Fix: aliveness must not trust repo_path alone.
    assert MainWindow._repo_window_alive(repo) is False


def test_old_path_only_heuristic_would_falsely_match_dead_window(
    qapp, tmp_path, process_events, monkeypatch
):
    """If prune only checked repo_path, a dead wrapper would still 'match'."""
    path = tmp_path / "repo"
    path.mkdir()
    resolved = str(path.resolve())
    repo = _force_dead_repo(resolved, monkeypatch, process_events)

    old_heuristic_match = repo.repo_path == resolved
    assert old_heuristic_match is True
    assert MainWindow._repo_window_alive(repo) is False


def test_reopen_after_close_creates_fresh_window(main, tmp_path, process_events):
    path = tmp_path / "myrepo"
    path.mkdir()
    resolved = str(path.resolve())

    main.open_repo_window(resolved, title="LabDesk — one")
    process_events()
    assert len(main._repo_windows) == 1
    first = main._repo_windows[0]
    first_id = id(first)
    assert isValid(first)
    assert first.isVisible()

    # Destroy C++ object but leave a stale list entry (old bug shape).
    shiboken_delete(first)
    process_events(5)
    assert isValid(first) is False
    main._repo_windows = [first]
    assert first.repo_path == resolved
    assert MainWindow._repo_window_alive(first) is False

    # Must not raise RuntimeError("Internal C++ object already deleted").
    main.open_repo_window(resolved, title="LabDesk — two")
    process_events(20)

    alive = [w for w in main._repo_windows if MainWindow._repo_window_alive(w) and w.isVisible()]
    assert len(alive) == 1
    assert id(alive[0]) != first_id
    assert isValid(alive[0])
    alive[0].raise_()
    alive[0].activateWindow()
    assert "LabDesk" in alive[0].windowTitle()


def test_reuse_visible_window_same_path(main, tmp_path, process_events):
    path = tmp_path / "same"
    path.mkdir()
    resolved = str(path.resolve())

    main.open_repo_window(resolved)
    process_events()
    first = main._repo_windows[0]
    first_id = id(first)
    main.open_repo_window(resolved)
    process_events()
    visible = [w for w in main._repo_windows if MainWindow._repo_window_alive(w) and w.isVisible()]
    assert len(visible) == 1
    assert id(visible[0]) == first_id


def test_prune_removes_invalid_wrappers(main, tmp_path, process_events):
    path = tmp_path / "gone"
    path.mkdir()
    main.open_repo_window(str(path))
    process_events()
    win = main._repo_windows[0]
    shiboken_delete(win)
    process_events(5)
    main._repo_windows = [win]  # stale entry
    main._prune_repo_windows_silent()
    assert win not in main._repo_windows
    assert main._repo_windows == []
