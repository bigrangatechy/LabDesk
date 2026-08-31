"""Slice I from-scratch in-app editor helpers and smoke tests."""

from __future__ import annotations

from pathlib import Path

from labdesk_ui.widgets.code_editor import (
    EDITOR_HARD_MAX_BYTES,
    EditorWindow,
    language_for_path,
    open_code_editor,
    probe_file_for_edit,
)


def test_language_for_path_by_suffix():
    assert language_for_path("a.py") == "python"
    assert language_for_path("src/lib.rs") == "rust"
    assert language_for_path("Cargo.toml") == "toml"
    assert language_for_path("README.md") == "markdown"
    assert language_for_path("noext") == "plain"


def test_probe_file_editable_and_binary(tmp_path: Path):
    text = tmp_path / "ok.py"
    text.write_text("print(1)\n", encoding="utf-8")
    info = probe_file_for_edit(text)
    assert info["mode"] == "editable"

    binary = tmp_path / "blob.bin"
    binary.write_bytes(b"abc\x00def")
    assert probe_file_for_edit(binary)["mode"] == "binary"

    missing = tmp_path / "gone.txt"
    assert probe_file_for_edit(missing)["mode"] == "missing"


def test_probe_file_hard_cap_readonly(tmp_path: Path, monkeypatch):
    big = tmp_path / "huge.txt"
    big.write_text("xx", encoding="utf-8")
    monkeypatch.setattr(
        "labdesk_ui.widgets.code_editor.EDITOR_HARD_MAX_BYTES",
        1,
    )
    info = probe_file_for_edit(big)
    assert info["mode"] == "readonly"
    assert isinstance(EDITOR_HARD_MAX_BYTES, int)


def test_editor_window_save_roundtrip(qapp, tmp_path: Path):
    path = tmp_path / "note.txt"
    path.write_text("hello\n", encoding="utf-8")
    win = EditorWindow(path)
    assert win.editor.toPlainText() == "hello\n"
    assert not win.editor.isReadOnly()
    win.editor.setPlainText("hello world\n")
    assert win.save() is True
    assert path.read_text(encoding="utf-8") == "hello world\n"
    win.close()


def test_open_code_editor_reuses_window(qapp, tmp_path: Path):
    path = tmp_path / "reuse.py"
    path.write_text("x = 1\n", encoding="utf-8")
    a = open_code_editor(path)
    b = open_code_editor(path)
    assert a is b
    a.close()


def test_conflict_dialog_has_edit_in_labdesk(monkeypatch, qapp, tmp_path):
    import labdesk_core
    from labdesk_ui.windows.conflict_dialog import ConflictDialog

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("conflicted\n", encoding="utf-8")
    monkeypatch.setattr(labdesk_core, "repo_list_conflicts", lambda _p: ["a.txt"])
    monkeypatch.setattr(labdesk_core, "repo_git_state", lambda _p: "Merge")
    monkeypatch.setattr(
        labdesk_core,
        "repo_conflict_side_text",
        lambda _p, _path, side: f"{side}\n",
    )
    dlg = ConflictDialog(str(repo), mode="merge")
    assert hasattr(dlg, "btn_edit")
    assert dlg.btn_edit.isEnabled()
    dlg.close()
