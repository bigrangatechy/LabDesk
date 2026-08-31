"""Per-forge feature matrix and unsupported-path expectations (Forgejo)."""

from __future__ import annotations

import pytest

labdesk_core = pytest.importorskip("labdesk_core")
if not hasattr(labdesk_core, "forge_feature_matrix"):
    pytest.skip("labdesk_core missing forge_feature_matrix", allow_module_level=True)


def test_forgejo_matrix_matches_gitea_shape():
    matrix = labdesk_core.forge_feature_matrix()
    fj = matrix["forgejo"]
    assert fj["display_name"] == "Forgejo"
    assert fj["supports_play_job"] is False
    assert fj["supports_mr_detail"] is True
    assert fj["supports_mr_update"] is True
    assert fj["supports_mr_retarget"] is True
    assert fj["supports_mr_merge"] is True
    assert fj["supports_mr_notes"] is True
    assert fj["supports_mr_note_create"] is True
    assert fj["supports_draft_mr"] is True


def test_forgejo_and_gitea_capability_parity():
    matrix = labdesk_core.forge_feature_matrix()
    keys = [
        "supports_play_job",
        "supports_mr_detail",
        "supports_mr_update",
        "supports_mr_retarget",
        "supports_mr_merge",
        "supports_mr_notes",
        "supports_mr_note_create",
        "supports_draft_mr",
        "supports_runners",
        "supports_runner_pause",
        "supports_runner_delete",
    ]
    for key in keys:
        assert matrix["forgejo"][key] == matrix["gitea"][key], key
