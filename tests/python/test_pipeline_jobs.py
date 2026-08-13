"""Pipeline job playability helpers."""

from __future__ import annotations

from labdesk_ui.windows.repo_window import _job_is_playable


def test_playable_when_status_manual():
    assert _job_is_playable({"status": "manual", "when": "on_success"}) is True


def test_playable_when_when_manual():
    assert _job_is_playable({"status": "created", "when": "manual"}) is True


def test_not_playable_success_job():
    assert _job_is_playable({"status": "success", "when": "on_success"}) is False


def test_not_playable_running_job():
    assert _job_is_playable({"status": "running", "when": "on_success"}) is False
