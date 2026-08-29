"""Forge-aware UI labels (MR/PR wording, Open in …, host combos)."""

from __future__ import annotations

from labdesk_ui.utils.forge_labels import (
    ci_tab_label,
    forge_info,
    forge_name,
    instance_label,
    open_in_label,
    pr_label,
    pr_label_plural,
)
from labdesk_ui.windows.mr_dialog import MRDialog


def test_defaults_are_gitlab_shaped():
    info = {
        "forge": "gitlab",
        "display_name": "GitLab",
        "pull_request_label": "Merge request",
        "pull_request_label_plural": "Merge requests",
        "ci_tab_label": "Pipelines",
        "open_in_label": "Open in GitLab",
    }
    assert pr_label(info) == "Merge request"
    assert pr_label_plural(info) == "Merge requests"
    assert open_in_label(info) == "Open in GitLab"
    assert ci_tab_label(info) == "Pipelines"
    assert forge_name(info) == "GitLab"


def test_gitea_pull_request_labels():
    info = {
        "forge": "gitea",
        "display_name": "Gitea",
        "pull_request_label": "Pull request",
        "pull_request_label_plural": "Pull requests",
        "ci_tab_label": "Actions",
        "open_in_label": "Open in Gitea",
        "supports_play_job": False,
    }
    assert pr_label(info) == "Pull request"
    assert open_in_label(info).endswith("Gitea")
    assert ci_tab_label(info) == "Actions"


def test_instance_label_uses_forge_fallback():
    assert instance_label(
        {"forge": "onedev", "base_url": "http://192.168.1.10:6610"}
    ) == "OneDev — http://192.168.1.10:6610"
    assert instance_label(
        {"name": "LAN", "forge": "gitea", "base_url": "https://git.lan"}
    ) == "LAN — https://git.lan"


def test_mr_dialog_title_follows_kind(qapp):
    dlg = MRDialog(
        source_branch="feature",
        target_branch="main",
        kind_label="Pull request",
    )
    assert dlg.windowTitle() == "Create pull request"
    dlg.close()


def test_forge_info_callable():
    info = forge_info()
    assert "display_name" in info
    assert "pull_request_label" in info
