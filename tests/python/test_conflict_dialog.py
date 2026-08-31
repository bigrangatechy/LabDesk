"""Conflict resolve dialog structure + wiring smoke tests."""

from __future__ import annotations

from PySide6.QtWidgets import QTabWidget, QTextEdit

from labdesk_ui.windows.conflict_dialog import ConflictDialog


def test_conflict_dialog_has_structured_actions(monkeypatch, qapp, tmp_path):
    """Slice D: ours/theirs/open/mark + Continue/Abort; not a freeform editor."""
    import labdesk_core

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("conflicted\n", encoding="utf-8")

    monkeypatch.setattr(labdesk_core, "repo_list_conflicts", lambda _p: ["a.txt"])
    monkeypatch.setattr(labdesk_core, "repo_git_state", lambda _p: "Merge")
    monkeypatch.setattr(
        labdesk_core,
        "repo_conflict_side_text",
        lambda _p, _path, side: f"{side}-content\n",
    )

    dlg = ConflictDialog(str(repo), mode="merge")
    assert "merge" in dlg.windowTitle().lower()
    assert isinstance(dlg.tabs, QTabWidget)
    assert dlg.tabs.count() == 3
    assert dlg.btn_ours.isEnabled()
    assert dlg.btn_theirs.isEnabled()
    assert dlg.btn_external.isEnabled()
    assert dlg.btn_mark.isEnabled()
    assert not dlg.btn_continue.isEnabled()  # conflicts remain
    assert dlg.btn_abort.isEnabled()
    assert isinstance(dlg.preview_ours, QTextEdit)
    assert dlg.preview_ours.isReadOnly()
    assert dlg.preview_theirs.isReadOnly()
    assert dlg.preview_work.isReadOnly()
    assert dlg.paths.count() == 1
    dlg.close()


def test_conflict_dialog_enables_continue_when_clean(monkeypatch, qapp, tmp_path):
    import labdesk_core

    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(labdesk_core, "repo_list_conflicts", lambda _p: [])
    monkeypatch.setattr(labdesk_core, "repo_git_state", lambda _p: "Clean")

    dlg = ConflictDialog(str(repo), mode="rebase")
    assert "rebase" in dlg.windowTitle().lower()
    assert dlg.btn_continue.isEnabled()
    assert not dlg.btn_ours.isEnabled()
    dlg.close()
