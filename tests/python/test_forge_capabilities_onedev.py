"""Per-forge feature matrix and unsupported-path expectations (OneDev)."""

from __future__ import annotations

import pytest

from labdesk_ui.windows.mr_dialog import MRDialog
from labdesk_ui.windows.mr_detail_dialog import MRDetailDialog

labdesk_core = pytest.importorskip("labdesk_core")
if not hasattr(labdesk_core, "forge_feature_matrix"):
    pytest.skip("labdesk_core missing forge_feature_matrix", allow_module_level=True)


def test_onedev_matrix_no_draft_retarget_or_play_job():
    matrix = labdesk_core.forge_feature_matrix()
    od = matrix["onedev"]
    assert od["display_name"] == "OneDev"
    assert od["supports_play_job"] is False
    assert od["supports_mr_detail"] is True
    assert od["supports_mr_update"] is True
    assert od["supports_mr_retarget"] is False
    assert od["supports_mr_merge"] is True
    assert od["supports_mr_notes"] is True
    assert od["supports_draft_mr"] is False


def test_onedev_mr_dialog_hides_draft_when_forge_info_says_so(qapp, monkeypatch):
    monkeypatch.setattr(
        "labdesk_ui.windows.mr_dialog.forge_info",
        lambda: {
            "forge": "onedev",
            "display_name": "OneDev",
            "supports_draft_mr": False,
            "pull_request_label": "Pull request",
        },
    )
    dlg = MRDialog(source_branch="a", target_branch="main", kind_label="Pull request")
    assert dlg.draft.isVisible() is False
    dlg.close()


def test_onedev_detail_disables_retarget_field(qapp, monkeypatch):
    monkeypatch.setattr(
        "labdesk_ui.windows.mr_detail_dialog.forge_info",
        lambda: {
            "forge": "onedev",
            "display_name": "OneDev",
            "supports_mr_update": True,
            "supports_mr_retarget": False,
            "supports_mr_merge": True,
            "supports_mr_notes": True,
            "pull_request_label": "Pull request",
            "open_in_label": "Open in OneDev",
        },
    )

    def boom(*_a, **_k):
        raise RuntimeError("no network in unit test")

    monkeypatch.setattr(
        "labdesk_ui.windows.mr_detail_dialog.MRDetailDialog._load",
        lambda self: None,
    )
    dlg = MRDetailDialog(project_id=1, mr_iid=2, kind_label="Pull request")
    assert dlg.target_edit.isReadOnly() is True
    assert dlg.btn_merge.isEnabled() is True
    dlg.close()
