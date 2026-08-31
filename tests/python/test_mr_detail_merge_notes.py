"""MR/PR detail merge + notes UI (Slice F)."""

from __future__ import annotations

from labdesk_ui.windows.mr_detail_dialog import MRDetailDialog, _format_notes


def test_format_notes_empty_and_rows():
    assert _format_notes([]) == "(no notes)"
    text = _format_notes(
        [{"author": "a", "created_at": "t1", "body": "hello"}, {"author": "b", "body": "x"}]
    )
    assert "— a  t1" in text
    assert "hello" in text
    assert "— b" in text


def test_mr_detail_notes_pagination_and_merge_gate(monkeypatch, qapp):
    import labdesk_core

    pages = {
        1: [{"author": f"u{i}", "body": f"n{i}"} for i in range(50)],
        2: [{"author": "u50", "body": "n50"}],
    }

    monkeypatch.setattr(
        "labdesk_ui.windows.mr_detail_dialog.forge_info",
        lambda: {
            "display_name": "GitLab",
            "supports_mr_detail": True,
            "supports_mr_update": True,
            "supports_mr_retarget": True,
            "supports_mr_merge": True,
            "supports_mr_notes": True,
            "supports_draft_mr": True,
        },
    )
    monkeypatch.setattr(
        labdesk_core,
        "get_merge_request",
        lambda *_a, **_k: {
            "title": "T",
            "source_branch": "feat",
            "target_branch": "main",
            "description": "",
            "state": "opened",
            "author": "me",
            "draft": False,
            "web_url": "https://example/mr/1",
        },
    )
    monkeypatch.setattr(
        labdesk_core,
        "list_merge_request_notes",
        lambda _pid, _iid, page=1: pages.get(int(page), []),
    )

    dlg = MRDetailDialog(project_id=1, mr_iid=7, kind_label="Merge request")
    assert dlg.btn_merge.isEnabled()
    assert dlg.btn_notes_more.isEnabled()
    assert len(dlg._notes) == 50
    dlg._load_more_notes()
    assert len(dlg._notes) == 51
    assert dlg.btn_notes_more.isEnabled() is False
    dlg.close()


def test_mr_detail_disables_merge_when_already_merged(monkeypatch, qapp):
    import labdesk_core

    monkeypatch.setattr(
        "labdesk_ui.windows.mr_detail_dialog.forge_info",
        lambda: {
            "display_name": "GitLab",
            "supports_mr_merge": True,
            "supports_mr_notes": True,
            "supports_mr_update": True,
            "supports_mr_retarget": True,
        },
    )
    monkeypatch.setattr(
        labdesk_core,
        "get_merge_request",
        lambda *_a, **_k: {
            "title": "T",
            "source_branch": "feat",
            "target_branch": "main",
            "state": "merged",
            "author": "me",
            "draft": False,
        },
    )
    monkeypatch.setattr(labdesk_core, "list_merge_request_notes", lambda *_a, **_k: [])

    dlg = MRDetailDialog(project_id=1, mr_iid=3, kind_label="Merge request")
    assert dlg.btn_merge.isEnabled() is False
    dlg.close()
