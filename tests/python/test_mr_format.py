"""Merge request / compare UI helpers."""

from __future__ import annotations

from labdesk_ui.windows.mr_dialog import MRDialog
from labdesk_ui.windows.repo_window import _format_mr_row, _ref_to_branch_name


def test_format_mr_row():
    row = _format_mr_row(
        {
            "iid": 12,
            "title": "Ship Flatpak",
            "state": "opened",
            "source_branch": "feature/fp",
            "target_branch": "main",
        }
    )
    assert row.startswith("!12 ")
    assert "Ship Flatpak" in row
    assert "[opened]" in row
    assert "feature/fp → main" in row


def test_ref_to_branch_name_keeps_nested_paths():
    assert _ref_to_branch_name("origin/feature/fp") == "feature/fp"
    assert _ref_to_branch_name("feature/fp") == "feature/fp"
    assert _ref_to_branch_name("main") == "main"


def test_mr_dialog_prefills_and_draft_visibility(qapp, monkeypatch):
    monkeypatch.setattr(
        "labdesk_ui.windows.mr_dialog.forge_info",
        lambda: {
            "display_name": "GitLab",
            "supports_draft_mr": True,
            "pr_singular": "Merge request",
        },
    )
    dlg = MRDialog(
        source_branch="feature/x",
        target_branch="main",
        title_prefill="feature/x into main",
        kind_label="Merge request",
    )
    assert dlg.source.text() == "feature/x"
    assert dlg.target.text() == "main"
    assert dlg.title.text() == "feature/x into main"
    assert dlg.draft.isHidden() is False
    src, tgt, title, _desc, draft = dlg.values()
    assert (src, tgt, title, draft) == (
        "feature/x",
        "main",
        "feature/x into main",
        False,
    )
    dlg.close()
