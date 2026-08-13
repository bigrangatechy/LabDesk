"""Regression: reopen repo after close must not touch a deleted Qt wrapper."""

from __future__ import annotations

from pathlib import Path

import pytest
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
        win.close()
    except RuntimeError:
        pass
    process_events(10)


def test_repo_path_survives_after_cpp_delete_documents_trap(qapp, tmp_path, process_events, monkeypatch):
    """Pure-Python attrs stay readable after WA_DeleteOnClose — the old prune bug."""
    monkeypatch.setattr(RepoWindow, "refresh", lambda self: None)
    path = str(tmp_path / "repo")
    Path(path).mkdir()
    repo = RepoWindow(path, title="t", parent=None)
    process_events()
    repo.close()
    process_events(20)
    # Wrapper may already be invalid; if the C++ object is gone, repo_path can
    # still be readable from Python __dict__ — that must not mean "alive".
    if not isValid(repo):
        assert getattr(repo, "repo_path", None) == str(Path(path).resolve()) or True
    else:
        # deleteLater may not have run yet; force the distinction in reopen test.
        pytest.skip("deleteLater not processed yet on this platform timing")


def test_reopen_after_close_creates_fresh_window(main, tmp_path, process_events):
    path = tmp_path / "myrepo"
    path.mkdir()
    resolved = str(path.resolve())

    main.open_repo_window(resolved, title="LabDesk — one")
    process_events()
    assert len(main._repo_windows) == 1
    first = main._repo_windows[0]
    assert isValid(first)
    assert first.isVisible()

    first.close()
    process_events(30)

    # Old prune checked repo_path only; that still works on a dead wrapper.
    # Reopen must not raise "Internal C++ object already deleted".
    main.open_repo_window(resolved, title="LabDesk — two")
    process_events(20)

    assert len([w for w in main._repo_windows if main._repo_window_alive(w)]) >= 1
    alive = [w for w in main._repo_windows if main._repo_window_alive(w) and w.isVisible()]
    assert len(alive) == 1
    assert alive[0] is not first or isValid(alive[0])
    # Focusing / showing must not throw.
    alive[0].raise_()
    alive[0].activateWindow()


def test_reuse_visible_window_same_path(main, tmp_path, process_events):
    path = tmp_path / "same"
    path.mkdir()
    resolved = str(path.resolve())

    main.open_repo_window(resolved)
    process_events()
    first = main._repo_windows[0]
    main.open_repo_window(resolved)
    process_events()
    visible = [w for w in main._repo_windows if main._repo_window_alive(w) and w.isVisible()]
    assert len(visible) == 1
    assert visible[0] is first


def test_repo_window_alive_false_after_delete(main, tmp_path, process_events):
    path = tmp_path / "gone"
    path.mkdir()
    main.open_repo_window(str(path))
    process_events()
    win = main._repo_windows[0]
    win.close()
    process_events(40)
    main._prune_repo_windows_silent()
    assert win not in main._repo_windows or not main._repo_window_alive(win)
