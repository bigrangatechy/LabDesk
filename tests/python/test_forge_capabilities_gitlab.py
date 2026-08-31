"""Per-forge feature matrix and unsupported-path expectations (GitLab)."""

from __future__ import annotations

import pytest

labdesk_core = pytest.importorskip("labdesk_core")
if not hasattr(labdesk_core, "forge_feature_matrix"):
    pytest.skip("labdesk_core missing forge_feature_matrix", allow_module_level=True)


def test_gitlab_matrix_full_mr_and_play_job():
    matrix = labdesk_core.forge_feature_matrix()
    gl = matrix["gitlab"]
    assert gl["display_name"] == "GitLab"
    assert gl["supports_play_job"] is True
    assert gl["supports_mr_detail"] is True
    assert gl["supports_mr_update"] is True
    assert gl["supports_mr_retarget"] is True
    assert gl["supports_mr_merge"] is True
    assert gl["supports_mr_notes"] is True
    assert gl["supports_draft_mr"] is True
    assert gl["supports_runners"] is True
    assert gl["supports_runner_pause"] is True
    assert gl["supports_runner_delete"] is True
