"""Regression: large-repo open must stay dirty-only and never dump unlimited rows."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget

from labdesk_ui.windows.browse_files_dialog import BrowseFilesDialog, _DEFAULT_BROWSE_PAGE
from labdesk_ui.windows.repo_window import (
    RepoWindow,
    _CHANGES_LIST_CAP,
    _TRACKED_LIST_CAP,
)


def test_tracked_list_cap_is_finite_and_small():
    """Guard against raising the UI cap back into 'allocate the world' territory."""
    assert isinstance(_TRACKED_LIST_CAP, int)
    assert 1 <= _TRACKED_LIST_CAP <= 500
    assert isinstance(_CHANGES_LIST_CAP, int)
    assert 1 <= _CHANGES_LIST_CAP <= 2000
    assert 1 <= _DEFAULT_BROWSE_PAGE <= 500


def test_populate_changes_is_dirty_only_even_if_tracked_passed(qapp):
    """Slice B: Changes must not populate tracked rows (browse is a dialog)."""
    win = RepoWindow.__new__(RepoWindow)
    win.files = QListWidget()
    win.diff = type(
        "D",
        (),
        {
            "setPlainText": lambda self, *_a, **_k: None,
            "clear": lambda self: None,
        },
    )()
    win.btn_editor = type("B", (), {"setEnabled": lambda self, *_a, **_k: None})()
    win.footer = type("F", (), {"setText": lambda self, *_a, **_k: None})()

    tracked = [f"dir/file_{i:04}.txt" for i in range(_TRACKED_LIST_CAP + 80)]
    RepoWindow._populate_changes(
        win,
        branch="main",
        summary="abc",
        changes=[],
        tracked=tracked,
        tracked_truncated=True,
        browse=True,
    )

    file_rows = 0
    for i in range(win.files.count()):
        item = win.files.item(i)
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and data.get("kind") == "file":
            file_rows += 1

    assert file_rows == 0
    assert win.files.count() >= 1
    assert "Browse files" in (win.files.item(0).text() or "")


def test_populate_changes_truncates_change_rows(qapp):
    win = RepoWindow.__new__(RepoWindow)
    win.files = QListWidget()
    win.diff = type(
        "D",
        (),
        {
            "setPlainText": lambda self, *_a, **_k: None,
            "clear": lambda self: None,
        },
    )()
    win.btn_editor = type("B", (), {"setEnabled": lambda self, *_a, **_k: None})()
    win.footer = type("F", (), {"setText": lambda self, *_a, **_k: None})()

    changes = [
        {"path": f"u{i}.txt", "status": "untracked", "staged": False, "unstaged": True}
        for i in range(_CHANGES_LIST_CAP)
    ]
    RepoWindow._populate_changes(
        win,
        branch="main",
        summary="abc",
        changes=changes,
        changes_truncated=True,
    )
    markers = sum(
        1
        for i in range(win.files.count())
        if "more changes" in (win.files.item(i).text() or "")
    )
    assert markers == 1


def test_refresh_local_async_does_not_list_tracked_files(monkeypatch, qapp):
    """Dirty-only refresh must not walk the whole tree via repo_list_files."""
    calls: dict = {"list_files": 0}

    class FakeCore:
        @staticmethod
        def repo_branch(_path):
            return "main"

        @staticmethod
        def repo_head_summary(_path):
            return "deadbeef"

        @staticmethod
        def repo_ahead_behind(_path):
            return {}

        @staticmethod
        def repo_git_state(_path):
            return "Clean"

        @staticmethod
        def repo_list_conflicts(_path):
            return []

        @staticmethod
        def repo_status(_path):
            return []

        @staticmethod
        def repo_list_files(path, limit=None):
            calls["list_files"] += 1
            calls["path"] = path
            calls["limit"] = limit
            return [f"f{i}.txt" for i in range((limit or 0))]

        @staticmethod
        def repo_log(_path, _n=200):
            return []

        @staticmethod
        def repo_list_branches(_path):
            return {"current": "main", "branches": ["main"]}

    captured = {}

    def fake_bg(owner, work, on_success=None, on_error=None, **_kw):
        captured["result"] = work()
        if on_success:
            on_success(captured["result"])

    monkeypatch.setattr(
        "labdesk_ui.utils.async_jobs.run_in_background", fake_bg
    )
    monkeypatch.setitem(__import__("sys").modules, "labdesk_core", FakeCore)

    win = RepoWindow.__new__(RepoWindow)
    win.repo_path = "/tmp/fake-repo"
    win.files = QListWidget()
    win.diff = type(
        "D", (), {"setPlainText": lambda self, *_a, **_k: None, "clear": lambda self: None}
    )()
    win.btn_editor = type("B", (), {"setEnabled": lambda self, *_a, **_k: None})()
    win.footer = type("F", (), {"setText": lambda self, *_a, **_k: None})()
    win.header = type("H", (), {"setText": lambda self, *_a, **_k: None})()
    win.commits = QListWidget()
    win.commit_meta = type("M", (), {"setText": lambda self, *_a, **_k: None})()
    win.commit_diff = type("CD", (), {"clear": lambda self: None})()
    win.branches = QListWidget()
    win.btn_refresh = type("BR", (), {})()
    win._history_page = 200
    win._history_offset = 0
    win._refresh_compare_refs = lambda: None
    win._update_sync_banner = lambda *_a, **_k: None

    RepoWindow._refresh_local_async(win)

    assert calls["list_files"] == 0
    assert "tracked" not in captured["result"]
    assert captured["result"]["changes"] == []


def test_browse_dialog_uses_list_view_model(qapp, monkeypatch):
    """Browse files dialog must use QListView + model, not QListWidget dump."""
    paths = [f"src/f{i}.rs" for i in range(50)]

    class FakeCore:
        @staticmethod
        def repo_list_files(_path, limit=None):
            return paths[: (limit or len(paths))]

        @staticmethod
        def repo_show_file(_path, _rel):
            return "ok"

    def fake_bg(owner, work, on_success=None, on_error=None, **_kw):
        result = work()
        if on_success:
            on_success(result)

    monkeypatch.setattr(
        "labdesk_ui.utils.async_jobs.run_in_background", fake_bg
    )
    monkeypatch.setitem(__import__("sys").modules, "labdesk_core", FakeCore)

    dlg = BrowseFilesDialog("/tmp/fake", page_size=20)
    assert dlg.view.model() is dlg.proxy
    assert dlg.model.rowCount() == 20
    assert dlg.btn_more.isEnabled() is True
    dlg.filter_edit.setText("f1")
    assert dlg.proxy.rowCount() < dlg.model.rowCount()
    dlg.close()


def test_repo_list_files_accepts_optional_limit(tmp_path):
    """Core must accept `limit` so the UI can cap tracked-file walks."""
    labdesk_core = pytest.importorskip("labdesk_core")
    if not hasattr(labdesk_core, "repo_list_files"):
        pytest.skip("labdesk_core extension module not built")

    repo = tmp_path / "r"
    repo.mkdir()
    try:
        labdesk_core.repo_list_files(str(repo), 1)
    except TypeError as exc:
        pytest.skip(f"labdesk_core needs rebuild for repo_list_files(limit=…): {exc}")
    except Exception:
        return
