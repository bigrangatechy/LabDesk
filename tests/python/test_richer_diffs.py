"""Slice G richer diff helpers."""

from __future__ import annotations

from PySide6.QtWidgets import QListWidget

from labdesk_ui.windows.repo_window import _diff_looks_truncated, _populate_diff_file_list


def test_diff_looks_truncated_detects_marker():
    assert _diff_looks_truncated("ok\n… (diff truncated)\n") is True
    assert _diff_looks_truncated("plain patch") is False


def test_populate_diff_file_list_binary_badge(qapp):
    from PySide6.QtCore import Qt

    w = QListWidget()
    _populate_diff_file_list(
        w,
        [{"path": "a.txt", "binary": False}, {"path": "bin.dat", "binary": True}],
    )
    assert w.count() == 2
    assert "[binary]" in w.item(1).text()
    assert w.item(1).data(Qt.ItemDataRole.UserRole)["binary"] is True
