"""Help → User Guide path resolution smoke tests."""

from __future__ import annotations

from pathlib import Path

from labdesk_ui.windows.help_dialog import load_user_guide_markdown, resolve_user_guide_path


def test_resolve_user_guide_finds_bundled_or_docs_copy():
    path = resolve_user_guide_path()
    assert path is not None
    assert path.is_file()
    assert path.name == "user-guide.md"
    text = path.read_text(encoding="utf-8")
    assert "LabDesk" in text
    assert len(text) > 100


def test_load_user_guide_markdown_nonempty():
    md = load_user_guide_markdown()
    assert "User Guide unavailable" not in md or Path("Docs/user-guide.md").is_file()
    assert "LabDesk" in md
