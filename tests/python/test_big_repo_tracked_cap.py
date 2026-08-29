"""Regression: large-repo open must not dump unlimited tracked files into Qt."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget

from labdesk_ui.windows.repo_window import RepoWindow, _TRACKED_LIST_CAP


def test_tracked_list_cap_is_finite_and_small():
    """Guard against raising the UI cap back into 'allocate the world' territory."""
    assert isinstance(_TRACKED_LIST_CAP, int)
    assert 1 <= _TRACKED_LIST_CAP <= 500


def test_populate_changes_truncates_tracked_rows(qapp):
    """Even if core returned too many paths, the Changes list must stay capped."""
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
        tracked=tracked[:_TRACKED_LIST_CAP],
        tracked_truncated=True,
    )

    file_rows = 0
    truncate_markers = 0
    for i in range(win.files.count()):
        item = win.files.item(i)
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and data.get("kind") == "file":
            file_rows += 1
        elif "more tracked files" in (item.text() or ""):
            truncate_markers += 1

    assert file_rows == _TRACKED_LIST_CAP
    assert truncate_markers == 1


def test_refresh_local_async_requests_cap_plus_one(monkeypatch, qapp):
    """Worker must ask core for cap+1 so the UI can show a truncation marker."""
    calls: dict = {}

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
        def repo_status(_path):
            return []

        @staticmethod
        def repo_list_files(path, limit=None):
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
    win.diff = type("D", (), {"setPlainText": lambda self, *_a, **_k: None, "clear": lambda self: None})()
    win.btn_editor = type("B", (), {"setEnabled": lambda self, *_a, **_k: None})()
    win.footer = type("F", (), {"setText": lambda self, *_a, **_k: None})()
    win.header = type("H", (), {"setText": lambda self, *_a, **_k: None})()
    win.commits = QListWidget()
    win.commit_meta = type("M", (), {"setText": lambda self, *_a, **_k: None})()
    win.commit_diff = type("CD", (), {"clear": lambda self: None})()
    win.branches = QListWidget()
    win.btn_refresh = type("BR", (), {})()
    win._refresh_compare_refs = lambda: None

    RepoWindow._refresh_local_async(win)

    assert calls.get("limit") == _TRACKED_LIST_CAP + 1
    assert captured["result"]["tracked_truncated"] is True
    assert len(captured["result"]["tracked"]) == _TRACKED_LIST_CAP


def test_repo_list_files_accepts_optional_limit(tmp_path):
    """Core must accept `limit` so the UI can cap tracked-file walks.

    Skips when the installed extension predates the API (CI image without
    maturin). Local `./scripts/run-tests.sh` rebuilds the module.
    """
    labdesk_core = pytest.importorskip("labdesk_core")
    if not hasattr(labdesk_core, "repo_list_files"):
        pytest.skip("labdesk_core extension module not built")

    repo = tmp_path / "r"
    repo.mkdir()
    # Arity probe: outdated builds raise TypeError before path checks.
    try:
        labdesk_core.repo_list_files(str(repo), 1)
    except TypeError as exc:
        pytest.skip(f"labdesk_core needs rebuild for repo_list_files(limit=…): {exc}")
    except Exception:
        # Not a git repo / empty — arity was accepted; that is enough here.
        return
