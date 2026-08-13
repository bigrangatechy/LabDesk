"""Pipeline job playability helpers."""

from __future__ import annotations

from labdesk_ui.windows.repo_window import (
    _format_job_row,
    _job_is_playable,
    _sort_pipeline_jobs,
)


def test_playable_when_status_manual():
    assert _job_is_playable({"status": "manual", "when": "on_success"}) is True


def test_playable_when_when_manual():
    assert _job_is_playable({"status": "created", "when": "manual"}) is True


def test_not_playable_success_job():
    assert _job_is_playable({"status": "success", "when": "on_success"}) is False


def test_not_playable_running_job():
    assert _job_is_playable({"status": "running", "when": "on_success"}) is False


def test_sort_playable_first_then_stage_name():
    jobs = [
        {"name": "test", "stage": "test", "status": "success", "when": "on_success"},
        {"name": "publish", "stage": "deploy", "status": "manual", "when": "manual"},
        {"name": "build", "stage": "build", "status": "success", "when": "on_success"},
        {"name": "approve", "stage": "deploy", "status": "created", "when": "manual"},
    ]
    ordered = _sort_pipeline_jobs(jobs)
    assert [j["name"] for j in ordered] == ["approve", "publish", "build", "test"]


def test_format_job_row_includes_stage_and_play_marker():
    row = _format_job_row(
        {"name": "publish", "stage": "deploy", "status": "manual", "when": "manual"}
    )
    assert row.startswith("▶ ")
    assert "deploy · publish" in row
    assert "[manual]" in row
