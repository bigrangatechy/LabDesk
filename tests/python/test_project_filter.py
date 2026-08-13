"""Project list filter and pipeline status glyph helpers."""

from __future__ import annotations

from labdesk_ui.plugins.projects_view import (
    filter_projects,
    pipeline_status_color,
    pipeline_status_glyph,
)


def test_filter_empty_query_returns_all():
    projects = [
        {"name": "a", "name_with_namespace": "g/a", "path_with_namespace": "g/a"},
        {"name": "b", "name_with_namespace": "g/b", "path_with_namespace": "g/b"},
    ]
    assert filter_projects(projects, "") == projects
    assert filter_projects(projects, "  ") == projects


def test_filter_matches_path_case_insensitive():
    projects = [
        {
            "name": "labdesk",
            "name_with_namespace": "Ranga / labdesk",
            "path_with_namespace": "Ranga/labdesk",
        },
        {
            "name": "other",
            "name_with_namespace": "Ranga / other",
            "path_with_namespace": "Ranga/other",
        },
    ]
    out = filter_projects(projects, "LABDESK")
    assert len(out) == 1
    assert out[0]["name"] == "labdesk"


def test_filter_matches_namespace():
    projects = [
        {"name": "a", "name_with_namespace": "Team/Alpha", "path_with_namespace": "team/a"},
        {"name": "b", "name_with_namespace": "Other/Beta", "path_with_namespace": "other/b"},
    ]
    out = filter_projects(projects, "team")
    assert len(out) == 1
    assert out[0]["name"] == "a"


def test_pipeline_status_glyph_known_statuses():
    assert pipeline_status_glyph("success")[0] == "✓"
    assert pipeline_status_glyph("failed")[0] == "✗"
    assert pipeline_status_glyph("running")[0] == "●"
    assert pipeline_status_glyph(None)[0] == "·"
    assert "success" in pipeline_status_glyph("success")[1]


def test_pipeline_status_color_success_differs_from_failed():
    ok = pipeline_status_color("success", dark=True)
    bad = pipeline_status_color("failed", dark=True)
    assert ok is not None and bad is not None
    assert ok.name() != bad.name()
