"""Per-forge feature matrix and unsupported-path expectations (Gitea)."""

from __future__ import annotations

import pytest

labdesk_core = pytest.importorskip("labdesk_core")
if not hasattr(labdesk_core, "forge_feature_matrix"):
    pytest.skip("labdesk_core missing forge_feature_matrix", allow_module_level=True)


def test_gitea_matrix_mr_yes_play_job_no():
    matrix = labdesk_core.forge_feature_matrix()
    gt = matrix["gitea"]
    assert gt["display_name"] == "Gitea"
    assert gt["supports_play_job"] is False
    assert gt["supports_mr_detail"] is True
    assert gt["supports_mr_update"] is True
    assert gt["supports_mr_retarget"] is True
    assert gt["supports_mr_merge"] is True
    assert gt["supports_mr_notes"] is True
    assert gt["supports_draft_mr"] is True
